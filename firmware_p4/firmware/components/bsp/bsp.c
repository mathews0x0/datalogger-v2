/**
 * @file bsp.c
 * @brief Board Support Package — Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3
 *
 * Implements hardware initialization for:
 *  - Battery ADC (GPIO 5, dual-EMA filter + charge detection)
 *  - SDMMC 4-bit SD card (GPIO 39-44, 20MHz)
 *  - Display stub (full MIPI-DSI + ST7701 in Phase 8)
 *  - Touch stub    (full GT911 in Phase 8)
 *
 * Battery algorithm ported from S3 firmware's get_battery_state() in main.py.
 * Business logic is identical; implementation uses esp_adc_cal instead of
 * MicroPython's ADC.read_uv().
 */

#include "bsp.h"
#include "bsp_display_target.h"

#include <string.h>
#include <math.h>
#include <sys/stat.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "driver/gpio.h"
#include "driver/sdmmc_host.h"
#include "sdmmc_cmd.h"
#include "esp_vfs_fat.h"

static const char *TAG = "bsp";

/* ──────────────────────────────────────────────────────────────────────────
 * ADC Handles
 * ────────────────────────────────────────────────────────────────────────*/
static adc_oneshot_unit_handle_t s_adc_handle = NULL;
static adc_cali_handle_t         s_adc_cali   = NULL;
static bool                      s_adc_ready  = false;

/* ADC unit for Battery Monitoring (from bsp.h) */
#ifndef BSP_BAT_ADC_UNIT
#define BSP_BAT_ADC_UNIT     ADC_UNIT_1
#endif
#ifndef BSP_BAT_ADC_ATTEN
  #if CONFIG_IDF_TARGET_ESP32S3
    #define BSP_BAT_ADC_ATTEN  ADC_ATTEN_DB_12
  #else
    #define BSP_BAT_ADC_ATTEN  ADC_ATTEN_DB_12
  #endif
#endif
#ifndef BSP_SDMMC_PWR_ACTIVE_LEVEL
#define BSP_SDMMC_PWR_ACTIVE_LEVEL 1
#endif
#define BSP_BAT_ADC_SAMPLES  6               /* Averaged per reading */

/* ──────────────────────────────────────────────────────────────────────────
 * Battery State (module-private)
 * ────────────────────────────────────────────────────────────────────────*/
static bsp_battery_state_t s_bat = {
    .raw_v      = 0.0f,
    .filtered_v = 0.0f,
    .slow_v     = 0.0f,
    .percent    = 0,
    .charging   = false,
};
static int   s_charge_score   = 0;
static float s_prev_raw_v     = 0.0f;

/* ──────────────────────────────────────────────────────────────────────────
 * SD Card State
 * ────────────────────────────────────────────────────────────────────────*/
static bool s_sdcard_mounted = false;
static sdmmc_card_t *s_sdcard = NULL;

/* ──────────────────────────────────────────────────────────────────────────
 * Battery: piecewise voltage → percentage curve
 * Identical to S3 firmware's calculate_battery_percentage()
 * ────────────────────────────────────────────────────────────────────────*/
static int _battery_pct_from_voltage(float v)
{
    if (v >= 4.2f) return 100;
    if (v <= 3.3f) return 0;

    static const float curve_v[] = {4.2f, 4.05f, 3.95f, 3.85f, 3.75f, 3.70f, 3.60f, 3.40f, 3.30f};
    static const int   curve_p[] = {100,  90,     80,    60,    40,    20,    10,    5,     0   };
    static const int   CURVE_LEN = 9;

    for (int i = 0; i < CURVE_LEN - 1; i++) {
        if (v <= curve_v[i] && v >= curve_v[i + 1]) {
            float range_v = curve_v[i] - curve_v[i + 1];
            float range_p = (float)(curve_p[i] - curve_p[i + 1]);
            float v_off   = v - curve_v[i + 1];
            return (int)roundf((float)curve_p[i + 1] + (v_off / range_v) * range_p);
        }
    }
    return 0;
}

/* ──────────────────────────────────────────────────────────────────────────
 * Battery: read averaged raw ADC voltage (volts, post-divider scale)
 * ────────────────────────────────────────────────────────────────────────*/
