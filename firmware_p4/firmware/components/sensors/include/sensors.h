/**
 * @file sensors.h
 * @brief Real-time sensor ingestion task — Core 0, 100Hz IMU / 10Hz GPS
 *
 * Architecture:
 *   - A FreeRTOS task is pinned to Core 0 (PRO_CPU).
 *   - A hardware gptimer fires at exactly 100Hz.
 *   - On each timer interrupt, a semaphore is given to the task.
 *   - The task: reads BMI323 → queues IMU row → every 10th tick reads GPS → queues GPS row.
 *   - The storage component (Phase 7C) drains the queue on Core 1.
 *
 * Inter-task communication:
 *   - sensors_get_latest_imu() — lock-free latest sample for UI use
 *   - sensors_get_latest_gps() — lock-free latest fix for UI use
 *   - sensors_register_row_callback() — called on Core 0 per row (advanced use)
 */

#ifndef SENSORS_H
#define SENSORS_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "bmi323.h"
#include "gps.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Configuration
 * ────────────────────────────────────────────────────────────────────────*/
#define SENSORS_IMU_RATE_HZ     100
#define SENSORS_GPS_EVERY_N     10    /**< GPS row every 10th IMU tick (10Hz) */
#define SENSORS_TASK_STACK_SZ   4096
#define SENSORS_TASK_PRIORITY   20    /**< High priority — real-time */
#define SENSORS_TASK_CORE       0     /**< Pinned to Core 0 (PRO_CPU) */

/* ──────────────────────────────────────────────────────────────────────────
 * Data row types (matches CSV schema row_type field)
 * ────────────────────────────────────────────────────────────────────────*/
typedef enum {
    ROW_TYPE_IMU = 'I',   /**< 100Hz IMU-only row    */
    ROW_TYPE_GPS = 'G',   /**< 10Hz GPS+IMU merged row */
    ROW_TYPE_MARKER = 'M', /**< Session integrity marker */
} sensor_row_type_t;

/**
 * @brief One telemetry row — matches the CSV schema exactly:
 *   tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,
 *   lat,lon,alt,speed,sats,vbat
 */
typedef struct {
    uint32_t          tick_ms;   /**< Monotonic clock (ms)         */
    sensor_row_type_t row_type;  /**< 'I', 'G', or 'M'            */
    /* IMU — always populated */
    float             ax, ay, az;    /**< Acceleration (g)         */
    float             gx, gy, gz;    /**< Angular rate (deg/s)     */
    /* GPS — populated on 'G' rows only */
    double            lat, lon;
    float             altitude_m;
    float             speed_kmh;
    int               satellites;
    /* System health — populated on 'G' rows */
    float             vbat;      /**< Battery voltage (V)          */
} sensor_row_t;

/**
 * @brief Runtime statistics for the sensor-to-storage row queue.
 *
 * Counters are scoped to the current logging interval when reset through
 * sensors_reset_queue_stats(). The CSV contract is intentionally unrelated
 * to these diagnostics and remains unchanged.
 */
typedef struct {
    uint32_t rows_enqueued;
    uint32_t rows_dropped;
    uint32_t max_depth;
    uint32_t pending_rows;
    bool     producer_active;
} sensors_queue_stats_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Public API
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Initialize sensor drivers and start the Core 0 sampling task.
 *
 * Must be called after bsp_init(). Initializes BMI323 and Neo-M8N,
 * creates the 100Hz hardware timer, and launches the FreeRTOS task.
 *
 * @return ESP_OK on success. Logs errors if sensors fail but task
 *         still runs (missing sensor rows will have zeroed fields).
 */
esp_err_t sensors_task_start(void);

/**
 * @brief Stop the sensor task and release hardware resources.
 * @return ESP_OK on success.
 */
esp_err_t sensors_task_stop(void);

/**
 * @brief Set whether rows should be queued for storage.
 *
 * Enable when logging starts, disable on logging stop.
 * Thread-safe — checked on Core 0 before each row enqueue.
 *
 * @param enable  true = queue rows, false = run sensors but discard rows
 */
void sensors_set_logging(bool enable);

/**
 * @brief Get monotonic tick in milliseconds.
 *
 * Derived from esp_timer_get_time() / 1000. Matches S3 time.ticks_ms() contract.
 * @return ms since boot.
 */
uint32_t sensors_get_tick_ms(void);

/**
 * @brief Copy the latest IMU raw sample (thread-safe, lock-free read).
 * @param[out] raw  Destination. Returns zeroed struct if sensor not ready.
 */
void sensors_get_latest_imu(bmi323_raw_t *raw);

/**
 * @brief Copy the latest GPS fix (thread-safe, lock-free read).
 * @param[out] fix  Destination.
 */
void sensors_get_latest_gps(gps_fix_t *fix);

/**
 * @brief Check if BMI323 initialized and returning valid data.
 * @return true if IMU is healthy.
 */
bool sensors_imu_ok(void);

/**
 * @brief Check if GPS has a valid fix.
 * @return true if GPS is healthy with a valid position.
 */
bool sensors_gps_ok(void);

/**
 * @brief Get the current tick count (total 100Hz ticks since task started).
 * @return Monotonic tick counter.
 */
uint64_t sensors_get_tick_count(void);

/**
 * @brief Dequeue the next pending sensor row (called from storage task on Core 1).
 *
 * Non-blocking. Returns false if the queue is empty.
 *
 * @param[out] row   Destination row.
 * @return true if a row was dequeued.
 */
bool sensors_dequeue_row(sensor_row_t *row);

/**
 * @brief Wait for and dequeue the next pending sensor row.
 *
 * The sensor component remains the sole owner of the queue. Storage uses
 * this API as its blocking consumer rather than maintaining a second queue.
 *
 * @param[out] row        Destination row.
 * @param[in] timeout_ms  Maximum wait in milliseconds.
 * @return true if a row was dequeued.
 */
bool sensors_wait_dequeue_row(sensor_row_t *row, uint32_t timeout_ms);

/** Reset queue counters, normally immediately before a new session starts. */
void sensors_reset_queue_stats(void);

/** Copy queue counters and current producer state. */
void sensors_get_queue_stats(sensors_queue_stats_t *stats);

/**
 * @brief Wait until the sensor task is no longer building a logging row.
 *
 * Call after sensors_set_logging(false) and before asking storage to drain.
 */
bool sensors_wait_for_quiescence(uint32_t timeout_ms);

#ifdef __cplusplus
}
#endif

#endif /* SENSORS_H */
