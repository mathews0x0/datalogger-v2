/**
 * @file bmi323.c
 * @brief BMI323 6-axis IMU driver — ESP-IDF native C implementation
 *
 * Ported from firmware_s3/firmware/drivers/bmi323.py.
 * Key fix: correct gyro sensitivity (16.4 LSB/dps), eliminating the
 * ~16x scale mismatch present in the S3 field logs (May 2026).
 *
 * I2C Protocol: BMI323 uses a 16-bit word-based format.
 *   Read:  send [reg], receive [dummy][dummy][lsb][msb]×N
 *   Write: send [reg][lsb][msb]
 */

#include "bmi323.h"
#include "bsp.h"
#include <string.h>
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "bmi323";

/* ──────────────────────────────────────────────────────────────────────────
 * Module state
 * ────────────────────────────────────────────────────────────────────────*/
static i2c_master_bus_handle_t  s_i2c_bus     = NULL;
static i2c_master_dev_handle_t  s_i2c_dev     = NULL;
static bool                     s_initialized = false;
static uint64_t                 s_fifo_ticks  = 0;   /* accumulated sensor ticks */
static bool                     s_fifo_seeded = false;

/* Last raw sample — used to skip duplicate FIFO frames */
static bmi323_raw_t s_last_raw;

/* ──────────────────────────────────────────────────────────────────────────
 * I2C helpers (word-based BMI323 protocol)
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Read N signed 16-bit words from a BMI323 register.
 * Protocol: write [reg_addr], read [dummy][dummy][lsb0][msb0]...[lsbN][msbN]
 */
static esp_err_t _read_words(uint8_t reg, int16_t *out, int count)
{
    uint8_t buf[2 + count * 2];
    esp_err_t ret = i2c_master_transmit_receive(s_i2c_dev, &reg, 1, buf, sizeof(buf), 50);
    if (ret != ESP_OK) return ret;
    for (int i = 0; i < count; i++) {
        uint16_t raw = (uint16_t)buf[2 + 2*i] | ((uint16_t)buf[3 + 2*i] << 8);
        out[i] = (int16_t)raw;
    }
    return ESP_OK;
}

/**
 * @brief Read N unsigned 16-bit words (for status/fill-level registers).
 */
static esp_err_t _read_u16_words(uint8_t reg, uint16_t *out, int count)
{
    uint8_t buf[2 + count * 2];
    esp_err_t ret = i2c_master_transmit_receive(s_i2c_dev, &reg, 1, buf, sizeof(buf), 50);
    if (ret != ESP_OK) return ret;
    for (int i = 0; i < count; i++) {
        out[i] = (uint16_t)buf[2 + 2*i] | ((uint16_t)buf[3 + 2*i] << 8);
    }
    return ESP_OK;
}

/**
 * @brief Write a 16-bit word to a BMI323 register.
 * Protocol: [reg_addr][lsb][msb]
 */
static esp_err_t _write_word(uint8_t reg, uint16_t val)
{
    uint8_t buf[3] = { reg, (uint8_t)(val & 0xFF), (uint8_t)((val >> 8) & 0xFF) };
    return i2c_master_transmit(s_i2c_dev, buf, sizeof(buf), 50);
}

/* ──────────────────────────────────────────────────────────────────────────
 * Sensor initialization
 * ────────────────────────────────────────────────────────────────────────*/
