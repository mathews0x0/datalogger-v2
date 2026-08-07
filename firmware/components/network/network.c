/**
 * @file network.c
 * @brief Network subsystem — WiFi Manager, HTTPS Uploader, Captive Portal
 *
 * Ported from S3 firmware:
 *   wifi_manager.py  → network_init / network_wifi_connect / AP mode
 *   uploader.py      → network_upload_file / network_sync_all (3-phase batch)
 *   captive_portal.py → network_start_captive_portal (DNS hijack + HTTP form)
 *
 * WiFi transport: ESP32-C6 via esp-hosted-ng SDIO driver.
 * TLS: IDF built-in MbedTLS via esp_tls / esp_http_client.
 */

#include "network.h"

#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <stdlib.h>
#include <math.h>
#include <errno.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#ifndef CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM
#define CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM 10
#endif
#ifndef CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM
#define CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM 32
#endif
#ifndef CONFIG_ESP_WIFI_TX_BUFFER_TYPE
#define CONFIG_ESP_WIFI_TX_BUFFER_TYPE 1
#endif
#ifndef CONFIG_ESP_WIFI_DYNAMIC_RX_MGMT_BUF
#define CONFIG_ESP_WIFI_DYNAMIC_RX_MGMT_BUF 1
#endif
#ifndef CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM
#define CONFIG_ESP_WIFI_CACHE_TX_BUFFER_NUM 16
#endif
#ifndef CONFIG_ESP_WIFI_ESPNOW_MAX_ENCRYPT_NUM
#define CONFIG_ESP_WIFI_ESPNOW_MAX_ENCRYPT_NUM 7
#endif
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "esp_sntp.h"
#include "esp_http_client.h"
#include "esp_tls.h"
#include "esp_crt_bundle.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "lwip/dns.h"
#include "nvs_flash.h"
#include "cJSON.h"
#include "storage.h"
#include "network_contract.h"
#include "network_provisioning.h"

static const char *TAG = "network";

#define TRACK_CATALOG_PATH       "/data/metadata/track_catalog.json"
#define TRACK_CATALOG_DIR        "/data/metadata/tracks"
#define TRACK_STATE_PATH         "/data/metadata/track_state.json"
#define TRACK_MANIFEST_CAPACITY  (16 * 1024)
#define TRACK_PAYLOAD_CAPACITY   (64 * 1024)

/* ──────────────────────────────────────────────────────────────────────────
 * Event group bits
 * ────────────────────────────────────────────────────────────────────────*/
#define WIFI_CONNECTED_BIT  BIT0
#define WIFI_FAIL_BIT       BIT1

static EventGroupHandle_t s_wifi_events = NULL;
static esp_netif_t       *s_sta_netif   = NULL;
static esp_netif_t       *s_ap_netif    = NULL;
static bool               s_initialized = false;
static int                s_retry_count = 0;
static bool               s_connect_requested = false;
#define MAX_STA_RETRIES   5

/* ──────────────────────────────────────────────────────────────────────────
 * Captive portal state
 * ────────────────────────────────────────────────────────────────────────*/
static volatile bool s_portal_running  = false;
static volatile bool s_dns_running     = false;

/* ══════════════════════════════════════════════════════════════════════════
 * SECTION 1: WiFi Manager
 * ══════════════════════════════════════════════════════════════════════════*/

static void _wifi_event_handler(void *arg, esp_event_base_t base,
                                 int32_t event_id, void *event_data)
{
    if (base == WIFI_EVENT) {
        if (event_id == WIFI_EVENT_STA_START) {
            if (s_connect_requested) {
                esp_wifi_connect();
            }
        } else if (event_id == WIFI_EVENT_STA_DISCONNECTED) {
            if (s_connect_requested && s_retry_count < MAX_STA_RETRIES) {
                s_retry_count++;
                ESP_LOGW(TAG, "WiFi disconnected, retry %d/%d", s_retry_count, MAX_STA_RETRIES);
                esp_wifi_connect();
            } else if (s_connect_requested) {
                xEventGroupSetBits(s_wifi_events, WIFI_FAIL_BIT);
            }
        }
    } else if (base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *evt = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "WiFi connected — IP: " IPSTR, IP2STR(&evt->ip_info.ip));
        s_retry_count = 0;
        xEventGroupSetBits(s_wifi_events, WIFI_CONNECTED_BIT);
    }
}

esp_err_t network_init(void)
{
    if (s_initialized) return ESP_OK;

    s_wifi_events = xEventGroupCreate();
    if (!s_wifi_events) return ESP_ERR_NO_MEM;

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    s_sta_netif = esp_netif_create_default_wifi_sta();
    s_ap_netif  = esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
        ESP_EVENT_ANY_ID, _wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
        IP_EVENT_STA_GOT_IP, _wifi_event_handler, NULL, NULL));

    s_initialized = true;
    ESP_LOGI(TAG, "Network subsystem initialized");
    return ESP_OK;
}

esp_err_t network_wifi_connect(const char *ssid, const char *password)
{
    /* Load from device config if not provided */
    network_device_config_t cfg = {0};
    if (!ssid || ssid[0] == '\0') {
        if (network_load_device_config(&cfg) == ESP_OK) {
            ssid     = cfg.ssid;
            password = cfg.password;
        }
    }
    if (!ssid || ssid[0] == '\0') {
        ESP_LOGW(TAG, "No SSID configured — cannot connect");
        return ESP_ERR_NOT_FOUND;
    }

    ESP_LOGI(TAG, "Connecting to WiFi: %s", ssid);
    xEventGroupClearBits(s_wifi_events, WIFI_CONNECTED_BIT | WIFI_FAIL_BIT);
    s_retry_count = 0;
    s_connect_requested = true;

    wifi_config_t wifi_cfg = {0};
    strncpy((char *)wifi_cfg.sta.ssid,     ssid,     sizeof(wifi_cfg.sta.ssid) - 1);
    strncpy((char *)wifi_cfg.sta.password, password ? password : "",
            sizeof(wifi_cfg.sta.password) - 1);
    wifi_cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    /* Wait for connect or fail */
    EventBits_t bits = xEventGroupWaitBits(s_wifi_events,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE, pdFALSE,
        pdMS_TO_TICKS(NETWORK_CONNECT_TIMEOUT_MS));

    if (bits & WIFI_CONNECTED_BIT) {
        /* Sync SNTP — required for MbedTLS certificate time validation */
        ESP_LOGI(TAG, "Syncing time via SNTP...");
        esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
        esp_sntp_setservername(0, "pool.ntp.org");
        esp_sntp_init();
        /* Wait up to 10s for time sync */
        time_t now = 0;
        struct tm timeinfo = {0};
        int sntp_retries = 0;
        while (timeinfo.tm_year < (2020 - 1900) && sntp_retries++ < 100) {
            vTaskDelay(pdMS_TO_TICKS(100));
            time(&now);
            localtime_r(&now, &timeinfo);
        }
        if (timeinfo.tm_year >= (2020 - 1900)) {
            ESP_LOGI(TAG, "SNTP synced: %04d-%02d-%02d %02d:%02d:%02d UTC",
                     timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
                     timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
        } else {
            ESP_LOGW(TAG, "SNTP sync timeout — TLS cert validation may fail");
        }
        return ESP_OK;
    }

    ESP_LOGE(TAG, "WiFi connection failed after %d retries", MAX_STA_RETRIES);
    s_connect_requested = false;
    esp_wifi_stop();
    return ESP_FAIL;
}

esp_err_t network_wifi_scan(uint16_t *ap_count)
{
    if (!s_initialized || !s_sta_netif) return ESP_ERR_INVALID_STATE;
    if (ap_count) *ap_count = 0;
    s_connect_requested = false;

    ESP_LOGI(TAG, "Starting credential-free Wi-Fi scan via hosted C6");

    esp_err_t ret = esp_wifi_set_mode(WIFI_MODE_STA);
    if (ret != ESP_OK) return ret;
    ret = esp_wifi_start();
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) return ret;

    wifi_scan_config_t scan_cfg = {
        .ssid = NULL,
        .bssid = NULL,
        .channel = 0,
        .show_hidden = true,
        .scan_type = WIFI_SCAN_TYPE_ACTIVE,
        .scan_time.active = {
            .min = 100,
            .max = 300,
        },
    };
    ret = esp_wifi_scan_start(&scan_cfg, true);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Wi-Fi scan failed: %s", esp_err_to_name(ret));
        esp_wifi_stop();
        return ret;
    }

    uint16_t count = 0;
    ret = esp_wifi_scan_get_ap_num(&count);
    if (ret == ESP_OK) {
        if (ap_count) *ap_count = count;
        ESP_LOGI(TAG, "Wi-Fi scan completed: %u access point(s)", count);
    }
    esp_wifi_clear_ap_list();
    esp_wifi_stop();
    return ret;
}

esp_err_t network_wifi_disconnect(void)
{
    s_connect_requested = false;
    esp_wifi_stop();
    return ESP_OK;
}

bool network_is_connected(void)
{
    if (!s_wifi_events) return false;
    return (xEventGroupGetBits(s_wifi_events) & WIFI_CONNECTED_BIT) != 0;
}

void network_get_ip(char *buf, int buf_len)
{
    if (!buf || buf_len < 16) return;
    esp_netif_ip_info_t ip_info;
    if (esp_netif_get_ip_info(s_sta_netif, &ip_info) == ESP_OK) {
        snprintf(buf, buf_len, IPSTR, IP2STR(&ip_info.ip));
    } else {
        strncpy(buf, "0.0.0.0", buf_len);
    }
}

void network_get_ap_name(char *buf, int buf_len)
{
    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_AP, mac);
    snprintf(buf, buf_len, "RS-Core-%02X%02X", mac[4], mac[5]);
}

