idf_component_register(
    SRCS
        "storage.c"
    INCLUDE_DIRS
        "include"
    REQUIRES
        sensors         # sensor_row_t used in storage.h (public type)
    PRIV_REQUIRES
        bsp             # bsp_sdcard_mounted(), bsp_sdcard_get_usage_percent(), bsp_battery_get_voltage()
        esp_timer       # esp_timer_get_time()
        freertos        # FreeRTOS queue, mutex, task
        fatfs           # dirent.h, DIR
)