static float _battery_read_raw_v(void)
{
    if (!s_adc_ready) return 0.0f;

    int64_t total_mv = 0;
    int     count    = 0;

    for (int i = 0; i < BSP_BAT_ADC_SAMPLES; i++) {
        int raw = 0;
        if (adc_oneshot_read(s_adc_handle, BSP_BAT_ADC_CHANNEL, &raw) != ESP_OK) {
            continue;
        }
        int mv = 0;
        if (s_adc_cali) {
            adc_cali_raw_to_voltage(s_adc_cali, raw, &mv);
        } else {
            /* Fallback: linear approximation without calibration */
            mv = (int)((raw / 4095.0f) * 3300.0f);
        }
        total_mv += mv;
        count++;
    }

    if (count <= 0) return 0.0f;
    float avg_v = ((float)(total_mv / count)) / 1000.0f;
    return avg_v * BSP_BATTERY_DIVIDER_SCALE;
}

/* ──────────────────────────────────────────────────────────────────────────
 * Battery: ensure directory exists (helper)
 * ────────────────────────────────────────────────────────────────────────*/
static void _mkdir_p(const char *path)
{
    struct stat st;
    if (stat(path, &st) == 0) return;  /* already exists */
    if (mkdir(path, 0755) != 0) {
        ESP_LOGW(TAG, "mkdir failed: %s", path);
    }
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API IMPLEMENTATION
 * ══════════════════════════════════════════════════════════════════════════*/

/* ──────────────────────────────────────────────────────────────────────────
 * bsp_battery_init
 * ────────────────────────────────────────────────────────────────────────*/
esp_err_t bsp_battery_init(void)
{
    if (s_adc_ready) return ESP_OK;

    /* Configure ADC unit */
    adc_oneshot_unit_init_cfg_t unit_cfg = {
        .unit_id  = BSP_BAT_ADC_UNIT,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&unit_cfg, &s_adc_handle));

    /* Configure ADC channel */
    adc_oneshot_chan_cfg_t chan_cfg = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten    = BSP_BAT_ADC_ATTEN,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc_handle, BSP_BAT_ADC_CHANNEL, &chan_cfg));

    /* Calibration (curve fitting preferred, line fitting as fallback) */
    esp_err_t cali_err = ESP_ERR_NOT_SUPPORTED;
#if defined(ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED) && ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id  = BSP_BAT_ADC_UNIT,
        .chan     = BSP_BAT_ADC_CHANNEL,
        .atten    = BSP_BAT_ADC_ATTEN,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    cali_err = adc_cali_create_scheme_curve_fitting(&cali_cfg, &s_adc_cali);
#elif defined(ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED) && ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
    adc_cali_line_fitting_config_t cali_cfg = {
        .unit_id  = BSP_BAT_ADC_UNIT,
        .atten    = BSP_BAT_ADC_ATTEN,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    cali_err = adc_cali_create_scheme_line_fitting(&cali_cfg, &s_adc_cali);
#endif
    if (cali_err != ESP_OK) {
        ESP_LOGW(TAG, "ADC calibration unavailable (%s), using raw conversion", esp_err_to_name(cali_err));
        s_adc_cali = NULL;
    } else {
        ESP_LOGI(TAG, "Battery ADC calibrated (GPIO %d)", BSP_PIN_BATTERY_ADC);
    }

    /* Mark the ADC ready before the first read; _battery_read_raw_v() is
     * intentionally guarded by this flag.  This also makes the boot value
     * agree with the first UI update instead of briefly reporting 0 V. */
    s_adc_ready = true;

    /* Take initial reading to seed filters */
    float v0 = _battery_read_raw_v();
    if (v0 > 0.0f) {
        s_bat.filtered_v = v0;
        s_bat.slow_v     = v0;
        s_prev_raw_v     = v0;
        s_bat.percent    = _battery_pct_from_voltage(v0);
    }

    ESP_LOGI(TAG, "Battery ADC ready: %.3fV / %d%%", v0, s_bat.percent);
    return ESP_OK;
}

