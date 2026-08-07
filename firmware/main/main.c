/**
 * @file main.c
 * @brief RaceSense ESP32-P4 Firmware — Application Entry Point
 *
 * This is the top-level application state machine for the RaceSense
 * motorcycle telemetry datalogger. It initializes all hardware subsystems
 * and manages transitions between application states.
 *
 * Core assignment:
 *   Core 0: Sensor ingestion (100Hz IMU + 10Hz GPS) — hard real-time (Phase 7B)
 *   Core 1: UI rendering (LVGL), storage flush, networking  (Phase 8 / 7C-D)
 *
 * Target: Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3
 * Framework: ESP-IDF v5.x / FreeRTOS SMP
 */

#include <stdio.h>
#include <string.h>
#include <math.h>
#include <sys/stat.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "esp_app_desc.h"
#include "nvs_flash.h"

/* Board Support Package */
#include "bsp.h"
#include "touch_calibration.h"

/* Sensor ingestion (Phase 7B) */
#include "sensors.h"

/* LVGL UI subsystem (Phase 8) */
#include "ui.h"
#include "ui_events.h"
#include "network.h"

/* Storage engine (Phase 7C) */
#include "storage.h"
#include "track_engine.h"
#include "feedback.h"

static const char *TAG = "racesense";

/* ──────────────────────────────────────────────────────────────────────────
 * Application States  (maps 1:1 to the UI screens)
 * ──────────────────────────────────────────────────────────────────────────*/
typedef enum {
    STATE_BOOT_INIT,         /* Screen 1:  Boot splash               */
    STATE_AUTO_COPY,         /* Internal:  Flash → SD session copy    */
    STATE_HOME_IDLE,         /* Screen 2:  Home                      */
    STATE_TRACK_VIEW,        /* Screen 15: Active track / TBL viewer  */
    STATE_TRACK_SELECTOR,    /* Cached offline track selection        */
    STATE_LOGGING_ACTIVE,    /* Screen 3:  Live Logging              */
    STATE_STORAGE_FAULT,     /* Screen 14: Logging stopped safely    */
    STATE_IMU_VALIDATION,    /* Screen 4:  IMU Validation (first 5s) */
    STATE_SECTOR_FLASH,      /* Screen 5:  Sector crossing overlay   */
    STATE_SYNC_WIFI_SEARCH,  /* Screen 6:  WiFi Search               */
    STATE_SYNC_HEARTBEAT,    /* Screen 7:  Heartbeat                 */
    STATE_SYNC_UPLOADING,    /* Screen 8:  Upload Progress           */
    STATE_SYNC_COMPLETE,     /* Screen 9:  Sync Complete / Idle      */
    STATE_SETTINGS,          /* Screen 10: Settings                  */
    STATE_IMU_CALIBRATION,   /* Screen 11: IMU Calibration Flow      */
    STATE_CAPTIVE_PORTAL,    /* Screen 12: Captive Portal Active     */
    STATE_HARDWARE_DEBUG,    /* Screen 13: GPS/IMU hardware debug    */
    STATE_DATA,              /* Screen 16: Pending session browser    */
    STATE_SHUTDOWN,          /* Internal:  Clean shutdown            */
} app_state_t;

static volatile app_state_t s_state = STATE_BOOT_INIT;
static volatile bool s_data_screen_pending;
static volatile int s_sync_files_done;
static volatile int s_sync_total_files;
static int64_t s_sync_started_us;
static QueueHandle_t s_track_event_queue;
static volatile uint32_t s_track_events_dropped;
#if !CONFIG_IDF_TARGET_ESP32P4 || CONFIG_ESP_WIFI_REMOTE_ENABLED
static TaskHandle_t s_portal_task;
#endif

static void _show_home_dashboard(void);

static void _log_provisioning_status(void)
{
    network_device_config_t cfg = {0};
    esp_err_t ret = network_load_device_config(&cfg);
    ESP_LOGI(TAG,
             "[BOOT] Provisioning config: ret=%s ssid=%s password=%s token=%s api_url=%s",
             esp_err_to_name(ret),
             cfg.ssid[0] ? "set" : "missing",
             cfg.password[0] ? "set" : "empty",
             cfg.token[0] ? "set" : "missing",
             cfg.api_url[0] ? "set" : "missing");
}

#if CONFIG_RS_NETWORK_SYNC_SELF_TEST
#define NETWORK_PROBE_TASK_STACK_SIZE 16384
static void _network_sync_probe_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "[BOOT] Starting provisioned server probe");
    bool ok = network_sync_probe();
    ESP_LOGI(TAG, "[BOOT] Provisioned server probe: %s", ok ? "PASS" : "FAIL");
    vTaskDelete(NULL);
}
#endif

#define TRACK_EVENT_QUEUE_DEPTH 8

/* The track engine runs beside the fresh GPS sample on the sensor task. Its
 * callback only copies the small event value into this queue; all feedback
 * and LVGL work is performed by app_main below. */
