/**
 * @file network.h
 * @brief Network subsystem — WiFi Manager, HTTPS Uploader, Captive Portal
 *
 * P4 WiFi note: WiFi 6 (802.11ax) is provided by the on-board ESP32-C6 module,
 * connected to the P4 via SDIO using the esp-hosted-ng driver. This component
 * uses the standard esp_wifi / esp_netif IDF APIs; the SDIO transport is
 * transparent after esp-hosted init.
 *
 * Device/server API contract:
 *   POST /api/device/ping          — authenticated heartbeat JSON
 *   GET  /api/device/active_track — authenticated active-track wrapper
 *   POST /api/upload/batch         — chunked binary body
 *   GET  /api/upload/status        — resume query
 *   POST /api/upload/complete      — finalize, moves file server-side
 *
 * Captive portal:
 *   SoftAP SSID:  RS-Core-XXXX  (last 4 MAC hex digits, uppercase)
 *   AP IP:        192.168.4.1
 *   DNS:          UDP :53 — all queries hijacked → AP IP  (FreeRTOS task)
 *   HTTP:         TCP :80 — setup form + provisioning handler
 *
 * Device config path: /data/metadata/device.json
 *   { "ssid": "...", "password": "...", "token": "rsk_xxx", "api_url": "https://..." }
 */

#ifndef NETWORK_H
#define NETWORK_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Config paths & constants
 * ────────────────────────────────────────────────────────────────────────*/
#define NETWORK_DEVICE_CONFIG_PATH  "/data/metadata/device.json"
#define NETWORK_AP_IP               "192.168.4.1"
#define NETWORK_BATCH_SIZE          (512 * 1024)  /**< 512KB per HTTP batch  */
#define NETWORK_READ_CHUNK_SIZE     (32  * 1024)  /**< 32KB read per chunk   */
#define NETWORK_MAX_RETRIES         3
#define NETWORK_RETRY_DELAY_MS      2000
#define NETWORK_CONNECT_TIMEOUT_MS  30000         /**< STA connect timeout   */
#define NETWORK_UPLOAD_TIMEOUT_MS   45000         /**< Per-batch HTTP timeout */

/* ──────────────────────────────────────────────────────────────────────────
 * Device configuration (stored in /data/metadata/device.json)
 * ────────────────────────────────────────────────────────────────────────*/
typedef struct {
    char ssid[64];
    char password[64];
    char token[128];
    char api_url[192];
} network_device_config_t;

/** Optional telemetry fields sent by network_heartbeat_with_telemetry().
 * Storage values use the server contract units: MB for SD and KB for flash.
 */
typedef struct {
    const char *device_uid;
    bool        has_vbatt_sense;
    float       vbatt_sense;
    uint64_t    storage_sd_free;
    uint64_t    storage_sd_total;
    uint64_t    storage_flash_free;
    uint64_t    storage_flash_total;
} network_heartbeat_telemetry_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Upload progress callback
 * ────────────────────────────────────────────────────────────────────────*/
typedef enum {
    UPLOAD_EVT_START,      /**< Starting upload of a file                    */
    UPLOAD_EVT_PROGRESS,   /**< Batch sent — update progress bar             */
    UPLOAD_EVT_DONE,       /**< File successfully uploaded and finalized      */
    UPLOAD_EVT_FAILED,     /**< File upload failed after all retries          */
    UPLOAD_EVT_ALL_DONE,   /**< All files in the queue are done               */
} upload_event_t;

typedef struct {
    upload_event_t event;
    const char    *filename;
    int            file_index;
    int            total_files;
    size_t         sent_bytes;
    size_t         total_bytes;
    size_t         global_sent;
    size_t         global_total;
    int            batch_count;
    int            total_batches;
    const char    *detail;
} upload_progress_t;

/** Callback invoked from the upload task on Core 1 for each progress event. */
typedef void (*upload_progress_cb_t)(const upload_progress_t *progress, void *user_ctx);

/* ──────────────────────────────────────────────────────────────────────────
 * WiFi Manager API
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Initialize TCP/IP stack and WiFi driver (call once at boot).
 * @return ESP_OK on success.
 */
esp_err_t network_init(void);

/**
 * @brief Connect to the saved WiFi network (STA mode).
 *
 * Blocks for up to NETWORK_CONNECT_TIMEOUT_MS. If connection succeeds,
 * syncs SNTP time (required for MbedTLS certificate validation).
 *
 * @param ssid      SSID string (may be NULL — loads from device config).
 * @param password  Password string (may be NULL — loads from device config).
 * @return ESP_OK if connected and IP obtained.
 */
esp_err_t network_wifi_connect(const char *ssid, const char *password);

/**
 * @brief Run a credential-free station scan through the hosted C6 radio.
 *
 * The station is started for the duration of the scan and stopped before
 * returning. This is intended for diagnostics and does not persist state.
 *
 * @param[out] ap_count Optional number of access points discovered.
 * @return ESP_OK when the scan completed, even if no APs were found.
 */
esp_err_t network_wifi_scan(uint16_t *ap_count);

/**
 * @brief Disconnect from WiFi and disable the STA interface.
 * @return ESP_OK on success.
 */
