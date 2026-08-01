/**
 * @file imu_calibration.c
 * @brief 6-Stage IMU Mount Calibration Solver
 *
 * Ported from firmware_s3/firmware/lib/imu_calibration.py (production-proven).
 *
 * Stage → Accumulator mapping:
 *   0  STATIC  — bike upright, engine off       → up_vector + gyro_bias
 *   1  ENGINE  — engine idling                  → vibration fingerprint
 *   2  LEAN_L  — 45° left lean                  → lateral vector (left)
 *   3  LEAN_R  — 45° right lean                 → lateral vector (right)
 *   4  PUSH    — roll forward 3m on level ground → forward_vector (+X)
 *   5  VERIFY  — triggers imu_cal_compute_profile()
 *
 * Output: 3×3 rotation matrix [forward | lateral | up] saved as JSON to
 *   /data/metadata/imu_profiles.json  (same schema as S3 firmware)
 */

#include "imu_calibration.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <math.h>
#include <sys/stat.h>
#include "esp_log.h"
#include "cJSON.h"

static const char *TAG = "imu_cal";

/* ──────────────────────────────────────────────────────────────────────────
 * Constants
 * ────────────────────────────────────────────────────────────────────────*/
#define IMU_CAL_PROFILES_PATH   "/data/metadata/imu_profiles.json"
#define IMU_CAL_VERSION         1
#define IMU_MAX_SAMPLES         150     /**< Per-stage sample ceiling         */
#define IMU_NUM_STAGES          5       /**< Stages 0-4 (verify is stage 5)   */

/* ──────────────────────────────────────────────────────────────────────────
 * Internal types
 * ────────────────────────────────────────────────────────────────────────*/
typedef struct {
    float ax, ay, az;
    float gx, gy, gz;
} imu_sample_t;

typedef struct {
    imu_sample_t buf[IMU_MAX_SAMPLES];
    int          count;
} stage_buf_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Module state
 * ────────────────────────────────────────────────────────────────────────*/
static stage_buf_t   s_stages[IMU_NUM_STAGES];
static int           s_active_stage = 0;
static bool          s_computed     = false;

/* Solved profile — written by imu_cal_compute_profile() */
static float  s_rotation[3][3];   /**< [forward_vec, lateral_vec, up_vec]   */
static float  s_gyro_bias[3];
static float  s_gravity[3];
static float  s_mount_pitch_deg;
static float  s_mount_roll_deg;
static float  s_quality_score;
static char   s_active_label[32];

/* ──────────────────────────────────────────────────────────────────────────
 * Internal math helpers  (mirrors Python: _normalize, _dot, _cross, _project)
 * ────────────────────────────────────────────────────────────────────────*/