static void _track_event_cb(const track_event_t *event, void *ctx)
{
    (void)ctx;
    if (!event || !s_track_event_queue ||
        xQueueSend(s_track_event_queue, event, 0) != pdTRUE) {
        s_track_events_dropped++;
    }
}

static int _feedback_state_for_event(const track_event_t *event)
{
    if (!event) return FEEDBACK_STATE_IDLE;
    if (event->type == TRACK_EVT_LAP) {
        switch (event->sub_type) {
            case TRACK_EVT_SECTOR_FAST:    return FEEDBACK_STATE_LAP_COMPLETE;
            case TRACK_EVT_SECTOR_NEUTRAL: return FEEDBACK_STATE_LAP_COMPLETE;
            case TRACK_EVT_SECTOR_SLOW:    return FEEDBACK_STATE_LAP_COMPLETE;
        }
    }
    switch (event->sub_type) {
        case TRACK_EVT_SECTOR_FAST:    return FEEDBACK_STATE_SECTOR_FAST;
        case TRACK_EVT_SECTOR_NEUTRAL: return FEEDBACK_STATE_SECTOR_NEUTRAL;
        case TRACK_EVT_SECTOR_SLOW:    return FEEDBACK_STATE_SECTOR_SLOW;
    }
    return FEEDBACK_STATE_LOGGING;
}

static void _format_timing_delta(float delta_s, char *out, size_t out_len)
{
    if (!out || out_len == 0) return;
    if (!isfinite(delta_s)) {
        snprintf(out, out_len, "Δ --");
    } else if (fabsf(delta_s) < 0.05f) {
        snprintf(out, out_len, "Δ 0.0s");
    } else {
        snprintf(out, out_len, "Δ %+.1fs", delta_s);
    }
}

static void _format_seconds(float seconds, char *out, size_t out_len)
{
    if (!out || out_len == 0) return;
    if (!isfinite(seconds) || seconds <= 0.0f) snprintf(out, out_len, "--.---");
    else snprintf(out, out_len, "%.3fs", seconds);
}

static void _format_lap_time(float seconds, char *out, size_t out_len)
{
    if (!out || out_len == 0) return;
    if (!isfinite(seconds) || seconds < 0.0f) {
        snprintf(out, out_len, "--.---");
        return;
    }
    int total_ms = (int)lroundf(seconds * 1000.0f);
    int minutes = total_ms / 60000;
    int whole_seconds = (total_ms % 60000) / 1000;
    int milliseconds = total_ms % 1000;
    if (minutes > 0) snprintf(out, out_len, "%d:%02d.%03d", minutes,
                              whole_seconds, milliseconds);
    else snprintf(out, out_len, "%d.%03d", whole_seconds, milliseconds);
}

static void _process_track_events(void)
{
    if (!s_track_event_queue) return;

    track_event_t event;
    while (xQueueReceive(s_track_event_queue, &event, 0) == pdTRUE) {
        if (s_state != STATE_LOGGING_ACTIVE && s_state != STATE_IMU_VALIDATION) {
            continue;
        }

        if (event.type == TRACK_EVT_FOUND) {
            ESP_LOGI(TAG, "[TIMING] Track found: %s", track_engine_get_track_name());
            feedback_set_state(FEEDBACK_STATE_LOGGING);
            continue;
        }

        feedback_set_state(_feedback_state_for_event(&event));

        char delta_buf[32];
        _format_timing_delta(event.delta_s, delta_buf, sizeof(delta_buf));

        if (event.type == TRACK_EVT_SECTOR) {
            char sector_time[24];
            char tbl_time[24];
            _format_seconds(event.sector_time, sector_time, sizeof(sector_time));
            _format_seconds(event.tbl_time, tbl_time, sizeof(tbl_time));
            ui_show_sector_flash(event.sector_index + 1,
                                 delta_buf,
                                 event.sub_type == TRACK_EVT_SECTOR_FAST,
                                 sector_time,
                                 tbl_time);
        } else if (event.type == TRACK_EVT_LAP) {
            char lap_time[24];
            _format_lap_time(event.lap_time, lap_time, sizeof(lap_time));
            ui_logging_update_lap(lap_time,
                                  delta_buf,
                                  event.sub_type == TRACK_EVT_SECTOR_FAST,
                                  track_engine_get_current_lap_number());
        }
    }
}

