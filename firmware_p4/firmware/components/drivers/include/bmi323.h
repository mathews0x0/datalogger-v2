/**
 * @file bmi323.h
 * @brief BMI323 6-axis IMU driver — Waveshare ESP32-P4 / RaceSense
 *
 * I2C address: 0x69 (SDO pulled high on Waveshare header)
 * Bus:         I2C0, GPIO 7 (SDA), GPIO 8 (SCL), 400kHz
 *
 * BMI323 uses a 16-bit word-based I2C protocol:
 *   Read:  [reg_addr] → [dummy_byte][dummy_byte][lsb][msb] × N
 *   Write: [reg_addr][lsb][msb]
 *
 * Configuration (matches S3 firmware exactly):
 *   Accel: 100Hz, ±4g, High-Performance, ODR/4 BW, 4x avg  (REG_ACC_CONF = 0x7298)
 *   Gyro:  100Hz, ±2000dps, HP, ODR/4 BW, 2x avg           (REG_GYR_CONF = 0x71C8)
 *   Sensitivity: ACC = 8192 LSB/g, GYR = 16.4 LSB/dps
 *
 * Note: The S3 firmware had a gyro scaling mismatch (~16x). This driver
 * applies the correct sensitivity divisor (16.4 LSB/dps) so gyro output
 * is properly scaled in deg/s without any post-processing correction.
 */

#ifndef BMI323_H
#define BMI323_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Register Map
 * ────────────────────────────────────────────────────────────────────────*/
#define BMI323_REG_CHIP_ID        0x00
#define BMI323_REG_ERR            0x01
#define BMI323_REG_STATUS         0x02
#define BMI323_REG_ACC_DATA_X     0x03
#define BMI323_REG_GYR_DATA_X     0x06
#define BMI323_REG_TEMP_DATA      0x09
#define BMI323_REG_FIFO_FILL_LVL 0x15
#define BMI323_REG_FIFO_DATA      0x16
#define BMI323_REG_ACC_CONF       0x20
#define BMI323_REG_GYR_CONF       0x21
#define BMI323_REG_FIFO_CONF      0x36
#define BMI323_REG_FIFO_CTRL      0x37
#define BMI323_REG_CMD            0x7E

/* ──────────────────────────────────────────────────────────────────────────
 * Configuration Values
 * ────────────────────────────────────────────────────────────────────────*/
#define BMI323_CHIP_ID            0x43

/* ACC_CONF: mode=HP(7), avg=4x(2), bw=ODR/4(1), range=±4g(1), odr=100Hz(8) */
#define BMI323_ACC_CONF_100HZ_4G    0x7298U
/* GYR_CONF: mode=HP(7), avg=2x(1), bw=ODR/4(1), range=±2000dps(4), odr=100Hz(8) */
#define BMI323_GYR_CONF_100HZ_2000  0x71C8U

#define BMI323_CMD_SOFT_RESET     0xDEAFU
#define BMI323_FIFO_ACC_EN        0x0200U
#define BMI323_FIFO_GYR_EN        0x0400U
#define BMI323_FIFO_TIME_EN       0x0100U
#define BMI323_FIFO_FRAME_WORDS   7
#define BMI323_STATUS_DRDY_MASK   0x00C0U

/* Sensitivity constants (correct values — fixes S3 gyro scaling bug) */
#define BMI323_ACC_SENSITIVITY    8192.0f  /**< LSB/g  for ±4g range    */
#define BMI323_GYR_SENSITIVITY    16.4f    /**< LSB/dps for ±2000dps    */
#define BMI323_SENSOR_TIME_LSB_US 39.0625f /**< µs per sensor tick      */

/* I2C address */
#define BMI323_I2C_ADDR           0x69

/* ──────────────────────────────────────────────────────────────────────────
 * Data Types
 * ────────────────────────────────────────────────────────────────────────*/

/** Raw 6-axis sample (LSB units, before sensitivity division) */
typedef struct {
    int16_t ax, ay, az;   /**< Accel raw LSB */
    int16_t gx, gy, gz;   /**< Gyro raw LSB  */
} bmi323_raw_t;

/** Scaled 6-axis sample (physical units) */
typedef struct {
    float ax, ay, az;     /**< Acceleration  (g)     */
    float gx, gy, gz;     /**< Angular rate   (deg/s) */
} bmi323_data_t;

/** FIFO frame with hardware sensor timestamp */
typedef struct {
    bmi323_raw_t  raw;
    uint64_t      sensor_ticks;   /**< Accumulated 16-bit tick counter */
    uint32_t      sensor_us;      /**< Sensor timestamp in microseconds */
} bmi323_fifo_frame_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Public API
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Initialize BMI323 on I2C0 (GPIO 7/8 @ 400kHz).
 *
 * Performs: soft reset → dummy read → chip ID verify → error check →
 * FIFO config → ACC_CONF → GYR_CONF → FIFO flush.
 *
 * @return ESP_OK on success, ESP_ERR_NOT_FOUND if chip ID mismatch,
 *         ESP_FAIL on I2C communication error.
 */
esp_err_t bmi323_init(void);

/**
 * @brief Read 6 raw values (ax, ay, az, gx, gy, gz) as a single I2C burst.
 *
 * Fast path — reads REG_ACC_DATA_X through GYR_DATA_Z in one transaction.
 * Returns raw LSB integers (divide by sensitivity for physical units).
 *
 * @param[out] raw  Destination struct.
 * @return ESP_OK on success.
 */
esp_err_t bmi323_read_raw(bmi323_raw_t *raw);

/**
 * @brief Read accelerometer and gyroscope, returning scaled physical values.
 *
 * @param[out] ax,ay,az  Acceleration in g.
 * @param[out] gx,gy,gz  Angular rate in deg/s.
 * @return ESP_OK on success.
 */
esp_err_t bmi323_read_accel_gyro(float *ax, float *ay, float *az,
                                  float *gx, float *gy, float *gz);

/**
 * @brief Read data only when sensor reports both accel+gyro data-ready.
 *
 * Checks STATUS register DRDY bits. Returns ESP_ERR_NOT_FINISHED if
 * data is not ready yet (caller should retry on next timer tick).
 *
 * @param[out] raw  Filled on ESP_OK only.
 * @return ESP_OK if fresh data read, ESP_ERR_NOT_FINISHED if not ready.
 */
esp_err_t bmi323_read_if_ready(bmi323_raw_t *raw);

/**
 * @brief Read available frames from the hardware FIFO.
 *
 * @param[out] frames     Caller-allocated frame array.
 * @param[in]  max_frames Maximum frames to read.
 * @param[out] count      Number of frames actually read.
 * @return ESP_OK on success.
 */
esp_err_t bmi323_read_fifo(bmi323_fifo_frame_t *frames, int max_frames, int *count);

/**
 * @brief Flush the hardware FIFO.
 * @return ESP_OK on success.
 */
esp_err_t bmi323_flush_fifo(void);

/**
 * @brief Perform a soft reset (CMD register 0x7E = 0xDEAF).
 * @return ESP_OK on success.
 */
esp_err_t bmi323_soft_reset(void);

/**
 * @brief Check if the BMI323 was initialized successfully.
 * @return true if init succeeded.
 */
bool bmi323_is_ok(void);

/**
 * @brief Convert raw struct to physical units.
 * @param[in]  raw   Raw LSB sample.
 * @param[out] data  Physical units (g, deg/s).
 */
void bmi323_raw_to_si(const bmi323_raw_t *raw, bmi323_data_t *data);

#ifdef __cplusplus
}
#endif

#endif /* BMI323_H */
