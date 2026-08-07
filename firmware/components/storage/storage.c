/**
 * @file storage.c
 * @brief Session Manager & CSV Writer — ESP-IDF native C
 *
 * Ported from the legacy session manager implementation.
 *
 * Architecture:
 *   - storage_init() starts a Core 1 flush task.
 *   - Sensor task (Core 0) owns the row queue and produces rows 100x/sec.
 *   - Flush task (Core 1) drains that sensor queue → writes to FILE* in
 *     ~32-row batches → fflush() to commit to FATFS.
 *   - Marker rows are written directly (not queued) with an fflush().
 *
 * CSV schema (server parses by column position — must not change):
 *   tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,
 *   lat,lon,alt,speed,sats,vbat
 */

#include "storage.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <dirent.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include "wear_levelling.h"
#include "bsp.h"

static const char *TAG = "storage";

/* ──────────────────────────────────────────────────────────────────────────
 * Internal configuration
 * ────────────────────────────────────────────────────────────────────────*/
#define FLUSH_BATCH_ROWS     32       /* Write to disk every N rows           */
#define FLUSH_TASK_STACK     4096
#define FLUSH_TASK_PRIORITY  5        /* Lower than sensor task               */
#define FLUSH_TASK_CORE      1        /* Core 1 — same as UI                  */
#define FLUSH_DRAIN_TIMEOUT_MS 2000   /* Maximum normal session-stop drain    */

/* CSV header — column order is the server contract */
static const char *CSV_HEADER =
    "tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,"
    "lat,lon,alt,speed,sats,vbat\n";

/* ──────────────────────────────────────────────────────────────────────────
 * Module state
 * ────────────────────────────────────────────────────────────────────────*/
static FILE             *s_file          = NULL;
static SemaphoreHandle_t s_file_mutex    = NULL;
static SemaphoreHandle_t s_drain_complete = NULL;
static TaskHandle_t      s_flush_task    = NULL;
static volatile bool     s_flush_running = false;
static volatile bool     s_drain_requested = false;

static storage_session_info_t  s_session  = {0};
static storage_health_t        s_health   = STORAGE_HEALTH_OK;
static volatile int            s_fault_code = STORAGE_FAULT_NONE;
static uint32_t                s_row_since_checkpoint = 0;
static wl_handle_t             s_flash_wl = WL_INVALID_HANDLE;

/* ──────────────────────────────────────────────────────────────────────────
 * Helpers
 * ────────────────────────────────────────────────────────────────────────*/

static void _mkdir_safe(const char *path)
{
    struct stat st;
    if (stat(path, &st) != 0) {
        mkdir(path, 0755);
    }
}

static bool _file_exists(const char *path)
{
    struct stat st;
    return stat(path, &st) == 0;
}

static long _file_size(const char *path)
{
    struct stat st;
    if (stat(path, &st) != 0) return -1;
    return (long)st.st_size;
}

/**
 * @brief Scan directory for sess_NNN.csv, return next available number.
 */
static int _next_session_number(const char *dir)
{
    DIR *d = opendir(dir);
    if (!d) return 1;

    int max_num = 0;
    struct dirent *entry;
    while ((entry = readdir(d)) != NULL) {
        const char *name = entry->d_name;
        if (strncmp(name, "sess_", 5) == 0) {
            const char *end = strrchr(name, '.');
            if (end && strcmp(end, ".csv") == 0) {
                int n = atoi(name + 5);
                if (n > max_num) max_num = n;
            }
        }
    }
    closedir(d);
    return max_num + 1;
}

/**
 * @brief Determine active session directory (SD preferred, flash fallback).
 */
static const char *_active_dir(void)
{
    return bsp_sdcard_mounted() ? STORAGE_SD_SESSIONS_DIR : STORAGE_FLASH_SESSIONS_DIR;
}

/**
 * @brief Update storage health state from current usage percent.
 */
