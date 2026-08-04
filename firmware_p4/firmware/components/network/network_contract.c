#include "network_contract.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cJSON.h"

#define NETWORK_TRACK_MAX_SECTORS 16

static void _trim_trailing_slashes(char *value)
{
    size_t len = strlen(value);
    while (len > 0 && value[len - 1] == '/') {
        value[--len] = '\0';
    }
}

static bool _strip_suffix(char *value, const char *suffix)
{
    size_t value_len = strlen(value);
    size_t suffix_len = strlen(suffix);
    if (value_len < suffix_len ||
        strcmp(value + value_len - suffix_len, suffix) != 0) {
        return false;
    }
    value[value_len - suffix_len] = '\0';
    _trim_trailing_slashes(value);
    return true;
}

esp_err_t network_contract_normalize_base_url(const char *api_url,
                                               char *out,
                                               size_t out_len)
{
    if (!api_url || !out || out_len == 0 || api_url[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }

    size_t input_len = strlen(api_url);
    if (input_len >= out_len) return ESP_FAIL;
    memcpy(out, api_url, input_len + 1);
    _trim_trailing_slashes(out);

    /* Accept legacy provisioning values while keeping one canonical base. */
    if (!_strip_suffix(out, "/api/upload")) {
        _strip_suffix(out, "/api");
    }

    if (out[0] == '\0') return ESP_ERR_INVALID_ARG;
    return ESP_OK;
}

esp_err_t network_contract_build_url(const char *api_url,
                                     const char *endpoint,
                                     char *out,
                                     size_t out_len)
{
    if (!endpoint || endpoint[0] != '/' || !out || out_len == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    char base[256];
    esp_err_t ret = network_contract_normalize_base_url(api_url, base, sizeof(base));
    if (ret != ESP_OK) return ret;

    int written = snprintf(out, out_len, "%s%s", base, endpoint);
    if (written < 0 || (size_t)written >= out_len) return ESP_FAIL;
    return ESP_OK;
}

esp_err_t network_contract_url_encode(const char *value,
                                      char *out,
                                      size_t out_len)
{
    static const char hex[] = "0123456789ABCDEF";
    if (!value || !out || out_len == 0) return ESP_ERR_INVALID_ARG;

    size_t pos = 0;
    for (const unsigned char *p = (const unsigned char *)value; *p; ++p) {
        bool unreserved = isalnum(*p) || *p == '-' || *p == '_' ||
                           *p == '.' || *p == '~';
        size_t needed = unreserved ? 1 : 3;
        if (pos + needed >= out_len) return ESP_FAIL;
        if (unreserved) {
            out[pos++] = (char)*p;
        } else {
            out[pos++] = '%';
            out[pos++] = hex[*p >> 4];
            out[pos++] = hex[*p & 0x0F];
        }
    }
    out[pos] = '\0';
    return ESP_OK;
}

static bool _number(cJSON *item, double *value)
{
    if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble)) return false;
    if (value) *value = item->valuedouble;
    return true;
}

static bool _coordinate_pair(cJSON *object, bool allow_end_names)
{
    if (!cJSON_IsObject(object)) return false;

    cJSON *lat = cJSON_GetObjectItemCaseSensitive(object, "lat");
    cJSON *lon = cJSON_GetObjectItemCaseSensitive(object, "lon");
    if (allow_end_names) {
        if (!lat) lat = cJSON_GetObjectItemCaseSensitive(object, "end_lat");
        if (!lon) lon = cJSON_GetObjectItemCaseSensitive(object, "end_lon");
    }

    double lat_value = 0.0;
    double lon_value = 0.0;
    if (!_number(lat, &lat_value) || !_number(lon, &lon_value) ||
        lat_value < -90.0 || lat_value > 90.0 ||
        lon_value < -180.0 || lon_value > 180.0) {
        return false;
    }

    cJSON *radius = cJSON_GetObjectItemCaseSensitive(object, "radius_m");
    double radius_value = 0.0;
    if (radius && (!_number(radius, &radius_value) || radius_value <= 0.0)) {
        return false;
    }
    return true;
}