/* ══════════════════════════════════════════════════════════════════════════
 * SECTION 2: Device Config
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t network_load_device_config(network_device_config_t *cfg)
{
    if (!cfg) return ESP_ERR_INVALID_ARG;
    memset(cfg, 0, sizeof(*cfg));

    FILE *f = fopen(NETWORK_DEVICE_CONFIG_PATH, "r");
    if (!f) return ESP_ERR_NOT_FOUND;

    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    rewind(f);
    if (sz <= 0 || sz > 4096) { fclose(f); return ESP_FAIL; }

    char *buf = malloc(sz + 1);
    if (!buf) { fclose(f); return ESP_ERR_NO_MEM; }
    fread(buf, 1, sz, f);
    buf[sz] = '\0';
    fclose(f);

    cJSON *root = cJSON_Parse(buf);
    free(buf);
    if (!root) return ESP_FAIL;

    cJSON *item;
    if ((item = cJSON_GetObjectItem(root, "ssid")) && cJSON_IsString(item))
        strncpy(cfg->ssid, item->valuestring, sizeof(cfg->ssid) - 1);
    if ((item = cJSON_GetObjectItem(root, "password")) && cJSON_IsString(item))
        strncpy(cfg->password, item->valuestring, sizeof(cfg->password) - 1);
    if ((item = cJSON_GetObjectItem(root, "token")) && cJSON_IsString(item))
        strncpy(cfg->token, item->valuestring, sizeof(cfg->token) - 1);
    if ((item = cJSON_GetObjectItem(root, "api_url")) && cJSON_IsString(item))
        strncpy(cfg->api_url, item->valuestring, sizeof(cfg->api_url) - 1);

    cJSON_Delete(root);

    if (cfg->token[0] == '\0' || cfg->api_url[0] == '\0') {
        return ESP_ERR_NOT_FOUND;
    }
    return ESP_OK;
}

esp_err_t network_save_device_config(const network_device_config_t *cfg)
{
    if (!cfg || network_provisioning_validate_config(cfg) != ESP_OK) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Ensure directory exists */
    mkdir("/data", 0755);
    mkdir("/data/metadata", 0755);

    cJSON *root = cJSON_CreateObject();
    if (!root) return ESP_ERR_NO_MEM;
    cJSON_AddStringToObject(root, "ssid",     cfg->ssid);
    cJSON_AddStringToObject(root, "password", cfg->password);
    cJSON_AddStringToObject(root, "token",    cfg->token);
    cJSON_AddStringToObject(root, "api_url",  cfg->api_url);

    char *json_str = cJSON_Print(root);
    cJSON_Delete(root);
    if (!json_str) return ESP_ERR_NO_MEM;

    const char *tmp_path = NETWORK_DEVICE_CONFIG_PATH ".tmp";
    FILE *f = fopen(tmp_path, "w");
    if (!f) { free(json_str); return ESP_FAIL; }
    bool write_ok = fputs(json_str, f) >= 0 && fflush(f) == 0;
    int fd = fileno(f);
    if (write_ok && fd >= 0) write_ok = fsync(fd) == 0;
    fclose(f);
    free(json_str);

    if (!write_ok || rename(tmp_path, NETWORK_DEVICE_CONFIG_PATH) != 0) {
        remove(tmp_path);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Device config saved to %s", NETWORK_DEVICE_CONFIG_PATH);
    return ESP_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * SECTION 3: HTTPS Uploader (3-phase batch streaming)
 * Mirrors S3 uploader.py _upload_file_persistent() exactly.
 * ══════════════════════════════════════════════════════════════════════════*/

/** Validate CSV header matches expected schema */
static bool _validate_session(const char *filepath)
{
    FILE *f = fopen(filepath, "r");
    if (!f) return false;
    char hdr[128] = {0};
    fgets(hdr, sizeof(hdr), f);
    fclose(f);
    return (strncmp(hdr, "tick_ms,", 8) == 0 ||
            strncmp(hdr, "gps_time,", 9) == 0 ||
            strncmp(hdr, "time,", 5) == 0);
}

/** HTTP event handler for esp_http_client (captures response body) */
typedef struct {
    char   body[4096];
    char  *external_body;
    size_t external_capacity;
    size_t body_len;
    bool   truncated;
    int    status_code;
} http_ctx_t;

static char *_http_ctx_buffer(http_ctx_t *ctx, size_t *capacity)
{
    if (ctx->external_body && ctx->external_capacity > 0) {
        if (capacity) *capacity = ctx->external_capacity;
        return ctx->external_body;
    }
    if (capacity) *capacity = sizeof(ctx->body);
    return ctx->body;
}

static const char *_http_ctx_data(const http_ctx_t *ctx)
{
    return (ctx->external_body && ctx->external_capacity > 0)
               ? ctx->external_body : ctx->body;
}

static esp_err_t _http_event_handler(esp_http_client_event_t *evt)
{
    http_ctx_t *ctx = (http_ctx_t *)evt->user_data;
    if (!ctx) return ESP_OK;
    if (evt->event_id == HTTP_EVENT_ON_DATA && evt->data_len > 0) {
        size_t capacity = 0;
        char *buffer = _http_ctx_buffer(ctx, &capacity);
        size_t rem = capacity > ctx->body_len ? capacity - ctx->body_len - 1 : 0;
        if (rem > 0) {
            size_t copy = (size_t)evt->data_len < rem ? (size_t)evt->data_len : rem;
            memcpy(buffer + ctx->body_len, evt->data, copy);
            ctx->body_len += copy;
            buffer[ctx->body_len] = '\0';
        }
        if ((size_t)evt->data_len > rem) ctx->truncated = true;
    }
    return ESP_OK;
}

static void _collect_heartbeat_telemetry(network_heartbeat_telemetry_t *telemetry,
                                         char *device_uid,
                                         size_t device_uid_len)
{
    memset(telemetry, 0, sizeof(*telemetry));
    telemetry->device_uid = NULL;

    uint8_t mac[6] = {0};
    if (device_uid && device_uid_len > 0 &&
        esp_wifi_get_mac(WIFI_IF_STA, mac) == ESP_OK) {
        snprintf(device_uid, device_uid_len, "%02X%02X%02X%02X%02X%02X",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
        telemetry->device_uid = device_uid;
    }

    /* The server stores SD telemetry as 32-bit MB values.  Keep the local
     * storage API in bytes, but convert at the network boundary so a normal
     * multi-gigabyte card cannot overflow the server's integer columns. */
    uint64_t sd_total_bytes = 0;
    uint64_t sd_free_bytes = 0;
    if (storage_get_space_bytes(&sd_total_bytes, &sd_free_bytes) == ESP_OK) {
        telemetry->storage_sd_total = sd_total_bytes / (1024ULL * 1024ULL);
        telemetry->storage_sd_free = sd_free_bytes / (1024ULL * 1024ULL);
    }

}

static bool _response_success(const http_ctx_t *ctx)
{
    if (!ctx || ctx->truncated || ctx->body_len == 0) return false;
    cJSON *root = cJSON_Parse(_http_ctx_data(ctx));
    if (!root) return false;
    cJSON *success = cJSON_GetObjectItemCaseSensitive(root, "success");
    bool ok = cJSON_IsTrue(success);
    cJSON_Delete(root);
    return ok;
}

esp_err_t network_heartbeat(const char *token, const char *api_url)
{
    network_heartbeat_telemetry_t telemetry;
    char device_uid[32] = {0};
    _collect_heartbeat_telemetry(&telemetry, device_uid, sizeof(device_uid));
    return network_heartbeat_with_telemetry(token, api_url, &telemetry);
}

esp_err_t network_heartbeat_with_telemetry(const char *token,
                                            const char *api_url,
                                            const network_heartbeat_telemetry_t *telemetry)
{
    network_device_config_t cfg = {0};
    if (!token || !api_url) {
        if (network_load_device_config(&cfg) != ESP_OK) return ESP_ERR_NOT_FOUND;
        token   = cfg.token;
        api_url = cfg.api_url;
    }

    char url[256];
    if (network_contract_build_url(api_url, NETWORK_ENDPOINT_DEVICE_PING,
                                   url, sizeof(url)) != ESP_OK) {
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *body = cJSON_CreateObject();
    if (!body) return ESP_ERR_NO_MEM;
    if (telemetry) {
        if (telemetry->device_uid && telemetry->device_uid[0]) {
            cJSON_AddStringToObject(body, "device_uid", telemetry->device_uid);
        }
        if (telemetry->has_vbatt_sense && isfinite(telemetry->vbatt_sense)) {
            cJSON_AddNumberToObject(body, "vbatt_sense", telemetry->vbatt_sense);
        }
        if (telemetry->storage_sd_total > 0) {
            cJSON_AddNumberToObject(body, "storage_sd_total",
                                    (double)telemetry->storage_sd_total);
            cJSON_AddNumberToObject(body, "storage_sd_free",
                                    (double)telemetry->storage_sd_free);
        }
        if (telemetry->storage_flash_total > 0) {
            cJSON_AddNumberToObject(body, "storage_flash_total",
                                    (double)telemetry->storage_flash_total);
            cJSON_AddNumberToObject(body, "storage_flash_free",
                                    (double)telemetry->storage_flash_free);
        }
    }
    char *body_str = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);
    if (!body_str) return ESP_ERR_NO_MEM;

    http_ctx_t ctx = {0};
    esp_http_client_config_t hcfg = {
        .url            = url,
        .method         = HTTP_METHOD_POST,
        .timeout_ms     = 10000,
        .event_handler  = _http_event_handler,
        .user_data      = &ctx,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .skip_cert_common_name_check = false,
    };

    char auth_hdr[160];
    snprintf(auth_hdr, sizeof(auth_hdr), "Bearer %s", token);

    esp_http_client_handle_t client = esp_http_client_init(&hcfg);
    if (!client) {
        free(body_str);
        return ESP_ERR_NO_MEM;
    }
    esp_http_client_set_header(client, "Authorization", auth_hdr);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, body_str, (int)strlen(body_str));

    esp_err_t ret = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);
    free(body_str);

    if (ret == ESP_OK && status == 200 && _response_success(&ctx)) {
        ESP_LOGI(TAG, "Heartbeat OK (POST /api/device/ping)");
        return ESP_OK;
    }
    ESP_LOGW(TAG, "Heartbeat failed: err=%s status=%d", esp_err_to_name(ret), status);
    return ESP_FAIL;
}

