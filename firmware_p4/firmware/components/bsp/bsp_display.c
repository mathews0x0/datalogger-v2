/**
 * @file bsp_display.c
 * @brief Multi-target display & touch driver for RaceSense ESP32-P4
 *
 * Selects the correct LCD + touch driver at compile time via
 * BSP_DISPLAY_TARGET in bsp_display_target.h:
 *
 *   0 → ST7701  MIPI-DSI 2-lane  800×480  GT911 I2C   (Waveshare P4 4.3")
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
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/i2c.h"

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

/* ST7701S init commands for Waveshare 4.3" 800×480 panel.
 * Source: Waveshare ESP32-P4 example (IDF v5.3+). */
static const st7701_lcd_init_cmd_t s_vendor_cmds[] = {
    /* PAGE1 */
    {0xFF, (uint8_t[]){0x77, 0x01, 0x00, 0x00, 0x10}, 5, 0},
    {0xC0, (uint8_t[]){0x3B, 0x00}, 2, 0},
    {0xC1, (uint8_t[]){0x0D, 0x02}, 2, 0},
    {0xC2, (uint8_t[]){0x31, 0x05}, 2, 0},
    {0xCD, (uint8_t[]){0x00}, 1, 0},
    /* Gamma positive */
    {0xB0, (uint8_t[]){0x00,0x11,0x18,0x0E,0x11,0x06,0x07,0x08,0x07,0x22,0x04,0x12,0x0F,0xAA,0x31,0x18}, 16, 0},
    /* Gamma negative */
    {0xB1, (uint8_t[]){0x00,0x11,0x19,0x0E,0x12,0x07,0x08,0x08,0x08,0x22,0x04,0x11,0x11,0xA9,0x32,0x18}, 16, 0},
    /* PAGE2 */
    {0xFF, (uint8_t[]){0x77, 0x01, 0x00, 0x00, 0x11}, 5, 0},
    {0xB0, (uint8_t[]){0x60}, 1, 0},
    {0xB1, (uint8_t[]){0x32}, 1, 0},
    {0xB2, (uint8_t[]){0x07}, 1, 0},
    {0xB3, (uint8_t[]){0x80}, 1, 0},
    {0xB5, (uint8_t[]){0x49}, 1, 0},
    {0xB7, (uint8_t[]){0x85}, 1, 0},
    {0xB8, (uint8_t[]){0x21}, 1, 0},
    {0xC1, (uint8_t[]){0x78}, 1, 0},
    {0xC2, (uint8_t[]){0x78}, 1, 0},
    {0xE0, (uint8_t[]){0x00, 0x1B, 0x02}, 3, 200},
    {0xE1, (uint8_t[]){0x08,0x00,0x0A,0x00,0x07,0x00,0x09,0x00,0x00,0x33,0x33}, 11, 0},
    {0xE2, (uint8_t[]){0x11,0x11,0x33,0x33,0xF4,0x00,0x00,0x00,0xF4,0x00,0x00,0x00}, 12, 0},
    {0xE3, (uint8_t[]){0x00,0x00,0x11,0x11}, 4, 0},
    {0xE4, (uint8_t[]){0x44,0x44}, 2, 0},
    {0xE5, (uint8_t[]){0x0A,0xE9,0xD8,0xA0,0x0C,0xEB,0xD8,0xA0,0x0E,0xED,0xD8,0xA0,0x10,0xEF,0xD8,0xA0}, 16, 0},
    {0xE6, (uint8_t[]){0x00,0x00,0x11,0x11}, 4, 0},
    {0xE7, (uint8_t[]){0x44,0x44}, 2, 0},
    {0xE8, (uint8_t[]){0x09,0xE8,0xD8,0xA0,0x0B,0xEA,0xD8,0xA0,0x0D,0xEC,0xD8,0xA0,0x0F,0xEE,0xD8,0xA0}, 16, 0},
    {0xEB, (uint8_t[]){0x02,0x00,0xE4,0xE4,0x88,0x00,0x40}, 7, 0},
    {0xEC, (uint8_t[]){0x3C,0x00}, 2, 0},
    {0xED, (uint8_t[]){0xAB,0x89,0x76,0x54,0x02,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0x20,0x45,0x67,0x98,0xBA}, 16, 0},
    /* Exit page */
    {0xFF, (uint8_t[]){0x77, 0x01, 0x00, 0x00, 0x00}, 5, 0},
    {0x3A, (uint8_t[]){0x60}, 1, 0},   /* COLMOD: 18-bit RGB */
    {0x11, (uint8_t[]){0x00}, 0, 120}, /* SLPOUT */
    {0x29, (uint8_t[]){0x00}, 0, 20},  /* DISPON */
};

