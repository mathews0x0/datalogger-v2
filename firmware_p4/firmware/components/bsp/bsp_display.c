/**
 * @file bsp_display.c
 * @brief Multi-target display & touch driver for RaceSense ESP32-P4
 *
 * Selects the correct LCD + touch driver at compile time via
 * BSP_DISPLAY_TARGET in bsp_display_target.h:
 *
 *   0 → ST7701  MIPI-DSI 2-lane  480×800  GT911 I2C   (Waveshare P4 4.3")
 *   1 → ILI9488 SPI              480×320  FT6336 I2C  (generic 3.5")
 *   2 → ILI9341 SPI              320×240  XPT2046 SPI (generic 2.8")
 *
 * Public API is identical for all targets:
 *   bsp_display_driver_init()  — registers LVGL display driver
 *   bsp_touch_driver_init()    — registers LVGL input driver
 *
 * Both are called from bsp.c:bsp_display_init() / bsp_touch_init().
 */

#include "bsp_display_target.h"
#include "bsp.h"

#include "esp_log.h"
#include "esp_err.h"
#include "esp_check.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/i2c_master.h"

/* LVGL headers — provided by esp_lvgl_port component */
#include "lvgl.h"
#include "esp_lvgl_port.h"

static const char *TAG = "bsp_display";

/* ══════════════════════════════════════════════════════════════════════════
 * TARGET 0 — ST7701 MIPI-DSI + GT911 I2C (Waveshare ESP32-P4-WIFI6-4.3)
 * ══════════════════════════════════════════════════════════════════════════*/
#if BSP_DISPLAY_TARGET == 0

#include "esp_lcd_panel_ops.h"
#include "esp_lcd_mipi_dsi.h"
#include "esp_lcd_st7701.h"         /* Component: espressif/esp_lcd_st7701 */
#include "esp_lcd_touch_gt911.h"    /* Component: espressif/esp_lcd_touch_gt911 */
#include "esp_ldo_regulator.h"
#include "esp_timer.h"
#include "touch_calibration.h"

/* The GT911 is on the board's dedicated I2C0 bus (GPIO7/8). */
static i2c_master_bus_handle_t s_touch_i2c_bus;

/* Temporary bring-up instrumentation: invoked before the orientation flags
 * are applied, so the physical GT911 axes can be mapped exactly. */
static void gt911_log_raw_touch(esp_lcd_touch_handle_t tp, uint16_t *x, uint16_t *y,
                                uint16_t *strength, uint8_t *point_num, uint8_t max_point_num)
{
    (void)tp;
    (void)tp; (void)strength; (void)max_point_num;
    static int64_t last_log_us;
    if (point_num && *point_num && esp_timer_get_time() - last_log_us > 300000) {
        ESP_LOGI(TAG, "GT911 contact: raw=(%u,%u), count=%u",
                 (unsigned)*x, (unsigned)*y, (unsigned)*point_num);
        last_log_us = esp_timer_get_time();
    }
    touch_calibration_process(x, y, point_num ? *point_num : 0);
}

/* Temporary calibration probe.  It observes the controller's status and first
 * contact record directly without acknowledging it; the normal LVGL driver
 * remains responsible for consuming/clearing the event. */

