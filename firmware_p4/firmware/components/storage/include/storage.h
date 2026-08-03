/**
 * @file storage.h
 * @brief Session Manager & CSV Writer — RaceSense ESP32-P4
 *
 * Owns:
 *  - Session file lifecycle: open, write, checkpoint, close
 *  - CSV schema (exact byte-for-byte compatibility with S3 sessions)
 *  - Dual ring-buffer: sensors fill one buffer, flush task drains the other
 *  - Auto-copy: move flash sessions → SD on boot
 *  - Integrity marker rows: LOG_OPEN, CHECKPOINT, LOG_STOP, IMU_PROFILE
 *  - Storage health: usage percent, STORAGE_CRITICAL (90%), HARD_STOP (98%)
 *
 * CSV Schema (column order must never change — server parses by position):
 *   tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,
 *   lat,lon,alt,speed,sats,vbat
 *
 * Session naming: sess_NNN.csv (NNN = next available number, 3 digits zero-padded)
 * Session path:   /sd/sessions/sess_NNN.csv  (or /data/learning/ if no SD)
 * Archive path:   /sd/sessions/uploaded/sess_NNN.csv
 */

#ifndef STORAGE_H
#define STORAGE_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "sensors.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Paths
 * ────────────────────────────────────────────────────────────────────────*/
#define STORAGE_SD_SESSIONS_DIR     "/sd/sessions"
#define STORAGE_SD_ARCHIVE_DIR      "/sd/sessions/uploaded"
#define STORAGE_FLASH_SESSIONS_DIR  "/data/learning"
#define STORAGE_FLASH_ARCHIVE_DIR   "/data/learning/uploaded"
#define STORAGE_FLASH_META_DIR      "/data/metadata"

/* Storage health thresholds */
#define STORAGE_CRITICAL_PCT        90   /**< Warn + latch STORAGE_CRITICAL */
#define STORAGE_HARD_STOP_PCT       98   /**< Stop writes to protect FS      */

/* Checkpoint marker interval (rows between CHECKPOINT markers) */
#define STORAGE_CHECKPOINT_INTERVAL 1000

/* ──────────────────────────────────────────────────────────────────────────
 * Storage health state
 * ────────────────────────────────────────────────────────────────────────*/
typedef enum {
    STORAGE_HEALTH_OK       = 0,
    STORAGE_HEALTH_CRITICAL = 1,   /**< >90% used — warn rider             */
    STORAGE_HEALTH_HARD_STOP = 2,  /**< >98% used — no more writes         */
} storage_health_t;

/** Summary of an open session */
typedef struct {
    char     filepath[64];   /**< Full path e.g. /sd/sessions/sess_042.csv */
    char     filename[24];   /**< e.g. sess_042.csv                         */
    uint32_t rows_written;   /**< Total rows written this session           */
    uint32_t rows_dropped;   /**< Rows dropped due to queue overflow        */
    uint64_t bytes_written;  /**< Total bytes flushed                       */
    bool     active;         /**< true if session is open                   */
} storage_session_info_t;

/** Summary of pending sessions (for sync UI) */
typedef struct {
    int      count;
    uint64_t total_bytes;
} storage_pending_summary_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Public API
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Initialize the storage subsystem.
 *
 * Ensures required directories exist on flash and SD (if mounted).
 * Starts the flush task on Core 1 (runs in background draining sensor queue).
 *
 * @return ESP_OK on success.
 */
esp_err_t storage_init(void);

/**
 * @brief Open a new logging session.
 *
 * Finds the next available sess_NNN.csv number, opens the file,
 * writes the CSV header, and emits a LOG_OPEN marker row.
 *
 * @return ESP_OK on success, or error if storage unavailable.
 */
esp_err_t storage_session_start(void);

/**
 * @brief Close the active logging session.
 *
 * Flushes any buffered rows, emits a LOG_STOP marker, fsyncs,
 * and closes the file handle.
 *
 * @return ESP_OK on success.
 */
