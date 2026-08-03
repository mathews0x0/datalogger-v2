/**
 * @file bsp.h
 * @brief Multi-Platform Board Support Package (ESP32-S3 & ESP32-P4)
 *
 * Automatically maps GPIO pin constants and peripheral channels for either target:
 *   - ESP32-S3: RaceSense RS-Core V4.2 PCB
 *   - ESP32-P4: Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3
 */

#ifndef BSP_H
#define BSP_H

#include <stdbool.h>
#include "esp_err.h"
#include "sdkconfig.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Target-Specific GPIO & Peripheral Mapping
 * ────────────────────────────────────────────────────────────────────────*/

#if CONFIG_IDF_TARGET_ESP32S3

  /* I2C0 — BMI323 6-DOF IMU sensor */
  #define BSP_PIN_I2C0_SDA        21
  #define BSP_PIN_I2C0_SCL        39
  #define BSP_PIN_BMI323_SDA      BSP_PIN_I2C0_SDA
  #define BSP_PIN_BMI323_SCL      BSP_PIN_I2C0_SCL

  /* UART1 — Neo-M8N GNSS (GPS) */
  #define BSP_PIN_GPS_TX          17
  #define BSP_PIN_GPS_RX          18

  /* Battery ADC — VBAT-SENSE (100k/100k divider) */
  #define BSP_PIN_BATTERY_ADC     14
  #define BSP_BAT_ADC_UNIT        ADC_UNIT_2      /**< GPIO 14 on S3 is on ADC2 */
  #define BSP_BAT_ADC_CHANNEL     ADC_CHANNEL_3   /**< GPIO 14 on S3 = ADC2 CH3 */
  #define BSP_BATTERY_DIVIDER_SCALE 2.10f

  /* SDMMC / SPI SD Card (S3 SDMMC slot 1 / SPI mode) */
  #define BSP_PIN_SDMMC_CLK       12
  #define BSP_PIN_SDMMC_CMD       11
  #define BSP_PIN_SDMMC_D0        13
  #define BSP_PIN_SDMMC_D1        (-1)
  #define BSP_PIN_SDMMC_D2        (-1)
  #define BSP_PIN_SDMMC_D3        (-1)
  #define BSP_PIN_SDMMC_PWR       (-1)

  /* Power Hold & Intent Sense (RS-Core V4.2 soft-latch) */
  #define BSP_PIN_PWR_HOLD        41
  #define BSP_PIN_PWR_SENSE       8
  #define BSP_PIN_DEBUG_LED       2

#else /* ESP32-P4 (Default) */

  /* I2C0 — GT911 touch controller */
  #define BSP_PIN_I2C0_SDA        7
  #define BSP_PIN_I2C0_SCL        8

  /* I2C1 — external BMI323 four-pin module */
  #define BSP_PIN_BMI323_SDA      21
  #define BSP_PIN_BMI323_SCL      22

  /* UART1 — Neo-M8N GNSS (GPS) */
  #define BSP_PIN_GPS_TX          3
  #define BSP_PIN_GPS_RX          4

  /* Battery ADC — BAT → 200kΩ → BAT_ADC → 100kΩ → GND, BAT_ADC on GPIO20 */
  #define BSP_PIN_BATTERY_ADC     20
  #define BSP_BAT_ADC_UNIT        ADC_UNIT_1      /**< GPIO 20 on P4 is on ADC1 */
  #define BSP_BAT_ADC_CHANNEL     ADC_CHANNEL_4   /**< GPIO 20 on P4 = ADC1 CH4 */
  #define BSP_BATTERY_DIVIDER_SCALE 3.00f

  /* SDMMC 4-bit — documented Waveshare TF card wiring; use IDF default host
   * (slot 1 on ESP32-P4) with GPIO-matrix routing. */
  #define BSP_PIN_SDMMC_CLK       43
  #define BSP_PIN_SDMMC_CMD       44
  #define BSP_PIN_SDMMC_D0        39
  #define BSP_PIN_SDMMC_D1        40
  #define BSP_PIN_SDMMC_D2        41
  #define BSP_PIN_SDMMC_D3        42
  #define BSP_PIN_SDMMC_PWR       45
  #define BSP_SDMMC_PWR_ACTIVE_LEVEL 0  /* AO3401 high-side switch is active-low */

  #define BSP_PIN_PWR_HOLD        (-1)
  #define BSP_PIN_PWR_SENSE       (-1)
  #define BSP_PIN_DEBUG_LED       (-1)

#endif

/* Common SD Card filesystem paths */
#define BSP_SDCARD_MOUNT_POINT  "/sd"
#define BSP_SESSIONS_DIR        "/sd/sessions"
#define BSP_SESSIONS_ARCH_DIR   "/sd/sessions/uploaded"

/* ──────────────────────────────────────────────────────────────────────────
 * Data Structures
 * ────────────────────────────────────────────────────────────────────────*/

typedef struct {
    float   raw_v;          /**< Latest raw ADC voltage (pre-filter)       */
    float   filtered_v;     /**< Dual-EMA filtered voltage (display value) */
    float   slow_v;         /**< Slow EMA used for charge-detect baseline  */
    int     percent;        /**< Battery % 0-100 (slow-stepped, no jumps)  */
    bool    charging;       /**< true when USB charge current is detected  */
} bsp_battery_state_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Public API
 * ────────────────────────────────────────────────────────────────────────*/

esp_err_t bsp_init(void);
esp_err_t bsp_battery_init(void);
esp_err_t bsp_battery_update(bsp_battery_state_t *state);
void      bsp_battery_get_state(bsp_battery_state_t *state);
int       bsp_battery_get_percent(void);
float     bsp_battery_get_voltage(void);
bool      bsp_battery_is_charging(void);

esp_err_t bsp_sdcard_init(void);
esp_err_t bsp_sdcard_validate(void);
void      bsp_sdcard_deinit(void);
bool      bsp_sdcard_mounted(void);
int       bsp_sdcard_get_usage_percent(void);

esp_err_t bsp_display_init(void);
esp_err_t bsp_touch_init(void);
void      bsp_power_hold_release(void);

#ifdef __cplusplus
}
#endif

#endif /* BSP_H */