/* Exact ST7701S sequence from Waveshare's 480×800 4.3-inch example. */
static const st7701_lcd_init_cmd_t s_vendor_cmds[] = {
    {0xFF, (uint8_t[]){0x77,0x01,0x00,0x00,0x13}, 5, 0},
    {0xEF, (uint8_t[]){0x08}, 1, 0},
    {0xFF, (uint8_t[]){0x77, 0x01, 0x00, 0x00, 0x10}, 5, 0},
    {0xC0, (uint8_t[]){0x63, 0x00}, 2, 0},
    {0xC1, (uint8_t[]){0x0D, 0x02}, 2, 0},
    {0xC2, (uint8_t[]){0x17, 0x08}, 2, 0},
    {0xCC, (uint8_t[]){0x10}, 1, 0},
    {0xB0, (uint8_t[]){0x40,0xC9,0x94,0x0E,0x10,0x05,0x0B,0x09,0x08,0x26,0x04,0x52,0x10,0x69,0x6B,0x69}, 16, 0},
    {0xB1, (uint8_t[]){0x40,0xD2,0x98,0x0C,0x92,0x07,0x09,0x08,0x07,0x25,0x02,0x0E,0x0C,0x6E,0x78,0x55}, 16, 0},
    {0xFF, (uint8_t[]){0x77, 0x01, 0x00, 0x00, 0x11}, 5, 0},
    {0xB0, (uint8_t[]){0x5D}, 1, 0},
    {0xB1, (uint8_t[]){0x4E}, 1, 0},
    {0xB2, (uint8_t[]){0x87}, 1, 0},
    {0xB3, (uint8_t[]){0x80}, 1, 0},
    {0xB5, (uint8_t[]){0x4E}, 1, 0},
    {0xB7, (uint8_t[]){0x85}, 1, 0},
    {0xB8, (uint8_t[]){0x21}, 1, 0},
    {0xB9, (uint8_t[]){0x10,0x1F}, 2, 0},
    {0xBB, (uint8_t[]){0x03}, 1, 0},
    {0xBC, (uint8_t[]){0x00}, 1, 0},
    {0xC1, (uint8_t[]){0x78}, 1, 0},
    {0xC2, (uint8_t[]){0x78}, 1, 0},
    {0xD0, (uint8_t[]){0x88}, 1, 0},
    {0xE0, (uint8_t[]){0x00,0x3A,0x02}, 3, 0},
    {0xE1, (uint8_t[]){0x04,0xA0,0x00,0xA0,0x05,0xA0,0x00,0xA0,0x00,0x40,0x40}, 11, 0},
    {0xE2, (uint8_t[]){0x30,0x00,0x40,0x40,0x32,0xA0,0x00,0xA0,0x00,0xA0,0x00,0xA0,0x00}, 13, 0},
    {0xE3, (uint8_t[]){0x00,0x00,0x33,0x33}, 4, 0},
    {0xE4, (uint8_t[]){0x44,0x44}, 2, 0},
    {0xE5, (uint8_t[]){0x09,0x2E,0xA0,0xA0,0x0B,0x30,0xA0,0xA0,0x05,0x2A,0xA0,0xA0,0x07,0x2C,0xA0,0xA0}, 16, 0},
    {0xE6, (uint8_t[]){0x00,0x00,0x33,0x33}, 4, 0},
    {0xE7, (uint8_t[]){0x44,0x44}, 2, 0},
    {0xE8, (uint8_t[]){0x08,0x2D,0xA0,0xA0,0x0A,0x2F,0xA0,0xA0,0x04,0x29,0xA0,0xA0,0x06,0x2B,0xA0,0xA0}, 16, 0},
    {0xEB, (uint8_t[]){0x00,0x00,0x4E,0x4E,0x00,0x00,0x00}, 7, 0},
    {0xEC, (uint8_t[]){0x08,0x01}, 2, 0},
    {0xED, (uint8_t[]){0xB0,0x2B,0x98,0xA4,0x56,0x7F,0xFF,0xFF,0xFF,0xFF,0xF7,0x65,0x4A,0x89,0xB2,0x0B}, 16, 0},
    {0xEF, (uint8_t[]){0x08,0x08,0x08,0x45,0x3F,0x54}, 6, 0},
    {0xFF, (uint8_t[]){0x77, 0x01, 0x00, 0x00, 0x00}, 5, 0},
    {0x11, (uint8_t[]){0x00}, 0, 120},
    {0x29, (uint8_t[]){0x00}, 0, 0},
};

