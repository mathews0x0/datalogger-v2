/**
 * @file ui.h
 * @brief Complete Adaptive LVGL UI Screens & Driver Abstraction Header
 *
 * Covers all 12 screen constructors across Waves 1 through 4, supporting
 * multi-resolution adaptive layouts and decoupled touch event dispatching.
 */

#ifndef UI_H
#define UI_H

#include "lvgl.h"

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "ui_layout.h"
#include "ui_events.h"
#include "ui_theme.h"
#include "storage.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Core UI Initialization & Driver Registration
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Initialize LVGL engine and register target-specific hardware drivers:
 *        - ESP32-P4 Widescreen: ST7701 MIPI-DSI display + GT911 touch controller
 *        - ESP32-S3 / Compact: ILI9488/ILI9341 SPI/RGB + touch controller
 *
 * @return ESP_OK on success.
 */
esp_err_t ui_init(void);

/**
 * @brief Acquire UI thread lock (for modifying LVGL elements outside UI task).
 * @param timeout_ms Maximum wait time in milliseconds (-1 for infinite).
 * @return true if lock acquired successfully.
 */
bool ui_lock(int timeout_ms);

/**
 * @brief Release UI thread lock.
 */
void ui_unlock(void);

/** Load a replacement screen and immediately free the previous screen tree.
 * Call while holding the UI lock. */
void ui_load_screen(lv_obj_t *screen);
void ui_load_screen_smooth(lv_obj_t *screen);

/* ──────────────────────────────────────────────────────────────────────────
 * Wave 1: Boot & Home Screen Constructors (ui_home.c)
 * ────────────────────────────────────────────────────────────────────────*/

/** @brief Screen 1: Show animated Boot Splash loading screen. */
void ui_show_boot_splash(void);

/**
 * @brief Screen 2: Show Home Dashboard landing page with interactive touch dock.
 * @param sd_ok True if SD card is correctly mounted.
 * @param imu_ok True if IMU is responsive at 100Hz.
 * @param gps_ok True if GPS has valid position fix.
 * @param sats Number of visible locked GPS satellites.
 * @param track_name Selected racing circuit name string.
 * @param mount_label Active IMU motorcycle mounting configuration name.
 * @param storage_pct Storage filesystem occupancy percentage (0-100).
 */
void ui_show_home(bool sd_ok, bool imu_ok, bool gps_ok, int sats,
                  const char *track_name, const char *mount_label, int storage_pct);

/** Stop periodic Home-screen updates before replacing the Home screen. */
void ui_home_deactivate(void);

/**
 * @brief Update Home Dashboard widget indicators with live sensor and system telemetry.
 * @param sd_ok True if SD card is correctly mounted.
 * @param imu_ok True if IMU is responsive and operational at 100Hz.
 * @param gps_ok True if GPS has valid 3D position fix.
 * @param sats Number of visible locked GPS satellites.
 * @param bat_pct Battery charge percentage (0-100).
 * @param storage_pct Storage filesystem occupancy percentage (0-100).
 * @param track_name Selected racing circuit name string.
 */
void ui_home_update(bool sd_ok, bool imu_ok, bool gps_ok, int sats, int bat_pct,
                    int storage_pct, const char *track_name);

/** Render the compact active-track preview inside a Home card. */
void ui_track_preview_render(lv_obj_t *parent, int x, int y, int width, int height);

/** Screen 15: Full-screen active-track map and TBL information viewer. */
void ui_show_track_view(void);

/** Update the rider marker while the full-screen map is visible. */
void ui_track_update_position(double lat, double lon, bool valid);

/** Stop track-view updates before another screen replaces the root. */
void ui_track_view_deactivate(void);

/* ──────────────────────────────────────────────────────────────────────────
 * Wave 2: Telemetry & Trackside Feedback (ui_logging.c)
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Screen 3: Show v4 Full-Width Hero Live Logging cockpit display.
 * @param track_name Current circuit name.
 * @param sats Current satellite count.
 */
void ui_show_logging(const char *track_name, int sats);

