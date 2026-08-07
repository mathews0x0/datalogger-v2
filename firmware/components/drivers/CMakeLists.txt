idf_component_register(
    SRCS
        "bmi323.c"
        "gps.c"
    INCLUDE_DIRS
        "include"
    PRIV_REQUIRES
        driver          # UART, GPIO
        freertos        # vTaskDelay
        esp_timer       # measured GPS sentence cadence
        bsp             # target GPIO definitions
)

target_link_libraries(${COMPONENT_LIB} PRIVATE idf::esp_driver_i2c)