esp_err_t network_upload_file(const char *filepath,
                               const char *token,
                               const char *api_url,
                               upload_progress_cb_t cb,
                               void *cb_ctx,
                               int file_index,
                               int total_files,
                               size_t global_offset,
                               size_t global_total)
{
    /* Get file size */
    struct stat st;
    if (stat(filepath, &st) != 0 || st.st_size == 0) return ESP_ERR_NOT_FOUND;
    size_t total_size = (size_t)st.st_size;

    const char *fname = strrchr(filepath, '/');
    fname = fname ? fname + 1 : filepath;

    if (!token || !api_url) return ESP_ERR_INVALID_ARG;

    /* Build endpoint URLs from the server root. This also accepts legacy
     * configs containing /api/upload and normalizes them to the root. */
    char batch_url[256], status_url[256], complete_url[256];
    if (network_contract_build_url(api_url, NETWORK_ENDPOINT_UPLOAD_BATCH,
                                   batch_url, sizeof(batch_url)) != ESP_OK ||
        network_contract_build_url(api_url, NETWORK_ENDPOINT_UPLOAD_STATUS,
                                   status_url, sizeof(status_url)) != ESP_OK ||
        network_contract_build_url(api_url, NETWORK_ENDPOINT_UPLOAD_COMPLETE,
                                   complete_url, sizeof(complete_url)) != ESP_OK) {
        return ESP_ERR_INVALID_ARG;
    }

    char encoded_fname[320];
    if (network_contract_url_encode(fname, encoded_fname, sizeof(encoded_fname)) != ESP_OK) {
        return ESP_ERR_INVALID_ARG;
    }

    char auth_hdr[160];
    snprintf(auth_hdr, sizeof(auth_hdr), "Bearer %s", token);

    /* ── Phase 1: Resume check ──────────────────────────────────────────── */
    size_t offset = 0;
    {
        char resume_url[320];
        int resume_len = snprintf(resume_url, sizeof(resume_url),
                                  "%s?filename=%s", status_url, encoded_fname);
        if (resume_len < 0 || (size_t)resume_len >= sizeof(resume_url)) {
            return ESP_FAIL;
        }

        http_ctx_t ctx = {0};
        esp_http_client_config_t hcfg = {
            .url = resume_url, .method = HTTP_METHOD_GET,
            .timeout_ms = 10000, .event_handler = _http_event_handler, .user_data = &ctx,
            .crt_bundle_attach = esp_crt_bundle_attach,
        };
        esp_http_client_handle_t client = esp_http_client_init(&hcfg);
        if (!client) return ESP_ERR_NO_MEM;
        esp_http_client_set_header(client, "Authorization", auth_hdr);
        esp_err_t status_ret = esp_http_client_perform(client);
        int status = esp_http_client_get_status_code(client);
        if (status_ret != ESP_OK || status != 200 || ctx.truncated || ctx.body_len == 0) {
            esp_http_client_cleanup(client);
            ESP_LOGW(TAG, "Upload resume check failed: err=%s status=%d",
                     esp_err_to_name(status_ret), status);
            return ESP_FAIL;
        }

        cJSON *root = cJSON_Parse(_http_ctx_data(&ctx));
        if (!root) {
            esp_http_client_cleanup(client);
            return ESP_FAIL;
        }
        cJSON *rb = cJSON_GetObjectItemCaseSensitive(root, "received_bytes");
        if (!rb || !cJSON_IsNumber(rb) || !isfinite(rb->valuedouble) ||
            rb->valuedouble < 0.0 || rb->valuedouble > (double)total_size) {
            cJSON_Delete(root);
            esp_http_client_cleanup(client);
            ESP_LOGW(TAG, "Invalid resume offset for %s", fname);
            return ESP_FAIL;
        }
        offset = (size_t)rb->valuedouble;
        if (offset > 0) ESP_LOGI(TAG, "Resuming %s from byte %zu", fname, offset);
        cJSON_Delete(root);
        esp_http_client_cleanup(client);
    }

    /* ── Phase 2: Batch upload ──────────────────────────────────────────── */
    int total_batches = (int)((total_size - offset + NETWORK_BATCH_SIZE - 1) / NETWORK_BATCH_SIZE);
    int batch_count   = 0;

    if (cb) {
        upload_progress_t prog = {
            .event = UPLOAD_EVT_START, .filename = fname,
            .file_index = file_index, .total_files = total_files,
            .sent_bytes = offset, .total_bytes = total_size,
            .global_sent = global_offset + offset, .global_total = global_total,
            .total_batches = total_batches, .batch_count = 0, .detail = "Starting",
        };
        cb(&prog, cb_ctx);
    }

    /* Allocate read buffer */
    uint8_t *read_buf = malloc(NETWORK_READ_CHUNK_SIZE);
    if (!read_buf) return ESP_ERR_NO_MEM;

    FILE *f = fopen(filepath, "rb");
    if (!f) { free(read_buf); return ESP_FAIL; }
    if (offset > 0) fseek(f, (long)offset, SEEK_SET);

    esp_err_t upload_ret = ESP_OK;

    while (offset < total_size) {
        size_t batch_size = total_size - offset;
        if (batch_size > NETWORK_BATCH_SIZE) batch_size = NETWORK_BATCH_SIZE;

        http_ctx_t ctx = {0};
        esp_http_client_config_t hcfg = {
            .url = batch_url, .method = HTTP_METHOD_POST,
            .timeout_ms = (int)NETWORK_UPLOAD_TIMEOUT_MS,
            .event_handler = _http_event_handler, .user_data = &ctx,
            .crt_bundle_attach = esp_crt_bundle_attach,
        };
        esp_http_client_handle_t client = esp_http_client_init(&hcfg);
        if (!client) {
            upload_ret = ESP_ERR_NO_MEM;
            break;
        }
        esp_http_client_set_header(client, "Authorization", auth_hdr);
        esp_http_client_set_header(client, "Content-Type", "application/octet-stream");
        esp_http_client_set_header(client, "X-Filename",   fname);

        char hdr_val[32];
        snprintf(hdr_val, sizeof(hdr_val), "%zu", offset);
        esp_http_client_set_header(client, "X-Offset", hdr_val);
        snprintf(hdr_val, sizeof(hdr_val), "%zu", total_size);
        esp_http_client_set_header(client, "X-Total-Size", hdr_val);
        snprintf(hdr_val, sizeof(hdr_val), "%zu", batch_size);
        esp_http_client_set_header(client, "Content-Length", hdr_val);

        /* Open connection for streaming write */
        if (esp_http_client_open(client, (int)batch_size) != ESP_OK) {
            esp_http_client_cleanup(client);
            upload_ret = ESP_FAIL;
            break;
        }

        /* Stream batch in NETWORK_READ_CHUNK_SIZE chunks */
        size_t sent_in_batch = 0;
        while (sent_in_batch < batch_size) {
            size_t to_read = batch_size - sent_in_batch;
            if (to_read > NETWORK_READ_CHUNK_SIZE) to_read = NETWORK_READ_CHUNK_SIZE;
            size_t n = fread(read_buf, 1, to_read, f);
            if (n == 0) break;
            int written = esp_http_client_write(client, (const char *)read_buf, (int)n);
            if (written != (int)n) { upload_ret = ESP_FAIL; break; }
            sent_in_batch += (size_t)written;
        }

        /* Fetch response */
        esp_http_client_fetch_headers(client);
        if (upload_ret == ESP_OK) {
            size_t body_capacity = 0;
            char *body_buffer = _http_ctx_buffer(&ctx, &body_capacity);
            size_t remaining = body_capacity > ctx.body_len
                                 ? body_capacity - ctx.body_len - 1 : 0;
            int read = remaining > 0
                     ? esp_http_client_read_response(client,
                                                     body_buffer + ctx.body_len,
                                                     (int)remaining)
                     : 0;
            if (read > 0) {
                ctx.body_len += (size_t)read;
                body_buffer[ctx.body_len] = '\0';
            }
        }
        int status = esp_http_client_get_status_code(client);
        esp_http_client_cleanup(client);

        if (upload_ret != ESP_OK) break;
        if (status != 200 || ctx.truncated || ctx.body_len == 0) {
            ESP_LOGE(TAG, "Batch %d HTTP error: %d", batch_count + 1, status);
            upload_ret = ESP_FAIL;
            break;
        }

        cJSON *batch_response = cJSON_Parse(_http_ctx_data(&ctx));
        cJSON *received = batch_response
                            ? cJSON_GetObjectItemCaseSensitive(batch_response, "received")
                            : NULL;
        cJSON *server_offset = batch_response
                               ? cJSON_GetObjectItemCaseSensitive(batch_response, "offset")
                               : NULL;
        cJSON *server_bytes = batch_response
                              ? cJSON_GetObjectItemCaseSensitive(batch_response, "bytes")
                              : NULL;
        bool response_ok = cJSON_IsTrue(received) &&
                           cJSON_IsNumber(server_offset) &&
                           cJSON_IsNumber(server_bytes) &&
                           server_offset->valuedouble == (double)(offset + sent_in_batch) &&
                           server_bytes->valuedouble == (double)sent_in_batch;
        if (batch_response) cJSON_Delete(batch_response);
        if (!response_ok || sent_in_batch != batch_size) {
            ESP_LOGE(TAG, "Batch %d response/length mismatch", batch_count + 1);
            upload_ret = ESP_FAIL;
            break;
        }

        offset += sent_in_batch;
        batch_count++;
        ESP_LOGI(TAG, "Batch %d/%d: %zu/%zu bytes", batch_count, total_batches, offset, total_size);

        if (cb) {
            upload_progress_t prog = {
                .event = UPLOAD_EVT_PROGRESS, .filename = fname,
                .file_index = file_index, .total_files = total_files,
                .sent_bytes = offset, .total_bytes = total_size,
                .global_sent = global_offset + offset, .global_total = global_total,
                .batch_count = batch_count, .total_batches = total_batches,
                .detail = "Uploading",
            };
            cb(&prog, cb_ctx);
        }
    }

    fclose(f);
    free(read_buf);

    if (upload_ret != ESP_OK) return upload_ret;

    /* ── Phase 3: Finalize ──────────────────────────────────────────────── */
    for (int attempt = 0; attempt < NETWORK_MAX_RETRIES; attempt++) {
        cJSON *body = cJSON_CreateObject();
        cJSON_AddStringToObject(body, "filename", fname);
        cJSON_AddNumberToObject(body, "total_size", (double)total_size);
        char *body_str = cJSON_Print(body);
        cJSON_Delete(body);

        http_ctx_t ctx = {0};
        esp_http_client_config_t hcfg = {
            .url = complete_url, .method = HTTP_METHOD_POST,
            .timeout_ms = 15000,
            .event_handler = _http_event_handler, .user_data = &ctx,
            .crt_bundle_attach = esp_crt_bundle_attach,
        };
        esp_http_client_handle_t client = esp_http_client_init(&hcfg);
        esp_http_client_set_header(client, "Authorization", auth_hdr);
        esp_http_client_set_header(client, "Content-Type", "application/json");
        esp_http_client_set_post_field(client, body_str, (int)strlen(body_str));

        esp_err_t ret = esp_http_client_perform(client);
        int status    = esp_http_client_get_status_code(client);
        esp_http_client_cleanup(client);
        free(body_str);

        if (ret == ESP_OK && status == 200 && _response_success(&ctx)) {
            ESP_LOGI(TAG, "Upload finalized: %s (%d batches, %zu bytes)", fname, batch_count, total_size);
            /* The per-file DONE callback is emitted only after the caller
             * archives the local source successfully. */
            return ESP_OK;
        }
        ESP_LOGW(TAG, "Finalize attempt %d failed (status %d)", attempt + 1, status);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    return ESP_FAIL;
}

bool network_sync_all(upload_progress_cb_t cb, void *cb_ctx)
{
    return network_sync_all_with_heartbeat(cb, cb_ctx, NULL, NULL);
}

bool network_sync_all_with_heartbeat(upload_progress_cb_t cb, void *cb_ctx,
                                     network_heartbeat_cb_t heartbeat_cb,
                                     void *heartbeat_ctx)
{
    network_device_config_t cfg = {0};
    esp_err_t config_ret = network_load_device_config(&cfg);
    ESP_LOGI(TAG,
             "Sync config load: ret=%s ssid=%s password=%s token=%s api_url=%s",
             esp_err_to_name(config_ret),
             cfg.ssid[0] ? "set" : "missing",
             cfg.password[0] ? "set" : "empty",
             cfg.token[0] ? "set" : "missing",
             cfg.api_url[0] ? "set" : "missing");
    if (config_ret != ESP_OK) {
        ESP_LOGE(TAG, "No device config — cannot sync");
        return false;
    }

    /* Connect to WiFi */
    if (!network_is_connected()) {
        ESP_LOGI(TAG, "Sync phase: connecting to provisioned WiFi");
        if (network_wifi_connect(cfg.ssid, cfg.password) != ESP_OK) {
            ESP_LOGE(TAG, "WiFi connection failed — aborting sync");
            return false;
        }
    }

    ESP_LOGI(TAG, "Sync phase: heartbeat");
    if (heartbeat_cb) {
        heartbeat_cb(NETWORK_HEARTBEAT_PINGING, heartbeat_ctx);
    }
    if (network_heartbeat(cfg.token, cfg.api_url) != ESP_OK) {
        if (heartbeat_cb) {
            heartbeat_cb(NETWORK_HEARTBEAT_FAILED, heartbeat_ctx);
        }
        ESP_LOGE(TAG, "Heartbeat failed — aborting sync");
        return false;
    }
    if (heartbeat_cb) {
        heartbeat_cb(NETWORK_HEARTBEAT_ACKNOWLEDGED, heartbeat_ctx);
    }

    ESP_LOGI(TAG, "Sync phase: checking offline track catalog");
    esp_err_t track_ret = network_sync_track_catalog(cfg.token, cfg.api_url);
    if (track_ret != ESP_OK) {
        /* Track refresh must not strand already-recorded sessions. */
        ESP_LOGW(TAG, "Track catalog reconciliation failed: %s", esp_err_to_name(track_ret));
    }

    /* Scan session directory for pending CSVs */
    const char *dir = "/sd/sessions"; /* storage always writes to SD when mounted */
    DIR *d = opendir(dir);
    if (!d) { dir = "/data/learning"; d = opendir(dir); }
    if (!d) return true; /* Nothing to sync */

    /* Build a dynamically sized list so sync is not silently capped at 64
     * files.  The old fixed array caused the UI to report completion while
     * later pending files were never considered. */
    typedef struct { char path[96]; size_t size; } entry_t;
    entry_t *entries      = NULL;
    size_t   entry_count  = 0;
    size_t   entry_cap    = 0;
    size_t   global_total = 0;

    struct dirent *de;
    while ((de = readdir(d)) != NULL) {
        if (strncmp(de->d_name, "sess_", 5) != 0) continue;
        if (!strstr(de->d_name, ".csv"))          continue;

        char path[320];
        snprintf(path, sizeof(path), "%s/%s", dir, de->d_name);
        if (!_validate_session(path)) {
            ESP_LOGW(TAG, "Invalid CSV header — archiving: %s", de->d_name);
            storage_archive_session(path);
            continue;
        }
        struct stat st;
        if (stat(path, &st) != 0 || st.st_size == 0) continue;

        if (entry_count == entry_cap) {
            size_t new_cap = entry_cap == 0 ? 16 : entry_cap * 2;
            entry_t *grown = realloc(entries, new_cap * sizeof(*entries));
            if (!grown) {
                ESP_LOGE(TAG, "Unable to allocate sync list for %zu files", entry_count + 1);
                free(entries);
                closedir(d);
                return false;
            }
            entries = grown;
            entry_cap = new_cap;
        }

        strncpy(entries[entry_count].path, path, sizeof(entries[entry_count].path) - 1);
        entries[entry_count].path[sizeof(entries[entry_count].path) - 1] = '\0';
        entries[entry_count].size = (size_t)st.st_size;
        global_total += entries[entry_count].size;
        entry_count++;
    }
    closedir(d);

    ESP_LOGI(TAG, "Sync: %zu files / %.2f MB total", entry_count,
             (float)global_total / (1024.0f * 1024.0f));

    int      success_count = 0;
    size_t   global_offset = 0;

    for (size_t i = 0; i < entry_count; i++) {
        bool ok = false;
        for (int attempt = 0; attempt < NETWORK_MAX_RETRIES; attempt++) {
            esp_err_t ret = network_upload_file(
                entries[i].path, cfg.token, cfg.api_url,
                cb, cb_ctx,
                (int)i, (int)entry_count,
                global_offset, global_total);
            if (ret == ESP_OK) { ok = true; break; }
            ESP_LOGW(TAG, "Retry %d/%d for %s", attempt + 1, NETWORK_MAX_RETRIES,
                     entries[i].path);
            vTaskDelay(pdMS_TO_TICKS(NETWORK_RETRY_DELAY_MS));
        }

        if (ok) {
            esp_err_t archive_ret = ESP_FAIL;
            for (int attempt = 0; attempt < NETWORK_MAX_RETRIES; attempt++) {
                archive_ret = storage_archive_session(entries[i].path);
                if (archive_ret == ESP_OK) break;
                ESP_LOGW(TAG, "Archive retry %d/%d for %s: %s",
                         attempt + 1, NETWORK_MAX_RETRIES,
                         entries[i].path, esp_err_to_name(archive_ret));
                vTaskDelay(pdMS_TO_TICKS(NETWORK_RETRY_DELAY_MS));
            }

            if (archive_ret == ESP_OK) {
                success_count++;
                if (cb) {
                    const char *fname = strrchr(entries[i].path, '/');
                    upload_progress_t prog = {
                        .event = UPLOAD_EVT_DONE,
                        .filename = fname ? fname + 1 : entries[i].path,
                        .file_index = (int)i,
                        .total_files = (int)entry_count,
                        .sent_bytes = entries[i].size,
                        .total_bytes = entries[i].size,
                        .global_sent = global_offset + entries[i].size,
                        .global_total = global_total,
                        .detail = "Uploaded and archived",
                    };
                    cb(&prog, cb_ctx);
                }
            } else if (cb) {
                const char *fname = strrchr(entries[i].path, '/');
                upload_progress_t prog = {
                    .event = UPLOAD_EVT_FAILED,
                    .filename = fname ? fname + 1 : entries[i].path,
                    .file_index = (int)i,
                    .total_files = (int)entry_count,
                    .total_bytes = entries[i].size,
                    .detail = "Server accepted file but local archive failed",
                };
                cb(&prog, cb_ctx);
            }
        } else if (cb) {
            const char *fname = strrchr(entries[i].path, '/');
            upload_progress_t prog = {
                .event = UPLOAD_EVT_FAILED,
                .filename = fname ? fname + 1 : entries[i].path,
                .file_index = (int)i, .total_files = (int)entry_count,
                .total_bytes = entries[i].size, .detail = "Upload failed",
            };
            cb(&prog, cb_ctx);
        }
        global_offset += entries[i].size;
    }

    free(entries);

    if (cb) {
        upload_progress_t prog = { .event = UPLOAD_EVT_ALL_DONE,
            .total_files = (int)entry_count,
            .detail = success_count == (int)entry_count
                          ? "Sync complete" : "Sync incomplete" };
        cb(&prog, cb_ctx);
    }

    ESP_LOGI(TAG, "Sync complete: %d/%zu files", success_count, entry_count);
    return success_count == entry_count;
}

bool network_sync_probe(void)
{
    network_device_config_t cfg = {0};
    esp_err_t config_ret = network_load_device_config(&cfg);
    if (config_ret != ESP_OK) {
        ESP_LOGE(TAG, "Probe config load failed: %s", esp_err_to_name(config_ret));
        return false;
    }

    ESP_LOGI(TAG, "Probe phase: connecting to saved WiFi");
    if (!network_is_connected() &&
        network_wifi_connect(cfg.ssid, cfg.password) != ESP_OK) {
        ESP_LOGE(TAG, "Probe WiFi connection failed");
        return false;
    }

    ESP_LOGI(TAG, "Probe phase: server heartbeat");
    if (network_heartbeat(cfg.token, cfg.api_url) != ESP_OK) {
        ESP_LOGE(TAG, "Probe heartbeat failed");
        network_wifi_disconnect();
        return false;
    }

    ESP_LOGI(TAG, "Probe phase: track catalog check");
    esp_err_t track_ret = network_sync_track_catalog(cfg.token, cfg.api_url);
    if (track_ret != ESP_OK && track_ret != ESP_ERR_NOT_FOUND) {
        ESP_LOGE(TAG, "Probe active-track fetch failed: %s", esp_err_to_name(track_ret));
        network_wifi_disconnect();
        return false;
    }

    network_wifi_disconnect();
    ESP_LOGI(TAG, "Probe completed without session upload");
    return true;
}

/* ══════════════════════════════════════════════════════════════════════════
 * SECTION 4: Captive Portal — DNS hijack + HTTP provisioning server
 * ══════════════════════════════════════════════════════════════════════════*/

/* Setup HTML page (pre-filled with saved config if any) */
static const char *SETUP_HTML_TMPL =
"<!DOCTYPE html><html><head>"
"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
"<title>RS-Core Setup</title>"
"<style>"
":root{--orange:#ff6b35;--bg:#121212;--card:#1e1e1e;--text:#e0e0e0;--border:#333}"
"*{box-sizing:border-box;margin:0;padding:0}"
"body{font-family:-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--text);"
"display:flex;align-items:center;justify-content:center;min-height:100vh;padding:1.5rem}"
".c{background:var(--card);width:100%%;max-width:400px;padding:2rem;border-radius:16px;"
"border:1px solid var(--border);box-shadow:0 10px 30px rgba(0,0,0,.5)}"
"h1{color:var(--orange);font-size:1.5rem;margin-bottom:.5rem;text-transform:uppercase;"
"letter-spacing:1px;text-align:center}"
"label{display:block;font-size:.75rem;font-weight:700;color:#aaa;text-transform:uppercase;"
"margin-top:1.2rem;margin-bottom:.4rem}"
"input{width:100%%;padding:.9rem;border:1px solid var(--border);border-radius:10px;"
"background:#2a2a2a;color:#fff;font-size:1rem}"
"button{width:100%%;padding:1rem;margin-top:2rem;border:none;border-radius:12px;"
"background:var(--orange);color:#fff;font-size:1rem;font-weight:800;text-transform:uppercase}"
"</style></head><body><div class=\"c\">"
"<h1>&#127950; RS-Core Setup</h1>"
"<form method=\"POST\" action=\"/setup\">"
"<label>Hotspot SSID</label>"
"<input name=\"ssid\" value=\"%s\" required placeholder=\"My Hotspot\">"
"<label>Hotspot Password</label>"
"<input name=\"password\" type=\"password\" value=\"%s\" placeholder=\"Leave blank if open\">"
"<label>Device Token</label>"
"<input name=\"token\" value=\"%s\" required placeholder=\"rsk_xxxxxxxx\">"
"<input type=\"hidden\" name=\"api_url\" value=\"%s\">"
"<button type=\"submit\">Verify &amp; Connect</button>"
"</form>"
"<p style=\"font-size:.7rem;color:#555;text-align:center;margin-top:1.5rem\">"
"RaceSense Datalogger V2 &bull; <a style=\"color:var(--orange)\" href=\"https://racesense.in\">racesense.in</a>"
"</p></div></body></html>";

static const char *SUCCESS_HTML =
"<!DOCTYPE html><html><head>"
"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
"<title>Setup Complete</title>"
"<style>body{font-family:system-ui;background:#050505;color:#fff;"
"display:flex;align-items:center;justify-content:center;min-height:100vh}"
".card{background:rgba(26,26,26,.9);border:1px solid rgba(255,255,255,.08);"
"border-radius:24px;padding:32px;text-align:center;max-width:400px}"
"h1{color:#00d26a;margin-bottom:12px}.big{font-size:52px;color:#ff6b35;font-weight:900}"
"</style></head><body><div class=\"card\">"
"<div class=\"big\">&#10003;</div>"
"<h1>Credentials Linked</h1>"
"<p style=\"color:#aaa\">RS-Core saved your settings and will reboot in <strong id='c'>15</strong>s.</p>"
"<p style=\"margin-top:16px;font-weight:700;color:#ff6b35\">Turn on your hotspot now</p>"
"</div><script>var n=15;setInterval(function(){n--;if(n<0)n=0;"
"document.getElementById('c').innerText=n},1000);</script>"
"</body></html>";

/**
 * Read one HTTP request, including a fragmented form body when the client
 * sends Content-Length. The portal is intentionally small, but a single
 * recv() is not sufficient for real phones on a busy AP.
 */
static int _read_http_request(int client_fd, char *req, size_t req_len)
{
    if (client_fd < 0 || !req || req_len < 2) return -1;

    size_t total = 0;
    while (total + 1 < req_len) {
        int received = recv(client_fd, req + total, req_len - total - 1, 0);
        if (received <= 0) break;
        total += (size_t)received;
        req[total] = '\0';

        const char *headers_end = strstr(req, "\r\n\r\n");
        if (!headers_end) continue;

        size_t expected = (size_t)(headers_end + 4 - req);
        const char *length_header = strcasestr(req, "Content-Length:");
        if (length_header) {
            long body_len = strtol(length_header + 15, NULL, 10);
            if (body_len < 0 || (size_t)body_len > req_len - expected - 1) {
                return -1;
            }
            expected += (size_t)body_len;
        }
        if (total >= expected || !length_header) break;
    }
    req[total] = '\0';
    return (int)total;
}

/** DNS hijack task — all queries resolve to AP IP */
static void _dns_task(void *arg)
{
    const char *ip_str = NETWORK_AP_IP;
    uint8_t ip_bytes[4];
    int a, b, c, d;
    sscanf(ip_str, "%d.%d.%d.%d", &a, &b, &c, &d);
    ip_bytes[0] = a; ip_bytes[1] = b; ip_bytes[2] = c; ip_bytes[3] = d;

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) { vTaskDelete(NULL); return; }

    struct sockaddr_in bind_addr = {
        .sin_family = AF_INET,
        .sin_addr.s_addr = INADDR_ANY,
        .sin_port = htons(53),
    };
    int reuse = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    bind(sock, (struct sockaddr *)&bind_addr, sizeof(bind_addr));

    struct timeval tv = {.tv_sec = 1, .tv_usec = 0};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    ESP_LOGI(TAG, "DNS hijack running (→ %s)", ip_str);

    uint8_t buf[512];
    while (s_dns_running) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        int n = recvfrom(sock, buf, sizeof(buf), 0,
                         (struct sockaddr *)&client_addr, &client_len);
        if (n < 12) continue;

        /* Build DNS response: copy header, set QR+AA+RA bits, echo question, add A answer */
        uint8_t resp[512];
        memcpy(resp, buf, n);
        resp[2] = 0x81; resp[3] = 0x80;          /* QR=1, AA=1, RA=1 */
        resp[6] = 0x00; resp[7] = 0x01;          /* ANCOUNT = 1 */
        resp[8] = 0x00; resp[9] = 0x00;          /* NSCOUNT = 0 */
        resp[10] = 0x00; resp[11] = 0x00;        /* ARCOUNT = 0 */
        int rlen = n;
        /* Answer record: name pointer, TYPE A, CLASS IN, TTL 60, RDLENGTH 4, IP */
        uint8_t answer[] = {
            0xC0, 0x0C,             /* Name: pointer to offset 12 */
            0x00, 0x01,             /* TYPE: A */
            0x00, 0x01,             /* CLASS: IN */
            0x00, 0x00, 0x00, 0x3C, /* TTL: 60s */
            0x00, 0x04,             /* RDLENGTH: 4 */
            ip_bytes[0], ip_bytes[1], ip_bytes[2], ip_bytes[3],
        };
        memcpy(resp + rlen, answer, sizeof(answer));
        rlen += sizeof(answer);
        sendto(sock, resp, rlen, 0, (struct sockaddr *)&client_addr, client_len);
    }

    close(sock);
    ESP_LOGI(TAG, "DNS task exiting");
    vTaskDelete(NULL);
}