static void _refresh_health(void)
{
    int pct = bsp_sdcard_get_usage_percent();
    if (pct < 0) pct = storage_get_usage_percent();

    if (pct >= STORAGE_HARD_STOP_PCT) {
        if (s_health != STORAGE_HEALTH_HARD_STOP) {
            ESP_LOGE(TAG, "HARD STOP — storage at %d%%", pct);
            s_health = STORAGE_HEALTH_HARD_STOP;
        }
    } else if (pct >= STORAGE_CRITICAL_PCT) {
        if (s_health == STORAGE_HEALTH_OK) {
            ESP_LOGW(TAG, "STORAGE CRITICAL — %d%% used", pct);
            s_health = STORAGE_HEALTH_CRITICAL;
        }
    }
}

static void _latch_fault(storage_fault_t fault, const char *operation)
{
    if (fault == STORAGE_FAULT_NONE) return;

    int expected = STORAGE_FAULT_NONE;
    if (__atomic_compare_exchange_n(&s_fault_code, &expected, (int)fault,
                                    false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        ESP_LOGE(TAG, "Storage fault latched: %s (%s)",
                 storage_fault_name(fault), operation ? operation : "unknown");
    }
}

/* ──────────────────────────────────────────────────────────────────────────
 * CSV row formatting
 * ────────────────────────────────────────────────────────────────────────*/

/** Write one IMU or GPS row directly to the open file (must hold file_mutex) */
static esp_err_t _write_imu_row_locked(uint32_t tick_ms,
                                       float ax, float ay, float az,
                                       float gx, float gy, float gz)
{
    int written = fprintf(s_file,
                          "%lu,I,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,,,,,,\n",
                          (unsigned long)tick_ms,
                          ax, ay, az, gx, gy, gz);
    return written < 0 ? ESP_FAIL : ESP_OK;
}

static esp_err_t _write_gps_row_locked(uint32_t tick_ms,
                                       float ax, float ay, float az,
                                       float gx, float gy, float gz,
                                       double lat, double lon,
                                       float alt, float speed, int sats, float vbat)
{
    int written = fprintf(s_file,
                          "%lu,G,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.8f,%.8f,%.2f,%.3f,%d,%.3f\n",
                          (unsigned long)tick_ms,
                          ax, ay, az, gx, gy, gz,
                          lat, lon, alt, speed, sats, vbat);
    return written < 0 ? ESP_FAIL : ESP_OK;
}

static esp_err_t _write_marker_locked(uint32_t tick_ms,
                                      const char *marker_type,
                                      const char *payload)
{
    int written;
    if (payload && payload[0]) {
        written = fprintf(s_file, "%lu,M,%s,\"%s\"\n",
                          (unsigned long)tick_ms, marker_type, payload);
    } else {
        written = fprintf(s_file, "%lu,M,%s,\n",
                          (unsigned long)tick_ms, marker_type);
    }
    if (written < 0 || fflush(s_file) != 0) return ESP_FAIL;
    return ESP_OK;
}

/** Close a file after a fault without attempting to append another marker. */
static void _close_faulted_file_locked(void)
{
    if (!s_file) return;
    if (fclose(s_file) != 0) _latch_fault(STORAGE_FAULT_CLOSE, "fclose after fault");
    s_file = NULL;
}

/**
 * @brief Complete a requested queue drain after the consumer is idle.
 *
 * This is called only by the flush task. Because the task reaches this point
 * after a receive timeout, it cannot still be holding a dequeued row while it
 * acknowledges the drain barrier.
 */
static void _maybe_complete_drain(void)
{
    if (!__atomic_load_n(&s_drain_requested, __ATOMIC_ACQUIRE)) return;

    sensors_queue_stats_t stats = {0};
    sensors_get_queue_stats(&stats);
    if (stats.pending_rows != 0 || stats.producer_active) return;

    if (s_file) {
        xSemaphoreTake(s_file_mutex, portMAX_DELAY);
        if (fflush(s_file) != 0) {
            _latch_fault(STORAGE_FAULT_FLUSH, "drain flush");
            _close_faulted_file_locked();
        }
        xSemaphoreGive(s_file_mutex);
    }

    __atomic_store_n(&s_drain_requested, false, __ATOMIC_RELEASE);
    xSemaphoreGive(s_drain_complete);
}

/**
 * @brief Ask the flush task to consume all rows currently produced.
 */
static esp_err_t _wait_for_queue_drain(uint32_t timeout_ms)
{
    if (!s_drain_complete) return ESP_ERR_INVALID_STATE;

    /* A binary semaphore should normally be empty; clear a stale completion
     * defensively before starting a new barrier. */
    (void)xSemaphoreTake(s_drain_complete, 0);
    __atomic_store_n(&s_drain_requested, true, __ATOMIC_RELEASE);

    if (xSemaphoreTake(s_drain_complete, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) {
        __atomic_store_n(&s_drain_requested, false, __ATOMIC_RELEASE);
        return ESP_ERR_TIMEOUT;
    }
    return ESP_OK;
}

/* ──────────────────────────────────────────────────────────────────────────
 * Flush task (Core 1) — drains the sensor-owned queue and writes to SD
 * ────────────────────────────────────────────────────────────────────────*/
static void _flush_task(void *arg)
{
    ESP_LOGI(TAG, "Flush task started on Core %d", xPortGetCoreID());
    sensor_row_t row;
    int batch_count = 0;

    while (s_flush_running) {
        /* Block for up to 20ms waiting for a row */
        if (!sensors_wait_dequeue_row(&row, 20)) {
            /* Nothing in queue — flush pending writes if we have any */
            if (batch_count > 0 && s_file) {
                xSemaphoreTake(s_file_mutex, portMAX_DELAY);
                if (fflush(s_file) != 0) {
                    _latch_fault(STORAGE_FAULT_FLUSH, "batch flush");
                    _close_faulted_file_locked();
                }
                xSemaphoreGive(s_file_mutex);
                batch_count = 0;
            }
            _maybe_complete_drain();
            /* The sensor queue is created after storage_init() during boot.
             * Avoid a tight loop during that short startup window. */
            vTaskDelay(pdMS_TO_TICKS(1));
            continue;
        }

        /* Health check every 100 rows */
        if ((s_session.rows_written % 100) == 0) {
            _refresh_health();
        }

        /* Once a write fault is latched, consume and discard queued rows so
         * the producer can quiesce cleanly while the app transitions UI. */
        if (storage_get_fault() != STORAGE_FAULT_NONE) {
            s_session.rows_dropped++;
            continue;
        }

        /* HARD_STOP: discard rows, do not write */
        if (s_health == STORAGE_HEALTH_HARD_STOP) {
            _latch_fault(STORAGE_FAULT_CAPACITY, "storage usage threshold");
            if (s_file) {
                xSemaphoreTake(s_file_mutex, portMAX_DELAY);
                _close_faulted_file_locked();
                xSemaphoreGive(s_file_mutex);
            }
            s_session.rows_dropped++;
            continue;
        }

        if (!s_file || !s_session.active) {
            ESP_LOGW(TAG, "Discarding row because no session is active");
            continue;
        }

        xSemaphoreTake(s_file_mutex, portMAX_DELAY);

        esp_err_t write_ret;
        if (row.row_type == ROW_TYPE_GPS) {
            write_ret = _write_gps_row_locked(row.tick_ms,
                                              row.ax, row.ay, row.az,
                                              row.gx, row.gy, row.gz,
                                              row.lat, row.lon,
                                              row.altitude_m, row.speed_kmh,
                                              row.satellites, row.vbat);
        } else {
            write_ret = _write_imu_row_locked(row.tick_ms,
                                              row.ax, row.ay, row.az,
                                              row.gx, row.gy, row.gz);
        }

        if (write_ret != ESP_OK) {
            _latch_fault(STORAGE_FAULT_WRITE, "telemetry row");
            s_session.rows_dropped++;
            _close_faulted_file_locked();
            xSemaphoreGive(s_file_mutex);
            batch_count = 0;
            continue;
        }

        s_session.rows_written++;
        s_session.bytes_written += 80; /* Approximate — updated on flush */
        batch_count++;

        /* Auto-checkpoint */
        s_row_since_checkpoint++;
        if (s_row_since_checkpoint >= STORAGE_CHECKPOINT_INTERVAL) {
            if (_write_marker_locked(row.tick_ms, "CHECKPOINT", NULL) != ESP_OK) {
                _latch_fault(STORAGE_FAULT_WRITE, "telemetry checkpoint");
                _close_faulted_file_locked();
                s_row_since_checkpoint = 0;
                xSemaphoreGive(s_file_mutex);
                batch_count = 0;
                continue;
            }
            s_row_since_checkpoint = 0;
        }

        /* Batch flush every FLUSH_BATCH_ROWS rows */
        if (batch_count >= FLUSH_BATCH_ROWS) {
            if (fflush(s_file) != 0) {
                _latch_fault(STORAGE_FAULT_FLUSH, "telemetry batch");
                _close_faulted_file_locked();
            }
            batch_count = 0;
        }

        xSemaphoreGive(s_file_mutex);
    }

    ESP_LOGI(TAG, "Flush task exiting");
    vTaskDelete(NULL);
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t storage_init(void)
{
    /* Mount the partition declared as `storage` in partitions.csv.  The old
     * code created /data paths without a VFS mount, so configuration files
     * (including touch calibration) could never persist. */
    if (s_flash_wl == WL_INVALID_HANDLE) {
        const esp_vfs_fat_mount_config_t flash_cfg = {
            .format_if_mount_failed = true,
            .max_files = 8,
            .allocation_unit_size = 4096,
        };
        esp_err_t mount_ret = esp_vfs_fat_spiflash_mount_rw_wl(
            "/data", "storage", &flash_cfg, &s_flash_wl);
        if (mount_ret != ESP_OK) {
            ESP_LOGE(TAG, "Internal storage mount failed: %s", esp_err_to_name(mount_ret));
            return mount_ret;
        }
    }

    /* Create required directory structure */
    _mkdir_safe("/data");
    _mkdir_safe(STORAGE_FLASH_META_DIR);
    _mkdir_safe(STORAGE_FLASH_SESSIONS_DIR);
    _mkdir_safe(STORAGE_FLASH_ARCHIVE_DIR);

    if (bsp_sdcard_mounted()) {
        _mkdir_safe(STORAGE_SD_SESSIONS_DIR);
        _mkdir_safe(STORAGE_SD_ARCHIVE_DIR);
    }

    /* Mutex protecting file handle */
    s_file_mutex = xSemaphoreCreateMutex();
    if (!s_file_mutex) return ESP_ERR_NO_MEM;

    /* Completion barrier used when stopping a session. */
    s_drain_complete = xSemaphoreCreateBinary();
    if (!s_drain_complete) return ESP_ERR_NO_MEM;

    /* Start flush task on Core 1 */
    s_flush_running = true;
    BaseType_t ret = xTaskCreatePinnedToCore(
        _flush_task, "storage_flush",
        FLUSH_TASK_STACK, NULL,
        FLUSH_TASK_PRIORITY, &s_flush_task,
        FLUSH_TASK_CORE
    );
    if (ret != pdPASS) return ESP_FAIL;

    ESP_LOGI(TAG, "Storage initialized — active dir: %s", _active_dir());
    return ESP_OK;
}

esp_err_t storage_session_start(void)
{
    if (!s_file_mutex || s_flash_wl == WL_INVALID_HANDLE) {
        _latch_fault(STORAGE_FAULT_NOT_READY, "session start before storage init");
        return ESP_ERR_INVALID_STATE;
    }
    if (storage_get_fault() != STORAGE_FAULT_NONE) {
        return ESP_ERR_INVALID_STATE;
    }

    if (s_session.active) {
        ESP_LOGW(TAG, "Session already open — stopping first");
        esp_err_t stop_ret = storage_session_stop();
        if (stop_ret != ESP_OK) return stop_ret;
    }

    _refresh_health();
    if (s_health == STORAGE_HEALTH_HARD_STOP) {
        _latch_fault(STORAGE_FAULT_CAPACITY, "session start capacity check");
        return ESP_ERR_NO_MEM;
    }

    const char *dir = _active_dir();
    int num = _next_session_number(dir);
    snprintf(s_session.filename, sizeof(s_session.filename), "sess_%03d.csv", num);
    snprintf(s_session.filepath, sizeof(s_session.filepath), "%s/%s", dir, s_session.filename);

    xSemaphoreTake(s_file_mutex, portMAX_DELAY);
    s_file = fopen(s_session.filepath, "w");
    xSemaphoreGive(s_file_mutex);

    if (!s_file) {
        ESP_LOGE(TAG, "Failed to open: %s", s_session.filepath);
        _latch_fault(STORAGE_FAULT_OPEN, "session file open");
        return ESP_FAIL;
    }

    /* Write CSV header */
    xSemaphoreTake(s_file_mutex, portMAX_DELAY);
    bool header_ok = fputs(CSV_HEADER, s_file) != EOF;
    esp_err_t marker_ret = header_ok
        ? _write_marker_locked((uint32_t)(esp_timer_get_time() / 1000ULL),
                               "LOG_OPEN", s_session.filename)
        : ESP_FAIL;
    if (header_ok && marker_ret == ESP_OK) {
        /* Make the session visible on disk before producers start. */
        header_ok = fflush(s_file) == 0;
    }
    if (!header_ok || marker_ret != ESP_OK) {
        _latch_fault(STORAGE_FAULT_WRITE, "session header/LOG_OPEN");
        _close_faulted_file_locked();
        xSemaphoreGive(s_file_mutex);
        return ESP_FAIL;
    }
    xSemaphoreGive(s_file_mutex);

    s_session.active          = true;
    s_session.rows_written    = 0;
    s_session.rows_dropped    = 0;
    s_session.bytes_written   = 0;
    s_row_since_checkpoint    = 0;
    sensors_reset_queue_stats();

    ESP_LOGI(TAG, "Session started: %s", s_session.filepath);
    return ESP_OK;
}

esp_err_t storage_session_stop(void)
{
    if (!s_session.active) return ESP_OK;

    /* The caller normally disables logging first; repeat it here so every
     * storage stop path has the same producer/consumer ordering. */
    sensors_set_logging(false);
    bool producer_quiesced = sensors_wait_for_quiescence(FLUSH_DRAIN_TIMEOUT_MS);
    esp_err_t drain_ret = producer_quiesced
        ? _wait_for_queue_drain(FLUSH_DRAIN_TIMEOUT_MS)
        : ESP_ERR_TIMEOUT;
    if (drain_ret != ESP_OK) {
        _latch_fault(STORAGE_FAULT_DRAIN_TIMEOUT, "session drain");
        sensors_queue_stats_t queue_stats = {0};
        sensors_get_queue_stats(&queue_stats);
        ESP_LOGE(TAG, "Session drain timed out: pending=%lu active=%s drops=%lu",
                 (unsigned long)queue_stats.pending_rows,
                 queue_stats.producer_active ? "yes" : "no",
                 (unsigned long)queue_stats.rows_dropped);
    }

    sensors_queue_stats_t queue_stats = {0};
    sensors_get_queue_stats(&queue_stats);
    s_session.rows_dropped += queue_stats.rows_dropped;

    xSemaphoreTake(s_file_mutex, portMAX_DELAY);
    if (s_file) {
        if (storage_get_fault() == STORAGE_FAULT_NONE) {
            if (_write_marker_locked((uint32_t)(esp_timer_get_time() / 1000ULL),
                                     "LOG_STOP", NULL) != ESP_OK) {
                _latch_fault(STORAGE_FAULT_WRITE, "LOG_STOP");
            }
        }
        if (s_file && storage_get_fault() == STORAGE_FAULT_NONE &&
            fflush(s_file) != 0) {
            _latch_fault(STORAGE_FAULT_FLUSH, "session stop flush");
        }
        if (s_file && fclose(s_file) != 0) {
            _latch_fault(STORAGE_FAULT_CLOSE, "session stop close");
        }
        s_file = NULL;
    }
    xSemaphoreGive(s_file_mutex);

    s_session.active = false;
    ESP_LOGI(TAG, "Session closed: %s — %lu rows / %llu bytes",
             s_session.filename,
             (unsigned long)s_session.rows_written,
             s_session.bytes_written);
    ESP_LOGI(TAG, "Session queue stats: enqueued=%lu dropped=%lu max_depth=%lu pending=%lu",
             (unsigned long)queue_stats.rows_enqueued,
             (unsigned long)queue_stats.rows_dropped,
             (unsigned long)queue_stats.max_depth,
             (unsigned long)queue_stats.pending_rows);
    if (storage_get_fault() != STORAGE_FAULT_NONE) return ESP_FAIL;
    return drain_ret;
}

esp_err_t storage_write_checkpoint(void)
{
    if (storage_get_fault() != STORAGE_FAULT_NONE || !s_file || !s_session.active) {
        return ESP_ERR_INVALID_STATE;
    }
    uint32_t tick = (uint32_t)(esp_timer_get_time() / 1000ULL);
    xSemaphoreTake(s_file_mutex, portMAX_DELAY);
    esp_err_t ret = _write_marker_locked(tick, "CHECKPOINT", NULL);
    if (ret != ESP_OK) {
        _latch_fault(STORAGE_FAULT_WRITE, "CHECKPOINT");
        _close_faulted_file_locked();
    }
    xSemaphoreGive(s_file_mutex);
    if (ret != ESP_OK) return ret;
    s_row_since_checkpoint = 0;
    return ESP_OK;
}

esp_err_t storage_write_imu_profile(const char *profile_json)
{
    if (storage_get_fault() != STORAGE_FAULT_NONE || !s_file || !s_session.active) {
        return ESP_ERR_INVALID_STATE;
    }
    uint32_t tick = (uint32_t)(esp_timer_get_time() / 1000ULL);
    xSemaphoreTake(s_file_mutex, portMAX_DELAY);
    esp_err_t ret = _write_marker_locked(tick, "IMU_PROFILE",
                                         profile_json ? profile_json : "");
    if (ret != ESP_OK) {
        _latch_fault(STORAGE_FAULT_WRITE, "IMU_PROFILE");
        _close_faulted_file_locked();
    }
    xSemaphoreGive(s_file_mutex);
    return ret;
}

esp_err_t storage_write_marker(uint32_t tick_ms,
                                const char *marker_type,
                                const char *payload)
{
    if (storage_get_fault() != STORAGE_FAULT_NONE || !s_file || !s_session.active) {
        return ESP_ERR_INVALID_STATE;
    }
    xSemaphoreTake(s_file_mutex, portMAX_DELAY);
    esp_err_t ret = _write_marker_locked(tick_ms, marker_type, payload);
    if (ret != ESP_OK) {
        _latch_fault(STORAGE_FAULT_WRITE, "marker");
        _close_faulted_file_locked();
    }
    xSemaphoreGive(s_file_mutex);
    return ret;
}

esp_err_t storage_write_imu_row(uint32_t tick_ms,
                                 float ax, float ay, float az,
                                 float gx, float gy, float gz)
{
    if (storage_get_fault() != STORAGE_FAULT_NONE || !s_file || !s_session.active) {
        return ESP_ERR_INVALID_STATE;
    }
    xSemaphoreTake(s_file_mutex, portMAX_DELAY);
    esp_err_t ret = _write_imu_row_locked(tick_ms, ax, ay, az, gx, gy, gz);
    if (ret != ESP_OK) {
        _latch_fault(STORAGE_FAULT_WRITE, "direct IMU row");
        _close_faulted_file_locked();
    }
    if (ret == ESP_OK) s_session.rows_written++;
    xSemaphoreGive(s_file_mutex);
    return ret;
}

esp_err_t storage_write_gps_row(uint32_t tick_ms,
                                 float ax, float ay, float az,
                                 float gx, float gy, float gz,
                                 double lat, double lon,
                                 float alt, float speed, int sats, float vbat)
{
    if (storage_get_fault() != STORAGE_FAULT_NONE || !s_file || !s_session.active) {
        return ESP_ERR_INVALID_STATE;
    }
    xSemaphoreTake(s_file_mutex, portMAX_DELAY);
    esp_err_t ret = _write_gps_row_locked(tick_ms, ax, ay, az, gx, gy, gz,
                                          lat, lon, alt, speed, sats, vbat);
    if (ret != ESP_OK) {
        _latch_fault(STORAGE_FAULT_WRITE, "direct GPS row");
        _close_faulted_file_locked();
    }
    if (ret == ESP_OK) s_session.rows_written++;
    xSemaphoreGive(s_file_mutex);
    return ret;
}

storage_health_t storage_get_health(void)
{
    return s_health;
}

storage_fault_t storage_get_fault(void)
{
    return (storage_fault_t)__atomic_load_n(&s_fault_code, __ATOMIC_ACQUIRE);
}

esp_err_t storage_clear_fault(void)
{
    if (s_session.active) return ESP_ERR_INVALID_STATE;
    __atomic_store_n(&s_fault_code, STORAGE_FAULT_NONE, __ATOMIC_RELEASE);
    return ESP_OK;
}

int storage_get_usage_percent(void)
{
    return bsp_sdcard_get_usage_percent();
}

esp_err_t storage_get_space_bytes(uint64_t *total_bytes, uint64_t *free_bytes)
{
    return bsp_sdcard_get_space_bytes(total_bytes, free_bytes);
}

void storage_get_session_info(storage_session_info_t *info)
{
    if (info) memcpy(info, &s_session, sizeof(*info));
}

void storage_get_pending_summary(storage_pending_summary_t *summary)
{
    if (!summary) return;
    summary->count       = 0;
    summary->total_bytes = 0;

    const char *dir = _active_dir();
    DIR *d = opendir(dir);
    if (!d) return;

    struct dirent *entry;
    while ((entry = readdir(d)) != NULL) {
        if (strncmp(entry->d_name, "sess_", 5) == 0 &&
            strstr(entry->d_name, ".csv")) {
            char path[320];
            snprintf(path, sizeof(path), "%s/%s", dir, entry->d_name);
            long sz = _file_size(path);
            if (sz > 0) {
                summary->count++;
                summary->total_bytes += (uint64_t)sz;
            }
        }
    }
    closedir(d);
}

static int _pending_file_compare(const void *lhs, const void *rhs)
{
    const storage_pending_file_t *a = lhs;
    const storage_pending_file_t *b = rhs;
    return strcmp(a->filename, b->filename);
}

size_t storage_list_pending_files(storage_pending_file_t *files, size_t capacity)
{
    if (!files || capacity == 0) return 0;

    const char *dir = _active_dir();
    DIR *d = opendir(dir);
    if (!d) return 0;

    size_t count = 0;
    struct dirent *entry;
    while ((entry = readdir(d)) != NULL && count < capacity) {
        if (strncmp(entry->d_name, "sess_", 5) != 0 ||
            !strstr(entry->d_name, ".csv")) {
            continue;
        }

        char path[320];
        snprintf(path, sizeof(path), "%s/%s", dir, entry->d_name);
        struct stat st;
        if (stat(path, &st) != 0 || st.st_size <= 0) continue;

        storage_pending_file_t *file = &files[count++];
        memset(file, 0, sizeof(*file));
        strncpy(file->filepath, path, sizeof(file->filepath) - 1);
        strncpy(file->filename, entry->d_name, sizeof(file->filename) - 1);
        file->size_bytes = (uint64_t)st.st_size;
    }
    closedir(d);

    qsort(files, count, sizeof(files[0]), _pending_file_compare);
    return count;
}

bool storage_has_flash_sessions(void)
{
    DIR *d = opendir(STORAGE_FLASH_SESSIONS_DIR);
    if (!d) return false;
    bool found = false;
    struct dirent *entry;
    while ((entry = readdir(d)) != NULL) {
        if (strstr(entry->d_name, ".csv")) { found = true; break; }
    }
    closedir(d);
    if (found) return true;

    /* Also check uploaded subfolder */
    d = opendir(STORAGE_FLASH_ARCHIVE_DIR);
    if (!d) return false;
    while ((entry = readdir(d)) != NULL) {
        if (strstr(entry->d_name, ".csv")) { found = true; break; }
    }
    closedir(d);
    return found;
}

/**
 * @brief Copy a single file src → dst, verify byte size, then delete src.
 * Collision-safe: if dst exists, appends _1, _2, etc.
 */
static bool _copy_and_delete(const char *src_dir, const char *dst_dir,
                              const char *fname)
{
    char src[96], dst[96];
    snprintf(src, sizeof(src), "%s/%s", src_dir, fname);

    /* Resolve collision-safe destination */
    snprintf(dst, sizeof(dst), "%s/%s", dst_dir, fname);
    if (_file_exists(dst)) {
        char base[48], ext[8];
        const char *dot = strrchr(fname, '.');
        if (dot) {
            int base_len = (int)(dot - fname);
            snprintf(base, sizeof(base), "%.*s", base_len, fname);
            snprintf(ext,  sizeof(ext),  "%s",   dot + 1);
        } else {
            snprintf(base, sizeof(base), "%s", fname);
            ext[0] = '\0';
        }
        int counter = 1;
        do {
            snprintf(dst, sizeof(dst), "%s/%s_%d.%s", dst_dir, base, counter++, ext);
        } while (_file_exists(dst) && counter < 100);
        ESP_LOGW(TAG, "Collision: renamed to %s", dst);
    }

    /* Copy in 64KB chunks */
    FILE *fsrc = fopen(src, "rb");
    FILE *fdst = fopen(dst, "wb");
    if (!fsrc || !fdst) {
        if (fsrc) fclose(fsrc);
        if (fdst) fclose(fdst);
        return false;
    }

    uint8_t *buf = malloc(64 * 1024);
    if (!buf) { fclose(fsrc); fclose(fdst); return false; }

    size_t n;
    while ((n = fread(buf, 1, 64 * 1024, fsrc)) > 0) {
        fwrite(buf, 1, n, fdst);
    }
    free(buf);
    fclose(fsrc);
    fclose(fdst);

    /* Verify size matches */
    long src_sz = _file_size(src);
    long dst_sz = _file_size(dst);
    if (src_sz != dst_sz || src_sz <= 0) {
        ESP_LOGE(TAG, "Copy size mismatch: %s (%ld vs %ld)", fname, src_sz, dst_sz);
        remove(dst);
        return false;
    }

    remove(src);
    ESP_LOGI(TAG, "Moved %s → SD (%ld bytes)", fname, src_sz);
    return true;
}

bool storage_move_flash_to_sd(void)
{
    if (!bsp_sdcard_mounted()) return false;

    _mkdir_safe(STORAGE_SD_SESSIONS_DIR);
    _mkdir_safe(STORAGE_SD_ARCHIVE_DIR);

    bool moved_any = false;

    /* Move pending sessions */
    DIR *d = opendir(STORAGE_FLASH_SESSIONS_DIR);
    if (d) {
        struct dirent *entry;
        while ((entry = readdir(d)) != NULL) {
            if (strstr(entry->d_name, ".csv")) {
                if (_copy_and_delete(STORAGE_FLASH_SESSIONS_DIR,
                                     STORAGE_SD_SESSIONS_DIR,
                                     entry->d_name)) {
                    moved_any = true;
                }
            }
        }
        closedir(d);
    }

    /* Move uploaded archive */
    d = opendir(STORAGE_FLASH_ARCHIVE_DIR);
    if (d) {
        struct dirent *entry;
        while ((entry = readdir(d)) != NULL) {
            if (strstr(entry->d_name, ".csv")) {
                if (_copy_and_delete(STORAGE_FLASH_ARCHIVE_DIR,
                                     STORAGE_SD_ARCHIVE_DIR,
                                     entry->d_name)) {
                    moved_any = true;
                }
            }
        }
        closedir(d);
    }

    return moved_any;
}

esp_err_t storage_archive_session(const char *filepath)
{
    if (!filepath) return ESP_ERR_INVALID_ARG;

    /* Derive filename from path */
    const char *fname = strrchr(filepath, '/');
    fname = fname ? fname + 1 : filepath;

    /* Determine archive dir (same medium as source) */
    const char *arch_dir = strncmp(filepath, "/sd/", 4) == 0
                           ? STORAGE_SD_ARCHIVE_DIR
                           : STORAGE_FLASH_ARCHIVE_DIR;

    _mkdir_safe(arch_dir);

    char dst[96];
    snprintf(dst, sizeof(dst), "%s/%s", arch_dir, fname);

    if (rename(filepath, dst) != 0) {
        ESP_LOGE(TAG, "Archive rename failed: %s → %s", filepath, dst);
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "Archived: %s", fname);
    return ESP_OK;
}
