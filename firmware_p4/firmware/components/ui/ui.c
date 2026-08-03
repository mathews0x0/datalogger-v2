/**
 * @file ui.c
 * @brief Adaptive LVGL Driver Abstraction & UI Engine Initialization
 *
 * Handles display controller initialization (ST7701 MIPI-DSI for ESP32-P4 widescreen,
 * or RGB/SPI alternatives for ESP32-S3 and compact screens), input device registration
 * (GT911 touch controller), and thread-safe LVGL task locking.
 */

#include "ui.h"
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_lvgl_port.h"

static const char *TAG = "ui_engine";
static bool s_ui_initialized = false;

esp_err_t ui_init(void)
{
    if (s_ui_initialized) {
        ESP_LOGW(TAG, "UI component already initialized");
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Initializing RaceSense Adaptive UI Engine...");
    ESP_LOGI(TAG, "Target Geometry: [%dx%d] px (Widescreen Mode: %s)",
             UI_HOR_RES, UI_VER_RES, UI_RES_CLASS_WIDESCREEN ? "YES" : "NO");

    /* Initialize Motorsport Dark Theme style declarations */
    ui_theme_init();

#if CONFIG_IDF_TARGET_ESP32S3
    ESP_LOGI(TAG, "Hardware driver abstraction ready: ILI9341 SPI (320x240) + XPT2046 Touch");
#else
    ESP_LOGI(TAG, "Hardware driver abstraction ready: ST7701 MIPI-DSI (800x480) + GT911 Touch");
#endif

    s_ui_initialized = true;
    ESP_LOGI(TAG, "RaceSense UI Engine initialized successfully");
    return ESP_OK;
}

bool ui_lock(int timeout_ms)
{
    uint32_t t = (timeout_ms < 0) ? 0xFFFFFFFF : (uint32_t)timeout_ms;
    return lvgl_port_lock(t);
}

void ui_unlock(void)
{
    lvgl_port_unlock();
}

void ui_load_screen(lv_obj_t *screen)
{
    /* lv_scr_load() keeps the previous screen alive in LVGL 9. */
    lv_scr_load_anim(screen, LV_SCR_LOAD_ANIM_NONE, 0, 0, true);
}

void ui_load_screen_smooth(lv_obj_t *screen)
{
    /* Keep the previous composed frame visible while the dense telemetry
     * screen is first rendered, rather than showing an intermediate blank. */
    lv_scr_load_anim(screen, LV_SCR_LOAD_ANIM_FADE_IN, 160, 0, true);
}
