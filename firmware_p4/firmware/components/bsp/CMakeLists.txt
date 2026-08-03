idf_component_register(
    SRCS
        "bsp.c"
        "bsp_display.c"
        "touch_calibration.c"
    INCLUDE_DIRS
        "include"
    PRIV_REQUIRES
        driver          # GPIO, ADC oneshot, SPI master, I2C
        esp_adc         # adc_oneshot, adc_cali
        sdmmc           # sdmmc_host, sdmmc_cmd
        fatfs           # FATFS & esp_vfs_fat.h (esp_vfs_fat_sdmmc_mount, f_getfree)
        nvs_flash       # persistent touch calibration fallback
        esp_timer       # timing utilities
        freertos        # FreeRTOS task delay
        esp_lcd         # esp_lcd_panel_ops, panel_io_spi/i2c/dbi
        esp_lvgl_port   # lvgl_port_init, lvgl_port_add_disp, lvgl_port_add_touch
        lvgl            # lv_init, lv_color_t, etc.
        esp_lcd_st7701  # ST7701 MIPI-DSI LCD driver (P4 4.3")
        esp_lcd_touch_gt911 # GT911 touch driver
        esp_lcd_touch   # Touch base component
        esp_lcd_ili9341 # ILI9341 SPI LCD driver (S3 2.8")
        esp_lcd_touch_xpt2046 # XPT2046 SPI touch driver
)