esp_err_t bsp_display_driver_init(void)
{
    ESP_LOGI(TAG, "Display init: ST7701 MIPI-DSI 2-lane %dx%d (Target 0)",
             BSP_LCD_H_RES, BSP_LCD_V_RES);

    /* The board powers the MIPI PHY from LDO_VO3 at 2.5 V. */
    static esp_ldo_channel_handle_t dsi_phy_ldo;
    const esp_ldo_channel_config_t ldo_cfg = {
        .chan_id = 3,
        .voltage_mv = 2500,
    };
    ESP_ERROR_CHECK(esp_ldo_acquire_channel(&ldo_cfg, &dsi_phy_ldo));

    /* Backlight is active-low PWM on GPIO26. */
    const ledc_timer_config_t bl_timer = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = LEDC_TIMER_1,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    const ledc_channel_config_t bl_channel = {
        .gpio_num = BSP_LCD_BL_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_1,
        .duty = 1023,
        .flags.output_invert = 1,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&bl_timer));
    ESP_ERROR_CHECK(ledc_channel_config(&bl_channel));

    /* ── 1. LVGL port init ──────────────────────────────────────────────*/
    const lvgl_port_cfg_t lv_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&lv_cfg));

    /* ── 2. MIPI-DSI bus ────────────────────────────────────────────────*/
    esp_lcd_dsi_bus_handle_t dsi_bus = NULL;
    esp_lcd_dsi_bus_config_t dsi_bus_cfg = {
        .bus_id           = 0,
        .num_data_lanes   = BSP_MIPI_DSI_LANE_NUM,
        .phy_clk_src      = MIPI_DSI_PHY_CLK_SRC_DEFAULT,
        .lane_bit_rate_mbps = BSP_MIPI_DSI_LANE_MBR,
    };
    ESP_ERROR_CHECK(esp_lcd_new_dsi_bus(&dsi_bus_cfg, &dsi_bus));

    /* ── 3. DBI interface (command mode) ────────────────────────────────*/
    esp_lcd_panel_io_handle_t io_handle = NULL;
    esp_lcd_dbi_io_config_t dbi_cfg = {
        .virtual_channel = 0,
        .lcd_cmd_bits    = 8,
        .lcd_param_bits  = 8,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_dbi(dsi_bus, &dbi_cfg, &io_handle));

    /* ── 4. ST7701 panel ────────────────────────────────────────────────*/
    esp_lcd_panel_handle_t panel_handle = NULL;
    esp_lcd_dpi_panel_config_t dpi_cfg = {
        .dpi_clk_src = MIPI_DSI_DPI_CLK_SRC_DEFAULT,
        .dpi_clock_freq_mhz = 30,
        .virtual_channel = 0,
        .pixel_format = LCD_COLOR_PIXEL_FORMAT_RGB565,
        .num_fbs = 1,
        .video_timing = {
            .h_size = BSP_LCD_H_RES,
            .v_size = BSP_LCD_V_RES,
            .hsync_back_porch = 42,
            .hsync_pulse_width = 12,
            .hsync_front_porch = 42,
            .vsync_back_porch = 2,
            .vsync_pulse_width = 8,
            .vsync_front_porch = 60,
        },
        .flags.use_dma2d = true,
    };
    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = BSP_LCD_RST_GPIO,
        .rgb_ele_order  = LCD_RGB_ELEMENT_ORDER_RGB,
        .bits_per_pixel = 16,
    };
    st7701_vendor_config_t vendor_cfg = {
        .init_cmds      = s_vendor_cmds,
        .init_cmds_size = sizeof(s_vendor_cmds) / sizeof(s_vendor_cmds[0]),
        .mipi_config = {
            .dsi_bus    = dsi_bus,
            .dpi_config = &dpi_cfg,
        },
        .flags = {
            .use_mipi_interface = 1,
        },
    };
    panel_cfg.vendor_config = &vendor_cfg;
    ESP_ERROR_CHECK(esp_lcd_new_panel_st7701(io_handle, &panel_cfg, &panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));

    /* ── 5. Register the MIPI-DSI display with LVGL ─────────────────────*/
    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle    = io_handle,
        .panel_handle = panel_handle,
        .buffer_size  = BSP_LCD_DRAW_BUF_SIZE,
        .double_buffer = BSP_LCD_DRAW_BUF_DOUBLE,
        .hres         = BSP_LCD_H_RES,
        .vres         = BSP_LCD_V_RES,
        .monochrome   = false,
        .rotation = {
            .swap_xy  = false,
            .mirror_x = false,
            .mirror_y = false,
        },
        .flags = {
            .buff_dma    = false,
            .buff_spiram = true,
            /* ST7701 MIPI has no hardware axis-swap operation.  Rotate the
             * 480x800 native panel in LVGL to present the 800x480 dashboard. */
            .sw_rotate   = true,
        },
    };
    const lvgl_port_display_dsi_cfg_t dsi_lvgl_cfg = { .flags.avoid_tearing = false };
    lv_disp_t *disp = lvgl_port_add_disp_dsi(&disp_cfg, &dsi_lvgl_cfg);
    if (!disp) {
        ESP_LOGE(TAG, "lvgl_port_add_disp failed");
        return ESP_FAIL;
    }

    /* Landscape, with the board's USB/header edge at the left. */
    lv_disp_set_rotation(disp, LV_DISP_ROT_90);

    ESP_LOGI(TAG, "Display registered: %dx%d panel, 800x480 landscape UI",
             BSP_LCD_H_RES, BSP_LCD_V_RES);
    return ESP_OK;
}

