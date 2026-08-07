/**
 * @file track_engine.c
 * @brief Lap & Sector Timing Engine
 *
 * Ported from the production-proven legacy implementation.
 *
 * Algorithm:
 *   Phase 1 — Track identification: Haversine proximity check against
 *              start_line gate with rectangular pre-filter (0.002° ≈ 220m).
 *   Phase 2 — Sector crossing:      Same Haversine check against each
 *              sector gate in sequence.
 *   Phase 3 — Lap complete:         All sectors crossed → lap time computed
 *              and TBL delta calculated.
 *
 * Track JSON format: /data/metadata/track.json
 *   {
 *     "name": "Buddh International Circuit",
 *     "start_line": {"lat": 28.349, "lon": 77.533, "radius_m": 20},
 *     "sectors": [{"end_lat": ..., "end_lon": ..., "radius_m": 15}, ...],
 *     "tbl":     {"lap_time": 112.5, "sectors": [34.2, 38.1, 40.2]},
 *     "pit_center_lat": ..., "pit_center_lon": ..., "pit_radius_m": 50
 *   }
 */

#include "track_engine.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "cJSON.h"

static const char *TAG = "track_engine";

#define TRACK_FILE_PATH     "/data/metadata/track.json"
#define GATE_RADIUS_M       15.0f
#define MAX_SECTORS         16
#define EARTH_RADIUS_M      6371000.0
#define PRE_FILTER_DEG      0.002  /**< ~220m — skip Haversine if farther */
#define GATE_REARM_MARGIN_M 5.0f
#define GATE_HEADING_TOLERANCE_DEG 100.0f

/* ──────────────────────────────────────────────────────────────────────────
 * Internal track definition
 * ────────────────────────────────────────────────────────────────────────*/
typedef struct {
    double lat, lon;
    float  radius_m;
    float  heading_deg;
    bool   has_heading;
} gate_t;

typedef struct {
    char   name[64];
    gate_t start_line;
    gate_t sectors[MAX_SECTORS];
    int    sector_count;
    float  tbl_sectors[MAX_SECTORS];
    float  tbl_lap_time;
    double pit_lat, pit_lon;
    float  pit_radius_m;
    track_display_layout_t display_layout;
    bool   loaded;
} track_def_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Runtime state
 * ────────────────────────────────────────────────────────────────────────*/
static track_def_t   s_track       = {0};
static bool          s_identified  = false;
static int           s_current_sector = 0;
static int           s_lap_count   = 0;
static uint32_t      s_sector_start_ms = 0;
static uint32_t      s_lap_start_ms    = 0;
static float         s_sector_times[MAX_SECTORS] = {0};
static char          s_last_lap_str[16]   = "0:00.000";
static char          s_last_sector_str[16] = "+0.000";
static float         s_last_delta_s       = 0.0f;
static bool           s_gate_armed         = true;
static bool           s_have_prev_position = false;
static double         s_prev_lat          = 0.0;
static double         s_prev_lon          = 0.0;
static uint32_t       s_prev_tick_ms      = 0;

/* Event callback */
static track_event_cb_t s_event_cb  = NULL;
static void            *s_event_ctx = NULL;

/* ──────────────────────────────────────────────────────────────────────────
 * Internal helpers
 * ────────────────────────────────────────────────────────────────────────*/

/** Haversine distance in metres between two GPS coordinates.
 *  Applies a rectangular pre-filter to skip expensive trig when clearly far. */
static float _haversine_m(double lat1, double lon1, double lat2, double lon2)
{
    /* Fast rectangular pre-filter */
    if (fabs(lat2 - lat1) > PRE_FILTER_DEG || fabs(lon2 - lon1) > PRE_FILTER_DEG) {
        return 99999.0f;
    }
    double lat1r = lat1 * M_PI / 180.0;
    double lat2r = lat2 * M_PI / 180.0;
    double dlat  = (lat2 - lat1) * M_PI / 180.0;
    double dlon  = (lon2 - lon1) * M_PI / 180.0;
    double a = sin(dlat/2)*sin(dlat/2)
             + cos(lat1r)*cos(lat2r)*sin(dlon/2)*sin(dlon/2);
    return (float)(EARTH_RADIUS_M * 2.0 * atan2(sqrt(a), sqrt(1.0 - a)));
}