#if !CONFIG_IDF_TARGET_ESP32P4 || CONFIG_ESP_WIFI_REMOTE_ENABLED
static void _sync_progress_cb(const upload_progress_t *p, void *ctx)
{
    (void)ctx;
    if (!p) return;
    s_sync_total_files = p->total_files;
    if (p->event == UPLOAD_EVT_START) s_sync_started_us = esp_timer_get_time();
    if (p->event == UPLOAD_EVT_DONE) s_sync_files_done++;
    if (p->event == UPLOAD_EVT_START || p->event == UPLOAD_EVT_PROGRESS || p->event == UPLOAD_EVT_DONE) {
        int pct = p->total_bytes ? (int)((p->sent_bytes * 100U) / p->total_bytes) : 0;
        int64_t elapsed_us = esp_timer_get_time() - s_sync_started_us;
        double elapsed_s = elapsed_us > 0 ? (double)elapsed_us / 1000000.0 : 0.0;
        double bytes_per_s = elapsed_s > 0.5
                           ? (double)p->global_sent / elapsed_s : 0.0;
        char speed[32] = "measuring speed";
        char eta[32] = "calculating";
        if (bytes_per_s > 0.0) {
            if (bytes_per_s >= 1024.0 * 1024.0) {
                snprintf(speed, sizeof(speed), "%.1f MB/s",
                         bytes_per_s / (1024.0 * 1024.0));
            } else {
                snprintf(speed, sizeof(speed), "%.0f KB/s",
                         bytes_per_s / 1024.0);
            }
            double remaining_s = (p->global_total > p->global_sent)
                               ? (double)(p->global_total - p->global_sent) / bytes_per_s
                               : 0.0;
            int remaining_seconds = (int)ceil(remaining_s);
            snprintf(eta, sizeof(eta), "%02d:%02d",
                     remaining_seconds / 60, remaining_seconds % 60);
        }
        int files_remaining = p->total_files - p->file_index;
        if (p->event == UPLOAD_EVT_DONE && files_remaining > 0) files_remaining--;
        ui_show_sync_uploading(p->file_index + 1, p->total_files, p->filename, pct,
                               p->global_sent, p->global_total, files_remaining,
                               speed, eta);
    }
}

static void _sync_heartbeat_cb(network_heartbeat_event_t event, void *ctx)
{
    (void)ctx;
    switch (event) {
    case NETWORK_HEARTBEAT_PINGING:
        ui_sync_heartbeat_pinging();
        break;
    case NETWORK_HEARTBEAT_ACKNOWLEDGED: {
        const int64_t ack_started_us = esp_timer_get_time();
        ui_sync_heartbeat_acknowledged();
        /* Hold the green acknowledgment for about 1.5 seconds, then
         * hand off to the existing upload/preparation screen while the sync
         * worker continues fetching metadata and pending files. */
        vTaskDelay(pdMS_TO_TICKS(1500));
        ESP_LOGI(TAG, "[SYNC] Heartbeat acknowledged; moving to sync preparation (%lld ms)",
                 (long long)((esp_timer_get_time() - ack_started_us) / 1000));
        ui_show_sync_uploading(0, 0, "CHECKING FOR PENDING DATA", 0,
                               0, 0, 0, "waiting", "calculating");
        break;
    }
    case NETWORK_HEARTBEAT_FAILED:
        ui_sync_heartbeat_failed();
        break;
    }
}
#endif

#if !CONFIG_IDF_TARGET_ESP32P4 || CONFIG_ESP_WIFI_REMOTE_ENABLED
static void _sync_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "[SYNC] Worker started");
    s_sync_files_done = 0;
    s_sync_total_files = 0;
    ui_show_sync_heartbeat();
    ESP_LOGI(TAG, "[SYNC] Heartbeat screen rendered; starting network sync");
    bool ok = network_sync_all_with_heartbeat(_sync_progress_cb, NULL,
                                              _sync_heartbeat_cb, NULL);
    ESP_LOGI(TAG, "[SYNC] Network sync returned: %s", ok ? "success" : "failure");
    /* The sync worker may have refreshed or cleared the cached track. Reload
     * through the engine so the next logging session uses the server state. */
    esp_err_t track_reload_ret = track_engine_init();
    ESP_LOGI(TAG, "[SYNC] Active-track cache reload: %s; runtime track='%s'",
             esp_err_to_name(track_reload_ret), track_engine_get_track_name());
    if (ok) {
        s_state = STATE_SYNC_COMPLETE;
        ui_show_sync_complete(s_sync_files_done, 0.0f, 0);
    } else {
        s_state = STATE_HOME_IDLE;
        ui_events_on_navigate_home();
    }
    vTaskDelete(NULL);
}
#endif

#if !CONFIG_IDF_TARGET_ESP32P4 || CONFIG_ESP_WIFI_REMOTE_ENABLED
static void _portal_task(void *arg)
{
    (void)arg;
    esp_err_t ret = network_start_captive_portal(NULL);
    s_portal_task = NULL;

    /* Successful provisioning restarts the device from network.c. A timeout
     * or explicit exit returns here and leaves the rider on the dashboard. */
    if (ret != ESP_OK && s_state == STATE_CAPTIVE_PORTAL) {
        ESP_LOGW(TAG, "Captive portal stopped: %s", esp_err_to_name(ret));
        s_state = STATE_HOME_IDLE;
        _show_home_dashboard();
    }
    vTaskDelete(NULL);
}
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Auto-Copy Check
 * Check if sessions exist on internal flash that need copying to SD.
 * Ported from S3 firmware's sm.has_flash_sessions() logic.
 * ──────────────────────────────────────────────────────────────────────────*/
static bool _has_flash_sessions(void)
{
    return storage_has_flash_sessions();
}