static void _normalize(const float v[3], float out[3], const float fallback[3])
{
    float mag = sqrtf(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
    if (mag < 1e-9f) {
        if (fallback) { out[0]=fallback[0]; out[1]=fallback[1]; out[2]=fallback[2]; }
        else          { out[0]=0; out[1]=0; out[2]=1; }
        return;
    }
    out[0] = v[0]/mag;  out[1] = v[1]/mag;  out[2] = v[2]/mag;
}

static float _dot(const float a[3], const float b[3])
{
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}

static void _cross(const float a[3], const float b[3], float out[3])
{
    out[0] = a[1]*b[2] - a[2]*b[1];
    out[1] = a[2]*b[0] - a[0]*b[2];
    out[2] = a[0]*b[1] - a[1]*b[0];
}

static void _project_plane(const float v[3], const float normal[3], float out[3])
{
    float scale = _dot(v, normal);
    out[0] = v[0] - scale*normal[0];
    out[1] = v[1] - scale*normal[1];
    out[2] = v[2] - scale*normal[2];
}

/** Mean of ax/ay/az or gx/gy/gz across a stage buffer */
static void _mean_acc(const stage_buf_t *s, float out[3])
{
    out[0] = out[1] = out[2] = 0.0f;
    if (!s->count) return;
    for (int i = 0; i < s->count; i++) {
        out[0] += s->buf[i].ax;
        out[1] += s->buf[i].ay;
        out[2] += s->buf[i].az;
    }
    out[0] /= s->count; out[1] /= s->count; out[2] /= s->count;
}

static void _mean_gyro(const stage_buf_t *s, float out[3])
{
    out[0] = out[1] = out[2] = 0.0f;
    if (!s->count) return;
    for (int i = 0; i < s->count; i++) {
        out[0] += s->buf[i].gx;
        out[1] += s->buf[i].gy;
        out[2] += s->buf[i].gz;
    }
    out[0] /= s->count; out[1] /= s->count; out[2] /= s->count;
}

/** RMS of acc components (for vibration fingerprint) */
static void _rms_acc(const stage_buf_t *s, float out[3])
{
    out[0] = out[1] = out[2] = 0.0f;
    if (!s->count) return;
    for (int i = 0; i < s->count; i++) {
        out[0] += s->buf[i].ax * s->buf[i].ax;
        out[1] += s->buf[i].ay * s->buf[i].ay;
        out[2] += s->buf[i].az * s->buf[i].az;
    }
    out[0] = sqrtf(out[0]/s->count);
    out[1] = sqrtf(out[1]/s->count);
    out[2] = sqrtf(out[2]/s->count);
}

/* ──────────────────────────────────────────────────────────────────────────
 * Filesystem helpers
 * ────────────────────────────────────────────────────────────────────────*/
static void _ensure_dir(void)
{
    mkdir("/data", 0755);
    mkdir("/data/metadata", 0755);
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t imu_cal_init(void)
{
    memset(s_stages, 0, sizeof(s_stages));
    s_active_stage   = 0;
    s_computed       = false;
    s_quality_score  = 0.0f;
    s_mount_pitch_deg = 0.0f;
    s_mount_roll_deg  = 0.0f;
    memset(s_rotation,  0, sizeof(s_rotation));
    memset(s_gyro_bias, 0, sizeof(s_gyro_bias));
    memset(s_gravity,   0, sizeof(s_gravity));
    ESP_LOGI(TAG, "IMU calibration solver initialised (%d stages, %d sample cap)",
             IMU_NUM_STAGES, IMU_MAX_SAMPLES);
    return ESP_OK;
}

esp_err_t imu_cal_start_stage(int stage)
{
    if (stage < 0 || stage >= IMU_NUM_STAGES) {
        ESP_LOGW(TAG, "Invalid stage %d (valid 0-%d)", stage, IMU_NUM_STAGES - 1);
        return ESP_ERR_INVALID_ARG;
    }
    s_active_stage = stage;
    memset(&s_stages[stage], 0, sizeof(stage_buf_t));
    s_computed = false;
    ESP_LOGI(TAG, "Stage %d started — buffer cleared", stage);
    return ESP_OK;
}

esp_err_t imu_cal_collect_sample(float ax, float ay, float az,
                                  float gx, float gy, float gz)
{
    stage_buf_t *s = &s_stages[s_active_stage];
    if (s->count >= IMU_MAX_SAMPLES) {
        return ESP_ERR_NO_MEM; /* buffer full — caller should call start_stage or compute */
    }
    imu_sample_t *sample = &s->buf[s->count++];
    sample->ax = ax; sample->ay = ay; sample->az = az;
    sample->gx = gx; sample->gy = gy; sample->gz = gz;
    return ESP_OK;
}

int imu_cal_get_sample_count(void)
{
    return s_stages[s_active_stage].count;
}

esp_err_t imu_cal_compute_profile(void)
{
    /* ── Compute per-stage means ─────────────────────────────────────── */
    float static_acc[3], engine_acc[3], left_acc[3], right_acc[3], push_acc[3];
    float static_gyro[3];
    float static_rms[3], engine_rms[3];

    _mean_acc (&s_stages[0], static_acc);
    _mean_gyro(&s_stages[0], static_gyro);
    _rms_acc  (&s_stages[0], static_rms);
    _mean_acc (&s_stages[1], engine_acc);
    _rms_acc  (&s_stages[1], engine_rms);
    _mean_acc (&s_stages[2], left_acc);
    _mean_acc (&s_stages[3], right_acc);
    _mean_acc (&s_stages[4], push_acc);

    /* ── 1. Up vector: normalised static gravity direction ───────────── */
    static const float up_fallback[3]  = {0,0,1};
    static const float fwd_fallback[3] = {1,0,0};
    static const float lat_fallback[3] = {0,1,0};

    float up_vec[3];
    _normalize(static_acc, up_vec, up_fallback);

    /* ── 2. Forward vector: push delta projected onto horizontal plane ── */
    float push_delta[3] = {
        push_acc[0] - static_acc[0],
        push_acc[1] - static_acc[1],
        push_acc[2] - static_acc[2],
    };
    float push_horiz[3];
    _project_plane(push_delta, up_vec, push_horiz);
    float forward_vec[3];
    _normalize(push_horiz, forward_vec, fwd_fallback);

    /* ── 3. Lateral vector: lean delta projected onto horizontal plane ── */
    float lean_delta[3] = {
        left_acc[0] - right_acc[0],
        left_acc[1] - right_acc[1],
        left_acc[2] - right_acc[2],
    };
    float lateral_raw[3];
    _project_plane(lean_delta, up_vec, lateral_raw);
    float lateral_vec[3];

    /* Fall back to cross product if lean is nearly parallel to forward */
    if (fabsf(_dot(lateral_raw, forward_vec)) > 0.75f * sqrtf(
            lateral_raw[0]*lateral_raw[0] + lateral_raw[1]*lateral_raw[1] + lateral_raw[2]*lateral_raw[2])) {
        float tmp[3];
        _cross(up_vec, forward_vec, tmp);
        _normalize(tmp, lateral_vec, lat_fallback);
    } else {
        _normalize(lateral_raw, lateral_vec, lat_fallback);
    }

    /* Ensure left-lean gives positive lateral projection */
    if (_dot(left_acc, lateral_vec) < _dot(right_acc, lateral_vec)) {
        lateral_vec[0] = -lateral_vec[0];
        lateral_vec[1] = -lateral_vec[1];
        lateral_vec[2] = -lateral_vec[2];
    }
    /* Recompute forward so axes are exactly orthogonal */
    float tmp[3];
    _cross(lateral_vec, up_vec, tmp);
    _normalize(tmp, forward_vec, fwd_fallback);

    /* ── 4. Store rotation matrix [forward | lateral | up] ───────────── */
    memcpy(s_rotation[0], forward_vec,  sizeof(float)*3);
    memcpy(s_rotation[1], lateral_vec,  sizeof(float)*3);
    memcpy(s_rotation[2], up_vec,       sizeof(float)*3);
    memcpy(s_gyro_bias,   static_gyro,  sizeof(float)*3);
    memcpy(s_gravity,     static_acc,   sizeof(float)*3);

    /* ── 5. Mount tilt angles ────────────────────────────────────────── */
    /* sensor_x_bike = [fwd·sensor_x, lat·sensor_x, up·sensor_x] */
    float sx_bike[3] = { forward_vec[0], lateral_vec[0], up_vec[0] };
    float sy_bike[3] = { forward_vec[1], lateral_vec[1], up_vec[1] };
    s_mount_pitch_deg = (180.0f / M_PI) *
        atan2f(sx_bike[2], fmaxf(0.1f, sx_bike[0]));
    s_mount_roll_deg  = (180.0f / M_PI) *
        atan2f(sy_bike[2], fmaxf(0.1f, fabsf(sy_bike[1]) > 0.1f ? sy_bike[1] : 1.0f));

    /* ── 6. Quality score ────────────────────────────────────────────── */
    float push_mag  = sqrtf(push_horiz[0]*push_horiz[0] + push_horiz[1]*push_horiz[1] + push_horiz[2]*push_horiz[2]);
    float lean_mag  = sqrtf(lean_delta[0]*lean_delta[0] + lean_delta[1]*lean_delta[1] + lean_delta[2]*lean_delta[2]);
    float vib_delta[3] = {
        fmaxf(0.0f, engine_rms[0] - static_rms[0]),
        fmaxf(0.0f, engine_rms[1] - static_rms[1]),
        fmaxf(0.0f, engine_rms[2] - static_rms[2]),
    };
    float vib_mag = sqrtf(vib_delta[0]*vib_delta[0] + vib_delta[1]*vib_delta[1] + vib_delta[2]*vib_delta[2]);
    float q = 0.45f
            + fminf(0.25f, push_mag * 4.0f)
            + fminf(0.20f, lean_mag * 0.8f)
            - fminf(0.12f, vib_mag  * 0.08f);
    s_quality_score = fmaxf(0.0f, fminf(1.0f, q));

    s_computed = true;
    ESP_LOGI(TAG, "Profile computed: pitch=%.2f° roll=%.2f° quality=%.3f",
             s_mount_pitch_deg, s_mount_roll_deg, s_quality_score);
    ESP_LOGI(TAG, "  forward=[%.4f,%.4f,%.4f]", forward_vec[0], forward_vec[1], forward_vec[2]);
    ESP_LOGI(TAG, "  lateral=[%.4f,%.4f,%.4f]", lateral_vec[0], lateral_vec[1], lateral_vec[2]);
    ESP_LOGI(TAG, "  up     =[%.4f,%.4f,%.4f]", up_vec[0],      up_vec[1],      up_vec[2]);
    return ESP_OK;
}

esp_err_t imu_cal_save_profile(const char *label)
{
    if (!s_computed) {
        ESP_LOGE(TAG, "Cannot save — profile not yet computed");
        return ESP_ERR_INVALID_STATE;
    }

    const char *lbl = (label && label[0]) ? label : "generic";
    strncpy(s_active_label, lbl, sizeof(s_active_label) - 1);

    _ensure_dir();

    /* ── Load existing store ─────────────────────────────────────────── */
    cJSON *store = NULL;
    {
        FILE *f = fopen(IMU_CAL_PROFILES_PATH, "r");
        if (f) {
            fseek(f, 0, SEEK_END);
            long sz = ftell(f); rewind(f);
            if (sz > 0 && sz < 65536) {
                char *buf = malloc(sz + 1);
                if (buf) { fread(buf, 1, sz, f); buf[sz] = '\0'; store = cJSON_Parse(buf); free(buf); }
            }
            fclose(f);
        }
    }
    if (!store || !cJSON_IsObject(store)) {
        cJSON_Delete(store);
        store = cJSON_CreateObject();
        cJSON_AddNumberToObject(store, "version", IMU_CAL_VERSION);
        cJSON_AddStringToObject(store, "selected_profile_id", lbl);
        cJSON_AddArrayToObject(store, "profiles");
    }

    /* ── Build profile JSON object ────────────────────────────────────  */
    cJSON *profile = cJSON_CreateObject();
    cJSON_AddStringToObject(profile, "id",    lbl);
    cJSON_AddStringToObject(profile, "label", lbl);
    cJSON_AddNumberToObject(profile, "calibration_version", IMU_CAL_VERSION);

    /* rotation_matrix as [[f],[l],[u]] */
    cJSON *mat = cJSON_CreateArray();
    for (int r = 0; r < 3; r++) {
        cJSON *row = cJSON_CreateArray();
        for (int c = 0; c < 3; c++) cJSON_AddItemToArray(row, cJSON_CreateNumber(s_rotation[r][c]));
        cJSON_AddItemToArray(mat, row);
    }
    cJSON_AddItemToObject(profile, "rotation_matrix", mat);

    cJSON *gb = cJSON_CreateArray();
    for (int i = 0; i < 3; i++) cJSON_AddItemToArray(gb, cJSON_CreateNumber(s_gyro_bias[i]));
    cJSON_AddItemToObject(profile, "gyro_bias", gb);

    cJSON *gv = cJSON_CreateArray();
    for (int i = 0; i < 3; i++) cJSON_AddItemToArray(gv, cJSON_CreateNumber(s_gravity[i]));
    cJSON_AddItemToObject(profile, "gravity_vector", gv);

    cJSON *tilt = cJSON_CreateObject();
    cJSON_AddNumberToObject(tilt, "pitch_deg", s_mount_pitch_deg);
    cJSON_AddNumberToObject(tilt, "roll_deg",  s_mount_roll_deg);
    cJSON_AddItemToObject(profile, "mount_tilt", tilt);

    cJSON_AddNumberToObject(profile, "quality_score", s_quality_score);

    /* ── Upsert into profiles array ──────────────────────────────────── */
    cJSON *profiles = cJSON_GetObjectItem(store, "profiles");
    if (!profiles) { profiles = cJSON_AddArrayToObject(store, "profiles"); }

    bool updated = false;
    cJSON *existing;
    cJSON_ArrayForEach(existing, profiles) {
        cJSON *id_obj = cJSON_GetObjectItem(existing, "id");
        if (id_obj && strcmp(id_obj->valuestring, lbl) == 0) {
            /* Replace in-place */
            int idx = 0;
            cJSON *it; cJSON_ArrayForEach(it, profiles) { if (it == existing) break; idx++; }
            cJSON_ReplaceItemInArray(profiles, idx, profile);
            updated = true;
            break;
        }
    }
    if (!updated) cJSON_AddItemToArray(profiles, profile);

    /* Update selected_profile_id */
    cJSON *sel = cJSON_GetObjectItem(store, "selected_profile_id");
    if (sel) cJSON_SetValuestring(sel, lbl);
    else     cJSON_AddStringToObject(store, "selected_profile_id", lbl);

    /* ── Atomic write via tmp file ────────────────────────────────────  */
    char tmp_path[64];
    snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", IMU_CAL_PROFILES_PATH);

    char *json_str = cJSON_Print(store);
    cJSON_Delete(store);
    if (!json_str) return ESP_ERR_NO_MEM;

    FILE *f = fopen(tmp_path, "w");
    if (!f) { free(json_str); return ESP_FAIL; }
    fputs(json_str, f);
    fclose(f);
    free(json_str);

    remove(IMU_CAL_PROFILES_PATH);
    rename(tmp_path, IMU_CAL_PROFILES_PATH);

    ESP_LOGI(TAG, "Profile '%s' saved to %s", lbl, IMU_CAL_PROFILES_PATH);
    return ESP_OK;
}

esp_err_t imu_cal_load_profiles(const char *json_path)
{
    const char *path = (json_path && json_path[0]) ? json_path : IMU_CAL_PROFILES_PATH;
    FILE *f = fopen(path, "r");
    if (!f) {
        ESP_LOGW(TAG, "No calibration file at %s — using identity matrix", path);
        /* Identity rotation (no mount offset) */
        memset(s_rotation, 0, sizeof(s_rotation));
        s_rotation[0][0] = 1; s_rotation[1][1] = 1; s_rotation[2][2] = 1;
        s_mount_pitch_deg = 0; s_mount_roll_deg = 0; s_quality_score = 0;
        return ESP_ERR_NOT_FOUND;
    }
    fseek(f, 0, SEEK_END); long sz = ftell(f); rewind(f);
    if (sz <= 0 || sz > 65536) { fclose(f); return ESP_FAIL; }

    char *buf = malloc(sz + 1);
    if (!buf) { fclose(f); return ESP_ERR_NO_MEM; }
    fread(buf, 1, sz, f); buf[sz] = '\0'; fclose(f);

    cJSON *store = cJSON_Parse(buf);
    free(buf);
    if (!store) return ESP_FAIL;

    /* Find selected profile */
    cJSON *sel_id  = cJSON_GetObjectItem(store, "selected_profile_id");
    cJSON *profiles = cJSON_GetObjectItem(store, "profiles");
    if (!sel_id || !profiles) { cJSON_Delete(store); return ESP_ERR_NOT_FOUND; }

    const char *wanted = sel_id->valuestring;
    cJSON *profile = NULL;
    cJSON *it;
    cJSON_ArrayForEach(it, profiles) {
        cJSON *id_obj = cJSON_GetObjectItem(it, "id");
        if (id_obj && strcmp(id_obj->valuestring, wanted) == 0) { profile = it; break; }
    }
    if (!profile) { cJSON_Delete(store); return ESP_ERR_NOT_FOUND; }

    /* Extract rotation_matrix */
    cJSON *mat = cJSON_GetObjectItem(profile, "rotation_matrix");
    if (mat && cJSON_IsArray(mat)) {
        int r = 0;
        cJSON *row;
        cJSON_ArrayForEach(row, mat) {
            if (r >= 3) break;
            int c = 0;
            cJSON *val;
            cJSON_ArrayForEach(val, row) {
                if (c >= 3) break;
                s_rotation[r][c] = (float)val->valuedouble;
                c++;
            }
            r++;
        }
    }

    /* Extract tilt and quality */
    cJSON *tilt = cJSON_GetObjectItem(profile, "mount_tilt");
    if (tilt) {
        cJSON *p = cJSON_GetObjectItem(tilt, "pitch_deg");
        cJSON *ro = cJSON_GetObjectItem(tilt, "roll_deg");
        if (p)  s_mount_pitch_deg = (float)p->valuedouble;
        if (ro) s_mount_roll_deg  = (float)ro->valuedouble;
    }
    cJSON *qs = cJSON_GetObjectItem(profile, "quality_score");
    if (qs) s_quality_score = (float)qs->valuedouble;

    strncpy(s_active_label, wanted, sizeof(s_active_label) - 1);
    s_computed = true;

    ESP_LOGI(TAG, "Loaded profile '%s': pitch=%.2f° roll=%.2f° quality=%.3f",
             wanted, s_mount_pitch_deg, s_mount_roll_deg, s_quality_score);

    cJSON_Delete(store);
    return ESP_OK;
}

float imu_cal_get_mount_pitch(void)   { return s_mount_pitch_deg; }
float imu_cal_get_mount_roll(void)    { return s_mount_roll_deg;  }
float imu_cal_get_quality_score(void) { return s_quality_score;   }

void imu_cal_get_rotation_matrix(float out[3][3])
{
    memcpy(out, s_rotation, sizeof(s_rotation));
}