static void _format_lap_time(float t, char *out, int out_len)
{
    if (t < 0) { snprintf(out, out_len, "--.---"); return; }
    int ms = (int)roundf(t * 1000.0f);
    int m  = ms / 60000;
    int s  = (ms % 60000) / 1000;
    int ms3 = ms % 1000;
    if (m > 0) snprintf(out, out_len, "%d:%02d.%03d", m, s, ms3);
    else       snprintf(out, out_len, "%d.%03d",       s, ms3);
}

static void _format_delta(float delta_s, char *out, int out_len)
{
    if (fabsf(delta_s) < 0.05f) { snprintf(out, out_len, "0.0"); return; }
    if (delta_s > 0) snprintf(out, out_len, "+%.1f", delta_s);
    else             snprintf(out, out_len, "%.1f",  delta_s);
}

/** Determine sector result — mirrors _calc_delta_event() */
static track_event_sub_t _classify_delta(float delta_s, bool has_tbl)
{
    if (!has_tbl) return TRACK_EVT_SECTOR_NEUTRAL;
    if (delta_s <= 0.0f) return TRACK_EVT_SECTOR_FAST;
    if (delta_s <= 1.0f) return TRACK_EVT_SECTOR_NEUTRAL;
    return TRACK_EVT_SECTOR_SLOW;
}

static void _emit(const track_event_t *evt)
{
    if (s_event_cb) s_event_cb(evt, s_event_ctx);
}

static bool _parse_layout_point(cJSON *item, track_layout_point_t *out)
{
    if (!cJSON_IsObject(item) || !out) return false;
    cJSON *x = cJSON_GetObjectItem(item, "x");
    cJSON *y = cJSON_GetObjectItem(item, "y");
    if (!cJSON_IsNumber(x) || !cJSON_IsNumber(y) ||
        x->valuedouble < 0.0 || x->valuedouble > 1000.0 ||
        y->valuedouble < 0.0 || y->valuedouble > 1000.0) {
        return false;
    }
    out->x = (uint16_t)lround(x->valuedouble);
    out->y = (uint16_t)lround(y->valuedouble);
    return true;
}

static bool _parse_layout_bounds(cJSON *item, track_display_layout_t *layout)
{
    if (!cJSON_IsObject(item) || !layout) return false;
    cJSON *min_lat = cJSON_GetObjectItem(item, "min_lat");
    cJSON *max_lat = cJSON_GetObjectItem(item, "max_lat");
    cJSON *min_lon = cJSON_GetObjectItem(item, "min_lon");
    cJSON *max_lon = cJSON_GetObjectItem(item, "max_lon");
    if (!cJSON_IsNumber(min_lat) || !cJSON_IsNumber(max_lat) ||
        !cJSON_IsNumber(min_lon) || !cJSON_IsNumber(max_lon) ||
        !isfinite(min_lat->valuedouble) || !isfinite(max_lat->valuedouble) ||
        !isfinite(min_lon->valuedouble) || !isfinite(max_lon->valuedouble) ||
        min_lat->valuedouble >= max_lat->valuedouble ||
        min_lon->valuedouble >= max_lon->valuedouble) {
        return false;
    }
    layout->min_lat = min_lat->valuedouble;
    layout->max_lat = max_lat->valuedouble;
    layout->min_lon = min_lon->valuedouble;
    layout->max_lon = max_lon->valuedouble;
    return true;
}

