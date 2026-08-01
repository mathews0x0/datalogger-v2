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
#include <stdlib.h>
#include <dirent.h>
#include <sys/stat.h>
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
#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "lwip/dns.h"
#include "nvs_flash.h"
#include "cJSON.h"
#include "storage.h"

static const char *TAG = "network";

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
            esp_wifi_connect();
        } else if (event_id == WIFI_EVENT_STA_DISCONNECTED) {
            if (s_retry_count < MAX_STA_RETRIES) {
                s_retry_count++;
                ESP_LOGW(TAG, "WiFi disconnected, retry %d/%d", s_retry_count, MAX_STA_RETRIES);
                esp_wifi_connect();
            } else {
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
    esp_wifi_stop();
    return ESP_FAIL;
}

esp_err_t network_wifi_disconnect(void)
{
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
    if ((item = cJSON_GetObjectItem(root, "ssid")))
        strncpy(cfg->ssid, item->valuestring, sizeof(cfg->ssid) - 1);
    if ((item = cJSON_GetObjectItem(root, "password")))
        strncpy(cfg->password, item->valuestring, sizeof(cfg->password) - 1);
    if ((item = cJSON_GetObjectItem(root, "token")))
        strncpy(cfg->token, item->valuestring, sizeof(cfg->token) - 1);
    if ((item = cJSON_GetObjectItem(root, "api_url")))
        strncpy(cfg->api_url, item->valuestring, sizeof(cfg->api_url) - 1);

    cJSON_Delete(root);

    if (cfg->token[0] == '\0' || cfg->api_url[0] == '\0') {
        return ESP_ERR_NOT_FOUND;
    }
    return ESP_OK;
}

esp_err_t network_save_device_config(const network_device_config_t *cfg)
{
    if (!cfg) return ESP_ERR_INVALID_ARG;

    /* Ensure directory exists */
    mkdir("/data", 0755);
    mkdir("/data/metadata", 0755);

    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "ssid",     cfg->ssid);
    cJSON_AddStringToObject(root, "password", cfg->password);
    cJSON_AddStringToObject(root, "token",    cfg->token);
    cJSON_AddStringToObject(root, "api_url",  cfg->api_url);

    char *json_str = cJSON_Print(root);
    cJSON_Delete(root);
    if (!json_str) return ESP_ERR_NO_MEM;

    FILE *f = fopen(NETWORK_DEVICE_CONFIG_PATH, "w");
    if (!f) { free(json_str); return ESP_FAIL; }
    fputs(json_str, f);
    fclose(f);
    free(json_str);

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
    int    body_len;
    int    status_code;
} http_ctx_t;

static esp_err_t _http_event_handler(esp_http_client_event_t *evt)
{
    http_ctx_t *ctx = (http_ctx_t *)evt->user_data;
    if (!ctx) return ESP_OK;
    if (evt->event_id == HTTP_EVENT_ON_DATA && evt->data_len > 0) {
        int rem = sizeof(ctx->body) - ctx->body_len - 1;
        if (rem > 0) {
            int copy = evt->data_len < rem ? evt->data_len : rem;
            memcpy(ctx->body + ctx->body_len, evt->data, copy);
            ctx->body_len += copy;
            ctx->body[ctx->body_len] = '\0';
        }
    }
    return ESP_OK;
}