esp_err_t network_start_captive_portal(const char *ap_name)
{
    if (!s_initialized) {
        esp_err_t init_ret = network_init();
        if (init_ret != ESP_OK) return init_ret;
    }

    /* ── Start SoftAP ───────────────────────────────────────────────────── */
    char ap_ssid[32] = {0};
    if (ap_name && ap_name[0]) {
        strncpy(ap_ssid, ap_name, sizeof(ap_ssid) - 1);
    } else {
        network_get_ap_name(ap_ssid, sizeof(ap_ssid));
    }

    wifi_config_t ap_cfg = {0};
    strncpy((char *)ap_cfg.ap.ssid, ap_ssid, sizeof(ap_cfg.ap.ssid) - 1);
    ap_cfg.ap.ssid_len    = strlen(ap_ssid);
    ap_cfg.ap.authmode    = WIFI_AUTH_OPEN;
    ap_cfg.ap.max_connection = 4;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "SoftAP started: SSID=%s IP=%s", ap_ssid, NETWORK_AP_IP);

    /* ── Start DNS hijack task ──────────────────────────────────────────── */
    s_dns_running = true;
    xTaskCreate(_dns_task, "dns_hijack", 4096, NULL, 5, NULL);

    /* ── HTTP server loop ───────────────────────────────────────────────── */
    struct sockaddr_in server_addr = {
        .sin_family = AF_INET,
        .sin_addr.s_addr = INADDR_ANY,
        .sin_port = htons(80),
    };
    int server_fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server_fd < 0) {
        s_dns_running = false;
        esp_wifi_stop();
        return ESP_FAIL;
    }
    int reuse = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    if (bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) != 0 ||
        listen(server_fd, 4) != 0) {
        close(server_fd);
        s_dns_running = false;
        esp_wifi_stop();
        return ESP_FAIL;
    }

    struct timeval tv = {.tv_sec = 0, .tv_usec = 100000}; /* 100ms timeout */
    setsockopt(server_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    /* Load saved config to pre-fill form */
    network_device_config_t saved_cfg = {0};
    network_load_device_config(&saved_cfg);
    if (saved_cfg.api_url[0] == '\0') {
        strncpy(saved_cfg.api_url, "https://racesense.in", sizeof(saved_cfg.api_url) - 1);
    }

    s_portal_running = true;
    int64_t last_conn_ms = esp_timer_get_time() / 1000;
    ESP_LOGI(TAG, "Captive portal running (SSID: %s)", ap_ssid);

    while (s_portal_running) {
        /* Timeout: exit if no client for 60s */
        if ((esp_timer_get_time() / 1000) - last_conn_ms > 60000) {
            ESP_LOGW(TAG, "Portal timeout — no connections for 60s");
            break;
        }

        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        int client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &client_len);
        if (client_fd < 0) continue; /* Timeout — loop back */

        last_conn_ms = esp_timer_get_time() / 1000;

        /* Read request, including fragmented form bodies. */
        char req[4096] = {0};
        struct timeval rtv = {.tv_sec = 3};
        setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &rtv, sizeof(rtv));
        if (_read_http_request(client_fd, req, sizeof(req)) < 0) {
            close(client_fd);
            continue;
        }

        /* Parse method and path */
        char method[8] = {0}, path[512] = {0};
        sscanf(req, "%7s %511s", method, path);

        /* OS captive detection probe suppression (Apple / Android / Windows) */
        const char *stealth_200 = NULL;
        if (strstr(path, "hotspot-detect") || strstr(path, "success.html")) {
            stealth_200 = "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>";
        }
        if (strstr(path, "connecttest.txt")) stealth_200 = "Microsoft Connect Test";
        if (strstr(path, "generate_204")) {
            const char *r204 = "HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
            send(client_fd, r204, strlen(r204), 0);
            close(client_fd);
            continue;
        }
        if (stealth_200) {
            char stealth_resp[512];
            snprintf(stealth_resp, sizeof(stealth_resp),
                     "HTTP/1.1 200 OK\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n%s",
                     strlen(stealth_200), stealth_200);
            send(client_fd, stealth_resp, strlen(stealth_resp), 0);
            close(client_fd);
            continue;
        }

        const char *body = strstr(req, "\r\n\r\n");
        if (body) body += 4;

        /* Parse both the original form POST and the existing web-app magic
         * link. The latter sends ssid/pass/token/api_url in the URL query. */
        network_device_config_t new_cfg = saved_cfg;
        network_provisioning_source_t source = NETWORK_PROVISIONING_NONE;
        esp_err_t provision_ret = network_provisioning_parse_request(
            method, path, body, &saved_cfg, &new_cfg, &source);

        /* Provisioning: save and reboot */
        if (provision_ret == ESP_OK) {
            if (network_save_device_config(&new_cfg) != ESP_OK) {
                ESP_LOGE(TAG, "Provisioning rejected: unable to persist device config");
                close(client_fd);
                continue;
            }

            /* Send success page */
            char hdr[128];
            snprintf(hdr, sizeof(hdr),
                     "HTTP/1.1 200 OK\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n",
                     strlen(SUCCESS_HTML));
            send(client_fd, hdr, strlen(hdr), 0);
            send(client_fd, SUCCESS_HTML, strlen(SUCCESS_HTML), 0);
            close(client_fd);

            ESP_LOGI(TAG, "PROVISIONED via %s; SSID=%s",
                     source == NETWORK_PROVISIONING_MAGIC_LINK ? "magic link" : "form",
                     new_cfg.ssid);
            vTaskDelay(pdMS_TO_TICKS(15000)); /* 15s countdown */
            esp_restart(); /* Never returns */
        }

        /* Show setup form (pre-filled) */
        char *html = malloc(4096);
        if (html) {
            snprintf(html, 4096, SETUP_HTML_TMPL,
                     new_cfg.ssid, new_cfg.password, new_cfg.token, new_cfg.api_url);
            char hdr[128];
            snprintf(hdr, sizeof(hdr),
                     "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                     "Content-Length: %zu\r\nConnection: close\r\n\r\n", strlen(html));
            send(client_fd, hdr, strlen(hdr), 0);
            send(client_fd, html, strlen(html), 0);
            free(html);
        }
        close(client_fd);
    }

    close(server_fd);
    s_dns_running    = false;
    s_portal_running = false;
    esp_wifi_stop();
    ESP_LOGI(TAG, "Captive portal stopped");
    return ESP_OK;
}