/* ──────────────────────────────────────────────────────────────────────────
 * bsp_battery_update  —  call every 250ms from UI task
 * Ports S3 get_battery_state() dual-EMA + score-based charge detection
 * ────────────────────────────────────────────────────────────────────────*/
esp_err_t bsp_battery_update(bsp_battery_state_t *out)
{
    if (!s_adc_ready) {
        if (out) memset(out, 0, sizeof(*out));
        return ESP_ERR_INVALID_STATE;
    }

    float raw_v   = _battery_read_raw_v();
    s_bat.raw_v   = raw_v;

    if (raw_v > 0.0f) {
        /* Seed filters on first valid reading */
        if (s_bat.filtered_v <= 0.0f) {
            s_bat.filtered_v = raw_v;
            s_bat.slow_v     = raw_v;
            s_prev_raw_v     = raw_v;
            s_charge_score   = 0;
        } else {
            /* Dual EMA filter (fast rises, slow falls to suppress noise) */
            float alpha_fast = (raw_v >= s_bat.filtered_v) ? 0.22f : 0.10f;
            s_bat.filtered_v = (s_bat.filtered_v * (1.0f - alpha_fast)) + (raw_v * alpha_fast);
            s_bat.slow_v     = (s_bat.slow_v * 0.97f) + (raw_v * 0.03f);

            float rise_v     = (s_prev_raw_v > 0.0f) ? (raw_v - s_prev_raw_v) : 0.0f;
            float fast_delta = s_bat.filtered_v - s_bat.slow_v;

            /* Score-based USB charge detection (same heuristics as S3) */
            int evidence = 0;
            if (raw_v >= 3.70f && fast_delta >= 0.025f) evidence++;
            if (raw_v >= 3.70f && rise_v    >= 0.012f) evidence++;
            if (raw_v >= 3.85f && fast_delta >= 0.045f) evidence++;

            if (evidence > 0) {
                s_charge_score = (s_charge_score + evidence > 6) ? 6 : (s_charge_score + evidence);
            } else {
                int decay = (s_bat.charging && raw_v >= 3.85f && fast_delta >= -0.004f) ? 0
                          : ((raw_v <= 3.62f || fast_delta <= 0.008f) ? 2 : 1);
                s_charge_score -= decay;
                if (s_charge_score < 0) s_charge_score = 0;
            }
            s_bat.charging = (s_charge_score >= 2) ||
                             (s_bat.charging && s_charge_score >= 1 && raw_v >= 3.80f);

            s_prev_raw_v = raw_v;
        }

        /* Slow-stepped percentage (±2% per call, no big jumps) */
        int new_pct = _battery_pct_from_voltage(s_bat.filtered_v);
        if (s_bat.percent == 0) {
            s_bat.percent = new_pct;
        } else if (abs(new_pct - s_bat.percent) >= 2) {
            int step = (new_pct > s_bat.percent) ? 2 : -2;
            int next = s_bat.percent + step;
            if ((step > 0 && next > new_pct) || (step < 0 && next < new_pct)) next = new_pct;
            s_bat.percent = (next < 0) ? 0 : (next > 100 ? 100 : next);
        }
    } else {
        s_bat.filtered_v = 0.0f;
        s_bat.slow_v     = 0.0f;
        s_bat.percent    = 0;
        s_bat.charging   = false;
        s_prev_raw_v     = 0.0f;
        s_charge_score   = 0;
    }

    ESP_LOGD(TAG, "BAT raw=%.3f filt=%.3f slow=%.3f score=%d chg=%s pct=%d",
             raw_v, s_bat.filtered_v, s_bat.slow_v,
             s_charge_score, s_bat.charging ? "yes" : "no", s_bat.percent);

    if (out) memcpy(out, &s_bat, sizeof(*out));
    return ESP_OK;
}

void bsp_battery_get_state(bsp_battery_state_t *state)
{
    if (state) memcpy(state, &s_bat, sizeof(*state));
}

int bsp_battery_get_percent(void)
{
    return s_adc_ready ? s_bat.percent : -1;
}

float bsp_battery_get_voltage(void)
{
    return s_adc_ready ? s_bat.filtered_v : 0.0f;
}

