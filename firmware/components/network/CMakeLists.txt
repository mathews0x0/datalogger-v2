# Keep dependency discovery independent from the selected source branch.  The
# ESP-IDF requirements pass does not have the final sdkconfig values available,
# so putting PRIV_REQUIRES only in the hosted branch makes the real sources
# compile without their public headers on a subsequent build.
if(CONFIG_ESP_WIFI_REMOTE_ENABLED)
    # The complete implementation owns STA connection, SoftAP/captive portal,
    # HTTPS sync, and active-track fetch over ESP-Hosted/remote Wi-Fi.
    set(NETWORK_SOURCES
        "network.c"
        "network_contract.c"
        "network_provisioning.c"
        "uploader.c"
        "captive_portal.c"
    )
else()
    # Keep the display image independent from esp-hosted while the P4/C6
    # transport is disabled. The application-side provisioning flow is still
    # compiled and ready to use when CONFIG_ESP_WIFI_REMOTE_ENABLED is set.
    set(NETWORK_SOURCES "network_stub.c")
endif()

idf_component_register(
    SRCS ${NETWORK_SOURCES}
    INCLUDE_DIRS "include"
    PRIV_REQUIRES esp_wifi esp_http_client esp_http_server mbedtls lwip
                  nvs_flash esp_timer esp-tls json storage
)