esp_err_t network_stop_captive_portal(void)
{
    s_portal_running = false;
    s_dns_running    = false;
    return ESP_OK;
}

esp_err_t network_fetch_active_track(const char *token, const char *api_url)
{
    network_device_config_t cfg = {0};
    if (!token || !api_url) {
        if (network_load_device_config(&cfg) != ESP_OK) return ESP_ERR_NOT_FOUND;
        token   = cfg.token;
        api_url = cfg.api_url;
    }

    char url[256];
    if (network_contract_build_url(api_url, NETWORK_ENDPOINT_ACTIVE_TRACK,
                                   url, sizeof(url)) != ESP_OK) {
        return ESP_ERR_INVALID_ARG;
    }

    char auth_hdr[160];
    snprintf(auth_hdr, sizeof(auth_hdr), "Bearer %s", token);

    const size_t response_capacity = 65536;
    char *response_body = calloc(1, response_capacity);
    char *track_payload = calloc(1, response_capacity);
    if (!response_body || !track_payload) {
        free(response_body);
        free(track_payload);
        return ESP_ERR_NO_MEM;
    }

    http_ctx_t ctx = {
        .external_body = response_body,
        .external_capacity = response_capacity,
    };
    esp_http_client_config_t hcfg = {
        .url = url, .method = HTTP_METHOD_GET,
        .timeout_ms = 10000,
        .event_handler = _http_event_handler, .user_data = &ctx,
        .crt_bundle_attach = esp_crt_bundle_attach,
    };
    esp_http_client_handle_t client = esp_http_client_init(&hcfg);
    if (!client) {
        free(response_body);
        free(track_payload);
        return ESP_ERR_NO_MEM;
    }
    esp_http_client_set_header(client, "Authorization", auth_hdr);
    /* The active assignment is mutable server state.  Do not allow a proxy
     * or gateway to reuse an earlier response after the rider changes the
     * active track in the web UI. */
    esp_http_client_set_header(client, "Cache-Control", "no-cache, no-store");
    esp_http_client_set_header(client, "Pragma", "no-cache");
    esp_err_t ret = esp_http_client_perform(client);
    int status    = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (ret != ESP_OK || status != 200 || ctx.truncated || ctx.body_len == 0) {
        ESP_LOGW(TAG, "Track fetch failed: %s / status %d", esp_err_to_name(ret), status);
        free(response_body);
        free(track_payload);
        return ESP_FAIL;
    }

    esp_err_t extract_ret = network_contract_extract_active_track(
        _http_ctx_data(&ctx), ctx.body_len, track_payload, response_capacity);
    free(response_body);
    if (extract_ret == ESP_ERR_NOT_FOUND) {
        ESP_LOGI(TAG, "No active track assigned by server");
        if (unlink("/data/metadata/track.json") != 0 && errno != ENOENT) {
            ESP_LOGW(TAG, "Could not clear stale active-track cache: errno=%d", errno);
            free(track_payload);
            return ESP_FAIL;
        }
        free(track_payload);
        return ESP_ERR_NOT_FOUND;
    }
    if (extract_ret != ESP_OK) {
        ESP_LOGW(TAG, "Active track response failed schema validation");
        free(track_payload);
        return extract_ret;
    }

    /* Log the identity that was actually returned, rather than only logging
     * that the file write succeeded.  This makes a stale server assignment
     * distinguishable from a stale in-memory track on the device. */
    cJSON *payload_root = cJSON_Parse(track_payload);
    if (payload_root) {
        cJSON *track_id = cJSON_GetObjectItemCaseSensitive(payload_root, "track_id");
        cJSON *name = cJSON_GetObjectItemCaseSensitive(payload_root, "name");
        if (!cJSON_IsString(name) || !name->valuestring || !name->valuestring[0]) {
            name = cJSON_GetObjectItemCaseSensitive(payload_root, "track_name");
        }
        ESP_LOGI(TAG, "Active track payload: id=%s name=%s",
                 cJSON_IsNumber(track_id) ? "present" : "missing",
                 cJSON_IsString(name) && name->valuestring ? name->valuestring : "(unnamed)");
        if (cJSON_IsNumber(track_id)) {
            ESP_LOGI(TAG, "Active track payload ID: %lld",
                     (long long)track_id->valuedouble);
        }
        cJSON_Delete(payload_root);
    }

    /* Save only after the wrapper/schema has been validated. */
    mkdir("/data", 0755);
    mkdir("/data/metadata", 0755);
    const char *track_path = "/data/metadata/track.json";
    const char *temp_path  = "/data/metadata/track.json.tmp";
    FILE *f = fopen(temp_path, "w");
    if (!f) {
        free(track_payload);
        return ESP_FAIL;
    }
    size_t payload_len = strlen(track_payload);
    bool write_ok = fwrite(track_payload, 1, payload_len, f) == payload_len &&
                    fflush(f) == 0;
    if (write_ok) {
        int fd = fileno(f);
        if (fd >= 0 && fsync(fd) != 0) write_ok = false;
    }
    if (fclose(f) != 0) write_ok = false;
    if (!write_ok || rename(temp_path, track_path) != 0) {
        unlink(temp_path);
        free(track_payload);
        ESP_LOGW(TAG, "Could not atomically replace %s", track_path);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Track JSON saved atomically (%zu bytes)", payload_len);
    free(track_payload);
    return ESP_OK;
}

/* ──────────────────────────────────────────────────────────────────────────
 * Offline track catalog
 * ────────────────────────────────────────────────────────────────────────*/

static esp_err_t _http_get_json(const char *url, const char *token,
                                size_t capacity, char **out_body, size_t *out_len)
{
    if (!url || !token || !out_body || !out_len) return ESP_ERR_INVALID_ARG;
    *out_body = NULL;
    *out_len = 0;

    char *body = calloc(1, capacity);
    if (!body) return ESP_ERR_NO_MEM;
    http_ctx_t ctx = {
        .external_body = body,
        .external_capacity = capacity,
    };
    esp_http_client_config_t hcfg = {
        .url = url,
        .method = HTTP_METHOD_GET,
        .timeout_ms = 15000,
        .event_handler = _http_event_handler,
        .user_data = &ctx,
        .crt_bundle_attach = esp_crt_bundle_attach,
    };
    esp_http_client_handle_t client = esp_http_client_init(&hcfg);
    if (!client) {
        free(body);
        return ESP_ERR_NO_MEM;
    }
    char auth_hdr[160];
    snprintf(auth_hdr, sizeof(auth_hdr), "Bearer %s", token);
    esp_http_client_set_header(client, "Authorization", auth_hdr);
    esp_http_client_set_header(client, "Cache-Control", "no-cache, no-store");
    esp_http_client_set_header(client, "Pragma", "no-cache");
    esp_err_t ret = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);
    if (ret != ESP_OK || status != 200 || ctx.truncated || ctx.body_len == 0) {
        ESP_LOGW(TAG, "Track catalog request failed: %s / status %d",
                 esp_err_to_name(ret), status);
        free(body);
        return ret != ESP_OK ? ret : ESP_FAIL;
    }
    *out_body = body;
    *out_len = ctx.body_len;
    return ESP_OK;
}