static esp_err_t _init_sensor(void)
{
    int16_t word;
    uint16_t u16;

    /* 1. Soft reset — may fail on first attempt (sensor waking up) */
    _write_word(BMI323_REG_CMD, BMI323_CMD_SOFT_RESET);
    vTaskDelay(pdMS_TO_TICKS(100));

    /* 2. Dummy read to wake the serial interface */
    _read_words(BMI323_REG_CHIP_ID, &word, 1);

    /* 3. Verify chip ID */
    esp_err_t ret = _read_words(BMI323_REG_CHIP_ID, &word, 1);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Chip ID read failed: %s", esp_err_to_name(ret));
        return ESP_FAIL;
    }
    if ((word & 0xFF) != BMI323_CHIP_ID) {
        ESP_LOGE(TAG, "Unexpected chip ID: 0x%02X (expected 0x%02X)", word & 0xFF, BMI323_CHIP_ID);
        return ESP_ERR_NOT_FOUND;
    }
    ESP_LOGI(TAG, "BMI323 chip ID: 0x%02X OK", word & 0xFF);

    /* 4. Check initial error register */
    _read_u16_words(BMI323_REG_ERR, &u16, 1);
    if (u16 != 0) {
        ESP_LOGW(TAG, "IMU pre-config error register: 0x%04X", u16);
    }

    /* 5. FIFO config — enable accel + gyro + sensor time headers */
    ret = _write_word(BMI323_REG_FIFO_CONF,
                      BMI323_FIFO_TIME_EN | BMI323_FIFO_ACC_EN | BMI323_FIFO_GYR_EN);
    if (ret != ESP_OK) return ret;

    /* 6. Accel: HP mode, 100Hz, ±4g, ODR/4 BW, 4x avg (0x7298) */
    ret = _write_word(BMI323_REG_ACC_CONF, BMI323_ACC_CONF_100HZ_4G);
    if (ret != ESP_OK) return ret;

    /* 7. Gyro: HP mode, 100Hz, ±2000dps, ODR/4 BW, 2x avg (0x71C8) */
    ret = _write_word(BMI323_REG_GYR_CONF, BMI323_GYR_CONF_100HZ_2000);
    if (ret != ESP_OK) return ret;

    vTaskDelay(pdMS_TO_TICKS(100));

    /* 8. Final error check */
    _read_u16_words(BMI323_REG_ERR, &u16, 1);
    if (u16 != 0) {
        ESP_LOGE(TAG, "IMU post-config error register: 0x%04X", u16);
        if (u16 & 0x0001) {
            ESP_LOGE(TAG, "IMU fatal error — may need power cycle");
        }
        return ESP_FAIL;
    }

    /* 9. Flush FIFO */
    bmi323_flush_fifo();

    ESP_LOGI(TAG, "BMI323 initialized: 100Hz Accel ±4g | 100Hz Gyro ±2000dps");
    return ESP_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t bmi323_init(void)
{
    if (s_initialized) return ESP_OK;

    /* Set up I2C master bus on I2C0 (dynamic pins from bsp.h @ 400kHz) */
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port          = I2C_NUM_0,
        .sda_io_num        = BSP_PIN_I2C0_SDA,
        .scl_io_num        = BSP_PIN_I2C0_SCL,
        .clk_source        = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    esp_err_t ret = i2c_new_master_bus(&bus_cfg, &s_i2c_bus);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "I2C bus init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    /* Add BMI323 device at 0x69 */
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address  = BMI323_I2C_ADDR,
        .scl_speed_hz    = 400000,
    };
    ret = i2c_master_bus_add_device(s_i2c_bus, &dev_cfg, &s_i2c_dev);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "I2C device add failed: %s", esp_err_to_name(ret));
        i2c_del_master_bus(s_i2c_bus);
        return ret;
    }

    /* Initialize the sensor */
    ret = _init_sensor();
    if (ret != ESP_OK) {
        i2c_master_bus_rm_device(s_i2c_dev);
        i2c_del_master_bus(s_i2c_bus);
        return ret;
    }

    memset(&s_last_raw, 0, sizeof(s_last_raw));
    s_initialized = true;
    return ESP_OK;
}

bool bmi323_is_ok(void)
{
    return s_initialized;
}

esp_err_t bmi323_soft_reset(void)
{
    if (!s_initialized) return ESP_ERR_INVALID_STATE;
    esp_err_t ret = _write_word(BMI323_REG_CMD, BMI323_CMD_SOFT_RESET);
    vTaskDelay(pdMS_TO_TICKS(100));
    return ret;
}

esp_err_t bmi323_flush_fifo(void)
{
    s_fifo_seeded = false;
    s_fifo_ticks  = 0;
    return _write_word(BMI323_REG_FIFO_CTRL, 0x0001);
}

esp_err_t bmi323_read_raw(bmi323_raw_t *raw)
{
    if (!s_initialized || !raw) return ESP_ERR_INVALID_STATE;
    /* Single burst: REG_ACC_DATA_X reads ax,ay,az,gx,gy,gz (6 words, 14 bytes + 2 dummy) */
    int16_t buf[6];
    esp_err_t ret = _read_words(BMI323_REG_ACC_DATA_X, buf, 6);
    if (ret != ESP_OK) return ret;
    raw->ax = buf[0]; raw->ay = buf[1]; raw->az = buf[2];
    raw->gx = buf[3]; raw->gy = buf[4]; raw->gz = buf[5];
    return ESP_OK;
}

