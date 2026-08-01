/**
 * @file sensors.c
 * @brief Real-time sensor ingestion task — Core 0, 100Hz IMU / 10Hz GPS
 *
 * Implementation of the dual-rate telemetry pipeline:
 *
 *   gptimer (100Hz) → ISR gives semaphore
 *   → sensors_task (Core 0, priority 20)
 *       ├── read BMI323 raw (every tick)
 *       ├── every 10th tick: call gps_update(), read GPS fix
 *       ├── build sensor_row_t
 *       └── enqueue to FreeRTOS queue (storage task drains on Core 1)
 *
 * The sensor task never touches LVGL, SD card, or network directly.
 * It only reads sensors and pushes to the shared queue.
 *
 * Lock-free UI access:
 *   s_latest_imu and s_latest_gps are written atomically on Core 0 and
 *   read-only from Core 1 (UI). Since they are simple structs and Core 1
 *   only reads, this is safe without a mutex (worst case: stale-by-1-tick).
 */

#include "sensors.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "driver/gptimer.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "bsp.h"

static const char *TAG = "sensors";

/* ──────────────────────────────────────────────────────────────────────────
 * Configuration
 * ────────────────────────────────────────────────────────────────────────*/
#define ROW_QUEUE_DEPTH     256    /* ~2.56 seconds of IMU headroom at 100Hz */

/* ──────────────────────────────────────────────────────────────────────────
 * Module state
 * ────────────────────────────────────────────────────────────────────────*/
static TaskHandle_t      s_task_handle  = NULL;
static gptimer_handle_t  s_gptimer      = NULL;
static QueueHandle_t     s_row_queue    = NULL;
static SemaphoreHandle_t s_timer_sem    = NULL;

static volatile bool     s_logging      = false;
static volatile bool     s_task_running = false;
static volatile bool     s_imu_ok       = false;
static volatile uint64_t s_tick_count   = 0;

/* Lock-free latest samples for UI read-only access */
static bmi323_raw_t   s_latest_imu = {0};
static gps_fix_t      s_latest_gps = {0};

/* ──────────────────────────────────────────────────────────────────────────
 * Hardware timer ISR — fires at 100Hz, gives semaphore to task
 * ────────────────────────────────────────────────────────────────────────*/
static bool IRAM_ATTR _timer_isr(gptimer_handle_t timer,
                                  const gptimer_alarm_event_data_t *edata,
                                  void *user_ctx)
{
    BaseType_t higher_woken = pdFALSE;
    xSemaphoreGiveFromISR(s_timer_sem, &higher_woken);
    return higher_woken == pdTRUE;
}

/* ──────────────────────────────────────────────────────────────────────────
 * Core 0 sensor task
 * ────────────────────────────────────────────────────────────────────────*/