esp_err_t bsp_display_driver_init(void)
{
    ESP_LOGI(TAG, "Display init: ST7701 MIPI-DSI 2-lane %dx%d (Target 0)",
             BSP_LCD_H_RES, BSP_LCD_V_RES);

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
    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = GPIO_NUM_NC,
        .rgb_ele_order  = LCD_RGB_ELEMENT_ORDER_RGB,
        .bits_per_pixel = 18,
    };
    st7701_vendor_config_t vendor_cfg = {
        .init_cmds      = s_vendor_cmds,
        .init_cmds_size = sizeof(s_vendor_cmds) / sizeof(s_vendor_cmds[0]),
        .mipi_config = {
            .dsi_bus    = dsi_bus,
            .dpi_config = NULL,
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

    /* ── 5. Allocate LVGL draw buffer (PSRAM) ───────────────────────────*/
    void *buf1 = heap_caps_malloc(BSP_LCD_DRAW_BUF_SIZE * sizeof(lv_color_t),
                                  MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    void *buf2 = BSP_LCD_DRAW_BUF_DOUBLE
               ? heap_caps_malloc(BSP_LCD_DRAW_BUF_SIZE * sizeof(lv_color_t),
                                  MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
               : NULL;
    if (!buf1) {
        ESP_LOGE(TAG, "Failed to allocate LVGL draw buffer in PSRAM");
        return ESP_ERR_NO_MEM;
    }

    /* ── 6. Register LVGL display ───────────────────────────────────────*/
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
            .sw_rotate   = false,
        },
    };
    lv_disp_t *disp = lvgl_port_add_disp(&disp_cfg);
    if (!disp) {
        ESP_LOGE(TAG, "lvgl_port_add_disp failed");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Display registered: %dx%d @ LVGL", BSP_LCD_H_RES, BSP_LCD_V_RES);
    (void)buf1; (void)buf2; /* owned by lvgl_port */
    return ESP_OK;
}

esp_err_t bsp_touch_driver_init(void)
{
    ESP_LOGI(TAG, "Touch init: GT911 I2C addr=0x%02X bus=%d", BSP_TOUCH_I2C_ADDR, BSP_TOUCH_I2C_NUM);

    /* GT911 requires I2C bus already configured (done in bsp_init via I2C master) */
    esp_lcd_touch_config_t tp_cfg = {
        .x_max        = BSP_LCD_H_RES,
        .y_max        = BSP_LCD_V_RES,
        .rst_gpio_num = (BSP_TOUCH_RST_GPIO >= 0) ? BSP_TOUCH_RST_GPIO : GPIO_NUM_NC,
        .int_gpio_num = (BSP_TOUCH_INT_GPIO >= 0) ? BSP_TOUCH_INT_GPIO : GPIO_NUM_NC,
        .levels = { .reset = 0, .interrupt = 0 },
        .flags  = { .swap_xy = 0, .mirror_x = 0, .mirror_y = 0 },
    };

    esp_lcd_panel_io_handle_t tp_io = NULL;
    esp_lcd_panel_io_i2c_config_t tp_io_cfg = {
        .dev_addr          = BSP_TOUCH_I2C_ADDR,
        .control_phase_bytes = 1,
        .dc_bit_offset     = 0,
        .lcd_cmd_bits      = 16,
        .lcd_param_bits    = 0,
        .flags             = { .disable_control_phase = 1 },
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(
        (esp_lcd_i2c_bus_handle_t)(uintptr_t)BSP_TOUCH_I2C_NUM,
        &tp_io_cfg, &tp_io));

    esp_lcd_touch_handle_t tp = NULL;
    ESP_ERROR_CHECK(esp_lcd_touch_new_i2c_gt911(tp_io, &tp_cfg, &tp));

    /* Register as LVGL input device */
    const lvgl_port_touch_cfg_t touch_cfg = { .disp = lv_disp_get_default(), .handle = tp };
    lv_indev_t *indev = lvgl_port_add_touch(&touch_cfg);
    if (!indev) {
        ESP_LOGE(TAG, "lvgl_port_add_touch failed");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Touch registered: GT911 %dx%d input device", BSP_LCD_H_RES, BSP_LCD_V_RES);
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

