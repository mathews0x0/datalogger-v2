/* P4 display bring-up: network functions are deliberately inert until the
 * ESP32-C6 SDIO transport is enabled and validated. */
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
    (void)cb; (void)cb_ctx;
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