static void _reset_logging_session_ui(void)
{
    feedback_set_state(FEEDBACK_STATE_IDLE);
    ui_hide_sector_flash();
    track_engine_reset_session();
    if (s_track_event_queue) xQueueReset(s_track_event_queue);
}

static void _show_home_dashboard(void)
{
    gps_fix_t gps = {0};
    sensors_get_latest_gps(&gps);
    int store_pct = storage_get_usage_percent();
    if (store_pct < 0) store_pct = 0;
    s_state = STATE_HOME_IDLE;
    ui_show_home(bsp_sdcard_mounted(), sensors_imu_ok(), sensors_gps_ok(),
                 gps.satellites, track_engine_get_track_name(),
                 "V4.2 Dash", store_pct);
}

static void _enter_storage_fault(storage_fault_t fault)
{
    if (fault == STORAGE_FAULT_NONE || s_state == STATE_STORAGE_FAULT) return;

    ESP_LOGE(TAG, "[STORAGE] Logging stopped: %s", storage_fault_name(fault));
    sensors_set_logging(false);

    storage_session_info_t session = {0};
    storage_get_session_info(&session);
    if (session.active) {
        (void)storage_session_stop();
    }

    _reset_logging_session_ui();
    s_state = STATE_STORAGE_FAULT;
    ui_show_storage_fault(fault);
}

/* ──────────────────────────────────────────────────────────────────────────
 * Application State Machine UI Event Listener
 * ──────────────────────────────────────────────────────────────────────────*/