esp_err_t network_wifi_disconnect(void);

/**
 * @brief Check if STA interface is connected with a valid IP.
 * @return true if connected.
 */
bool network_is_connected(void);

/**
 * @brief Get the current STA IP address string.
 * @param[out] buf     Destination buffer.
 * @param[in]  buf_len Buffer length (16 bytes minimum for dotted-quad).
 */
void network_get_ip(char *buf, int buf_len);

/**
 * @brief Get the AP SSID that would be used for the captive portal.
 *
 * Format: "RS-Core-XXXX" where XXXX is last 4 hex digits of AP MAC.
 *
 * @param[out] buf     Destination buffer (min 24 bytes).
 * @param[in]  buf_len Buffer length.
 */
void network_get_ap_name(char *buf, int buf_len);

/* ──────────────────────────────────────────────────────────────────────────
 * Device Config API
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Load device config from /data/metadata/device.json.
 * @param[out] cfg  Destination struct.
 * @return ESP_OK if file read and parsed. ESP_ERR_NOT_FOUND if not configured.
 */
esp_err_t network_load_device_config(network_device_config_t *cfg);

/**
 * @brief Save device config to /data/metadata/device.json.
 * @param cfg  Config to save.
 * @return ESP_OK on success.
 */
esp_err_t network_save_device_config(const network_device_config_t *cfg);

/* ──────────────────────────────────────────────────────────────────────────
 * Upload API
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Send heartbeat ping to the cloud API.
 *
 * POST /api/device/ping with the locally available device/storage telemetry.
 * Used for the sync heartbeat screen before uploading.
 *
 * @param token    Auth token (if NULL, loads from device config).
 * @param api_url  Base API URL (if NULL, loads from device config).
 * @return ESP_OK if server responded 200.
 */
esp_err_t network_heartbeat(const char *token, const char *api_url);

/** Send a heartbeat with explicitly supplied telemetry values. */
esp_err_t network_heartbeat_with_telemetry(const char *token,
                                            const char *api_url,
                                            const network_heartbeat_telemetry_t *telemetry);

/**
 * @brief Upload a single file to the cloud API with batch streaming.
 *
 * Uses the same 3-phase protocol as S3 uploader.py:
 *   1. GET /api/upload/status?filename=X — resume check
 *   2. POST /api/upload/batch (×N)       — 512KB each
 *   3. POST /api/upload/complete         — finalize
 *
 * @param filepath   Filesystem path to the CSV session file.
 * @param token      Auth token.
 * @param api_url    Base API URL.
 * @param cb         Optional progress callback (may be NULL).
 * @param cb_ctx     Optional user context passed to callback.
 * @param file_index File index for multi-file progress tracking.
 * @param total_files Total files in this sync run.
 * @param global_offset Bytes already uploaded before this file.
 * @param global_total Total bytes across all files in sync run.
 * @return ESP_OK on success.
 */
esp_err_t network_upload_file(const char *filepath,
                               const char *token,
                               const char *api_url,
                               upload_progress_cb_t cb,
                               void *cb_ctx,
                               int file_index,
                               int total_files,
                               size_t global_offset,
                               size_t global_total);

/**
 * @brief Upload all pending session files (sync_all equivalent).
 *
 * Connects to WiFi, loads device config, scans session directory,
 * validates CSV headers, uploads each file with retry, archives on success.
 *
 * @param cb      Optional progress callback.
 * @param cb_ctx  Optional user context.
 * @return true if all files uploaded successfully.
 */
bool network_sync_all(upload_progress_cb_t cb, void *cb_ctx);

/**
 * @brief Probe saved Wi-Fi and server credentials without uploading sessions.
 * @return true if Wi-Fi, heartbeat, and active-track retrieval all succeed.
 */
bool network_sync_probe(void);

/* ──────────────────────────────────────────────────────────────────────────
 * Captive Portal API
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Start SoftAP + captive portal (HTTP server + DNS hijack).
 *
 * Launches two FreeRTOS tasks:
 *  - DNS task: UDP :53 hijack (all queries → 192.168.4.1)
 *  - HTTP task: TCP :80 setup form + provisioning handler
 *
 * Blocks until provisioning completes or timeout (60s of no connection).
 * On successful provisioning, saves device.json and calls esp_restart().
 *
 * @param ap_name  SoftAP SSID (NULL = auto-generated RS-Core-XXXX).
 * @return ESP_OK if portal exited cleanly (no provisioning), ESP_FAIL otherwise.
 *         NOTE: On successful provisioning, this function never returns (reboots).
 */
esp_err_t network_start_captive_portal(const char *ap_name);

/**
 * @brief Stop captive portal server and tear down SoftAP.
 * @return ESP_OK on success.
 */
esp_err_t network_stop_captive_portal(void);

/**
 * @brief Fetch and save the active track database from the cloud.
 * @param token    Auth token.
 * @param api_url  Base API URL.
 * @return ESP_OK on success.
 */
esp_err_t network_fetch_active_track(const char *token, const char *api_url);

#ifdef __cplusplus
}
#endif

#endif /* NETWORK_H */
