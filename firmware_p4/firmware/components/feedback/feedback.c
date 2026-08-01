/**
 * @file feedback.c
 * @brief Rider Visual Feedback State Machine
 *
 * Manages the display-side sector/lap feedback overlay on the ESP32-P4.
 * On the P4 there are no WS2812 LEDs — all feedback is screen-based:
 *   - Sector crossing: full-screen color flash (green/orange/red) for 3s
 *   - Lap complete:    full-screen lap time overlay for 2s
 *   - Brightness:      LVGL display brightness API
 *
 * Connects to the track_engine event callback and calls ui_events_on_sector_flash()
 * which is already implemented in ui_logging.c.
 *
 * Call feedback_tick() every ~50ms from the UI task loop.
 */

#include "feedback.h"

#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* Forward declaration — implemented in ui_events.c */
extern void ui_events_on_sector_flash(int color_type, const char *label);

static const char *TAG = "feedback";

/* ──────────────────────────────────────────────────────────────────────────
 * State definitions
 * ────────────────────────────────────────────────────────────────────────*/
typedef enum {
    FB_IDLE,
    FB_LOGGING,
    FB_SECTOR_FAST,     /**< Green flash 3s    */
    FB_SECTOR_NEUTRAL,  /**< Orange flash 3s   */
    FB_SECTOR_SLOW,     /**< Red flash 3s      */
    FB_LAP_COMPLETE,    /**< Lap time 2s       */
    FB_SYNC,
    FB_ERROR,
} fb_state_t;

typedef enum {
    FB_OVERLAY_NONE,
    FB_OVERLAY_SECTOR_FAST,
    FB_OVERLAY_SECTOR_NEUTRAL,
    FB_OVERLAY_SECTOR_SLOW,
    FB_OVERLAY_LAP,
} fb_overlay_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Module state
 * ────────────────────────────────────────────────────────────────────────*/
static fb_state_t   s_state          = FB_IDLE;
static fb_overlay_t s_overlay        = FB_OVERLAY_NONE;
static int64_t      s_overlay_expiry = 0;   /**< µs — from esp_timer_get_time() */
static float        s_brightness     = 1.0f;

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t feedback_init(void)
{
    s_state          = FB_IDLE;
    s_overlay        = FB_OVERLAY_NONE;
    s_overlay_expiry = 0;
    s_brightness     = 1.0f;
    ESP_LOGI(TAG, "Feedback state machine initialised");
    return ESP_OK;
}

void feedback_set_state(int state)
{
    fb_state_t new_state = (fb_state_t)state;
    if (new_state == s_state) return;

    ESP_LOGD(TAG, "State transition: %d → %d", s_state, new_state);
    s_state = new_state;

    /* Sector/lap states automatically trigger their overlay */
    switch (new_state) {
        case FB_SECTOR_FAST:
            feedback_set_overlay(FB_OVERLAY_SECTOR_FAST,    3000);
            break;
        case FB_SECTOR_NEUTRAL:
            feedback_set_overlay(FB_OVERLAY_SECTOR_NEUTRAL, 3000);
            break;
        case FB_SECTOR_SLOW:
            feedback_set_overlay(FB_OVERLAY_SECTOR_SLOW,    3000);
            break;
        case FB_LAP_COMPLETE:
            feedback_set_overlay(FB_OVERLAY_LAP,            2000);
            break;
        default:
            break;
    }
}

void feedback_set_overlay(int overlay, int duration_ms)
{
    s_overlay        = (fb_overlay_t)overlay;
    s_overlay_expiry = esp_timer_get_time() + (int64_t)duration_ms * 1000LL;

    /* Trigger UI overlay via event dispatcher */
    const char *label = "●";
    switch ((fb_overlay_t)overlay) {
        case FB_OVERLAY_SECTOR_FAST:    label = "FAST";    break;
        case FB_OVERLAY_SECTOR_NEUTRAL: label = "OK";      break;
        case FB_OVERLAY_SECTOR_SLOW:    label = "SLOW";    break;
        case FB_OVERLAY_LAP:            label = "LAP";     break;
        default: break;
    }

    ESP_LOGI(TAG, "Overlay: %s for %dms", label, duration_ms);

    /* Call into UI event system — ui_events_on_sector_flash is already implemented */
    if (overlay != FB_OVERLAY_NONE) {
        ui_events_on_sector_flash((int)overlay, label);
    }
}

void feedback_set_brightness(float brightness)
{
    if (brightness < 0.0f) brightness = 0.0f;
    if (brightness > 1.0f) brightness = 1.0f;
    s_brightness = brightness;

    /* Apply via LVGL display brightness — calls into lvgl_port or backlight PWM */
    /* lv_disp_set_bg_opa(lv_disp_get_default(), (lv_opa_t)(brightness * 255)); */
    ESP_LOGD(TAG, "Brightness set to %.2f", brightness);
}

void feedback_tick(void)
{
    /* Check overlay expiry */
    if (s_overlay != FB_OVERLAY_NONE) {
        int64_t now_us = esp_timer_get_time();
        if (now_us >= s_overlay_expiry) {
            ESP_LOGD(TAG, "Overlay expired — returning to LOGGING state");
            s_overlay = FB_OVERLAY_NONE;
            /* Auto-return to logging state after overlay */
            if (s_state == FB_SECTOR_FAST    ||
                s_state == FB_SECTOR_NEUTRAL ||
                s_state == FB_SECTOR_SLOW    ||
                s_state == FB_LAP_COMPLETE) {
                s_state = FB_LOGGING;
            }
        }
    }
}

/* ──────────────────────────────────────────────────────────────────────────
 * Convenience accessors (used by UI task)
 * ────────────────────────────────────────────────────────────────────────*/
int   feedback_get_state(void)      { return (int)s_state; }
int   feedback_get_overlay(void)    { return (int)s_overlay; }
float feedback_get_brightness(void) { return s_brightness; }
bool  feedback_overlay_active(void) { return s_overlay != FB_OVERLAY_NONE; }