static void _on_ui_event_cb(ui_event_type_t event, void *param)
{
    ESP_LOGI(TAG, "System event listener triggered: ID=%d", (int)event);
    gps_fix_t gps_cur = {0};
    sensors_get_latest_gps(&gps_cur);

    switch (event) {
        case UI_EVENT_START_LOG_CLICKED: {
            ESP_LOGI(TAG, "[NAV] Opening telemetry session");
            esp_err_t session_ret = storage_session_start();
            if (session_ret != ESP_OK) {
                ESP_LOGE(TAG, "[NAV] Cannot start logging session: %s",
                         esp_err_to_name(session_ret));
                storage_fault_t fault = storage_get_fault();
                if (fault != STORAGE_FAULT_NONE) {
                    _enter_storage_fault(fault);
                } else {
                    _show_home_dashboard();
                }
                break;
            }

            ESP_LOGI(TAG, "[NAV] Transitioning to LIVE LOGGING (Screen 3)");
            track_engine_reset_session();
            if (s_track_event_queue) xQueueReset(s_track_event_queue);
            s_track_events_dropped = 0;
            s_state = STATE_LOGGING_ACTIVE;
            ui_show_logging(track_engine_get_track_name(), gps_cur.satellites);
            feedback_set_state(FEEDBACK_STATE_LOGGING);
            sensors_set_logging(true);
            break;
        }

        case UI_EVENT_TRACK_VIEW_CLICKED:
            ESP_LOGI(TAG, "[NAV] Opening ACTIVE TRACK viewer");
            s_state = STATE_TRACK_VIEW;
            ui_show_track_view();
            break;

        case UI_EVENT_TRACK_SELECT_CLICKED:
            ESP_LOGI(TAG, "[NAV] Opening CACHED TRACK selector");
            s_state = STATE_TRACK_SELECTOR;
            ui_show_track_selector();
            break;

        case UI_EVENT_TRACK_SELECTED: {
            int32_t track_id = (int32_t)(intptr_t)param;
            ESP_LOGI(TAG, "[NAV] Selecting cached track %ld", (long)track_id);
            esp_err_t select_ret = network_select_cached_track(track_id);
            if (select_ret == ESP_OK) {
                esp_err_t load_ret = track_engine_load_track(NULL);
                ui_track_refresh_layout();
                ESP_LOGI(TAG, "[NAV] Cached track reload: %s; active='%s'",
                         esp_err_to_name(load_ret), track_engine_get_track_name());
                if (load_ret != ESP_OK) {
                    ESP_LOGW(TAG, "[NAV] Track file was selected but could not be loaded");
                }
            } else {
                ESP_LOGW(TAG, "[NAV] Cached track selection failed: %s",
                         esp_err_to_name(select_ret));
            }
            _show_home_dashboard();
            break;
        }

        case UI_EVENT_STOP_LOG_HELD:
        case UI_EVENT_BACK_CLICKED:
        case UI_EVENT_SYNC_CANCEL_CLICKED:
        case UI_EVENT_SYNC_DONE_CLICKED: {
            if (s_state == STATE_CAPTIVE_PORTAL) {
                ESP_LOGI(TAG, "[NAV] Stopping captive portal and returning HOME");
                network_stop_captive_portal();
            }
            if (s_state == STATE_STORAGE_FAULT) {
                ESP_LOGI(TAG, "[NAV] Storage fault acknowledged; returning home");
                storage_clear_fault();
                _show_home_dashboard();
                break;
            }

            ESP_LOGI(TAG, "[NAV] Returning to HOME DASHBOARD (Screen 2)");
            if (s_state == STATE_LOGGING_ACTIVE || s_state == STATE_IMU_VALIDATION) {
                sensors_set_logging(false);
                esp_err_t session_ret = storage_session_stop();
                storage_fault_t fault = storage_get_fault();
                if (session_ret != ESP_OK || fault != STORAGE_FAULT_NONE) {
                    ESP_LOGE(TAG, "[NAV] Logging session closed with storage error: %s",
                             fault != STORAGE_FAULT_NONE
                                 ? storage_fault_name(fault)
                                 : esp_err_to_name(session_ret));
                    _enter_storage_fault(fault != STORAGE_FAULT_NONE
                                             ? fault : STORAGE_FAULT_DRAIN_TIMEOUT);
                    break;
                }
                _reset_logging_session_ui();
            }
            _show_home_dashboard();
            break;
        }

        case UI_EVENT_SYNC_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to CLOUD SYNC / WIFI SEARCH (Screen 6)");
            s_state = STATE_SYNC_WIFI_SEARCH;
            ui_show_sync_searching("RaceSense_AP");
#if !CONFIG_IDF_TARGET_ESP32P4 || CONFIG_ESP_WIFI_REMOTE_ENABLED
            xTaskCreate(_sync_task, "racesense_sync", 16384, NULL, 4, NULL);
#else
            /* Fallback for builds that intentionally disable hosted Wi-Fi. */
            ESP_LOGW(TAG, "Cloud sync unavailable: ESP32-C6 transport disabled");
#endif
            break;

        case UI_EVENT_SETTINGS_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to SETTINGS (Screen 10)");
            s_state = STATE_SETTINGS;
            ui_show_settings();
            break;

        case UI_EVENT_HARDWARE_DEBUG_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to HARDWARE DEBUG (Screen 13)");
            s_state = STATE_HARDWARE_DEBUG;
            ui_show_hardware_debug();
            break;

        case UI_EVENT_DATA_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to DATA / pending files (Screen 16)");
            s_state = STATE_DATA;
            /* Defer LVGL screen construction until the application loop.  The
             * event arrives from the LVGL touch callback; building a composed
             * screen there can starve the input handler long enough to look
             * like a frozen device. */
            s_data_screen_pending = true;
            break;

        case UI_EVENT_IMU_CALIB_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to IMU CALIBRATION WIZARD (Screen 11)");
            s_state = STATE_IMU_CALIBRATION;
            ui_show_imu_calibration_wizard();
            break;

        case UI_EVENT_WIFI_SETUP_CLICKED: {
            ESP_LOGI(TAG, "[NAV] Transitioning to CAPTIVE PORTAL (Screen 12)");
            s_state = STATE_CAPTIVE_PORTAL;
            char ap_name[32] = {0};
            network_get_ap_name(ap_name, sizeof(ap_name));
            ui_show_captive_portal(ap_name);
#if !CONFIG_IDF_TARGET_ESP32P4 || CONFIG_ESP_WIFI_REMOTE_ENABLED
            if (s_portal_task == NULL &&
                xTaskCreate(_portal_task, "racesense_portal", 8192, NULL, 4,
                            &s_portal_task) != pdPASS) {
                ESP_LOGE(TAG, "Unable to create captive-portal task");
                s_state = STATE_HOME_IDLE;
                _show_home_dashboard();
            }
#else
            /* Fallback for builds that intentionally disable hosted Wi-Fi. */
            ESP_LOGW(TAG, "Captive portal unavailable: ESP32-C6 transport disabled");
#endif
            break;
        }

        default:
            ESP_LOGD(TAG, "[NAV] Event %d ignored by top-level state machine", (int)event);
            break;
    }
}

/* ──────────────────────────────────────────────────────────────────────────
 * NVS Init
 * ──────────────────────────────────────────────────────────────────────────*/
static esp_err_t _nvs_init(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition needs erase (reason: %s)", esp_err_to_name(ret));
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    return ret;
}

/* ──────────────────────────────────────────────────────────────────────────
 * Application Entry Point
 * ──────────────────────────────────────────────────────────────────────────*/