/**
 * @brief Update hero lap timer on Live Logging cockpit (Core 0 / Track Engine loop).
 * @param lap_time Formatted lap time string (e.g. "1:53.120").
 * @param delta Formatted lap delta vs reference TBL (e.g. "Δ -0.48s").
 * @param faster True if lap is currently ahead of TBL reference.
 * @param lap_count Completed lap counter integer.
 */
void ui_logging_update_lap(const char *lap_time, const char *delta, bool faster, int lap_count);

/**
 * @brief Update live lean angle arc widget on logging cockpit (30Hz stream).
 * @param angle_deg Lean angle in degrees.
 * @param side Lean side indicator ('L' for left, 'R' for right, '-' for vertical).
 */
void ui_logging_update_lean(float angle_deg, char side);

/** @brief Screen 4: Show 5-second IMU Validation overlay at log initiation. */
void ui_show_imu_validation(void);

/**
 * @brief Screen 5: Trigger 3-second trackside Sector Crossing Flash feedback overlay.
 * @param sector_num Sector sequence number (1, 2, 3...).
 * @param delta Sector completion delta string.
 * @param faster True if personal best sector achieved.
 * @param sector_time Elapsed duration in current sector.
 * @param tbl_time Theoretical best lap reference time for sector.
 */
void ui_show_sector_flash(int sector_num, const char *delta, bool faster,
                          const char *sector_time, const char *tbl_time);

/** Hide the active sector/lap feedback overlay, if one is visible. */
void ui_hide_sector_flash(void);

/** @brief Screen 14: Explain why logging stopped after a storage fault. */
void ui_show_storage_fault(storage_fault_t fault);

/* ──────────────────────────────────────────────────────────────────────────
 * Wave 3: Settings & IMU Calibration (ui_settings.c / ui_calibration.c)
 * ────────────────────────────────────────────────────────────────────────*/

/** @brief Screen 10: Show responsive 2x2 Settings configuration grid. */
void ui_show_settings(void);

/** @brief Screen 13: Live GPS and BMI323 hardware diagnostics with two tabs. */
void ui_show_hardware_debug(void);
void ui_hardware_debug_update(void);

/** @brief Screen 11: Launch 5-Stage IMU Mount Calibration Wizard. */
void ui_show_imu_calibration_wizard(void);

/**
 * @brief Update sample progression and G-force readings during calibration wizard.
 * @param step Active wizard stage index (1 to 5).
 * @param sample_count Completed static sample collection count out of 100.
 * @param stable True if motorcycle vibration sits below maximum noise floor threshold.
 */
void ui_calibration_update_progress(int step, int sample_count, bool stable);

/* ──────────────────────────────────────────────────────────────────────────
 * Wave 4: Cloud Sync & WiFi Provisioning (ui_sync.c)
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Screen 6: Show WiFi network searching and scanning screen.
 * @param target_ssid Network name currently being scanned/verified.
 */
void ui_show_sync_searching(const char *target_ssid);

/** @brief Screen 7: Show cloud server Heartbeat verification handshake screen. */
void ui_show_sync_heartbeat(void);

/**
 * @brief Screen 8: Show active multi-file batch upload progress screen.
 * @param file_idx Current sequence index of active file upload.
 * @param total_files Total count of pending session CSV files in sync queue.
 * @param filename File name currently streaming over MbedTLS.
 * @param progress_pct Overall file transfer progress percentage (0-100).
 * @param speed Calculated transfer bandwidth speed string.
 * @param eta Estimated completion time string.
 */
void ui_show_sync_uploading(int file_idx, int total_files, const char *filename,
                            int progress_pct, const char *speed, const char *eta);

/**
 * @brief Screen 9: Show sync completion and upload summary report screen.
 * @param files_synced Total files uploaded without error.
 * @param mb_total Megabytes transferred during sync run.
 * @param seconds Total elapsed sync duration in seconds.
 */
void ui_show_sync_complete(int files_synced, float mb_total, int seconds);

/**
 * @brief Screen 12: Show Captive Portal WiFi provisioning pairing view with QR code.
 * @param ap_name Broadcast SoftAP SSID (e.g. "RS-Core-A1F4").
 */
void ui_show_captive_portal(const char *ap_name);

#ifdef __cplusplus
}
#endif

#endif /* UI_H */
