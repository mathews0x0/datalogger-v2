/**
 * @file track_engine.c
 * @brief Lap & Sector Timing Engine
 *
 * Ported from firmware_s3/firmware/lib/track_engine.py (production-proven).
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

/* ──────────────────────────────────────────────────────────────────────────
 * Internal track definition
 * ────────────────────────────────────────────────────────────────────────*/
typedef struct {
    double lat, lon;
    float  radius_m;
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
static track_event_type_t _classify_delta(float delta_s)
{
    if (delta_s <= 0.0f) return TRACK_EVT_SECTOR_FAST;
    if (delta_s <= 1.0f) return TRACK_EVT_SECTOR_NEUTRAL;
    return TRACK_EVT_SECTOR_SLOW;
}

static void _emit(const track_event_t *evt)
{
    if (s_event_cb) s_event_cb(evt, s_event_ctx);
}

/* ──────────────────────────────────────────────────────────────────────────
 * JSON parsing
 * ────────────────────────────────────────────────────────────────────────*/
static void _parse_gate(cJSON *obj, gate_t *g, float default_radius)
{
    if (!obj) return;
    cJSON *lat = cJSON_GetObjectItem(obj, "lat");
    cJSON *lon = cJSON_GetObjectItem(obj, "lon");
    cJSON *r   = cJSON_GetObjectItem(obj, "radius_m");
    /* Also handle end_lat/end_lon field names (sector gates) */
    if (!lat) lat = cJSON_GetObjectItem(obj, "end_lat");
    if (!lon) lon = cJSON_GetObjectItem(obj, "end_lon");
    if (lat) g->lat      = lat->valuedouble;
    if (lon) g->lon      = lon->valuedouble;
    g->radius_m = r ? (float)r->valuedouble : default_radius;
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t track_engine_init(void)
{
    memset(&s_track, 0, sizeof(s_track));
    s_identified     = false;
    s_current_sector = 0;
    s_lap_count      = 0;
    s_sector_start_ms = 0;
    s_lap_start_ms   = 0;
    memset(s_sector_times, 0, sizeof(s_sector_times));
    snprintf(s_last_lap_str,    sizeof(s_last_lap_str),    "0:00.000");
    snprintf(s_last_sector_str, sizeof(s_last_sector_str), "+0.000");

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

    /* Start line */
    _parse_gate(cJSON_GetObjectItem(root, "start_line"), &s_track.start_line, 20.0f);

    /* Sectors */
    cJSON *sectors = cJSON_GetObjectItem(root, "sectors");
    if (sectors && cJSON_IsArray(sectors)) {
        cJSON *sec;
        cJSON_ArrayForEach(sec, sectors) {
            if (s_track.sector_count >= MAX_SECTORS) break;
            _parse_gate(sec, &s_track.sectors[s_track.sector_count], GATE_RADIUS_M);
            s_track.sector_count++;
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

    /* Pit area */
    cJSON *pit_lat = cJSON_GetObjectItem(root, "pit_center_lat");
    cJSON *pit_lon = cJSON_GetObjectItem(root, "pit_center_lon");
    cJSON *pit_r   = cJSON_GetObjectItem(root, "pit_radius_m");
    if (pit_lat) s_track.pit_lat      = pit_lat->valuedouble;
    if (pit_lon) s_track.pit_lon      = pit_lon->valuedouble;
    s_track.pit_radius_m = pit_r ? (float)pit_r->valuedouble : 50.0f;

    cJSON_Delete(root);
    s_track.loaded   = true;
    s_identified     = false;
    s_current_sector = 0;
    s_lap_count      = 0;

    ESP_LOGI(TAG, "Track loaded: '%s' — %d sectors, TBL %.3fs",
             s_track.name, s_track.sector_count, s_track.tbl_lap_time);
    return ESP_OK;
}

void track_engine_update_gps(double lat, double lon, uint32_t tick_ms)
{
    if (!s_track.loaded || lat == 0.0 || lon == 0.0) return;

    /* ── Phase 1: Track identification ─────────────────────────────── */
    if (!s_identified) {
        float d = _haversine_m(lat, lon,
                               s_track.start_line.lat,
                               s_track.start_line.lon);
        if (d < s_track.start_line.radius_m) {
            s_identified      = true;
            s_current_sector  = 0;
            s_sector_start_ms = tick_ms;
            s_lap_start_ms    = tick_ms;
            ESP_LOGI(TAG, "Track identified: %s", s_track.name);
            track_event_t evt = { .type = TRACK_EVT_FOUND };
            _emit(&evt);
        }
        return;
    }

    /* ── Phase 2: Sector gate crossing ───────────────────────────────*/
    if (s_current_sector < s_track.sector_count) {
        gate_t *gate = &s_track.sectors[s_current_sector];
        float dist = _haversine_m(lat, lon, gate->lat, gate->lon);

        if (dist < gate->radius_m) {
            /* Compute sector time */
            float sector_time = (tick_ms - s_sector_start_ms) / 1000.0f;
            s_sector_times[s_current_sector] = sector_time;

            /* TBL delta */
            float tbl_t = (s_current_sector < MAX_SECTORS)
                        ? s_track.tbl_sectors[s_current_sector] : 0.0f;
            float delta = (tbl_t > 0) ? (sector_time - tbl_t) : 0.0f;
            s_last_delta_s = delta;
            _format_delta(delta, s_last_sector_str, sizeof(s_last_sector_str));

            int sector_idx = s_current_sector;
            s_current_sector++;
            s_sector_start_ms = tick_ms;

            ESP_LOGI(TAG, "Sector %d: %.3fs (TBL %.3fs Δ%+.3fs)",
                     sector_idx + 1, sector_time, tbl_t, delta);

            /* ── Phase 3: Lap complete? ─────────────────────────── */
            if (s_current_sector >= s_track.sector_count) {
                float lap_time = (tick_ms - s_lap_start_ms) / 1000.0f;
                s_lap_count++;
                _format_lap_time(lap_time, s_last_lap_str, sizeof(s_last_lap_str));

                float tbl_lap = s_track.tbl_lap_time;
                float lap_delta = (tbl_lap > 0) ? (lap_time - tbl_lap) : 0.0f;

                ESP_LOGI(TAG, "Lap %d complete: %s (Δ%+.3fs)", s_lap_count, s_last_lap_str, lap_delta);

                track_event_t evt = {
                    .type         = TRACK_EVT_LAP,
                    .lap_time     = lap_time,
                    .delta_s      = lap_delta,
                    .sector_index = sector_idx,
                    .sector_time  = sector_time,
                };
                evt.sub_type = _classify_delta(lap_delta);
                _emit(&evt);

                /* Reset for next lap */
                s_current_sector = 0;
                s_lap_start_ms   = tick_ms;
                memset(s_sector_times, 0, sizeof(s_sector_times));
            } else {
                track_event_t evt = {
                    .type         = TRACK_EVT_SECTOR,
                    .sub_type     = _classify_delta(delta),
                    .delta_s      = delta,
                    .sector_time  = sector_time,
                    .sector_index = sector_idx,
                };
                _emit(&evt);
            }
        }
    }
}

esp_err_t track_engine_set_event_cb(track_event_cb_t cb, void *ctx)
{
    s_event_cb  = cb;
    s_event_ctx = ctx;
    return ESP_OK;
}

bool          track_engine_is_track_found(void)       { return s_identified; }
int           track_engine_get_lap_count(void)         { return s_lap_count; }
const char   *track_engine_get_last_lap_time(void)    { return s_last_lap_str; }
const char   *track_engine_get_last_sector_gap(void)  { return s_last_sector_str; }
float         track_engine_get_last_delta_s(void)     { return s_last_delta_s; }
