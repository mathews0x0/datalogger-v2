/**
 * @file ui_events.c
 * @brief Resolution-Agnostic UI Touch Event & Backend Dispatch Layer Implementation
 */

#include "ui_events.h"
#include <stdio.h>
#include "esp_log.h"

static const char *TAG = "ui_events";

/** Registered application state listener callback */
static ui_event_listener_cb_t s_app_listener_cb = NULL;

esp_err_t ui_events_register_listener(ui_event_listener_cb_t cb)
{
    s_app_listener_cb = cb;
    ESP_LOGI(TAG, "Application state event listener registered successfully");
    return ESP_OK;
}

void ui_events_dispatch(ui_event_type_t event, void *param)
{
    ESP_LOGD(TAG, "Dispatching UI Event: ID=%d, Param=%p", (int)event, param);
    if (s_app_listener_cb != NULL) {
        s_app_listener_cb(event, param);
    } else {
        ESP_LOGW(TAG, "UI event dispatched (ID=%d), but no system listener registered!", (int)event);
    }
}

/* ──────────────────────────────────────────────────────────────────────────
 * Direct Event Trigger Convenience Helpers
 * ────────────────────────────────────────────────────────────────────────*/

void ui_events_on_start_log(void)
{
    ESP_LOGI(TAG, "Touch Action: START LOG triggered");
    ui_events_dispatch(UI_EVENT_START_LOG_CLICKED, NULL);
}

void ui_events_on_stop_log(void)
{
    ESP_LOGI(TAG, "Touch Action: STOP LOG confirmed (Hold-to-confirm completed)");
    ui_events_dispatch(UI_EVENT_STOP_LOG_HELD, NULL);
}

void ui_events_on_sync_start(void)
{
    ESP_LOGI(TAG, "Touch Action: SYNC mode triggered");
    ui_events_dispatch(UI_EVENT_SYNC_CLICKED, NULL);
}

void ui_events_on_open_settings(void)
{
    ESP_LOGI(TAG, "Touch Action: SETTINGS screen requested");
    ui_events_dispatch(UI_EVENT_SETTINGS_CLICKED, NULL);
}

void ui_events_on_open_hardware_debug(void)
{
    ESP_LOGI(TAG, "Touch Action: HARDWARE DEBUG screen requested");
    ui_events_dispatch(UI_EVENT_HARDWARE_DEBUG_CLICKED, NULL);
}

void ui_events_on_open_data(void)
{
    ESP_LOGI(TAG, "Touch Action: DATA / pending files screen requested");
    ui_events_dispatch(UI_EVENT_DATA_CLICKED, NULL);
}

void ui_events_on_navigate_home(void)
{
    ESP_LOGI(TAG, "Touch Action: NAVIGATE HOME / CANCEL requested");
    ui_events_dispatch(UI_EVENT_BACK_CLICKED, NULL);
}

void ui_events_on_open_track_view(void)
{
    ESP_LOGI(TAG, "Touch Action: ACTIVE TRACK viewer requested");
    ui_events_dispatch(UI_EVENT_TRACK_VIEW_CLICKED, NULL);
}

void ui_events_on_open_track_selector(void)
{
    ESP_LOGI(TAG, "Touch Action: OFFLINE TRACK SELECTOR requested");
    ui_events_dispatch(UI_EVENT_TRACK_SELECT_CLICKED, NULL);
}

void ui_events_on_select_track(int32_t track_id)
{
    ESP_LOGI(TAG, "Touch Action: cached track %ld selected", (long)track_id);
    ui_events_dispatch(UI_EVENT_TRACK_SELECTED, (void *)(intptr_t)track_id);
}

void ui_events_on_start_captive_portal(void)
{
    ESP_LOGI(TAG, "Touch Action: START CAPTIVE PORTAL (WiFi Setup) requested");
    ui_events_dispatch(UI_EVENT_WIFI_SETUP_CLICKED, NULL);
}

void ui_events_on_toggle_autolog(bool enabled)
{
    ESP_LOGI(TAG, "Touch Action: TOGGLE AUTO-LOG swiched to: %s", enabled ? "ENABLED" : "DISABLED");
    ui_events_dispatch(UI_EVENT_AUTO_LOG_TOGGLED, (void *)(uintptr_t)enabled);
}

void ui_events_on_calib_next_step(void)
{
    ESP_LOGI(TAG, "Touch Action: IMU CALIBRATION next stage triggered");
    ui_events_dispatch(UI_EVENT_CALIB_NEXT_STAGE_CLICKED, NULL);
}

void ui_events_on_cancel_sync(void)
{
    ESP_LOGI(TAG, "Touch Action: CANCEL SYNC triggered");
    ui_events_dispatch(UI_EVENT_SYNC_CANCEL_CLICKED, NULL);
}

void ui_events_on_close_captive_portal(void)
{
    ESP_LOGI(TAG, "Touch Action: CLOSE CAPTIVE PORTAL requested");
    ui_events_dispatch(UI_EVENT_BACK_CLICKED, NULL);
}

void ui_events_on_sector_flash(int color_type, const char *label)
{
    ESP_LOGI(TAG, "Feedback Event: Sector flash color=%d label=%s", color_type, label ? label : "");
}