esp_err_t network_heartbeat(const char *token, const char *api_url)
{
    network_device_config_t cfg = {0};
    if (!token || !api_url) {
        if (network_load_device_config(&cfg) != ESP_OK) return ESP_ERR_NOT_FOUND;
        token   = cfg.token;
        api_url = cfg.api_url;
    }

    char url[256];
    snprintf(url, sizeof(url), "%s/heartbeat", api_url);

    http_ctx_t ctx = {0};
    esp_http_client_config_t hcfg = {
        .url            = url,
        .method         = HTTP_METHOD_GET,
        .timeout_ms     = 10000,
        .event_handler  = _http_event_handler,
        .user_data      = &ctx,
        .skip_cert_common_name_check = false,
    };

    char auth_hdr[160];
    snprintf(auth_hdr, sizeof(auth_hdr), "Bearer %s", token);

    esp_http_client_handle_t client = esp_http_client_init(&hcfg);
    esp_http_client_set_header(client, "Authorization", auth_hdr);

    esp_err_t ret = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (ret == ESP_OK && status == 200) {
        ESP_LOGI(TAG, "Heartbeat OK (200)");
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

    /* Build endpoint URLs */
    char batch_url[256], status_url[256], complete_url[256];
    snprintf(batch_url,    sizeof(batch_url),    "%s/batch",    api_url);
    snprintf(status_url,   sizeof(status_url),   "%s/status",   api_url);
    snprintf(complete_url, sizeof(complete_url), "%s/complete", api_url);

    char auth_hdr[160];
    snprintf(auth_hdr, sizeof(auth_hdr), "Bearer %s", token);

    /* ── Phase 1: Resume check ──────────────────────────────────────────── */
    size_t offset = 0;
    {
        char resume_url[320];
        snprintf(resume_url, sizeof(resume_url), "%s?filename=%s", status_url, fname);

        http_ctx_t ctx = {0};
        esp_http_client_config_t hcfg = {
            .url = resume_url, .method = HTTP_METHOD_GET,
            .timeout_ms = 10000, .event_handler = _http_event_handler, .user_data = &ctx,
        };
        esp_http_client_handle_t client = esp_http_client_init(&hcfg);
        esp_http_client_set_header(client, "Authorization", auth_hdr);
        if (esp_http_client_perform(client) == ESP_OK &&
            esp_http_client_get_status_code(client) == 200 && ctx.body_len > 0) {
            cJSON *root = cJSON_Parse(ctx.body);
            if (root) {
                cJSON *rb = cJSON_GetObjectItem(root, "received_bytes");
                if (rb && cJSON_IsNumber(rb) && rb->valuedouble > 0) {
                    offset = (size_t)rb->valuedouble;
                    ESP_LOGI(TAG, "Resuming %s from byte %zu", fname, offset);
                }
                cJSON_Delete(root);
            }
        }
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

        /* Build batch POST headers manually since we stream the body */
        char extra_headers[512];
        snprintf(extra_headers, sizeof(extra_headers),
                 "Authorization: %s\r\n"
                 "Content-Type: application/octet-stream\r\n"
                 "X-Filename: %s\r\n"
                 "X-Offset: %zu\r\n"
                 "X-Total-Size: %zu\r\n"
                 "X-Global-Progress: %zu\r\n"
                 "X-Global-Total: %zu\r\n"
                 "X-Total-Files: %d\r\n"
                 "X-File-Index: %d\r\n",
                 auth_hdr,
                 fname, offset, total_size,
                 global_offset + offset, global_total,
                 total_files, file_index);

        http_ctx_t ctx = {0};
        esp_http_client_config_t hcfg = {
            .url = batch_url, .method = HTTP_METHOD_POST,
            .timeout_ms = (int)NETWORK_UPLOAD_TIMEOUT_MS,
            .event_handler = _http_event_handler, .user_data = &ctx,
        };
        esp_http_client_handle_t client = esp_http_client_init(&hcfg);
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
            if (written < 0) { upload_ret = ESP_FAIL; break; }
            sent_in_batch += n;
        }

        /* Fetch response */
        esp_http_client_fetch_headers(client);
        int status = esp_http_client_get_status_code(client);
        esp_http_client_cleanup(client);

        if (upload_ret != ESP_OK) break;
        if (status != 200) {
            ESP_LOGE(TAG, "Batch %d HTTP error: %d", batch_count + 1, status);
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
        };
        esp_http_client_handle_t client = esp_http_client_init(&hcfg);
        esp_http_client_set_header(client, "Authorization", auth_hdr);
        esp_http_client_set_header(client, "Content-Type", "application/json");
        esp_http_client_set_post_field(client, body_str, (int)strlen(body_str));

        esp_err_t ret = esp_http_client_perform(client);
        int status    = esp_http_client_get_status_code(client);
        esp_http_client_cleanup(client);
        free(body_str);

        if (ret == ESP_OK && status == 200) {
            ESP_LOGI(TAG, "Upload finalized: %s (%d batches, %zu bytes)", fname, batch_count, total_size);
            if (cb) {
                upload_progress_t prog = {
                    .event = UPLOAD_EVT_DONE, .filename = fname,
                    .file_index = file_index, .total_files = total_files,
                    .sent_bytes = total_size, .total_bytes = total_size,
                    .global_sent = global_offset + total_size, .global_total = global_total,
                    .batch_count = batch_count, .total_batches = total_batches,
                    .detail = "Done",
                };
                cb(&prog, cb_ctx);
            }
            return ESP_OK;
        }
        ESP_LOGW(TAG, "Finalize attempt %d failed (status %d)", attempt + 1, status);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    return ESP_FAIL;
}

bool network_sync_all(upload_progress_cb_t cb, void *cb_ctx)
{
    network_device_config_t cfg = {0};
    if (network_load_device_config(&cfg) != ESP_OK) {
        ESP_LOGE(TAG, "No device config — cannot sync");
        return false;
    }

    /* Connect to WiFi */
    if (!network_is_connected()) {
        if (network_wifi_connect(cfg.ssid, cfg.password) != ESP_OK) {
            ESP_LOGE(TAG, "WiFi connection failed — aborting sync");
            return false;
        }
    }

    /* Scan session directory for pending CSVs */
    const char *dir = "/sd/sessions"; /* storage always writes to SD when mounted */
    DIR *d = opendir(dir);
    if (!d) { dir = "/data/learning"; d = opendir(dir); }
    if (!d) return true; /* Nothing to sync */

    /* Build list of valid session files */
    typedef struct { char path[96]; size_t size; } entry_t;
    entry_t entries[64];
    int     entry_count   = 0;
    size_t  global_total  = 0;

    struct dirent *de;
    while ((de = readdir(d)) != NULL && entry_count < 64) {
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

        strncpy(entries[entry_count].path, path, sizeof(entries[0].path) - 1);
        entries[entry_count].size = (size_t)st.st_size;
        global_total += entries[entry_count].size;
        entry_count++;
    }
    closedir(d);

    ESP_LOGI(TAG, "Sync: %d files / %.2f MB total", entry_count,
             (float)global_total / (1024.0f * 1024.0f));

    int      success_count = 0;
    size_t   global_offset = 0;

    for (int i = 0; i < entry_count; i++) {
        bool ok = false;
        for (int attempt = 0; attempt < NETWORK_MAX_RETRIES; attempt++) {
            esp_err_t ret = network_upload_file(
                entries[i].path, cfg.token, cfg.api_url,
                cb, cb_ctx,
                i, entry_count,
                global_offset, global_total);
            if (ret == ESP_OK) { ok = true; break; }
            ESP_LOGW(TAG, "Retry %d/%d for %s", attempt + 1, NETWORK_MAX_RETRIES,
                     entries[i].path);
            vTaskDelay(pdMS_TO_TICKS(NETWORK_RETRY_DELAY_MS));
        }

        if (ok) {
            storage_archive_session(entries[i].path);
            success_count++;
        } else if (cb) {
            const char *fname = strrchr(entries[i].path, '/');
            upload_progress_t prog = {
                .event = UPLOAD_EVT_FAILED,
                .filename = fname ? fname + 1 : entries[i].path,
                .file_index = i, .total_files = entry_count,
                .total_bytes = entries[i].size, .detail = "Upload failed",
            };
            cb(&prog, cb_ctx);
        }
        global_offset += entries[i].size;
    }

    if (cb) {
        upload_progress_t prog = { .event = UPLOAD_EVT_ALL_DONE,
            .total_files = entry_count, .detail = "Sync complete" };
        cb(&prog, cb_ctx);
    }

    ESP_LOGI(TAG, "Sync complete: %d/%d files", success_count, entry_count);
    return success_count == entry_count;
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

/** Simple URL-decode for form fields (subset matching S3 _parse_params) */
static void _url_decode(const char *src, char *dst, int dst_len)
{
    int i = 0, j = 0;
    while (src[i] && j < dst_len - 1) {
        if (src[i] == '+') {
            dst[j++] = ' ';
            i++;
        } else if (src[i] == '%' && src[i+1] && src[i+2]) {
            char hex[3] = {src[i+1], src[i+2], 0};
            dst[j++] = (char)strtol(hex, NULL, 16);
            i += 3;
        } else {
            dst[j++] = src[i++];
        }
    }
    dst[j] = '\0';
}

/** Parse a single key from a form body string (modifies working copy) */
static void _parse_form_field(const char *body, const char *key, char *out, int out_len)
{
    char search[64];
    snprintf(search, sizeof(search), "%s=", key);
    const char *p = strstr(body, search);
    if (!p) { out[0] = '\0'; return; }
    p += strlen(search);
    const char *end = strchr(p, '&');
    int raw_len = end ? (int)(end - p) : (int)strlen(p);
    char raw[256] = {0};
    if (raw_len > (int)sizeof(raw) - 1) raw_len = sizeof(raw) - 1;
    memcpy(raw, p, raw_len);
    _url_decode(raw, out, out_len);
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
    /* ── Start SoftAP ───────────────────────────────────────────────────── */
    char ap_ssid[32];
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
    int reuse = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr));
    listen(server_fd, 4);

    struct timeval tv = {.tv_sec = 0, .tv_usec = 100000}; /* 100ms timeout */
    setsockopt(server_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    /* Load saved config to pre-fill form */
    network_device_config_t saved_cfg = {0};
    network_load_device_config(&saved_cfg);
    if (saved_cfg.api_url[0] == '\0') {
        strncpy(saved_cfg.api_url, "https://racesense.in/api/upload", sizeof(saved_cfg.api_url) - 1);
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

        /* Read request (up to 2KB) */
        char req[2048] = {0};
        struct timeval rtv = {.tv_sec = 3};
        setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &rtv, sizeof(rtv));
        recv(client_fd, req, sizeof(req) - 1, 0);

        /* Parse method and path */
        char method[8] = {0}, path[128] = {0};
        sscanf(req, "%7s %127s", method, path);

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

        /* Extract POST body */
        char body_ssid[64]={0}, body_pass[64]={0}, body_token[128]={0}, body_api[192]={0};
        if (strcmp(method, "POST") == 0) {
            const char *body = strstr(req, "\r\n\r\n");
            if (body) {
                body += 4;
                _parse_form_field(body, "ssid",     body_ssid,  sizeof(body_ssid));
                _parse_form_field(body, "password", body_pass,  sizeof(body_pass));
                _parse_form_field(body, "token",    body_token, sizeof(body_token));
                _parse_form_field(body, "api_url",  body_api,   sizeof(body_api));
            }
        }

        /* Resolve final field values (POST overrides saved) */
        const char *ssid  = body_ssid[0]  ? body_ssid  : saved_cfg.ssid;
        const char *pass  = body_pass[0]  ? body_pass  : saved_cfg.password;
        const char *token = body_token[0] ? body_token : saved_cfg.token;
        const char *api   = body_api[0]   ? body_api   : saved_cfg.api_url;

        /* Provisioning: save and reboot */
        if ((strcmp(method, "POST") == 0 || (ssid[0] && token[0])) &&
            body_ssid[0] && body_token[0]) {
            network_device_config_t new_cfg = {0};
            strncpy(new_cfg.ssid,     ssid,  sizeof(new_cfg.ssid)  - 1);
            strncpy(new_cfg.password, pass,  sizeof(new_cfg.password) - 1);
            strncpy(new_cfg.token,    token, sizeof(new_cfg.token)  - 1);
            strncpy(new_cfg.api_url,  api,   sizeof(new_cfg.api_url) - 1);
            network_save_device_config(&new_cfg);

            /* Send success page */
            char hdr[128];
            snprintf(hdr, sizeof(hdr),
                     "HTTP/1.1 200 OK\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n",
                     strlen(SUCCESS_HTML));
            send(client_fd, hdr, strlen(hdr), 0);
            send(client_fd, SUCCESS_HTML, strlen(SUCCESS_HTML), 0);
            close(client_fd);

            ESP_LOGI(TAG, "PROVISIONED! SSID=%s Token=%.*s...", ssid, 8, token);
            vTaskDelay(pdMS_TO_TICKS(15000)); /* 15s countdown */
            esp_restart(); /* Never returns */
        }

        /* Show setup form (pre-filled) */
        char *html = malloc(4096);
        if (html) {
            snprintf(html, 4096, SETUP_HTML_TMPL, ssid, pass, token, api);
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
    snprintf(url, sizeof(url), "%s/tracks/active", api_url);

    char auth_hdr[160];
    snprintf(auth_hdr, sizeof(auth_hdr), "Bearer %s", token);

    http_ctx_t ctx = {0};
    esp_http_client_config_t hcfg = {
        .url = url, .method = HTTP_METHOD_GET,
        .timeout_ms = 10000,
        .event_handler = _http_event_handler, .user_data = &ctx,
    };
    esp_http_client_handle_t client = esp_http_client_init(&hcfg);
    esp_http_client_set_header(client, "Authorization", auth_hdr);
    esp_err_t ret = esp_http_client_perform(client);
    int status    = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (ret != ESP_OK || status != 200) {
        ESP_LOGW(TAG, "Track fetch failed: %s / status %d", esp_err_to_name(ret), status);
        return ESP_FAIL;
    }

    /* Save track JSON to /data/metadata/track.json */
    mkdir("/data", 0755);
    mkdir("/data/metadata", 0755);
    FILE *f = fopen("/data/metadata/track.json", "w");
    if (f) {
        fputs(ctx.body, f);
        fclose(f);
        ESP_LOGI(TAG, "Track JSON saved (%d bytes)", ctx.body_len);
    }
    return ESP_OK;
}