esp_err_t bsp_touch_driver_init(void)
{
    ESP_LOGI(TAG, "Touch init: GT911 on I2C%d (SDA=%d SCL=%d)",
             BSP_TOUCH_I2C_NUM, BSP_PIN_I2C0_SDA, BSP_PIN_I2C0_SCL);

    if (!s_touch_i2c_bus) {
        const i2c_master_bus_config_t bus_cfg = {
            .i2c_port = BSP_TOUCH_I2C_NUM,
            .sda_io_num = BSP_PIN_I2C0_SDA,
            .scl_io_num = BSP_PIN_I2C0_SCL,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .flags.enable_internal_pullup = true,
        };
        ESP_RETURN_ON_ERROR(i2c_new_master_bus(&bus_cfg, &s_touch_i2c_bus), TAG,
                            "create GT911 I2C bus failed");
    }

    /* The GT911 straps either 0x5D or 0x14 at reset; Waveshare normally uses
     * 0x5D, but probing both makes the board bring-up tolerant of either state. */
    esp_lcd_panel_io_i2c_config_t tp_io_cfg = ESP_LCD_TOUCH_IO_I2C_GT911_CONFIG();
    if (i2c_master_probe(s_touch_i2c_bus, BSP_TOUCH_I2C_ADDR, 100) != ESP_OK) {
        if (i2c_master_probe(s_touch_i2c_bus,
                             ESP_LCD_TOUCH_IO_I2C_GT911_ADDRESS_BACKUP, 100) != ESP_OK) {
            ESP_LOGE(TAG, "GT911 not found on I2C0 (tried 0x5D and 0x14)");
            return ESP_ERR_NOT_FOUND;
        }
        tp_io_cfg.dev_addr = ESP_LCD_TOUCH_IO_I2C_GT911_ADDRESS_BACKUP;
    }
    /* The Waveshare GT911 reference uses standard-mode I2C; 400 kHz probes
     * but fails during the controller's configuration-register read. */
    tp_io_cfg.scl_speed_hz = 100000;

    /* Dashboard is LVGL-rotated 90 degrees: physical (x,y) maps to logical
     * (y, 479-x), hence the X mirror followed by axis swap. */
    esp_lcd_touch_config_t tp_cfg = {
        .x_max        = BSP_LCD_H_RES,
        .y_max        = BSP_LCD_V_RES,
        .rst_gpio_num = (BSP_TOUCH_RST_GPIO >= 0) ? BSP_TOUCH_RST_GPIO : GPIO_NUM_NC,
        .int_gpio_num = (BSP_TOUCH_INT_GPIO >= 0) ? BSP_TOUCH_INT_GPIO : GPIO_NUM_NC,
        .levels = { .reset = 0, .interrupt = 0 },
        .flags  = { .swap_xy = 0, .mirror_x = 0, .mirror_y = 0 },
        .process_coordinates = gt911_log_raw_touch,
    };

    esp_lcd_panel_io_handle_t tp_io = NULL;
    ESP_RETURN_ON_ERROR(esp_lcd_new_panel_io_i2c(s_touch_i2c_bus, &tp_io_cfg, &tp_io), TAG,
                        "create GT911 IO failed");

    esp_lcd_touch_handle_t tp = NULL;
    ESP_RETURN_ON_ERROR(esp_lcd_touch_new_i2c_gt911(tp_io, &tp_cfg, &tp), TAG,
                        "create GT911 driver failed");

    uint8_t gt_cfg[5] = {0};
    if (esp_lcd_panel_io_rx_param(tp_io, 0x8047, gt_cfg, sizeof(gt_cfg)) == ESP_OK) {
        ESP_LOGI(TAG, "GT911 native range: %ux%u (config v%u)",
                 (unsigned)(gt_cfg[1] | (gt_cfg[2] << 8)),
                 (unsigned)(gt_cfg[3] | (gt_cfg[4] << 8)), gt_cfg[0]);
    }

    /* Register as LVGL input device */
    const lvgl_port_touch_cfg_t touch_cfg = { .disp = lv_disp_get_default(), .handle = tp };
    lv_indev_t *indev = lvgl_port_add_touch(&touch_cfg);
    if (!indev) {
        ESP_LOGE(TAG, "lvgl_port_add_touch failed");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Touch registered: GT911 landscape input device");
    return ESP_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * TARGET 1 — ILI9488 SPI 480×320 + FT6336 I2C
 * ══════════════════════════════════════════════════════════════════════════*/
#elif BSP_DISPLAY_TARGET == 1

#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_ili9488.h"        /* Component: espressif/esp_lcd_ili9488 */
#include "esp_lcd_touch_ft5x06.h"   /* Component: espressif/esp_lcd_touch_ft5x06 (covers FT6336) */
#include "driver/spi_master.h"

esp_err_t bsp_display_driver_init(void)
{
    ESP_LOGI(TAG, "Display init: ILI9488 SPI %dx%d (Target 1)", BSP_LCD_H_RES, BSP_LCD_V_RES);

    const lvgl_port_cfg_t lv_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&lv_cfg));

    /* SPI bus */
    spi_bus_config_t buscfg = {
        .mosi_io_num   = BSP_LCD_SPI_MOSI,
        .miso_io_num   = -1,
        .sclk_io_num   = BSP_LCD_SPI_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = BSP_LCD_H_RES * 80 * sizeof(uint16_t),
    };
    ESP_ERROR_CHECK(spi_bus_initialize(BSP_SPI_HOST, &buscfg, SPI_DMA_CH_AUTO));

    /* Panel IO */
    esp_lcd_panel_io_handle_t io_handle = NULL;
    esp_lcd_panel_io_spi_config_t io_cfg = {
        .dc_gpio_num       = BSP_LCD_DC_GPIO,
        .cs_gpio_num       = BSP_LCD_SPI_CS,
        .pclk_hz           = BSP_LCD_SPI_MHZ * 1000000,
        .lcd_cmd_bits      = 8,
        .lcd_param_bits    = 8,
        .spi_mode          = 0,
        .trans_queue_depth = 10,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(BSP_SPI_HOST, &io_cfg, &io_handle));

    /* ILI9488 panel */
    esp_lcd_panel_handle_t panel_handle = NULL;
    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = BSP_LCD_RST_GPIO,
        .rgb_ele_order  = LCD_RGB_ELEMENT_ORDER_BGR,
        .bits_per_pixel = 16,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_ili9488(io_handle, &panel_cfg, 0, &panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));

    if (BSP_LCD_BL_GPIO >= 0) {
        gpio_set_direction(BSP_LCD_BL_GPIO, GPIO_MODE_OUTPUT);
        gpio_set_level(BSP_LCD_BL_GPIO, 1);
    }

    /* Draw buffer in internal SRAM */
    lv_color_t *buf1 = heap_caps_malloc(BSP_LCD_DRAW_BUF_SIZE * sizeof(lv_color_t), MALLOC_CAP_DMA);
    if (!buf1) return ESP_ERR_NO_MEM;

    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = io_handle, .panel_handle = panel_handle,
        .buffer_size = BSP_LCD_DRAW_BUF_SIZE, .double_buffer = false,
        .hres = BSP_LCD_H_RES, .vres = BSP_LCD_V_RES,
        .flags = { .buff_dma = true },
    };
    lvgl_port_add_disp(&disp_cfg);
    (void)buf1;
    ESP_LOGI(TAG, "ILI9488 display registered %dx%d", BSP_LCD_H_RES, BSP_LCD_V_RES);
    return ESP_OK;
}