static void _parse_display_layout(cJSON *root, track_display_layout_t *layout)
{
    if (!root || !layout) return;
    memset(layout, 0, sizeof(*layout));

    cJSON *device_layout = cJSON_GetObjectItem(root, "device_layout");
    if (!cJSON_IsObject(device_layout)) return;

    cJSON *polyline = cJSON_GetObjectItem(device_layout, "polyline");
    if (!cJSON_IsArray(polyline)) return;
    cJSON *point = NULL;
    cJSON_ArrayForEach(point, polyline) {
        if (layout->polyline_count >= TRACK_ENGINE_MAX_LAYOUT_POINTS) break;
        track_layout_point_t parsed = {0};
        if (_parse_layout_point(point, &parsed)) {
            layout->polyline[layout->polyline_count++] = parsed;
        }
    }

    cJSON *start_marker = cJSON_GetObjectItem(device_layout, "start_marker");
    if (_parse_layout_point(start_marker, &layout->start_marker)) {
        layout->has_start_marker = true;
    }

    cJSON *sector_markers = cJSON_GetObjectItem(device_layout, "sector_markers");
    if (cJSON_IsArray(sector_markers)) {
        int marker_idx = 0;
        cJSON_ArrayForEach(point, sector_markers) {
            if (layout->sector_marker_count >= TRACK_ENGINE_MAX_SECTORS) break;
            track_layout_point_t parsed = {0};
            if (!_parse_layout_point(point, &parsed)) continue;
            track_layout_marker_t *marker =
                &layout->sector_markers[layout->sector_marker_count++];
            marker->point = parsed;
            cJSON *index = cJSON_GetObjectItem(point, "sector_index");
            marker->sector_index = cJSON_IsNumber(index)
                ? (int)index->valuedouble : marker_idx + 1;
            marker_idx++;
        }
    }

    layout->has_layout = layout->polyline_count >= 2 &&
                         _parse_layout_bounds(cJSON_GetObjectItem(device_layout, "bounds"),
                                               layout);
}

/* ──────────────────────────────────────────────────────────────────────────
 * JSON parsing
 * ────────────────────────────────────────────────────────────────────────*/
static bool _parse_gate(cJSON *obj, gate_t *g, float default_radius)
{
    if (!obj || !g) return false;
    cJSON *lat = cJSON_GetObjectItem(obj, "lat");
    cJSON *lon = cJSON_GetObjectItem(obj, "lon");
    cJSON *r   = cJSON_GetObjectItem(obj, "radius_m");
    /* Also handle end_lat/end_lon field names (sector gates) */
    if (!lat) lat = cJSON_GetObjectItem(obj, "end_lat");
    if (!lon) lon = cJSON_GetObjectItem(obj, "end_lon");
    if (!cJSON_IsNumber(lat) || !cJSON_IsNumber(lon)) return false;
    g->lat      = lat->valuedouble;
    g->lon      = lon->valuedouble;
    g->radius_m = cJSON_IsNumber(r) ? (float)r->valuedouble : default_radius;
    if (!isfinite(g->lat) || !isfinite(g->lon) ||
        !isfinite(g->radius_m) || g->radius_m <= 0.0f) return false;

    cJSON *heading = cJSON_GetObjectItem(obj, "heading");
    if (cJSON_IsNumber(heading) && isfinite(heading->valuedouble)) {
        g->heading_deg = (float)heading->valuedouble;
        g->has_heading = true;
    }
    return true;
}

static void _reset_runtime(void)
{
    s_identified         = false;
    s_current_sector     = 0;
    s_lap_count          = 0;
    s_sector_start_ms    = 0;
    s_lap_start_ms       = 0;
    s_gate_armed         = true;
    s_have_prev_position = false;
    s_prev_lat           = 0.0;
    s_prev_lon           = 0.0;
    s_prev_tick_ms       = 0;
    memset(s_sector_times, 0, sizeof(s_sector_times));
    snprintf(s_last_lap_str, sizeof(s_last_lap_str), "0:00.000");
    snprintf(s_last_sector_str, sizeof(s_last_sector_str), "+0.000");
    s_last_delta_s = 0.0f;
}

static void _remember_position(double lat, double lon, uint32_t tick_ms)
{
    s_prev_lat = lat;
    s_prev_lon = lon;
    s_prev_tick_ms = tick_ms;
    s_have_prev_position = true;
}

