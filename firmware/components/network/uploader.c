/**
 * @file uploader.c
 * @brief CONSOLIDATED: All uploader logic lives in network.c
 *
 * network_heartbeat(), network_upload_file(), network_sync_all(), and
 * network_fetch_active_track() are fully implemented in network.c and
 * share a single esp_http_client handle pool and authentication context.
 *
 * This file is intentionally empty — it exists only as a build-system
 * placeholder so that the idf_component_register SRCS list does not need
 * to be conditionally modified. No symbols are defined here.
 */