void app_main(void)
{
    const esp_app_desc_t *app_desc = esp_app_get_description();
    ESP_LOGI(TAG, "╔══════════════════════════════════════════╗");
    ESP_LOGI(TAG, "║   RaceSense ESP32-P4 Firmware %s   ║", app_desc->version);
    ESP_LOGI(TAG, "║   Waveshare ESP32-P4-WIFI6-LCD-4.3     ║");
    ESP_LOGI(TAG, "╚══════════════════════════════════════════╝");

    /* ── Step 1: NVS (required before any config read) ─────────────────── */
    ESP_ERROR_CHECK(_nvs_init());
    ESP_LOGI(TAG, "[BOOT] NVS initialized");

    /* ── Step 2: Early display/UI ───────────────────────────────────────── */
    /* Bring up the panel and show the splash before SD, network, storage,
     * and sensor initialization. Those subsystems continue below while the
     * rider already has branded visual feedback. */
    ESP_ERROR_CHECK(bsp_display_init());
    esp_err_t ret = ui_init();
    bool ui_ready = ret == ESP_OK;
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "UI init failed: %s", esp_err_to_name(ret));
        bsp_display_backlight_on();
    } else {
        ui_events_register_listener(_on_ui_event_cb);
        ui_show_boot_splash();
        bsp_display_backlight_on();
    }

    /* ── Step 3: Board Support Package ─────────────────────────────────── */
    /* Initializes: Battery ADC → SD card → display (already ready) → touch */
    ESP_ERROR_CHECK(bsp_init());
    if (bsp_sdcard_mounted()) {
        esp_err_t sd_validation = bsp_sdcard_validate();
        ESP_LOGI(TAG, "[BOOT] SD hardware validation: %s",
                 sd_validation == ESP_OK ? "PASS" : "FAIL");
        uint64_t sd_total = 0;
        uint64_t sd_free = 0;
        esp_err_t space_ret = bsp_sdcard_get_space_bytes(&sd_total, &sd_free);
        ESP_LOGI(TAG, "[BOOT] SD space: %s total=%llu bytes (%.2f GiB) free=%llu bytes (%.2f GiB)",
                 esp_err_to_name(space_ret), (unsigned long long)sd_total,
                 (double)sd_total / (1024.0 * 1024.0 * 1024.0),
                 (unsigned long long)sd_free,
                 (double)sd_free / (1024.0 * 1024.0 * 1024.0));
    }
    ESP_ERROR_CHECK(network_init());
#if CONFIG_RS_NETWORK_SELF_TEST
    uint16_t network_ap_count = 0;
    esp_err_t network_scan_ret = network_wifi_scan(&network_ap_count);
    ESP_LOGI(TAG, "[BOOT] Hosted Wi-Fi scan self-test: %s (%u APs)",
             esp_err_to_name(network_scan_ret), network_ap_count);
#endif

    /* ── Step 4: Storage engine ────────────────────────────────── */
    /* Must init before auto-copy check and before sensor task.        */
    ESP_ERROR_CHECK(storage_init());
    ESP_LOGI(TAG, "[BOOT] Storage engine ready");
    _log_provisioning_status();

    /* ── Step 5: Log boot health summary ───────────────────────────────── */
    bsp_battery_state_t bat;
    bsp_battery_get_state(&bat);
    ESP_LOGI(TAG, "[BOOT] Battery: %.2fV / %d%% / %s",
             bat.filtered_v, bat.percent,
             bat.charging ? "charging" : "on battery");
    ESP_LOGI(TAG, "[BOOT] SD card: %s",
             bsp_sdcard_mounted() ? "mounted at /sd" : "NOT present");

    /* ── Step 6: Auto-Copy check ────────────────────────────────────────── */
    /* If SD is mounted AND flash sessions exist → copy then reboot        */
    if (bsp_sdcard_mounted() && _has_flash_sessions()) {
        ESP_LOGI(TAG, "[BOOT] Flash sessions detected — entering AUTO_COPY");
        s_state = STATE_AUTO_COPY;
    } else {
        s_state = STATE_HOME_IDLE;
        ESP_LOGI(TAG, "[BOOT] Entering HOME_IDLE");
    }

    /* ── Step 7: Track timing and sensor ingestion ──────────────────────── */
    s_track_event_queue = xQueueCreate(TRACK_EVENT_QUEUE_DEPTH, sizeof(track_event_t));
    if (!s_track_event_queue) {
        ESP_LOGE(TAG, "Track event queue allocation failed — timing disabled");
    } else {
        esp_err_t track_ret = track_engine_init();
        if (track_ret != ESP_OK) {
            ESP_LOGW(TAG, "Track engine init failed: %s", esp_err_to_name(track_ret));
        }
        track_engine_set_event_cb(_track_event_cb, NULL);
    }
    ret = feedback_init();
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Feedback init failed: %s", esp_err_to_name(ret));
    }

    /* Sensor task runs on Core 0 at 100Hz IMU / 10Hz GPS. */
    ret = sensors_task_start();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Sensor task start failed: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "[BOOT] Sensor task running: 100Hz IMU | 10Hz GPS");
    }

    /* ── Step 8: Complete the first visible boot flow ──────────────────── */
    if (ui_ready && s_state == STATE_HOME_IDLE) {
        bool touch_calibrating = touch_calibration_start_if_needed();
        if (touch_calibrating) {
            /* Calibration owns the first visible screen on a fresh unit. */
        } else {
            vTaskDelay(pdMS_TO_TICKS(1800));
            gps_fix_t gps_init = {0};
            sensors_get_latest_gps(&gps_init);
            int store_pct = storage_get_usage_percent();
            if (store_pct < 0) store_pct = 0;
            ui_show_home(bsp_sdcard_mounted(), sensors_imu_ok(), sensors_gps_ok(),
                         gps_init.satellites, track_engine_get_track_name(),
                         "V4.2 Dash", store_pct);
        }
    }