static double _bearing_deg(double lat1, double lon1, double lat2, double lon2)
{
    const double lat1r = lat1 * M_PI / 180.0;
    const double lat2r = lat2 * M_PI / 180.0;
    const double dlon = (lon2 - lon1) * M_PI / 180.0;
    const double y = sin(dlon) * cos(lat2r);
    const double x = cos(lat1r) * sin(lat2r) -
                     sin(lat1r) * cos(lat2r) * cos(dlon);
    double bearing = atan2(y, x) * 180.0 / M_PI;
    if (bearing < 0.0) bearing += 360.0;
    return bearing;
}

static bool _crossing_direction_ok(const gate_t *gate, double lat, double lon,
                                   uint32_t tick_ms)
{
    if (!gate->has_heading || !s_have_prev_position || tick_ms == s_prev_tick_ms) {
        return true;
    }
    if (_haversine_m(s_prev_lat, s_prev_lon, lat, lon) < 1.0f) return true;

    double bearing = _bearing_deg(s_prev_lat, s_prev_lon, lat, lon);
    double diff = fabs(bearing - gate->heading_deg);
    if (diff > 180.0) diff = 360.0 - diff;
    return diff <= GATE_HEADING_TOLERANCE_DEG;
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t track_engine_init(void)
{
    memset(&s_track, 0, sizeof(s_track));
    _reset_runtime();

    /* Auto-load track on init */
    esp_err_t ret = track_engine_load_track(TRACK_FILE_PATH);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "Track loaded at init: %s (%d sectors)", s_track.name, s_track.sector_count);
    } else {
        ESP_LOGW(TAG, "No track file found — timing inactive until track loaded");
    }
    return ESP_OK;
}

esp_err_t track_engine_load_track(const char *json_path)
{
    const char *path = (json_path && json_path[0]) ? json_path : TRACK_FILE_PATH;
    FILE *f = fopen(path, "r");
    if (!f) return ESP_ERR_NOT_FOUND;

    fseek(f, 0, SEEK_END); long sz = ftell(f); rewind(f);
    if (sz <= 0 || sz > 65536) { fclose(f); return ESP_FAIL; }

    char *buf = malloc(sz + 1);
    if (!buf) { fclose(f); return ESP_ERR_NO_MEM; }
    fread(buf, 1, sz, f); buf[sz] = '\0'; fclose(f);

    cJSON *root = cJSON_Parse(buf);
    free(buf);
    if (!root) return ESP_FAIL;

    memset(&s_track, 0, sizeof(s_track));

    /* Name */
    cJSON *name = cJSON_GetObjectItem(root, "name");
    if (!name) name = cJSON_GetObjectItem(root, "track_name");
    if (name && name->valuestring)
        strncpy(s_track.name, name->valuestring, sizeof(s_track.name) - 1);
    if (!s_track.name[0]) snprintf(s_track.name, sizeof(s_track.name), "Unnamed track");

    /* Start line */
    if (!_parse_gate(cJSON_GetObjectItem(root, "start_line"), &s_track.start_line, 20.0f)) {
        cJSON_Delete(root);
        memset(&s_track, 0, sizeof(s_track));
        return ESP_ERR_INVALID_ARG;
    }

    /* Sectors */
    cJSON *sectors = cJSON_GetObjectItem(root, "sectors");
    if (sectors && cJSON_IsArray(sectors)) {
        cJSON *sec;
        cJSON_ArrayForEach(sec, sectors) {
            if (s_track.sector_count >= MAX_SECTORS) break;
            gate_t parsed = {0};
            if (_parse_gate(sec, &parsed, GATE_RADIUS_M)) {
                s_track.sectors[s_track.sector_count++] = parsed;
            }
        }
    }

    /* TBL (track benchmark lap) */
    cJSON *tbl = cJSON_GetObjectItem(root, "tbl");
    if (tbl) {
        cJSON *lt = cJSON_GetObjectItem(tbl, "lap_time");
        if (lt) s_track.tbl_lap_time = (float)lt->valuedouble;
        cJSON *ts = cJSON_GetObjectItem(tbl, "sectors");
        if (ts && cJSON_IsArray(ts)) {
            int i = 0;
            cJSON *t;
            cJSON_ArrayForEach(t, ts) {
                if (i >= MAX_SECTORS) break;
                s_track.tbl_sectors[i++] = (float)t->valuedouble;
            }
        }
    }

    /* Older server payloads carried only per-sector TBL values.  Recover the
     * theoretical lap target locally so the detail view remains useful even
     * before the device receives a refreshed payload with lap_time. */
    if (s_track.tbl_lap_time <= 0.0f && s_track.sector_count > 0) {
        float sector_total = 0.0f;
        bool complete_tbl = true;
        for (int i = 0; i < s_track.sector_count; ++i) {
            if (s_track.tbl_sectors[i] <= 0.0f) {
                complete_tbl = false;
                break;
            }
            sector_total += s_track.tbl_sectors[i];
        }
        if (complete_tbl) s_track.tbl_lap_time = sector_total;
    }

    /* Pit area */
    cJSON *pit_lat = cJSON_GetObjectItem(root, "pit_center_lat");
    cJSON *pit_lon = cJSON_GetObjectItem(root, "pit_center_lon");
    cJSON *pit_r   = cJSON_GetObjectItem(root, "pit_radius_m");
    if (pit_lat) s_track.pit_lat      = pit_lat->valuedouble;
    if (pit_lon) s_track.pit_lon      = pit_lon->valuedouble;
    s_track.pit_radius_m = pit_r ? (float)pit_r->valuedouble : 50.0f;

    _parse_display_layout(root, &s_track.display_layout);

    cJSON_Delete(root);
    s_track.loaded   = true;
    _reset_runtime();

    ESP_LOGI(TAG, "Track loaded: '%s' — %d sectors, TBL %.3fs",
             s_track.name, s_track.sector_count, s_track.tbl_lap_time);
    return ESP_OK;
}