esp_err_t bsp_touch_driver_init(void)
{
    ESP_LOGI(TAG, "Touch init: FT6336 I2C (Target 1)");
    esp_lcd_touch_config_t tp_cfg = {
        .x_max = BSP_LCD_H_RES, .y_max = BSP_LCD_V_RES,
        .rst_gpio_num = GPIO_NUM_NC, .int_gpio_num = GPIO_NUM_NC,
    };
    esp_lcd_panel_io_handle_t tp_io = NULL;
    esp_lcd_panel_io_i2c_config_t tp_io_cfg = {
        .dev_addr = BSP_TOUCH_I2C_ADDR, .control_phase_bytes = 1,
        .lcd_cmd_bits = 8, .lcd_param_bits = 8,
        .flags = { .disable_control_phase = 1 },
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(
        (esp_lcd_i2c_bus_handle_t)(uintptr_t)BSP_TOUCH_I2C_NUM, &tp_io_cfg, &tp_io));
    esp_lcd_touch_handle_t tp = NULL;
    ESP_ERROR_CHECK(esp_lcd_touch_new_i2c_ft5x06(tp_io, &tp_cfg, &tp));
    const lvgl_port_touch_cfg_t touch_cfg = { .disp = lv_disp_get_default(), .handle = tp };
    lvgl_port_add_touch(&touch_cfg);
    return ESP_OK;
}