bool bsp_battery_is_charging(void)
{
    return s_bat.charging;
}

/* ──────────────────────────────────────────────────────────────────────────
 * bsp_sdcard_init  —  SDMMC 4-bit mount via esp_vfs_fat
 * ────────────────────────────────────────────────────────────────────────*/
esp_err_t bsp_sdcard_init(void)
{
    if (s_sdcard_mounted) return ESP_OK;

    /* Power up the SD card via load switch if configured */
    if (BSP_PIN_SDMMC_PWR >= 0) {
        gpio_set_direction(BSP_PIN_SDMMC_PWR, GPIO_MODE_OUTPUT);
        gpio_set_level(BSP_PIN_SDMMC_PWR, BSP_SDMMC_PWR_ACTIVE_LEVEL);
        vTaskDelay(pdMS_TO_TICKS(50)); /* Allow rail to stabilize */
    }

    int sd_power_level = -1;
#if BSP_PIN_SDMMC_PWR >= 0
    sd_power_level = gpio_get_level(BSP_PIN_SDMMC_PWR);
#endif
    ESP_LOGI(TAG, "SD power: GPIO%d=%d (active=%d)",
             BSP_PIN_SDMMC_PWR, sd_power_level, BSP_SDMMC_PWR_ACTIVE_LEVEL);

    /* SDMMC host: IDF default slot 1 on P4; slot 1 explicitly on S3. */
    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
#if CONFIG_IDF_TARGET_ESP32S3
    host.slot = SDMMC_HOST_SLOT_1;
#else
    host.slot = SDMMC_HOST_SLOT_1;
#endif
    host.max_freq_khz = SDMMC_FREQ_DEFAULT; /* documented 20 MHz default */

    sdmmc_slot_config_t slot = SDMMC_SLOT_CONFIG_DEFAULT();
    slot.width = (BSP_PIN_SDMMC_D1 >= 0) ? 4 : 1;
    slot.clk   = BSP_PIN_SDMMC_CLK;
    slot.cmd   = BSP_PIN_SDMMC_CMD;
    slot.d0    = BSP_PIN_SDMMC_D0;
    if (BSP_PIN_SDMMC_D1 >= 0) slot.d1 = BSP_PIN_SDMMC_D1;
    if (BSP_PIN_SDMMC_D2 >= 0) slot.d2 = BSP_PIN_SDMMC_D2;
    if (BSP_PIN_SDMMC_D3 >= 0) slot.d3 = BSP_PIN_SDMMC_D3;
    slot.flags |= SDMMC_SLOT_FLAG_INTERNAL_PULLUP;

    /* FAT filesystem mount config */
    esp_vfs_fat_sdmmc_mount_config_t mount_cfg = {
        .format_if_mount_failed = false,
        .max_files              = 8,
        .allocation_unit_size   = 16 * 1024,
    };

    ESP_LOGI(TAG, "SD probe: slot=%d width=%d clk=%d cmd=%d d0=%d d1=%d d2=%d d3=%d freq=%dkHz",
             host.slot, slot.width, slot.clk, slot.cmd, slot.d0,
             slot.d1, slot.d2, slot.d3, host.max_freq_khz);

    esp_err_t ret = esp_vfs_fat_sdmmc_mount(BSP_SDCARD_MOUNT_POINT, &host, &slot,
                                             &mount_cfg, &s_sdcard);

#if CONFIG_IDF_TARGET_ESP32P4
    /* A 4-bit timeout can be caused by a bad D1-D3 connection or marginal
     * signal integrity.  Retry at the card's safe probing speed in 1-bit
     * mode so the validation screen can distinguish those faults from a
     * dead/powerless card. */
    if (ret == ESP_ERR_TIMEOUT && slot.width == 4) {
        ESP_LOGW(TAG, "SD 4-bit probe timed out; retrying 1-bit at %dkHz",
                 SDMMC_FREQ_PROBING);
        if (BSP_PIN_SDMMC_PWR >= 0) {
            gpio_set_level(BSP_PIN_SDMMC_PWR, !BSP_SDMMC_PWR_ACTIVE_LEVEL);
            vTaskDelay(pdMS_TO_TICKS(20));
            gpio_set_level(BSP_PIN_SDMMC_PWR, BSP_SDMMC_PWR_ACTIVE_LEVEL);
            vTaskDelay(pdMS_TO_TICKS(50));
        }
        host.max_freq_khz = SDMMC_FREQ_PROBING;
        slot.width = 1;
        ret = esp_vfs_fat_sdmmc_mount(BSP_SDCARD_MOUNT_POINT, &host, &slot,
                                       &mount_cfg, &s_sdcard);
        if (ret == ESP_OK) {
            ESP_LOGW(TAG, "SD mounted in 1-bit fallback; D1-D3/4-bit path needs follow-up");
        }
    }
#endif
    if (ret != ESP_OK) {
        if (ret == ESP_FAIL) {
            ESP_LOGE(TAG, "SD mount failed — card may need formatting as FAT32");
        } else {
            ESP_LOGW(TAG, "SD not found or mount error: %s", esp_err_to_name(ret));
        }
        if (BSP_PIN_SDMMC_PWR >= 0) {
            gpio_set_level(BSP_PIN_SDMMC_PWR, !BSP_SDMMC_PWR_ACTIVE_LEVEL); /* Cut SD power */
        }
        return ret;
    }

    s_sdcard_mounted = true;
    sdmmc_card_print_info(stdout, s_sdcard);

    /* Create required directory structure on first mount */
    _mkdir_p(BSP_SESSIONS_DIR);
    _mkdir_p(BSP_SESSIONS_ARCH_DIR);

    /* Log storage info */
    uint64_t total_bytes = (uint64_t)s_sdcard->csd.capacity * s_sdcard->csd.sector_size;
    ESP_LOGI(TAG, "SD mounted at %s — %.1f GB", BSP_SDCARD_MOUNT_POINT,
             (float)total_bytes / (1024.0f * 1024.0f * 1024.0f));

    return ESP_OK;
}