static bool _copy_temp_over_target(const char *temp, const char *target)
{
    FILE *in = fopen(temp, "r");
    if (!in) return false;
    FILE *out = fopen(target, "w");
    if (!out) {
        fclose(in);
        return false;
    }
    char buffer[4096];
    size_t n;
    bool ok = true;
    while ((n = fread(buffer, 1, sizeof(buffer), in)) > 0) {
        if (fwrite(buffer, 1, n, out) != n) {
            ok = false;
            break;
        }
    }
    if (ferror(in) || fflush(out) != 0) ok = false;
    fclose(in);
    if (fclose(out) != 0) ok = false;
    if (ok) unlink(temp);
    return ok;
}

/* FATFS/VFS on the device returns EEXIST when rename() targets an existing
 * file, unlike POSIX rename().  Remove the old destination and retry.  Some
 * card/VFS combinations still reject that second rename, so fall back to
 * copying the fully-written temp file over the destination. */
static bool _rename_replace(const char *temp, const char *target)
{
    if (rename(temp, target) == 0) return true;
    if (errno != EEXIST) return false;
    if (unlink(target) == 0 || errno == ENOENT) {
        if (rename(temp, target) == 0) return true;
    }
    ESP_LOGW(TAG, "FAT rename replacement fallback: %s -> %s", temp, target);
    return _copy_temp_over_target(temp, target);
}

