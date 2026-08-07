idf_component_register(
    SRCS "ui.c"
         "ui_events.c"
         "ui_theme.c"
         "ui_home.c"
         "ui_logging.c"
         "ui_settings.c"
         "ui_debug.c"
         "ui_data.c"
         "ui_calibration.c"
         "ui_sync.c"
         "ui_track.c"
         "ui_storage_fault.c"
    INCLUDE_DIRS "include"
    EMBED_FILES "assets/racesense_splash_rgb565.bin"
    REQUIRES esp_timer driver nvs_flash esp_app_format storage network sensors track_engine lvgl esp_lvgl_port
)
