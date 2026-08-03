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
#include <sys/stat.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
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

static const char *TAG = "racesense";

/* ──────────────────────────────────────────────────────────────────────────
 * Application States  (maps 1:1 to the UI screens)
 * ──────────────────────────────────────────────────────────────────────────*/
typedef enum {
    STATE_BOOT_INIT,         /* Screen 1:  Boot splash               */
    STATE_AUTO_COPY,         /* Internal:  Flash → SD session copy    */
    STATE_HOME_IDLE,         /* Screen 2:  Home                      */
    STATE_LOGGING_ACTIVE,    /* Screen 3:  Live Logging              */
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
    STATE_SHUTDOWN,          /* Internal:  Clean shutdown            */
} app_state_t;

static volatile app_state_t s_state = STATE_BOOT_INIT;
static volatile int s_sync_files_done;
static volatile int s_sync_total_files;

#if !CONFIG_IDF_TARGET_ESP32P4
static void _sync_progress_cb(const upload_progress_t *p, void *ctx)
{
    (void)ctx;
    if (!p) return;
    s_sync_total_files = p->total_files;
    if (p->event == UPLOAD_EVT_DONE) s_sync_files_done++;
    if (p->event == UPLOAD_EVT_START || p->event == UPLOAD_EVT_PROGRESS || p->event == UPLOAD_EVT_DONE) {
        int pct = p->total_bytes ? (int)((p->sent_bytes * 100U) / p->total_bytes) : 0;
        ui_show_sync_uploading(p->file_index, p->total_files, p->filename, pct,
                               p->detail ? p->detail : "Uploading", "");
    }
}
#endif

