if(CONFIG_IDF_TARGET_ESP32P4)
    # The P4 board's ESP32-C6 Wi-Fi transport is still being brought up.  Keep
    # the UI firmware independent of esp-hosted so a transport failure cannot
    # reboot the display application.
    idf_component_register(
        SRCS "network_stub.c"
        INCLUDE_DIRS "include"
    )
else()
    idf_component_register(
        SRCS "network.c" "uploader.c" "captive_portal.c"
        INCLUDE_DIRS "include"
        PRIV_REQUIRES esp_wifi esp_http_client esp_http_server mbedtls lwip nvs_flash esp_timer esp-tls json storage
    )
endif()