esp_err_t storage_session_stop(void);

/**
 * @brief Emit a periodic CHECKPOINT marker row.
 *
 * Called automatically every STORAGE_CHECKPOINT_INTERVAL rows.
 * Can also be called manually (e.g., on sector crossing).
 *
 * @return ESP_OK on success.
 */
esp_err_t storage_write_checkpoint(void);

/**
 * @brief Write an IMU_PROFILE marker row.
 *
 * Called at session start to embed the active mount profile in the CSV.
 *
 * @param profile_json  JSON string of the active IMU profile (may be NULL).
 * @return ESP_OK on success.
 */
esp_err_t storage_write_imu_profile(const char *profile_json);

/**
 * @brief Write a single IMU row (raw values — scaling happens in caller).
 *
 * Preferred path: use storage_enqueue_row() from the sensor task.
 * This direct write is for testing / calibration recording.
 *
 * @return ESP_OK on success.
 */
esp_err_t storage_write_imu_row(uint32_t tick_ms,
                                 float ax, float ay, float az,
                                 float gx, float gy, float gz);

/**
 * @brief Write a GPS+IMU merged row.
 * @return ESP_OK on success.
 */
esp_err_t storage_write_gps_row(uint32_t tick_ms,
                                 float ax, float ay, float az,
                                 float gx, float gy, float gz,
                                 double lat, double lon,
                                 float alt, float speed, int sats, float vbat);

/**
 * @brief Write a custom marker row (M type).
 *
 * @param tick_ms       Current monotonic tick.
 * @param marker_type   Marker label (LOG_OPEN, CHECKPOINT, LOG_STOP, etc.)
 * @param payload       Optional JSON payload (may be NULL or empty string).
 * @return ESP_OK on success.
 */
esp_err_t storage_write_marker(uint32_t tick_ms,
                                const char *marker_type,
                                const char *payload);

/**
 * @brief Enqueue a sensor row from the sensor task for async flush.
 *
 * Non-blocking — returns false if the internal queue is full.
 * This is the hot path called 100 times per second from Core 0.
 *
 * @param row  Row to enqueue.
 * @return true if enqueued, false if dropped.
 */
bool storage_enqueue_row(const sensor_row_t *row);

/**
 * @brief Get the current storage health state (OK / CRITICAL / HARD_STOP).
 * @return Current health enum.
 */
storage_health_t storage_get_health(void);

/**
 * @brief Get current SD card or flash usage percent.
 * @return 0-100, or -1 if not available.
 */
int storage_get_usage_percent(void);

/** Return mounted SD filesystem capacity and free space in bytes. */
esp_err_t storage_get_space_bytes(uint64_t *total_bytes, uint64_t *free_bytes);

/**
 * @brief Get info about the currently open session.
 * @param[out] info  Filled with session stats.
 */
void storage_get_session_info(storage_session_info_t *info);

/**
 * @brief Get list of pending sessions (for sync UI display).
 * @param[out] summary  Filled with count and total_bytes.
 */
void storage_get_pending_summary(storage_pending_summary_t *summary);

/**
 * @brief Check if any session CSV files exist on internal flash.
 *
 * Used during boot to detect auto-copy condition.
 *
 * @return true if flash sessions exist.
 */
bool storage_has_flash_sessions(void);

/**
 * @brief Copy all flash sessions to SD card (auto-copy on boot).
 *
 * Collision-safe: appends _1, _2 suffixes if filename already exists.
 * Verifies byte size after copy before deleting the flash original.
 *
 * @return true if at least one file was moved successfully.
 */
bool storage_move_flash_to_sd(void);

/**
 * @brief Archive a session file to the uploaded/ subfolder after sync.
 *
 * @param filepath  Full path to the session file.
 * @return ESP_OK on success.
 */
esp_err_t storage_archive_session(const char *filepath);

#ifdef __cplusplus
}
#endif

#endif /* STORAGE_H */