/* ══════════════════════════════════════════════════════════════════════════
 * TARGET 2 — ILI9341 SPI 320×240 + XPT2046 SPI resistive (RS-Core V4.2)
 * ══════════════════════════════════════════════════════════════════════════*/
#elif BSP_DISPLAY_TARGET == 2

#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_ili9341.h"        /* Component: espressif/esp_lcd_ili9341 */
#include "esp_lcd_touch.h"
#include "esp_lcd_touch_xpt2046.h"  /* Component: atanisoft/esp_lcd_touch_xpt2046 */
#include "driver/spi_master.h"

/* Proven MicroPython Vendor Init Sequence for generic ILI9341 modules */
static const ili9341_lcd_init_cmd_t s_mpy_init_cmds[] = {
    {0xCF, (uint8_t []){0x00, 0xC1, 0x30}, 3, 0},
    {0xED, (uint8_t []){0x64, 0x03, 0x12, 0x81}, 4, 0},
    {0xE8, (uint8_t []){0x85, 0x00, 0x78}, 3, 0},
    {0xCB, (uint8_t []){0x39, 0x2C, 0x00, 0x34, 0x02}, 5, 0},
    {0xF7, (uint8_t []){0x20}, 1, 0},
    {0xEA, (uint8_t []){0x00, 0x00}, 2, 0},
    {0xC0, (uint8_t []){0x23}, 1, 0},
    {0xC1, (uint8_t []){0x10}, 1, 0},
    {0xC5, (uint8_t []){0x3E, 0x28}, 2, 0},
    {0xC7, (uint8_t []){0x86}, 1, 0},
    {0x3A, (uint8_t []){0x55}, 1, 0},
    {0xB1, (uint8_t []){0x00, 0x18}, 2, 0},
    {0xB6, (uint8_t []){0x08, 0x82, 0x27}, 3, 0},
    {0xF2, (uint8_t []){0x00}, 1, 0},
    {0x26, (uint8_t []){0x01}, 1, 0},
    {0xE0, (uint8_t []){0x0F, 0x31, 0x2B, 0x0C, 0x0E, 0x08, 0x4E, 0xF1, 0x37, 0x07, 0x10, 0x03, 0x0E, 0x09, 0x00}, 15, 0},
    {0xE1, (uint8_t []){0x00, 0x0E, 0x14, 0x03, 0x11, 0x07, 0x31, 0xC1, 0x48, 0x08, 0x0F, 0x0C, 0x31, 0x36, 0x0F}, 15, 0},
    {0x11, (uint8_t []){0}, 0, 120},
};

