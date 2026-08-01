/**
 * @file track_engine.h
 * @brief Lap and Sector Timing Logic Component Header
 *
 * Track JSON schema: /data/metadata/track.json
 * Events emitted via callback registered with track_engine_set_event_cb().
 */

#ifndef TRACK_ENGINE_H
#define TRACK_ENGINE_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Event types
 * ────────────────────────────────────────────────────────────────────────*/
typedef enum {
    TRACK_EVT_FOUND,          /**< Track start line crossed for first time */
    TRACK_EVT_SECTOR,         /**< Sector gate crossed (not final)         */
    TRACK_EVT_LAP,            /**< All sectors done — lap complete         */
} track_event_type_t;

typedef enum {
    TRACK_EVT_SECTOR_FAST,    /**< delta_s ≤ 0   — green                  */
    TRACK_EVT_SECTOR_NEUTRAL, /**< delta_s ≤ 1.0 — orange                 */
    TRACK_EVT_SECTOR_SLOW,    /**< delta_s > 1.0 — red                    */
} track_event_sub_t;

typedef struct {
    track_event_type_t type;
    track_event_sub_t  sub_type;  /**< Speed classification (sector/lap) */
    float  delta_s;               /**< vs. TBL: positive = slower        */
    float  sector_time;           /**< This sector's elapsed seconds      */
    float  lap_time;              /**< Complete lap time (lap events)     */
    int    sector_index;          /**< 0-based sector that just completed */
} track_event_t;

/** Callback invoked from track_engine_update_gps() on gate crossings. */
typedef void (*track_event_cb_t)(const track_event_t *evt, void *ctx);

/* ──────────────────────────────────────────────────────────────────────────
 * Public API
 * ────────────────────────────────────────────────────────────────────────*/

/** @brief Initialize track engine and auto-load track from default path. */
esp_err_t track_engine_init(void);

/** @brief Load track geometry and TBL from JSON file. */
esp_err_t track_engine_load_track(const char *json_path);

/** @brief Register event callback for sector/lap crossing notifications. */
esp_err_t track_engine_set_event_cb(track_event_cb_t cb, void *ctx);

/**
 * @brief Update engine with latest GPS coordinate. Call at 10Hz from GPS task.
 * May invoke the registered event callback synchronously.
 */
void track_engine_update_gps(double lat, double lon, uint32_t tick_ms);

bool         track_engine_is_track_found(void);
int          track_engine_get_lap_count(void);
const char  *track_engine_get_last_lap_time(void);   /**< "M:SS.mmm" format */
const char  *track_engine_get_last_sector_gap(void); /**< "+0.000" format    */
float        track_engine_get_last_delta_s(void);    /**< Raw delta in secs  */

#ifdef __cplusplus
}
#endif

#endif /* TRACK_ENGINE_H */