esp_err_t bsp_sdcard_validate(void)
{
    static const char *path = "/sd/.racesense_hw_test.tmp";
    static const char pattern[] = "RaceSense SD hardware validation\n";
    char readback[sizeof(pattern)] = {0};

    if (!s_sdcard_mounted) return ESP_ERR_INVALID_STATE;

    FILE *f = fopen(path, "wb");
    if (!f) {
        ESP_LOGE(TAG, "SD validation: cannot create %s", path);
        return ESP_FAIL;
    }
    size_t written = fwrite(pattern, 1, sizeof(pattern) - 1, f);
    int flush_ret = fflush(f);
    int close_ret = fclose(f);
    if (written != sizeof(pattern) - 1 || flush_ret != 0 || close_ret != 0) {
        remove(path);
        ESP_LOGE(TAG, "SD validation: write failed (%u/%u bytes)",
                 (unsigned)written, (unsigned)(sizeof(pattern) - 1));
        return ESP_FAIL;
    }

    f = fopen(path, "rb");
    if (!f) {
        remove(path);
        ESP_LOGE(TAG, "SD validation: cannot reopen test file");
        return ESP_FAIL;
    }
    size_t read = fread(readback, 1, sizeof(pattern) - 1, f);
    int read_error = ferror(f);
    fclose(f);
    int remove_ret = remove(path);

    if (read != sizeof(pattern) - 1 || read_error ||
        memcmp(readback, pattern, sizeof(pattern) - 1) != 0 || remove_ret != 0) {
        ESP_LOGE(TAG, "SD validation: readback failed (%u/%u bytes)",
                 (unsigned)read, (unsigned)(sizeof(pattern) - 1));
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "SD validation: write/readback/remove OK");
    return ESP_OK;
}

void bsp_sdcard_deinit(void)
{
    if (!s_sdcard_mounted) return;
    esp_vfs_fat_sdcard_unmount(BSP_SDCARD_MOUNT_POINT, s_sdcard);
    s_sdcard_mounted = false;
    s_sdcard = NULL;
    if (BSP_PIN_SDMMC_PWR >= 0) {
        gpio_set_level(BSP_PIN_SDMMC_PWR, !BSP_SDMMC_PWR_ACTIVE_LEVEL);
    }
    ESP_LOGI(TAG, "SD unmounted");
}