#if !CONFIG_IDF_TARGET_ESP32P4
static void _sync_task(void *arg)
{
    (void)arg;
    s_sync_files_done = 0;
    s_sync_total_files = 0;
    ui_show_sync_heartbeat();
    bool ok = network_sync_all(_sync_progress_cb, NULL);
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

/* ──────────────────────────────────────────────────────────────────────────
 * Auto-Copy Check
 * Check if sessions exist on internal flash that need copying to SD.
 * Ported from S3 firmware's sm.has_flash_sessions() logic.
 * ──────────────────────────────────────────────────────────────────────────*/
static bool _has_flash_sessions(void)
{
    return storage_has_flash_sessions();
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
        case UI_EVENT_START_LOG_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to LIVE LOGGING (Screen 3)");
            s_state = STATE_LOGGING_ACTIVE;
            /* Present the new screen before potentially slow filesystem work
             * so the touch transition never visibly stalls or flashes. */
            ui_show_logging("Silverstone", gps_cur.satellites);
            storage_session_start();
            sensors_set_logging(true);
            break;

        case UI_EVENT_STOP_LOG_HELD:
        case UI_EVENT_BACK_CLICKED:
        case UI_EVENT_SYNC_CANCEL_CLICKED:
        case UI_EVENT_SYNC_DONE_CLICKED:
            ESP_LOGI(TAG, "[NAV] Returning to HOME DASHBOARD (Screen 2)");
            bool close_logging_session = (s_state == STATE_LOGGING_ACTIVE ||
                                          s_state == STATE_IMU_VALIDATION);
            if (s_state == STATE_LOGGING_ACTIVE || s_state == STATE_IMU_VALIDATION) {
                sensors_set_logging(false);
            }
            s_state = STATE_HOME_IDLE;
            int store_pct = storage_get_usage_percent();
            if (store_pct < 0) store_pct = 0;
            ui_show_home(bsp_sdcard_mounted(), sensors_imu_ok(), sensors_gps_ok(),
                         gps_cur.satellites, "Silverstone", "V4.2 Dash", store_pct);
            if (close_logging_session) {
                storage_session_stop();
            }
            break;

        case UI_EVENT_SYNC_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to CLOUD SYNC / WIFI SEARCH (Screen 6)");
            s_state = STATE_SYNC_WIFI_SEARCH;
            ui_show_sync_searching("RaceSense_AP");
#if !CONFIG_IDF_TARGET_ESP32P4
            xTaskCreate(_sync_task, "racesense_sync", 8192, NULL, 4, NULL);
#else
            /* The Waveshare C6 co-processor transport is not configured yet.
             * Keep the informative Sync screen open instead of immediately
             * failing the task and bouncing the user back to Home. */
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

        case UI_EVENT_IMU_CALIB_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to IMU CALIBRATION WIZARD (Screen 11)");
            s_state = STATE_IMU_CALIBRATION;
            ui_show_imu_calibration_wizard();
            break;

        case UI_EVENT_WIFI_SETUP_CLICKED:
            ESP_LOGI(TAG, "[NAV] Transitioning to CAPTIVE PORTAL (Screen 12)");
            s_state = STATE_CAPTIVE_PORTAL;
            ui_show_captive_portal("RaceSense_Setup");
            break;

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
    ESP_LOGI(TAG, "╔══════════════════════════════════════════╗");
    ESP_LOGI(TAG, "║   RaceSense ESP32-P4 Firmware  v0.1.0  ║");
    ESP_LOGI(TAG, "║   Waveshare ESP32-P4-WIFI6-LCD-4.3     ║");
    ESP_LOGI(TAG, "╚══════════════════════════════════════════╝");

    /* ── Step 1: NVS (required before any config read) ─────────────────── */
    ESP_ERROR_CHECK(_nvs_init());
    ESP_LOGI(TAG, "[BOOT] NVS initialized");

    /* ── Step 2: Board Support Package ─────────────────────────────────── */
    /* Initializes: Battery ADC → SD card → display → touch                */
    ESP_ERROR_CHECK(bsp_init());
    if (bsp_sdcard_mounted()) {
        esp_err_t sd_validation = bsp_sdcard_validate();
        ESP_LOGI(TAG, "[BOOT] SD hardware validation: %s",
                 sd_validation == ESP_OK ? "PASS" : "FAIL");
    }
    ESP_ERROR_CHECK(network_init());

    /* ── Step 3: Storage engine ────────────────────────────────── */
    /* Must init before auto-copy check and before sensor task.        */
    ESP_ERROR_CHECK(storage_init());
    ESP_LOGI(TAG, "[BOOT] Storage engine ready");

    /* ── Step 4: Log boot health summary ───────────────────────────────── */
    bsp_battery_state_t bat;
    bsp_battery_get_state(&bat);
    ESP_LOGI(TAG, "[BOOT] Battery: %.2fV / %d%% / %s",
             bat.filtered_v, bat.percent,
             bat.charging ? "charging" : "on battery");
    ESP_LOGI(TAG, "[BOOT] SD card: %s",
             bsp_sdcard_mounted() ? "mounted at /sd" : "NOT present");

    /* ── Step 5: Auto-Copy check ────────────────────────────────────────── */
    /* If SD is mounted AND flash sessions exist → copy then reboot        */
    if (bsp_sdcard_mounted() && _has_flash_sessions()) {
        ESP_LOGI(TAG, "[BOOT] Flash sessions detected — entering AUTO_COPY");
        s_state = STATE_AUTO_COPY;
    } else {
        s_state = STATE_HOME_IDLE;
        ESP_LOGI(TAG, "[BOOT] Entering HOME_IDLE");
    }

    /* ── Step 5: Sensor ingestion task (Core 0, 100Hz IMU / 10Hz GPS) ───── */
    esp_err_t ret = sensors_task_start();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Sensor task start failed: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "[BOOT] Sensor task running: 100Hz IMU | 10Hz GPS");
    }

    /* ── Step 6: UI init ───────────────────────────────────────────────── */
    ret = ui_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "UI init failed: %s", esp_err_to_name(ret));
    } else if (s_state == STATE_HOME_IDLE && !touch_calibration_start_if_needed()) {
        ESP_LOGI(TAG, "[BOOT] Showing RaceSense splash before dashboard");
        ui_events_register_listener(_on_ui_event_cb);
        ui_show_boot_splash();
        vTaskDelay(pdMS_TO_TICKS(1800));
        gps_fix_t gps_init = {0};
        sensors_get_latest_gps(&gps_init);
        int store_pct = storage_get_usage_percent();
        if (store_pct < 0) store_pct = 0;
        ui_show_home(bsp_sdcard_mounted(), sensors_imu_ok(), sensors_gps_ok(),
                     gps_init.satellites, "Silverstone", "V4.2 Dash", store_pct);
    }

    /* ════════════════════════════════════════════════════════════════════
     * Main State Machine Loop
     * Runs on Core 1 (app_main stack). Core 0 will run sensor tasks.
     * ════════════════════════════════════════════════════════════════════*/
    while (1) {
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
                               "Silverstone");

                vTaskDelay(pdMS_TO_TICKS(500));
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
                    uint32_t elapsed_sec = sensors_get_tick_ms() / 1000;
                    snprintf(time_buf, sizeof(time_buf), "%lu:%02lu.%03lu",
                             (unsigned long)(elapsed_sec / 60),
                             (unsigned long)(elapsed_sec % 60),
                             (unsigned long)(sensors_get_tick_ms() % 1000));

                    char speed_buf[32];
                    snprintf(speed_buf, sizeof(speed_buf), "SPD: %.1f km/h", gps_live.speed_kmh);

                    ui_logging_update_lap(time_buf, speed_buf, true, 1);
                    ui_logging_update_lean(lean_est, side);
                }
                vTaskDelay(pdMS_TO_TICKS(100)); /* 10Hz live dashboard update rate */
                break;
            }

            case STATE_HARDWARE_DEBUG:
                ui_hardware_debug_update();
                vTaskDelay(pdMS_TO_TICKS(50));
                break;

            case STATE_SECTOR_FLASH:
                /* TODO Phase 8: Brief full-screen color overlay (3s).     */
                vTaskDelay(pdMS_TO_TICKS(33));
                break;

            case STATE_SYNC_WIFI_SEARCH:
            case STATE_SYNC_HEARTBEAT:
            case STATE_SYNC_UPLOADING:
            case STATE_SYNC_COMPLETE:
                /* TODO Phase 7D: WiFi 6 (esp-hosted), heartbeat, uploader */
                vTaskDelay(pdMS_TO_TICKS(100));
                break;

            case STATE_SETTINGS:
            case STATE_IMU_CALIBRATION:
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
