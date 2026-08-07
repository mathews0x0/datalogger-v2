/* Fallback implementation for builds that intentionally disable the
 * ESP32-C6 SDIO/ESP-Hosted transport. */
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "network.h"

static const char *TAG = "network";

esp_err_t network_init(void)
{
    ESP_LOGW(TAG, "Wi-Fi deferred during P4 display bring-up");
    return ESP_OK;
}

esp_err_t network_wifi_connect(const char *ssid, const char *password)
{
    (void)ssid; (void)password;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t network_wifi_disconnect(void) { return ESP_OK; }
bool network_is_connected(void) { return false; }

void network_get_ip(char *buf, int buf_len)
{
    if (buf && buf_len > 0) snprintf(buf, buf_len, "offline");
}

void network_get_ap_name(char *buf, int buf_len)
{
    if (buf && buf_len > 0) snprintf(buf, buf_len, "RS-Core-P4");
}

esp_err_t network_load_device_config(network_device_config_t *cfg)
{
    if (cfg) memset(cfg, 0, sizeof(*cfg));
    return ESP_ERR_NOT_FOUND;
}

esp_err_t network_save_device_config(const network_device_config_t *cfg)
{
    (void)cfg;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t network_heartbeat(const char *token, const char *api_url)
{
    (void)token; (void)api_url;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t network_heartbeat_with_telemetry(
    const char *token, const char *api_url,
    const network_heartbeat_telemetry_t *telemetry)
{
    (void)token; (void)api_url; (void)telemetry;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t network_upload_file(const char *filepath, const char *token,
                              const char *api_url, upload_progress_cb_t cb,
                              void *cb_ctx, int file_index, int total_files,
                              size_t global_offset, size_t global_total)
{
    (void)filepath; (void)token; (void)api_url; (void)cb; (void)cb_ctx;
    (void)file_index; (void)total_files; (void)global_offset; (void)global_total;
    return ESP_ERR_NOT_SUPPORTED;
}

bool network_sync_all(upload_progress_cb_t cb, void *cb_ctx)
{
    return network_sync_all_with_heartbeat(cb, cb_ctx, NULL, NULL);
}

bool network_sync_all_with_heartbeat(upload_progress_cb_t cb, void *cb_ctx,
                                     network_heartbeat_cb_t heartbeat_cb,
                                     void *heartbeat_ctx)
{
    (void)cb; (void)cb_ctx; (void)heartbeat_cb; (void)heartbeat_ctx;
    return false;
}

esp_err_t network_start_captive_portal(const char *ap_name)
{
    (void)ap_name;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t network_stop_captive_portal(void) { return ESP_OK; }

esp_err_t network_fetch_active_track(const char *token, const char *api_url)
{
    (void)token; (void)api_url;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t network_sync_track_catalog(const char *token, const char *api_url)
{
    (void)token; (void)api_url;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t network_select_cached_track(int32_t track_id)
{
    (void)track_id;
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t network_list_cached_tracks(network_cached_track_t *tracks, int max_tracks,
                                     int *out_count, int32_t *out_active_id)
{
    (void)tracks; (void)max_tracks;
    if (out_count) *out_count = 0;
    if (out_active_id) *out_active_id = 0;
    return ESP_ERR_NOT_SUPPORTED;
}
