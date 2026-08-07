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
#include <stddef.h>
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
    float  tbl_time;              /**< TBL time for this sector, if known */
    float  lap_time;              /**< Complete lap time (lap events)     */
    int    sector_index;          /**< 0-based sector that just completed */
} track_event_t;

/** Callback invoked from track_engine_update_gps() on gate crossings. */
typedef void (*track_event_cb_t)(const track_event_t *evt, void *ctx);

#define TRACK_ENGINE_MAX_SECTORS       16
#define TRACK_ENGINE_MAX_LAYOUT_POINTS 96

typedef struct {
    uint16_t x;
    uint16_t y;
} track_layout_point_t;

typedef struct {
    track_layout_point_t point;
    int sector_index;
} track_layout_marker_t;

/** Display-ready active-track metadata cached from the server payload. */
typedef struct {
    bool has_layout;
    int sector_count;
    float tbl_lap_time;
    float tbl_sector_times[TRACK_ENGINE_MAX_SECTORS];

    int polyline_count;
    track_layout_point_t polyline[TRACK_ENGINE_MAX_LAYOUT_POINTS];
    bool has_start_marker;
    track_layout_point_t start_marker;
    int sector_marker_count;
    track_layout_marker_t sector_markers[TRACK_ENGINE_MAX_SECTORS];

    double min_lat;
    double max_lat;
    double min_lon;
    double max_lon;
} track_display_layout_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Public API
 * ────────────────────────────────────────────────────────────────────────*/

/** @brief Initialize track engine and auto-load track from default path. */
esp_err_t track_engine_init(void);

/** Reset lap/sector state while retaining the loaded track metadata. */
void track_engine_reset_session(void);

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
int          track_engine_get_current_lap_number(void);
const char  *track_engine_get_track_name(void);
const char  *track_engine_get_last_lap_time(void);   /**< "M:SS.mmm" format */
const char  *track_engine_get_last_sector_gap(void); /**< "+0.000" format    */
float        track_engine_get_last_delta_s(void);    /**< Raw delta in secs  */

/** Copy the cached display layout and TBL metadata for the active track. */
bool track_engine_get_display_layout(track_display_layout_t *out);

/** Format the in-progress lap time, or "--.---" before track identification. */
void track_engine_get_current_lap_time(uint32_t tick_ms, char *out, size_t out_len);

#ifdef __cplusplus
}
#endif

#endif /* TRACK_ENGINE_H */