/**
 * @brief Empirical Affine Coordinate Calibration Matrix
 * Derived from user-verified 4-point glass calibration protocol:
 * - Horizontal (Screen X 15..305): Mapped from raw Y (28..210)
 * - Vertical   (Screen Y 15..225): Mapped from raw X (61..269)
 */
static void oem_process_coordinates(esp_lcd_touch_handle_t tp, uint16_t *x, uint16_t *y,
                                    uint16_t *strength, uint8_t *point_num, uint8_t max_point_num)
{
    for (int i = 0; i < *point_num; i++) {
        uint16_t raw_x = x[i];
        uint16_t raw_y = y[i];

        /* Perform axis transposition and precise scale-offset transformation */
        int32_t cal_x = 15 + ((int32_t)(raw_y - 28) * 290) / 182;
        int32_t cal_y = 15 + ((int32_t)(raw_x - 61) * 210) / 208;

        /* Enforce absolute bounds against 320x240 display geometry */
        if (cal_x < 0) cal_x = 0;
        if (cal_x >= BSP_LCD_H_RES) cal_x = BSP_LCD_H_RES - 1;
        if (cal_y < 0) cal_y = 0;
        if (cal_y >= BSP_LCD_V_RES) cal_y = BSP_LCD_V_RES - 1;

        x[i] = (uint16_t)cal_x;
        y[i] = (uint16_t)cal_y;
    }
}

