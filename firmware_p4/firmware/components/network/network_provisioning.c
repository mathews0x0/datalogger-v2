/**
 * @file network_provisioning.c
 * @brief Host-testable captive-portal request parsing and validation.
 */

#include "network_provisioning.h"

#include <ctype.h>
#include <stddef.h>
#include <string.h>

static void _clear_config(network_device_config_t *cfg)
{
    if (cfg) memset(cfg, 0, sizeof(*cfg));
}

static bool _hex_digit(char c, unsigned char *value)
{
    if (c >= '0' && c <= '9') *value = (unsigned char)(c - '0');
    else if (c >= 'a' && c <= 'f') *value = (unsigned char)(c - 'a' + 10);
    else if (c >= 'A' && c <= 'F') *value = (unsigned char)(c - 'A' + 10);
    else return false;
    return true;
}

static bool _decode_value(const char *src, size_t len, char *dst, size_t dst_len)
{
    if (!src || !dst || dst_len == 0) return false;

    size_t out_len = 0;
    for (size_t i = 0; i < len; ++i) {
        unsigned char value = 0;
        if (src[i] == '%') {
            if (i + 2 >= len || !_hex_digit(src[i + 1], &value)) return false;
            unsigned char low = 0;
            if (!_hex_digit(src[i + 2], &low)) return false;
            value = (unsigned char)((value << 4) | low);
            i += 2;
        } else if (src[i] == '+') {
            value = ' ';
        } else {
            value = (unsigned char)src[i];
        }

        if (value == '\0' || out_len + 1 >= dst_len) return false;
        dst[out_len++] = (char)value;
    }
    dst[out_len] = '\0';
    return true;
}

/** Find and URL-decode one key from a query string or form body. */
static bool _find_field(const char *params, const char *key,
                        char *out, size_t out_len)
{
    if (!params || !key || !out || out_len == 0) return false;

    const char *p = params;
    while (*p) {
        while (*p == '?' || *p == '&') p++;
        if (!*p) break;

        const char *segment_end = strchr(p, '&');
        if (!segment_end) segment_end = p + strlen(p);
        const char *equals = memchr(p, '=', (size_t)(segment_end - p));
        if (equals) {
            size_t key_len = (size_t)(equals - p);
            if (strlen(key) == key_len && strncmp(p, key, key_len) == 0) {
                return _decode_value(equals + 1,
                                     (size_t)(segment_end - equals - 1),
                                     out, out_len);
            }
        }
        p = *segment_end ? segment_end + 1 : segment_end;
    }
    out[0] = '\0';
    return false;
}

static bool _setup_path(const char *path, const char **params)
{
    if (!path) return false;
    const char *query = strchr(path, '?');
    size_t path_len = query ? (size_t)(query - path) : strlen(path);
    bool valid = (path_len == 1 && path[0] == '/') ||
                 (path_len == 6 && strncmp(path, "/setup", path_len) == 0);
    if (params) *params = query ? query + 1 : NULL;
    return valid;
}

static bool _has_control_chars(const char *value)
{
    if (!value) return true;
    for (const unsigned char *p = (const unsigned char *)value; *p; ++p) {
        if (*p < 0x20 || *p == 0x7F) return true;
    }
    return false;
}

esp_err_t network_provisioning_validate_config(const network_device_config_t *cfg)
{
    if (!cfg || !cfg->ssid[0] || !cfg->token[0] || !cfg->api_url[0]) {
        return ESP_ERR_INVALID_ARG;
    }
    if (strlen(cfg->ssid) >= sizeof(cfg->ssid) ||
        strlen(cfg->password) >= sizeof(cfg->password) ||
        strlen(cfg->token) >= sizeof(cfg->token) ||
        strlen(cfg->api_url) >= sizeof(cfg->api_url)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (strncmp(cfg->token, "rsk_", 4) != 0 ||
        _has_control_chars(cfg->ssid) ||
        _has_control_chars(cfg->password) ||
        _has_control_chars(cfg->token) ||
        _has_control_chars(cfg->api_url)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (strncmp(cfg->api_url, "http://", 7) != 0 &&
        strncmp(cfg->api_url, "https://", 8) != 0) {
        return ESP_ERR_INVALID_ARG;
    }
    return ESP_OK;
}

esp_err_t network_provisioning_parse_request(
    const char *method,
    const char *path,
    const char *body,
    const network_device_config_t *saved,
    network_device_config_t *out,
    network_provisioning_source_t *source)
{
    if (!method || !path || !out) return ESP_ERR_INVALID_ARG;

    if (saved) memcpy(out, saved, sizeof(*out));
    else _clear_config(out);
    if (source) *source = NETWORK_PROVISIONING_NONE;

    const char *query = NULL;
    if (!_setup_path(path, &query)) return ESP_ERR_NOT_FOUND;

    bool is_get = strcmp(method, "GET") == 0;
    bool is_post = strcmp(method, "POST") == 0;
    if (!is_get && !is_post) return ESP_ERR_NOT_FOUND;

    const char *params = is_get ? query : body;
    if (!params || !*params) return ESP_ERR_NOT_FOUND;

    char ssid[sizeof(out->ssid)] = {0};
    char password[sizeof(out->password)] = {0};
    char token[sizeof(out->token)] = {0};
    char api_url[sizeof(out->api_url)] = {0};
    bool found_ssid = _find_field(params, "ssid", ssid, sizeof(ssid));
    bool found_password = _find_field(params, "password", password, sizeof(password));
    bool found_pass = false;
    if (!found_password) {
        found_pass = _find_field(params, "pass", password, sizeof(password));
    }
    bool found_token = _find_field(params, "token", token, sizeof(token));
    bool found_api = _find_field(params, "api_url", api_url, sizeof(api_url));

    /* A POST must include the required fields. A magic link is identified by
     * the same required fields arriving in a GET query string. */
    if (!found_ssid || !found_token) return ESP_ERR_NOT_FOUND;
    if (!found_password && !found_pass && saved) {
        strncpy(password, saved->password, sizeof(password) - 1);
    }
    if (!found_api && saved) {
        strncpy(api_url, saved->api_url, sizeof(api_url) - 1);
    }

    strncpy(out->ssid, ssid, sizeof(out->ssid) - 1);
    strncpy(out->password, password, sizeof(out->password) - 1);
    strncpy(out->token, token, sizeof(out->token) - 1);
    strncpy(out->api_url, api_url, sizeof(out->api_url) - 1);

    esp_err_t valid = network_provisioning_validate_config(out);
    if (valid != ESP_OK) return valid;
    if (source) {
        *source = is_get ? NETWORK_PROVISIONING_MAGIC_LINK
                         : NETWORK_PROVISIONING_FORM;
    }
    return ESP_OK;
}
