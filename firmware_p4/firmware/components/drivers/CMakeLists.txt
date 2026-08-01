idf_component_register(
    SRCS
        "bmi323.c"
        "gps.c"
    INCLUDE_DIRS
        "include"
    PRIV_REQUIRES
        driver          # UART, GPIO
        esp_driver_i2c  # i2c_master (new unified I2C driver in IDF v5.x)
        freertos        # vTaskDelay
        bsp             # target GPIO definitions
)
