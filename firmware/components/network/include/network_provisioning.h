/**
 * @file network_provisioning.h
 * @brief Pure request parsing and validation for the device setup portal.
 *
 * This layer deliberately has no socket, Wi-Fi, or filesystem dependencies.
 * It keeps the captive-portal contract testable on the host while the network
 * backend is brought up on the P4/C6 transport.
 */

#ifndef NETWORK_PROVISIONING_H
#define NETWORK_PROVISIONING_H

#include "network.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    NETWORK_PROVISIONING_NONE = 0,
    NETWORK_PROVISIONING_FORM,
    NETWORK_PROVISIONING_MAGIC_LINK,
} network_provisioning_source_t;

/**
 * Parse a setup request into a candidate device configuration.
 *
 * Supported inputs:
 *   POST /setup with form fields ssid, password, token, api_url
 *   GET  /setup?ssid=...&pass=...&token=...&api_url=...
 *
 * `pass` is retained as an alias for the existing web-app magic link. The
 * output starts with `saved` so omitted API/password values retain their
 * existing values. ESP_ERR_NOT_FOUND means the request is only a page view.
 */
esp_err_t network_provisioning_parse_request(
    const char *method,
    const char *path,
    const char *body,
    const network_device_config_t *saved,
    network_device_config_t *out,
    network_provisioning_source_t *source);

/** Validate the fields that are persisted to device.json. */
esp_err_t network_provisioning_validate_config(const network_device_config_t *cfg);

#ifdef __cplusplus
}
#endif

#endif /* NETWORK_PROVISIONING_H */
