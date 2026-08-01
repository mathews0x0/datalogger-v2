idf_component_register(
    SRCS "network.c" "uploader.c" "captive_portal.c"
    INCLUDE_DIRS "include"
    PRIV_REQUIRES esp_wifi esp_http_client esp_http_server mbedtls lwip nvs_flash esp_timer esp-tls json storage
)