esp_err_t bmi323_read_if_ready(bmi323_raw_t *raw)
{
    if (!s_initialized || !raw) return ESP_ERR_INVALID_STATE;
    uint16_t status;
    esp_err_t ret = _read_u16_words(BMI323_REG_STATUS, &status, 1);
    if (ret != ESP_OK) return ret;
    if ((status & BMI323_STATUS_DRDY_MASK) != BMI323_STATUS_DRDY_MASK) {
        return ESP_ERR_NOT_FINISHED; /* Data not ready yet */
    }
    return bmi323_read_raw(raw);
}

esp_err_t bmi323_read_accel_gyro(float *ax, float *ay, float *az,
                                  float *gx, float *gy, float *gz)
{
    bmi323_raw_t raw;
    esp_err_t ret = bmi323_read_raw(&raw);
    if (ret != ESP_OK) return ret;
    bmi323_data_t data;
    bmi323_raw_to_si(&raw, &data);
    if (ax) *ax = data.ax;
    if (ay) *ay = data.ay;
    if (az) *az = data.az;
    if (gx) *gx = data.gx;
    if (gy) *gy = data.gy;
    if (gz) *gz = data.gz;
    return ESP_OK;
}

void bmi323_raw_to_si(const bmi323_raw_t *raw, bmi323_data_t *data)
{
    data->ax = (float)raw->ax / BMI323_ACC_SENSITIVITY;
    data->ay = (float)raw->ay / BMI323_ACC_SENSITIVITY;
    data->az = (float)raw->az / BMI323_ACC_SENSITIVITY;
    data->gx = (float)raw->gx / BMI323_GYR_SENSITIVITY;
    data->gy = (float)raw->gy / BMI323_GYR_SENSITIVITY;
    data->gz = (float)raw->gz / BMI323_GYR_SENSITIVITY;
}

esp_err_t bmi323_read_fifo(bmi323_fifo_frame_t *frames, int max_frames, int *count)
{
    if (!s_initialized || !frames || !count) return ESP_ERR_INVALID_STATE;
    *count = 0;

    /* How many frames are in the FIFO? */
    uint16_t fill_words;
    esp_err_t ret = _read_u16_words(BMI323_REG_FIFO_FILL_LVL, &fill_words, 1);
    if (ret != ESP_OK) return ret;
    fill_words &= 0x07FF;

    int frame_count = fill_words / BMI323_FIFO_FRAME_WORDS;
    if (frame_count <= 0) return ESP_OK;
    if (frame_count > max_frames) frame_count = max_frames;

    /* Burst read all frames: 2 dummy + (frame_count × 7 words × 2 bytes) */
    int byte_count = 2 + frame_count * BMI323_FIFO_FRAME_WORDS * 2;
    uint8_t *buf = (uint8_t *)alloca(byte_count);
    uint8_t reg = BMI323_REG_FIFO_DATA;
    ret = i2c_master_transmit_receive(s_i2c_dev, &reg, 1, buf, byte_count, 100);
    if (ret != ESP_OK) return ret;

    int pos = 2; /* skip dummy bytes */
    int out_idx = 0;
    for (int f = 0; f < frame_count; f++) {
        uint16_t words[BMI323_FIFO_FRAME_WORDS];
        for (int w = 0; w < BMI323_FIFO_FRAME_WORDS; w++) {
            words[w] = (uint16_t)buf[pos] | ((uint16_t)buf[pos+1] << 8);
            pos += 2;
        }
        /* Skip internal settling / dummy frames */
        if (words[0] == 0x7F01 || words[3] == 0x7F02) continue;

        /* Accumulate sensor timestamp (wrapping 16-bit counter) */
        uint16_t tick16 = words[6];
        if (!s_fifo_seeded) {
            s_fifo_ticks  = tick16;
            s_fifo_seeded = true;
        } else {
            uint16_t prev16 = (uint16_t)(s_fifo_ticks & 0xFFFF);
            uint16_t delta  = (uint16_t)(tick16 - prev16);
            s_fifo_ticks   += delta;
        }

        bmi323_raw_t raw = {
            .ax = (int16_t)words[0], .ay = (int16_t)words[1], .az = (int16_t)words[2],
            .gx = (int16_t)words[3], .gy = (int16_t)words[4], .gz = (int16_t)words[5],
        };
        /* Skip duplicate samples */
        if (memcmp(&raw, &s_last_raw, sizeof(raw)) == 0) continue;
        s_last_raw = raw;

        frames[out_idx].raw         = raw;
        frames[out_idx].sensor_ticks = s_fifo_ticks;
        frames[out_idx].sensor_us   = (uint32_t)(s_fifo_ticks * BMI323_SENSOR_TIME_LSB_US);
        out_idx++;
    }

    *count = out_idx;
    return ESP_OK;
}
