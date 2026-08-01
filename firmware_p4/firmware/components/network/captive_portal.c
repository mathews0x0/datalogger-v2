/**
 * @file captive_portal.c
 * @brief CONSOLIDATED: All captive portal logic lives in network.c
 *
 * network_start_captive_portal() and network_stop_captive_portal() are
 * fully implemented in network.c:
 *
 *   - SoftAP bringup (RS-Core-XXXX SSID, derived from AP MAC)
 *   - DNS hijack FreeRTOS task (_dns_task) — UDP :53 → 192.168.4.1
 *   - HTTP provisioning server (esp_http_server) — TCP :80
 *     • GET  /        → Setup form (pre-filled from device.json)
 *     • POST /setup   → Saves credentials to device.json → esp_restart()
 *     • OS probe suppression: Apple /hotspot-detect.html → 200 OK
 *                             Android /generate_204 → 204
 *                             Windows /connecttest.txt → 200 text
 *
 * This file is intentionally empty — it exists only as a build-system
 * placeholder so that the idf_component_register SRCS list does not need
 * to be conditionally modified. No symbols are defined here.
 */