void track_engine_update_gps(double lat, double lon, uint32_t tick_ms)
{
    if (!s_track.loaded || !isfinite(lat) || !isfinite(lon) ||
        lat < -90.0 || lat > 90.0 || lon < -180.0 || lon > 180.0 ||
        (lat == 0.0 && lon == 0.0)) return;

    /* ── Phase 1: Track identification ─────────────────────────────── */
    if (!s_identified) {
        float d = _haversine_m(lat, lon,
                               s_track.start_line.lat,
                               s_track.start_line.lon);
        if (d < s_track.start_line.radius_m) {
            if (!_crossing_direction_ok(&s_track.start_line, lat, lon, tick_ms)) {
                _remember_position(lat, lon, tick_ms);
                return;
            }
            s_identified      = true;
            s_current_sector  = 0;
            s_sector_start_ms = tick_ms;
            s_lap_start_ms    = tick_ms;
            s_gate_armed      = true;
            ESP_LOGI(TAG, "Track identified: %s", s_track.name);
            track_event_t evt = { .type = TRACK_EVT_FOUND };
            _emit(&evt);
        }
        _remember_position(lat, lon, tick_ms);
        return;
    }

    /* ── Phase 2: Sector gate crossing ───────────────────────────────*/
    if (s_current_sector < s_track.sector_count) {
        gate_t *gate = &s_track.sectors[s_current_sector];
        float dist = _haversine_m(lat, lon, gate->lat, gate->lon);

        if (dist >= gate->radius_m + GATE_REARM_MARGIN_M) {
            s_gate_armed = true;
        }

        if (s_gate_armed && dist < gate->radius_m &&
            _crossing_direction_ok(gate, lat, lon, tick_ms)) {
            /* Compute sector time */
            float sector_time = (tick_ms - s_sector_start_ms) / 1000.0f;
            s_sector_times[s_current_sector] = sector_time;

            /* TBL delta */
            float tbl_t = (s_current_sector < MAX_SECTORS)
                        ? s_track.tbl_sectors[s_current_sector] : 0.0f;
            bool has_tbl = tbl_t > 0.0f;
            float delta = has_tbl ? (sector_time - tbl_t) : 0.0f;
            s_last_delta_s = delta;
            _format_delta(delta, s_last_sector_str, sizeof(s_last_sector_str));

            int sector_idx = s_current_sector;
            s_current_sector++;
            s_sector_start_ms = tick_ms;
            s_gate_armed = true;

            ESP_LOGI(TAG, "Sector %d: %.3fs (TBL %.3fs Δ%+.3fs)",
                     sector_idx + 1, sector_time, tbl_t, delta);

            /* ── Phase 3: Lap complete? ─────────────────────────── */
            if (s_current_sector >= s_track.sector_count) {
                float lap_time = (tick_ms - s_lap_start_ms) / 1000.0f;
                s_lap_count++;
                _format_lap_time(lap_time, s_last_lap_str, sizeof(s_last_lap_str));

                float tbl_lap = s_track.tbl_lap_time;
                bool has_lap_tbl = tbl_lap > 0.0f;
                float lap_delta = has_lap_tbl ? (lap_time - tbl_lap) : 0.0f;
                s_last_delta_s = lap_delta;
                _format_delta(lap_delta, s_last_sector_str, sizeof(s_last_sector_str));

                ESP_LOGI(TAG, "Lap %d complete: %s (Δ%+.3fs)", s_lap_count, s_last_lap_str, lap_delta);

                track_event_t evt = {
                    .type         = TRACK_EVT_LAP,
                    .lap_time     = lap_time,
                    .delta_s      = lap_delta,
                    .sector_index = sector_idx,
                    .sector_time  = sector_time,
                    .tbl_time     = tbl_t,
                };
                evt.sub_type = _classify_delta(lap_delta, has_lap_tbl);
                _emit(&evt);

                /* Reset for next lap */
                s_current_sector = 0;
                s_lap_start_ms   = tick_ms;
                memset(s_sector_times, 0, sizeof(s_sector_times));
            } else {
                track_event_t evt = {
                    .type         = TRACK_EVT_SECTOR,
                    .sub_type     = _classify_delta(delta, has_tbl),
                    .delta_s      = delta,
                    .sector_time  = sector_time,
                    .tbl_time     = tbl_t,
                    .sector_index = sector_idx,
                };
                _emit(&evt);
            }
        }
    }

    _remember_position(lat, lon, tick_ms);
}

