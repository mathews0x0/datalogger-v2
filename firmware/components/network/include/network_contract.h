/**
 * @file network_contract.h
 * @brief Pure helpers for the RaceSense device/server HTTP contract.
 *
 * These helpers intentionally have no ESP-IDF networking dependency so URL
 * construction and active-track validation can be exercised on the host.
 */

#ifndef NETWORK_CONTRACT_H
#define NETWORK_CONTRACT_H

#include <stdbool.h>
#include <stddef.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NETWORK_ENDPOINT_DEVICE_PING       "/api/device/ping"
#define NETWORK_ENDPOINT_ACTIVE_TRACK      "/api/device/active_track"
#define NETWORK_ENDPOINT_UPLOAD_BATCH      "/api/upload/batch"
#define NETWORK_ENDPOINT_UPLOAD_STATUS     "/api/upload/status"
#define NETWORK_ENDPOINT_UPLOAD_COMPLETE   "/api/upload/complete"

/**
 * Normalize a provisioned URL to the server root.
 *
 * Older device configurations may contain https://host/api/upload. The
 * current contract stores or accepts either that value or https://host and
 * resolves both to the same server-root URL.
 */
esp_err_t network_contract_normalize_base_url(const char *api_url,
                                               char *out,
                                               size_t out_len);

/** Build an endpoint URL from a server-root URL and an absolute path. */
esp_err_t network_contract_build_url(const char *api_url,
                                     const char *endpoint,
                                     char *out,
                                     size_t out_len);

/** Percent-encode a query-string component using RFC 3986 unreserved bytes. */
esp_err_t network_contract_url_encode(const char *value,
                                      char *out,
                                      size_t out_len);

/**
 * Validate the server response wrapper and extract a device track payload.
 *
 * The output is a compact JSON object containing the active track metadata and
 * the normalized device_layout used by the track viewer. ESP_ERR_NOT_FOUND
 * means the server explicitly returned {"active_track": null}.
 */
esp_err_t network_contract_extract_active_track(const char *json,
                                                size_t json_len,
                                                char *payload,
                                                size_t payload_len);

#ifdef __cplusplus
}
#endif

#endif /* NETWORK_CONTRACT_H */