static bool _valid_tbl(cJSON *tbl)
{
    if (!tbl) return true;
    if (!cJSON_IsObject(tbl)) return false;

    cJSON *lap_time = cJSON_GetObjectItemCaseSensitive(tbl, "lap_time");
    double lap_value = 0.0;
    if (lap_time && (!_number(lap_time, &lap_value) || lap_value < 0.0)) {
        return false;
    }

    cJSON *sectors = cJSON_GetObjectItemCaseSensitive(tbl, "sectors");
    if (!sectors) return true;
    if (!cJSON_IsArray(sectors) || cJSON_GetArraySize(sectors) > NETWORK_TRACK_MAX_SECTORS) {
        return false;
    }

    cJSON *item = NULL;
    cJSON_ArrayForEach(item, sectors) {
        double value = 0.0;
        if (!_number(item, &value) || value < 0.0) return false;
    }
    return true;
}

esp_err_t network_contract_extract_active_track(const char *json,
                                                size_t json_len,
                                                char *payload,
                                                size_t payload_len)
{
    if (!json || json_len == 0 || !payload || payload_len == 0 ||
        json_len > 65536) {
        return ESP_ERR_INVALID_ARG;
    }

    char *input = malloc(json_len + 1);
    if (!input) return ESP_ERR_NO_MEM;
    memcpy(input, json, json_len);
    input[json_len] = '\0';

    cJSON *root = cJSON_Parse(input);
    free(input);
    if (!root || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return ESP_FAIL;
    }

    cJSON *active = cJSON_GetObjectItemCaseSensitive(root, "active_track");
    if (!active) {
        cJSON_Delete(root);
        return ESP_FAIL;
    }
    if (cJSON_IsNull(active)) {
        cJSON_Delete(root);
        return ESP_ERR_NOT_FOUND;
    }
    if (!cJSON_IsObject(active)) {
        cJSON_Delete(root);
        return ESP_FAIL;
    }

    cJSON *name = cJSON_GetObjectItemCaseSensitive(active, "name");
    if (!cJSON_IsString(name) || !name->valuestring || name->valuestring[0] == '\0') {
        name = cJSON_GetObjectItemCaseSensitive(active, "track_name");
    }
    cJSON *start_line = cJSON_GetObjectItemCaseSensitive(active, "start_line");
    cJSON *sectors = cJSON_GetObjectItemCaseSensitive(active, "sectors");
    if (!cJSON_IsString(name) || !name->valuestring || name->valuestring[0] == '\0' ||
        !_coordinate_pair(start_line, false) ||
        !cJSON_IsArray(sectors) ||
        cJSON_GetArraySize(sectors) > NETWORK_TRACK_MAX_SECTORS ||
        !_valid_tbl(cJSON_GetObjectItemCaseSensitive(active, "tbl"))) {
        cJSON_Delete(root);
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *sector = NULL;
    cJSON_ArrayForEach(sector, sectors) {
        if (!_coordinate_pair(sector, true)) {
            cJSON_Delete(root);
            return ESP_ERR_INVALID_ARG;
        }
    }

    /* Preserve the normalized layout: it is the device's display geometry. */
    cJSON *track = cJSON_Duplicate(active, true);
    cJSON_Delete(root);
    if (!track) return ESP_ERR_NO_MEM;

    char *serialized = cJSON_PrintUnformatted(track);
    cJSON_Delete(track);
    if (!serialized) return ESP_ERR_NO_MEM;

    size_t serialized_len = strlen(serialized);
    if (serialized_len + 1 > payload_len) {
        free(serialized);
        return ESP_FAIL;
    }
    memcpy(payload, serialized, serialized_len + 1);
    free(serialized);
    return ESP_OK;
}
