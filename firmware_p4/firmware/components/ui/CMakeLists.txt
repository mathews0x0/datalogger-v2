idf_component_register(
    SRCS "ui.c"
         "ui_events.c"
         "ui_theme.c"
         "ui_home.c"
         "ui_logging.c"
         "ui_settings.c"
         "ui_calibration.c"
         "ui_sync.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_timer driver nvs_flash storage network sensors lvgl esp_lvgl_port
)