void track_engine_reset_session(void)
{
    if (s_track.loaded) _reset_runtime();
}

esp_err_t track_engine_set_event_cb(track_event_cb_t cb, void *ctx)
{
    s_event_cb  = cb;
    s_event_ctx = ctx;
    return ESP_OK;
}

bool          track_engine_is_track_found(void)       { return s_identified; }
int           track_engine_get_lap_count(void)         { return s_lap_count; }
int           track_engine_get_current_lap_number(void)
{
    return s_identified ? (s_lap_count + 1) : 0;
}
const char   *track_engine_get_track_name(void)
{
    return (s_track.loaded && s_track.name[0]) ? s_track.name : "NO TRACK";
}
const char   *track_engine_get_last_lap_time(void)    { return s_last_lap_str; }
const char   *track_engine_get_last_sector_gap(void)  { return s_last_sector_str; }
float         track_engine_get_last_delta_s(void)     { return s_last_delta_s; }

bool track_engine_get_display_layout(track_display_layout_t *out)
{
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    if (!s_track.loaded) return false;

    *out = s_track.display_layout;
    out->sector_count = s_track.sector_count;
    out->tbl_lap_time = s_track.tbl_lap_time;
    memcpy(out->tbl_sector_times, s_track.tbl_sectors,
           sizeof(out->tbl_sector_times));
    return out->has_layout;
}

void track_engine_get_current_lap_time(uint32_t tick_ms, char *out, size_t out_len)
{
    if (!out || out_len == 0) return;
    if (!s_identified) {
        snprintf(out, out_len, "--.---");
        return;
    }
    float elapsed = (tick_ms - s_lap_start_ms) / 1000.0f;
    _format_lap_time(elapsed, out, (int)out_len);
}