esp_err_t bsp_display_driver_init(void)
{
    ESP_LOGI(TAG, "Display init: ILI9341 SPI %dx%d @ %dMHz (Target 2)", BSP_LCD_H_RES, BSP_LCD_V_RES, BSP_LCD_SPI_MHZ);

    /* CRITICAL SPI BUS ISOLATION: Assert TOUCH_CS HIGH immediately to prevent 
       XPT2046 touchscreen bus contention during ILI9341 transactions! */
    if (BSP_TOUCH_SPI_CS >= 0) {
        gpio_config_t touch_cs_cfg = {
            .pin_bit_mask = (1ULL << BSP_TOUCH_SPI_CS),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE
        };
        gpio_config(&touch_cs_cfg);
        gpio_set_level(BSP_TOUCH_SPI_CS, 1);
        ESP_LOGI(TAG, "Touch CS isolated on GPIO %d to prevent SPI bus contention", BSP_TOUCH_SPI_CS);
    }

    const lvgl_port_cfg_t lv_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&lv_cfg));

    spi_bus_config_t buscfg = {
        .mosi_io_num   = BSP_LCD_SPI_MOSI, .miso_io_num = BSP_LCD_SPI_MISO,
        .sclk_io_num   = BSP_LCD_SPI_CLK,
        .quadwp_io_num = -1, .quadhd_io_num = -1,
        .max_transfer_sz = BSP_LCD_H_RES * 80 * sizeof(uint16_t),
    };
    ESP_ERROR_CHECK(spi_bus_initialize(BSP_SPI_HOST, &buscfg, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_handle_t io_handle = NULL;
    esp_lcd_panel_io_spi_config_t io_cfg = {
        .dc_gpio_num = BSP_LCD_DC_GPIO, .cs_gpio_num = BSP_LCD_SPI_CS,
        .pclk_hz = BSP_LCD_SPI_MHZ * 1000000,
        .lcd_cmd_bits = 8, .lcd_param_bits = 8,
        .spi_mode = 0, .trans_queue_depth = 10,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(BSP_SPI_HOST, &io_cfg, &io_handle));

    ili9341_vendor_config_t vendor_config = {
        .init_cmds = s_mpy_init_cmds,
        .init_cmds_size = sizeof(s_mpy_init_cmds) / sizeof(ili9341_lcd_init_cmd_t),
    };

    esp_lcd_panel_handle_t panel_handle = NULL;
    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = BSP_LCD_RST_GPIO,
        .rgb_endian     = LCD_RGB_ENDIAN_BGR,
        .bits_per_pixel = 16,
        .vendor_config  = &vendor_config,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(io_handle, &panel_cfg, &panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
    
    /* Apply verified color and gamma profiles */
    ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_handle, false));
    esp_lcd_panel_io_tx_param(io_handle, 0x20, NULL, 0);
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));

    if (BSP_LCD_BL_GPIO >= 0) {
        gpio_set_direction(BSP_LCD_BL_GPIO, GPIO_MODE_OUTPUT);
        gpio_set_level(BSP_LCD_BL_GPIO, 1);
    }

    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = io_handle, .panel_handle = panel_handle,
        .buffer_size = BSP_LCD_DRAW_BUF_SIZE, .double_buffer = false,
        .hres = BSP_LCD_H_RES, .vres = BSP_LCD_V_RES,
        .rotation = {0},
        .flags = { .buff_dma = true },
    };
    lv_disp_t *lv_disp = lvgl_port_add_disp(&disp_cfg);
    if (!lv_disp) {
        ESP_LOGE(TAG, "lvgl_port_add_disp failed");
        return ESP_FAIL;
    }

    /* Override orientation via explicit MADCTL register configuration after LVGL registration */
    uint8_t verified_madctl = 0x80;
    esp_lcd_panel_io_tx_param(io_handle, 0x36, &verified_madctl, 1);

    ESP_LOGI(TAG, "ILI9341 display registered %dx%d with verified MADCTL 0x80", BSP_LCD_H_RES, BSP_LCD_V_RES);
    return ESP_OK;
}

esp_err_t bsp_touch_driver_init(void)
{
    ESP_LOGI(TAG, "Touch init: XPT2046 SPI resistive (Target 2) with OEM Affine Calibration");

    esp_lcd_touch_handle_t tp_handle = NULL;
    esp_lcd_panel_io_handle_t tp_io_handle = NULL;
    esp_lcd_panel_io_spi_config_t tp_io_config = ESP_LCD_TOUCH_IO_SPI_XPT2046_CONFIG(BSP_TOUCH_SPI_CS);
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)BSP_SPI_HOST, &tp_io_config, &tp_io_handle));

    esp_lcd_touch_config_t tp_cfg = {
        .x_max = BSP_LCD_H_RES,
        .y_max = BSP_LCD_V_RES,
        .rst_gpio_num = -1,
        .int_gpio_num = BSP_TOUCH_IRQ_GPIO,
        .levels = {
            .reset = 0,
            .interrupt = 0,
        },
        .flags = {
            .swap_xy = 0,
            .mirror_x = 0,
            .mirror_y = 0,
        },
        .process_coordinates = oem_process_coordinates,
    };
    ESP_ERROR_CHECK(esp_lcd_touch_new_spi_xpt2046(tp_io_handle, &tp_cfg, &tp_handle));

    const lvgl_port_touch_cfg_t touch_port_cfg = {
        .disp = lv_disp_get_default(),
        .handle = tp_handle,
    };
    lv_indev_t *lv_touch = lvgl_port_add_touch(&touch_port_cfg);
    if (!lv_touch) {
        ESP_LOGE(TAG, "lvgl_port_add_touch failed for XPT2046");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Touch registered: XPT2046 calibrated input device");
    return ESP_OK;
}

#endif /* BSP_DISPLAY_TARGET */