#if CONFIG_RS_NETWORK_SYNC_SELF_TEST
    xTaskCreate(_network_sync_probe_task, "network_probe",
                NETWORK_PROBE_TASK_STACK_SIZE, NULL, 4, NULL);
#endif

    /* ════════════════════════════════════════════════════════════════════
    * Main State Machine Loop
     * Runs on Core 1 (app_main stack). Core 0 will run sensor tasks.
     * ════════════════════════════════════════════════════════════════════*/
    while (1) {
        if ((s_state == STATE_LOGGING_ACTIVE || s_state == STATE_IMU_VALIDATION) &&
            storage_get_fault() != STORAGE_FAULT_NONE) {
            _enter_storage_fault(storage_get_fault());
        }
        _process_track_events();
        feedback_tick();
        static int64_t last_health_log_us;
        int64_t now_us = esp_timer_get_time();
        if (now_us - last_health_log_us >= 2000000) {
            bsp_battery_state_t hw_bat;
            bsp_battery_update(&hw_bat);

            gps_health_t gps_health = {0};
            gps_fix_t gps_fix = {0};
            char last_nmea[128] = {0};
            gps_get_health(&gps_health);
            gps_get_fix(&gps_fix);
            gps_get_last_nmea(last_nmea, sizeof(last_nmea));

            bmi323_raw_t imu_raw = {0};
            bmi323_data_t imu_si = {0};
            sensors_get_latest_imu(&imu_raw);
            bmi323_raw_to_si(&imu_raw, &imu_si);

            ESP_LOGI(TAG, "health: state=%d heap=%u psram=%u",
                     (int)s_state,
                     (unsigned)esp_get_free_heap_size(),
                     (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
            sensors_queue_stats_t queue_stats = {0};
            sensors_get_queue_stats(&queue_stats);
            ESP_LOGI(TAG, "[HW] Rows: enqueued=%lu dropped=%lu max_depth=%lu pending=%lu producer=%s",
                     (unsigned long)queue_stats.rows_enqueued,
                     (unsigned long)queue_stats.rows_dropped,
                     (unsigned long)queue_stats.max_depth,
                     (unsigned long)queue_stats.pending_rows,
                     queue_stats.producer_active ? "active" : "idle");
            ESP_LOGI(TAG, "[HW] ADC GPIO%d: raw=%.3fV filtered=%.3fV pct=%d",
                     BSP_PIN_BATTERY_ADC, hw_bat.raw_v, hw_bat.filtered_v, hw_bat.percent);
            ESP_LOGI(TAG, "[HW] SD: %s usage=%d%%",
                     bsp_sdcard_mounted() ? "mounted" : "not-mounted",
                     bsp_sdcard_get_usage_percent());
            ESP_LOGI(TAG, "[HW] GPS UART1 GPIO%d->RX/GPIO%d<-TX: lines=%lu RMC=%lu GGA=%lu rate=%.2fHz period=%.0fms[%lu..%lu] ACK=%lu/%lu checksum_fail=%lu fix=%s sats=%d lat=%.6f lon=%.6f last=%s",
                     GPS_PIN_TX, GPS_PIN_RX,
                     (unsigned long)gps_health.lines_processed,
                     (unsigned long)gps_health.rmc_received,
                     (unsigned long)gps_health.gga_received,
                     gps_health.rmc_rate_hz, gps_health.rmc_period_avg_ms,
                     (unsigned long)gps_health.rmc_period_min_ms,
                     (unsigned long)gps_health.rmc_period_max_ms,
                     (unsigned long)gps_health.ubx_ack_ok,
                     (unsigned long)gps_health.ubx_ack_fail,
                     (unsigned long)gps_health.checksum_failures,
                     gps_fix.valid ? "valid" : "invalid", gps_fix.satellites,
                     gps_fix.lat, gps_fix.lon,
                     last_nmea[0] ? last_nmea : "<none>");
            ESP_LOGI(TAG, "[HW] BMI323 I2C1 SDA=%d SCL=%d addr=0x%02X init=%s raw=[%d,%d,%d,%d,%d,%d] si=[%.3f,%.3f,%.3f g; %.3f,%.3f,%.3f dps]",
                     BSP_PIN_BMI323_SDA, BSP_PIN_BMI323_SCL, bmi323_get_i2c_address(),
                     sensors_imu_ok() ? "ok" : "failed",
                     imu_raw.ax, imu_raw.ay, imu_raw.az,
                     imu_raw.gx, imu_raw.gy, imu_raw.gz,
                     imu_si.ax, imu_si.ay, imu_si.az,
                     imu_si.gx, imu_si.gy, imu_si.gz);
            last_health_log_us = now_us;
        }
        switch (s_state) {

            case STATE_AUTO_COPY:
                /* Copy flash sessions to SD, then reboot cleanly */
                ESP_LOGI(TAG, "AUTO_COPY: moving flash sessions to SD...");
                if (storage_move_flash_to_sd()) {
                    ESP_LOGI(TAG, "AUTO_COPY: complete — rebooting");
                    vTaskDelay(pdMS_TO_TICKS(500));
                    esp_restart();
                } else {
                    ESP_LOGW(TAG, "AUTO_COPY: nothing moved or failed");
                    s_state = STATE_HOME_IDLE;
                }
                break;

            case STATE_HOME_IDLE: {
                /* Sample live sensor and storage metrics at 2Hz for zero-flicker UI updates */
                bsp_battery_state_t bat_live;
                bsp_battery_get_state(&bat_live);

                gps_fix_t gps_live = {0};
                sensors_get_latest_gps(&gps_live);

                int live_store = storage_get_usage_percent();
                if (live_store < 0) live_store = 0;

                ui_home_update(bsp_sdcard_mounted(),
                               sensors_imu_ok(),
                               sensors_gps_ok(),
                               gps_live.satellites,
                               bat_live.percent,
                               live_store,
                               track_engine_get_track_name());

                vTaskDelay(pdMS_TO_TICKS(500));
                break;
            }

            case STATE_TRACK_VIEW: {
                gps_fix_t gps_live = {0};
                sensors_get_latest_gps(&gps_live);
                ui_track_update_position(gps_live.lat, gps_live.lon, gps_live.valid);
                vTaskDelay(pdMS_TO_TICKS(100));
                break;
            }

            case STATE_LOGGING_ACTIVE:
            case STATE_IMU_VALIDATION: {
                /* Sensor task on Core 0 pushes rows into storage queue.
                 * Storage flush task on Core 1 drains and writes to SD.   */
                if (s_state == STATE_LOGGING_ACTIVE) {
                    gps_fix_t gps_live = {0};
                    sensors_get_latest_gps(&gps_live);
                    bmi323_raw_t imu_live = {0};
                    sensors_get_latest_imu(&imu_live);

                    /* Compute lean angle estimate from accel Y/Z for live display */
                    float ay = imu_live.ay / 8192.0f;
                    float az = imu_live.az / 8192.0f;
                    float lean_est = (az != 0.0f) ? (ay / az) * 57.2958f : 0.0f;
                    char side = (lean_est < 0) ? 'R' : 'L';
                    if (lean_est < 0) lean_est = -lean_est;

                    char time_buf[32];
                    track_engine_get_current_lap_time(sensors_get_tick_ms(),
                                                      time_buf, sizeof(time_buf));

                    float timing_delta = track_engine_get_last_delta_s();
                    char delta_buf[32];
                    if (track_engine_is_track_found()) {
                        _format_timing_delta(timing_delta, delta_buf, sizeof(delta_buf));
                    } else {
                        snprintf(delta_buf, sizeof(delta_buf), "Δ --");
                    }
                    ui_logging_update_lap(time_buf, delta_buf,
                                          track_engine_is_track_found() && timing_delta <= 0.0f,
                                          track_engine_get_current_lap_number());
                    ui_logging_update_lean(lean_est, side);
                }
                vTaskDelay(pdMS_TO_TICKS(100)); /* 10Hz live dashboard update rate */
                break;
            }

            case STATE_STORAGE_FAULT:
                /* Await the rider's acknowledgement on the fault screen. */
                vTaskDelay(pdMS_TO_TICKS(100));
                break;

            case STATE_HARDWARE_DEBUG:
                ui_hardware_debug_update();
                vTaskDelay(pdMS_TO_TICKS(50));
                break;

            case STATE_DATA:
                if (s_data_screen_pending) {
                    s_data_screen_pending = false;
                    ui_show_data();
                }
                ui_data_update();
                vTaskDelay(pdMS_TO_TICKS(100));
                break;

            case STATE_SECTOR_FLASH:
                /* TODO Phase 8: Brief full-screen color overlay (3s).     */
                vTaskDelay(pdMS_TO_TICKS(33));
                break;

            case STATE_SYNC_WIFI_SEARCH:
            case STATE_SYNC_HEARTBEAT:
            case STATE_SYNC_UPLOADING:
            case STATE_SYNC_COMPLETE:
                /* Network workers own the blocking sync phases. */
                vTaskDelay(pdMS_TO_TICKS(100));
                break;

            case STATE_SETTINGS:
            case STATE_IMU_CALIBRATION:
            case STATE_TRACK_SELECTOR:
            case STATE_CAPTIVE_PORTAL:
                /* TODO Phase 7C/8: Settings sub-screens, calibration, portal */
                vTaskDelay(pdMS_TO_TICKS(100));
                break;

            case STATE_SHUTDOWN:
                ESP_LOGI(TAG, "Shutdown requested — unmounting SD and releasing power rail...");
                bsp_sdcard_deinit();
                vTaskDelay(pdMS_TO_TICKS(200));
                bsp_power_hold_release();
                vTaskDelay(pdMS_TO_TICKS(100));
                esp_restart();
                break;

            default:
                s_state = STATE_HOME_IDLE;
                break;
        }
    }
}