static void _sensors_task(void *arg)
{
    ESP_LOGI(TAG, "Sensor task started on Core %d", xPortGetCoreID());

    /* Initialize IMU */
    esp_err_t imu_ret = bmi323_init();
    if (imu_ret == ESP_OK) {
        s_imu_ok = true;
        ESP_LOGI(TAG, "BMI323 ready");
    } else {
        ESP_LOGE(TAG, "BMI323 init failed: %s — IMU rows will be zeroed",
                 esp_err_to_name(imu_ret));
    }

    /* Initialize GPS */
    esp_err_t gps_ret = gps_init();
    if (gps_ret == ESP_OK) {
        ESP_LOGI(TAG, "Neo-M8N GPS ready");
    } else {
        ESP_LOGE(TAG, "GPS init failed: %s — GPS rows will be zeroed",
                 esp_err_to_name(gps_ret));
    }

    s_task_running = true;

    while (s_task_running) {
        /* Wait for 100Hz timer tick (10ms budget) */
        if (xSemaphoreTake(s_timer_sem, pdMS_TO_TICKS(20)) != pdTRUE) {
            /* Timer missed — watchdog will catch sustained overruns */
            continue;
        }

        uint64_t tick = s_tick_count++;
        uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000ULL);

        /* ── Read IMU ──────────────────────────────────────────────────── */
        bmi323_raw_t raw = {0};
        bmi323_data_t imu = {0};
        if (s_imu_ok) {
            if (bmi323_read_raw(&raw) == ESP_OK) {
                bmi323_raw_to_si(&raw, &imu);
                s_latest_imu = raw;  /* lock-free update for UI */
            }
        }

        /* ── GPS tick (every 10th IMU tick = 10Hz) ─────────────────────── */
        bool is_gps_tick = (tick % SENSORS_GPS_EVERY_N == 0);
        bool gps_valid = false;
        if (is_gps_tick) {
            gps_update(32); /* drain up to 32 NMEA lines */
            if (gps_has_fix()) {
                gps_get_fix(&s_latest_gps);
                gps_valid = true;
            }
        }

        /* ── Build and enqueue row ─────────────────────────────────────── */
        if (s_logging) {
            sensor_row_t row = {
                .tick_ms  = now_ms,
                .row_type = is_gps_tick ? ROW_TYPE_GPS : ROW_TYPE_IMU,
                .ax = imu.ax, .ay = imu.ay, .az = imu.az,
                .gx = imu.gx, .gy = imu.gy, .gz = imu.gz,
            };

            if (is_gps_tick) {
                row.lat         = s_latest_gps.lat;
                row.lon         = s_latest_gps.lon;
                row.altitude_m  = s_latest_gps.altitude_m;
                row.speed_kmh   = s_latest_gps.speed_kmh;
                row.satellites  = s_latest_gps.satellites;
                row.vbat        = bsp_battery_get_voltage();
                (void)gps_valid; /* logged regardless — storage filters if needed */
            }

            /* Non-blocking enqueue — if queue is full, row is dropped */
            if (xQueueSendToBack(s_row_queue, &row, 0) != pdTRUE) {
                /* Queue full: storage flush is lagging — not critical for 1 row */
                ESP_LOGD(TAG, "Row queue full — dropped tick %llu", tick);
            }
        }
    }

    ESP_LOGI(TAG, "Sensor task exiting");
    vTaskDelete(NULL);
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t sensors_task_start(void)
{
    if (s_task_handle) return ESP_OK; /* Already running */

    /* Create semaphore for timer→task signaling */
    s_timer_sem = xSemaphoreCreateBinary();
    if (!s_timer_sem) return ESP_ERR_NO_MEM;

    /* Create row queue for Core 0 → Core 1 transfer */
    s_row_queue = xQueueCreate(ROW_QUEUE_DEPTH, sizeof(sensor_row_t));
    if (!s_row_queue) return ESP_ERR_NO_MEM;

    /* Configure gptimer at 100Hz (10ms period, 1MHz resolution) */
    gptimer_config_t timer_cfg = {
        .clk_src       = GPTIMER_CLK_SRC_DEFAULT,
        .direction     = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000, /* 1MHz tick */
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer_cfg, &s_gptimer));

    gptimer_alarm_config_t alarm_cfg = {
        .alarm_count              = 10000, /* 10ms = 100Hz */
        .reload_count             = 0,
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(s_gptimer, &alarm_cfg));

    gptimer_event_callbacks_t cbs = {
        .on_alarm = _timer_isr,
    };
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(s_gptimer, &cbs, NULL));
    ESP_ERROR_CHECK(gptimer_enable(s_gptimer));

    /* Launch sensor task pinned to Core 0 */
    BaseType_t ret = xTaskCreatePinnedToCore(
        _sensors_task,
        "sensors",
        SENSORS_TASK_STACK_SZ,
        NULL,
        SENSORS_TASK_PRIORITY,
        &s_task_handle,
        SENSORS_TASK_CORE
    );
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create sensor task");
        return ESP_FAIL;
    }

    /* Start the hardware timer */
    ESP_ERROR_CHECK(gptimer_start(s_gptimer));
    ESP_LOGI(TAG, "Sensor task started: 100Hz IMU | 10Hz GPS | Queue depth: %d", ROW_QUEUE_DEPTH);
    return ESP_OK;
}

esp_err_t sensors_task_stop(void)
{
    s_task_running = false;
    if (s_gptimer) {
        gptimer_stop(s_gptimer);
        gptimer_disable(s_gptimer);
        gptimer_del_timer(s_gptimer);
        s_gptimer = NULL;
    }
    /* Task self-deletes after s_task_running is false */
    s_task_handle = NULL;
    ESP_LOGI(TAG, "Sensor task stopped");
    return ESP_OK;
}

void sensors_set_logging(bool enable)
{
    s_logging = enable;
    ESP_LOGI(TAG, "Logging %s", enable ? "ENABLED" : "DISABLED");
}

uint32_t sensors_get_tick_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000ULL);
}

uint64_t sensors_get_tick_count(void)
{
    return s_tick_count;
}

void sensors_get_latest_imu(bmi323_raw_t *raw)
{
    if (raw) memcpy(raw, &s_latest_imu, sizeof(*raw));
}

void sensors_get_latest_gps(gps_fix_t *fix)
{
    if (fix) memcpy(fix, &s_latest_gps, sizeof(*fix));
}

bool sensors_imu_ok(void)
{
    return s_imu_ok;
}

bool sensors_gps_ok(void)
{
    return gps_has_fix();
}

bool sensors_dequeue_row(sensor_row_t *row)
{
    if (!row || !s_row_queue) return false;
    return xQueueReceive(s_row_queue, row, 0) == pdTRUE;
}