bool bsp_sdcard_mounted(void)
{
    return s_sdcard_mounted;
}

int bsp_sdcard_get_usage_percent(void)
{
    if (!s_sdcard_mounted) return -1;
    FATFS *fs;
    DWORD  fre_clust;
    if (f_getfree("0:", &fre_clust, &fs) != FR_OK) return -1;
    uint64_t total = ((uint64_t)(fs->n_fatent - 2)) * fs->csize;
    uint64_t free_  = (uint64_t)fre_clust * fs->csize;
    if (total == 0) return -1;
    return (int)(((total - free_) * 100ULL) / total);
}

/* ──────────────────────────────────────────────────────────────────────────
 * Display & Touch — Phase 8 stubs
 * ────────────────────────────────────────────────────────────────────────*/
/* Forward declarations — implemented in bsp_display.c */
extern esp_err_t bsp_display_driver_init(void);
extern esp_err_t bsp_touch_driver_init(void);

esp_err_t bsp_display_init(void)
{
    ESP_LOGI(TAG, "Display init: target=%d (%dx%d)",
             BSP_DISPLAY_TARGET, BSP_LCD_H_RES, BSP_LCD_V_RES);
    return bsp_display_driver_init();
}

esp_err_t bsp_touch_init(void)
{
    ESP_LOGI(TAG, "Touch init: target=%d", BSP_DISPLAY_TARGET);
    return bsp_touch_driver_init();
}

/* ──────────────────────────────────────────────────────────────────────────
 * bsp_init  —  master boot sequence
 * ────────────────────────────────────────────────────────────────────────*/
esp_err_t bsp_init(void)
{
#if CONFIG_IDF_TARGET_ESP32S3
    ESP_LOGI(TAG, "BSP init: RaceSense RS-Core V4.2 (ESP32-S3)");
    if (BSP_PIN_PWR_HOLD >= 0) {
        gpio_reset_pin(BSP_PIN_PWR_HOLD);
        gpio_set_direction(BSP_PIN_PWR_HOLD, GPIO_MODE_OUTPUT);
        gpio_set_level(BSP_PIN_PWR_HOLD, 1); /* Latch power immediately on boot */
        ESP_LOGI(TAG, "[PWR] Soft-latch hold asserted on GPIO %d", BSP_PIN_PWR_HOLD);
    }
#else
    ESP_LOGI(TAG, "BSP init: Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3");
#endif

    /* 1. Battery ADC */
    esp_err_t ret = bsp_battery_init();
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Battery ADC init failed: %s", esp_err_to_name(ret));
        /* Non-fatal — device can run without battery monitoring */
    }

    /* 2. SD card — non-fatal if absent */
    ret = bsp_sdcard_init();
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "SD card not available: %s", esp_err_to_name(ret));
    }

    /* 3. Display (stub until Phase 8) */
    bsp_display_init();

    /* 4. Touch is optional: a missing controller must never prevent the UI
     * from starting.  The P4 driver owns I2C0 using the modern IDF API. */
    ret = bsp_touch_init();
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Touch unavailable: %s", esp_err_to_name(ret));
    }

    ESP_LOGI(TAG, "BSP init complete — SD:%s Battery:%.2fV/%d%% Charging:%s",
             s_sdcard_mounted ? "OK" : "ABSENT",
             s_bat.filtered_v,
             s_bat.percent,
             s_bat.charging ? "yes" : "no");

    return ESP_OK;
}

/* ──────────────────────────────────────────────────────────────────────────
 * bsp_power_hold_release  —  release soft power latch on ESP32-S3
 * ────────────────────────────────────────────────────────────────────────*/
void bsp_power_hold_release(void)
{
#if CONFIG_IDF_TARGET_ESP32S3
    if (BSP_PIN_PWR_HOLD >= 0) {
        gpio_set_level(BSP_PIN_PWR_HOLD, 0);
        ESP_LOGI(TAG, "[PWR] Power hold released — hardware power dropping");
    }
#endif
}