static esp_err_t _atomic_write_text(const char *path, const char *text, size_t len)
{
    if (!path || !text) return ESP_ERR_INVALID_ARG;
    char temp[192];
    snprintf(temp, sizeof(temp), "%s.tmp", path);
    FILE *f = fopen(temp, "w");
    if (!f) {
        ESP_LOGW(TAG, "Metadata write open failed: %s errno=%d", temp, errno);
        return ESP_FAIL;
    }
    bool ok = fwrite(text, 1, len, f) == len && fflush(f) == 0;
    int fd = fileno(f);
    /* FATFS/VFS builds used by some board images report fsync as unsupported
     * even after fflush has committed the file.  Treat that as a durability
     * warning, not as a failed catalog update; rename is still atomic. */
    if (ok && fd >= 0 && fsync(fd) != 0) {
        ESP_LOGW(TAG, "Metadata fsync unavailable: %s errno=%d", temp, errno);
    }
    if (fclose(f) != 0) ok = false;
    if (!ok || !_rename_replace(temp, path)) {
        ESP_LOGW(TAG, "Metadata write failed: %s -> %s errno=%d", temp, path, errno);
        unlink(temp);
        return ESP_FAIL;
    }
    return ESP_OK;
}

static esp_err_t _copy_file_atomic(const char *source, const char *target)
{
    FILE *in = fopen(source, "r");
    if (!in) {
        ESP_LOGW(TAG, "Metadata copy source open failed: %s errno=%d", source, errno);
        return ESP_ERR_NOT_FOUND;
    }
    char temp[192];
    snprintf(temp, sizeof(temp), "%s.tmp", target);
    FILE *out = fopen(temp, "w");
    if (!out) {
        fclose(in);
        ESP_LOGW(TAG, "Metadata copy target open failed: %s errno=%d", temp, errno);
        return ESP_FAIL;
    }
    char buffer[4096];
    size_t n;
    bool ok = true;
    while ((n = fread(buffer, 1, sizeof(buffer), in)) > 0) {
        if (fwrite(buffer, 1, n, out) != n) {
            ok = false;
            break;
        }
    }
    if (ferror(in)) ok = false;
    if (fflush(out) != 0) ok = false;
    int fd = fileno(out);
    if (ok && fd >= 0 && fsync(fd) != 0) {
        ESP_LOGW(TAG, "Metadata copy fsync unavailable: %s errno=%d", temp, errno);
    }
    fclose(in);
    if (fclose(out) != 0) ok = false;
    if (!ok || !_rename_replace(temp, target)) {
        ESP_LOGW(TAG, "Metadata copy failed: %s -> %s errno=%d", source, target, errno);
        unlink(temp);
        return ESP_FAIL;
    }
    return ESP_OK;
}

static void _track_cache_path(int32_t track_id, char *path, size_t path_len)
{
    snprintf(path, path_len, TRACK_CATALOG_DIR "/%ld.json", (long)track_id);
}

static cJSON *_catalog_track_entry(cJSON *tracks, int32_t track_id)
{
    if (!cJSON_IsArray(tracks)) return NULL;
    cJSON *entry = NULL;
    cJSON_ArrayForEach(entry, tracks) {
        cJSON *id = cJSON_GetObjectItemCaseSensitive(entry, "track_id");
        if (cJSON_IsNumber(id) && (int32_t)id->valuedouble == track_id) return entry;
    }
    return NULL;
}

static bool _catalog_cache_complete(cJSON *tracks)
{
    if (!cJSON_IsArray(tracks)) return false;
    cJSON *entry = NULL;
    cJSON_ArrayForEach(entry, tracks) {
        cJSON *id = cJSON_GetObjectItemCaseSensitive(entry, "track_id");
        if (!cJSON_IsNumber(id)) return false;
        char path[96];
        _track_cache_path((int32_t)id->valuedouble, path, sizeof(path));
        if (access(path, F_OK) != 0) return false;
    }
    return true;
}

static int32_t _catalog_default_id(cJSON *root)
{
    cJSON *value = cJSON_GetObjectItemCaseSensitive(root, "default_track_id");
    return cJSON_IsNumber(value) ? (int32_t)value->valuedouble : 0;
}

static esp_err_t _save_catalog_track(int32_t track_id, const char *body, size_t body_len)
{
    cJSON *root = cJSON_ParseWithLength(body, body_len);
    if (!root) return ESP_FAIL;
    cJSON *track = cJSON_GetObjectItemCaseSensitive(root, "track");
    cJSON *start = cJSON_IsObject(track)
                 ? cJSON_GetObjectItemCaseSensitive(track, "start_line") : NULL;
    if (cJSON_IsObject(start) && !cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(start, "lat"))) {
        cJSON *center = cJSON_GetObjectItemCaseSensitive(start, "center");
        cJSON *center_lat = cJSON_IsObject(center)
                          ? cJSON_GetObjectItemCaseSensitive(center, "lat") : NULL;
        cJSON *center_lon = cJSON_IsObject(center)
                          ? cJSON_GetObjectItemCaseSensitive(center, "lon") : NULL;
        if (cJSON_IsNumber(center_lat) && cJSON_IsNumber(center_lon)) {
            cJSON_AddItemToObject(start, "lat", cJSON_Duplicate(center_lat, true));
            cJSON_AddItemToObject(start, "lon", cJSON_Duplicate(center_lon, true));
        }
    }
    cJSON *sectors = cJSON_IsObject(track)
                   ? cJSON_GetObjectItemCaseSensitive(track, "sectors") : NULL;
    cJSON *name = cJSON_IsObject(track)
                ? cJSON_GetObjectItemCaseSensitive(track, "name") : NULL;
    if (!cJSON_IsObject(track) || !cJSON_IsObject(start) ||
        !cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(start, "lat")) ||
        !cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(start, "lon")) ||
        !cJSON_IsString(name) || !name->valuestring || !name->valuestring[0] ||
        !cJSON_IsArray(sectors) || cJSON_GetArraySize(sectors) > 16) {
        ESP_LOGW(TAG, "Track payload rejected: id=%ld bytes=%zu start=%s name=%s sectors=%s count=%d",
                 (long)track_id, body_len,
                 cJSON_IsObject(start) ? "object" : "missing",
                 cJSON_IsString(name) && name->valuestring ? name->valuestring : "missing",
                 cJSON_IsArray(sectors) ? "array" : "missing",
                 cJSON_IsArray(sectors) ? cJSON_GetArraySize(sectors) : -1);
        cJSON_Delete(root);
        return ESP_ERR_INVALID_ARG;
    }
    char *compact = cJSON_PrintUnformatted(track);
    cJSON_Delete(root);
    if (!compact) return ESP_ERR_NO_MEM;
    char path[96];
    _track_cache_path(track_id, path, sizeof(path));
    esp_err_t ret = _atomic_write_text(path, compact, strlen(compact));
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Track payload cache write failed: id=%ld path=%s ret=%s",
                 (long)track_id, path, esp_err_to_name(ret));
    }
    free(compact);
    return ret;
}

static esp_err_t _load_catalog_root(cJSON **out_root)
{
    if (!out_root) return ESP_ERR_INVALID_ARG;
    *out_root = NULL;
    FILE *f = fopen(TRACK_CATALOG_PATH, "r");
    if (!f) return ESP_ERR_NOT_FOUND;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    rewind(f);
    if (size <= 0 || size > TRACK_MANIFEST_CAPACITY) {
        fclose(f);
        return ESP_FAIL;
    }
    char *buf = malloc((size_t)size + 1);
    if (!buf) {
        fclose(f);
        return ESP_ERR_NO_MEM;
    }
    size_t read = fread(buf, 1, (size_t)size, f);
    fclose(f);
    buf[read] = '\0';
    *out_root = cJSON_Parse(buf);
    free(buf);
    return *out_root ? ESP_OK : ESP_FAIL;
}

