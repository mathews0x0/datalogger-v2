idf_component_register(
    SRCS
        "sensors.c"
    INCLUDE_DIRS
        "include"
    REQUIRES
        drivers         # bmi323.h and gps.h (public API used in sensors.h)
    PRIV_REQUIRES
        bsp             # bsp_battery_get_voltage()
        driver          # gptimer
        esp_timer       # esp_timer_get_time()
        freertos        # FreeRTOS primitives
        track_engine    # GPS updates feed the lap/sector timing engine
)