esp_err_t network_sync_track_catalog(const char *token, const char *api_url)
{
    network_device_config_t cfg = {0};
    if (!token || !api_url) {
        if (network_load_device_config(&cfg) != ESP_OK) return ESP_ERR_NOT_FOUND;
        token = cfg.token;
        api_url = cfg.api_url;
    }

    char url[256];
    if (network_contract_build_url(api_url, "/api/device/track_catalog",
                                   url, sizeof(url)) != ESP_OK) {
        return ESP_ERR_INVALID_ARG;
    }
    char *manifest_body = NULL;
    size_t manifest_len = 0;
    esp_err_t ret = _http_get_json(url, token, TRACK_MANIFEST_CAPACITY,
                                   &manifest_body, &manifest_len);
    if (ret != ESP_OK) return ret;

    cJSON *manifest = cJSON_ParseWithLength(manifest_body, manifest_len);
    if (!manifest) {
        free(manifest_body);
        return ESP_FAIL;
    }
    cJSON *tracks = cJSON_GetObjectItemCaseSensitive(manifest, "tracks");
    cJSON *revision = cJSON_GetObjectItemCaseSensitive(manifest, "revision");
    if (!cJSON_IsArray(tracks) || cJSON_GetArraySize(tracks) > NETWORK_TRACK_CATALOG_MAX_TRACKS ||
        !cJSON_IsString(revision) || !revision->valuestring) {
        cJSON_Delete(manifest);
        free(manifest_body);
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *old = NULL;
    _load_catalog_root(&old);
    cJSON *old_revision = old ? cJSON_GetObjectItemCaseSensitive(old, "revision") : NULL;
    int32_t default_id = _catalog_default_id(manifest);
    int32_t old_default_id = old ? _catalog_default_id(old) : 0;
    bool catalog_same = old && cJSON_IsString(old_revision) &&
                        strcmp(old_revision->valuestring, revision->valuestring) == 0;
    bool needs_active_repair = access("/data/metadata/track.json", F_OK) != 0;
    if (catalog_same && !needs_active_repair && _catalog_cache_complete(tracks)) {
        ESP_LOGI(TAG, "Track catalog current (%s); all %d payloads cached",
                 revision->valuestring, cJSON_GetArraySize(tracks));
        cJSON_Delete(old);
        cJSON_Delete(manifest);
        free(manifest_body);
        return ESP_OK;
    }
    if (catalog_same) {
        ESP_LOGI(TAG, "Track catalog manifest current but payload cache incomplete; repairing");
    }

    mkdir("/data", 0755);
    mkdir("/data/metadata", 0755);
    mkdir(TRACK_CATALOG_DIR, 0755);
    cJSON *old_tracks = old ? cJSON_GetObjectItemCaseSensitive(old, "tracks") : NULL;
    cJSON *entry = NULL;
    cJSON_ArrayForEach(entry, tracks) {
        cJSON *id_json = cJSON_GetObjectItemCaseSensitive(entry, "track_id");
        cJSON *fingerprint = cJSON_GetObjectItemCaseSensitive(entry, "fingerprint");
        if (!cJSON_IsNumber(id_json) || !cJSON_IsString(fingerprint)) {
            ret = ESP_ERR_INVALID_ARG;
            break;
        }
        int32_t track_id = (int32_t)id_json->valuedouble;
        char track_path[96];
        _track_cache_path(track_id, track_path, sizeof(track_path));
        cJSON *old_entry = _catalog_track_entry(old_tracks, track_id);
        cJSON *old_fp = old_entry
                      ? cJSON_GetObjectItemCaseSensitive(old_entry, "fingerprint") : NULL;
        bool current = old_fp && cJSON_IsString(old_fp) &&
                       strcmp(old_fp->valuestring, fingerprint->valuestring) == 0 &&
                       access(track_path, F_OK) == 0;
        if (current) continue;

        char item_path[256];
        snprintf(item_path, sizeof(item_path), "/api/device/track_catalog/%ld", (long)track_id);
        if (network_contract_build_url(api_url, item_path, url, sizeof(url)) != ESP_OK) {
            ret = ESP_ERR_INVALID_ARG;
            break;
        }
        char *track_body = NULL;
        size_t track_len = 0;
        ret = _http_get_json(url, token, TRACK_PAYLOAD_CAPACITY, &track_body, &track_len);
        if (ret == ESP_OK) {
            ret = _save_catalog_track(track_id, track_body, track_len);
            free(track_body);
        }
        if (ret != ESP_OK) {
            ESP_LOGW(TAG, "Track catalog item failed: id=%ld ret=%s",
                     (long)track_id, esp_err_to_name(ret));
            break;
        }
        ESP_LOGI(TAG, "Cached track %ld", (long)track_id);
    }

    if (ret == ESP_OK) {
        /* Remove tracks no longer present in the profile only after all new
         * payloads have been validated and written successfully. */
        if (old_tracks) {
            cJSON *old_entry = NULL;
            cJSON_ArrayForEach(old_entry, old_tracks) {
                cJSON *id_json = cJSON_GetObjectItemCaseSensitive(old_entry, "track_id");
                if (!cJSON_IsNumber(id_json)) continue;
                int32_t old_id = (int32_t)id_json->valuedouble;
                if (!_catalog_track_entry(tracks, old_id)) {
                    char stale_path[96];
                    _track_cache_path(old_id, stale_path, sizeof(stale_path));
                    unlink(stale_path);
                }
            }
        }
        ret = _atomic_write_text(TRACK_CATALOG_PATH, manifest_body, manifest_len);
        if (ret != ESP_OK) {
            ESP_LOGW(TAG, "Track catalog manifest write failed: ret=%s", esp_err_to_name(ret));
        }
    }

    if (ret == ESP_OK && (default_id != old_default_id || needs_active_repair)) {
        if (default_id > 0) {
            ret = network_select_cached_track(default_id);
        } else {
            unlink("/data/metadata/track.json");
            unlink(TRACK_STATE_PATH);
        }
    }
    ESP_LOGI(TAG, "Track catalog reconciliation: %s", esp_err_to_name(ret));
    cJSON_Delete(old);
    cJSON_Delete(manifest);
    free(manifest_body);
    return ret;
}

esp_err_t network_select_cached_track(int32_t track_id)
{
    if (track_id <= 0) return ESP_ERR_INVALID_ARG;
    cJSON *root = NULL;
    esp_err_t ret = _load_catalog_root(&root);
    if (ret != ESP_OK) return ret;
    cJSON *tracks = cJSON_GetObjectItemCaseSensitive(root, "tracks");
    if (!_catalog_track_entry(tracks, track_id)) {
        cJSON_Delete(root);
        return ESP_ERR_NOT_FOUND;
    }
    char source[96];
    _track_cache_path(track_id, source, sizeof(source));
    ESP_LOGI(TAG, "Selecting cached track %ld from %s", (long)track_id, source);
    mkdir("/data", 0755);
    mkdir("/data/metadata", 0755);
    ret = _copy_file_atomic(source, "/data/metadata/track.json");
    if (ret == ESP_OK) {
        cJSON *state = cJSON_CreateObject();
        if (!state) ret = ESP_ERR_NO_MEM;
        else {
            cJSON_AddNumberToObject(state, "active_track_id", track_id);
            char *text = cJSON_PrintUnformatted(state);
            cJSON_Delete(state);
            if (!text) ret = ESP_ERR_NO_MEM;
            else {
                ret = _atomic_write_text(TRACK_STATE_PATH, text, strlen(text));
                free(text);
            }
        }
    }
    cJSON_Delete(root);
    if (ret == ESP_OK) ESP_LOGI(TAG, "Selected cached track %ld", (long)track_id);
    return ret;
}

esp_err_t network_list_cached_tracks(network_cached_track_t *tracks, int max_tracks,
                                     int *out_count, int32_t *out_active_id)
{
    if (!tracks || max_tracks <= 0 || !out_count) return ESP_ERR_INVALID_ARG;
    *out_count = 0;
    if (out_active_id) *out_active_id = 0;
    cJSON *root = NULL;
    esp_err_t ret = _load_catalog_root(&root);
    if (ret != ESP_OK) return ret;
    int32_t active_id = 0;
    FILE *state_file = fopen(TRACK_STATE_PATH, "r");
    if (state_file) {
        char state_buf[128] = {0};
        size_t state_len = fread(state_buf, 1, sizeof(state_buf) - 1, state_file);
        fclose(state_file);
        cJSON *state = cJSON_ParseWithLength(state_buf, state_len);
        if (state) {
            cJSON *id = cJSON_GetObjectItemCaseSensitive(state, "active_track_id");
            if (cJSON_IsNumber(id)) active_id = (int32_t)id->valuedouble;
            cJSON_Delete(state);
        }
    }
    cJSON *default_id = cJSON_GetObjectItemCaseSensitive(root, "default_track_id");
    cJSON *items = cJSON_GetObjectItemCaseSensitive(root, "tracks");
    cJSON *item = NULL;
    cJSON_ArrayForEach(item, items) {
        if (*out_count >= max_tracks) break;
        cJSON *id = cJSON_GetObjectItemCaseSensitive(item, "track_id");
        cJSON *name = cJSON_GetObjectItemCaseSensitive(item, "track_name");
        if (!cJSON_IsNumber(id) || !cJSON_IsString(name)) continue;
        network_cached_track_t *out = &tracks[*out_count];
        memset(out, 0, sizeof(*out));
        out->track_id = (int32_t)id->valuedouble;
        strncpy(out->track_name, name->valuestring, sizeof(out->track_name) - 1);
        out->is_server_default = cJSON_IsNumber(default_id) &&
                                 (int32_t)default_id->valuedouble == out->track_id;
        (*out_count)++;
    }
    if (out_active_id) *out_active_id = active_id;
    cJSON_Delete(root);
    return ESP_OK;
}
