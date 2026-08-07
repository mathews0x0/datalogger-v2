/**
 * @file main.c
 * @brief RaceSense Precision Touch Verification Suite (OEM Calibrated)
 *
 * Implements the empirically derived affine calibration matrix from our 4-point
 * glass verification protocol. Translates and scales raw XPT2046 sensor data
 * directly into accurate 320x240 screen pixel coordinates.
 */

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_err.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_ili9341.h"
#include "esp_lcd_touch.h"
#include "esp_lcd_touch_xpt2046.h"
#include "lvgl.h"
#include "esp_lvgl_port.h"

static const char *TAG = "TOUCH_VERIFY";

/* RS-Core V4.2 Physical Pin Assignments */
#define PIN_PWR_LATCH 41
#define PIN_TOUCH_CS  7
#define PIN_TOUCH_IRQ 38
#define PIN_LCD_CLK   15
#define PIN_LCD_MOSI  16
#define PIN_LCD_MISO  9
#define PIN_LCD_CS    5
#define PIN_LCD_DC    6
#define PIN_LCD_RST   42

static lv_obj_t *lbl_status = NULL;
static lv_obj_t *lbl_coords = NULL;
static lv_obj_t *cursor_marker = NULL;

/* Proven vendor initialization sequence */
static const ili9341_lcd_init_cmd_t mpy_init_cmds[] = {
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

static void init_board_hardware_pins(void)
{
    gpio_config_t pwr_cfg = {
        .pin_bit_mask = (1ULL << PIN_PWR_LATCH),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };
    gpio_config(&pwr_cfg);
    gpio_set_level(PIN_PWR_LATCH, 1);
}

/**
 * @brief Empirical Affine Coordinate Calibration Matrix
 * Derived from user-supplied raw extreme measurements:
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
        if (cal_x >= 320) cal_x = 319;
        if (cal_y < 0) cal_y = 0;
        if (cal_y >= 240) cal_y = 239;

        x[i] = (uint16_t)cal_x;
        y[i] = (uint16_t)cal_y;
    }
}

static void scr_touch_cb(lv_event_t *e)
{
    lv_indev_t *indev = lv_indev_get_act();
    if (indev && lbl_coords) {
        lv_point_t point;
        lv_indev_get_point(indev, &point);
        lv_label_set_text_fmt(lbl_coords, "Calibrated -> X: %03d | Y: %03d", point.x, point.y);
        lv_obj_set_style_text_color(lbl_coords, lv_color_hex(0x00E5FF), 0);
        
        /* Update visual cursor indicator to track touch precisely */
        if (cursor_marker) {
            lv_obj_clear_flag(cursor_marker, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_pos(cursor_marker, point.x - 6, point.y - 6);
        }
    }
}

static void btn_touch_cb(lv_event_t *e)
{
    lv_event_code_t code = lv_event_get_code(e);
    lv_obj_t *obj = lv_event_get_current_target(e);
    lv_indev_t *indev = lv_indev_get_act();

    if (code == LV_EVENT_CLICKED || code == LV_EVENT_PRESSED) {
        if (indev && lbl_coords) {
            lv_point_t point;
            lv_indev_get_point(indev, &point);
            lv_label_set_text_fmt(lbl_coords, "Calibrated -> X: %03d | Y: %03d", point.x, point.y);
            if (cursor_marker) {
                lv_obj_clear_flag(cursor_marker, LV_OBJ_FLAG_HIDDEN);
                lv_obj_set_pos(cursor_marker, point.x - 6, point.y - 6);
            }
        }
        if (code == LV_EVENT_CLICKED) {
            const char *btn_name = (const char *)lv_event_get_user_data(e);
            if (btn_name && lbl_status) {
                lv_label_set_text_fmt(lbl_status, "VERIFIED: [%s]", btn_name);
                lv_obj_set_style_text_color(lbl_status, lv_color_hex(0x00FF7F), 0);
                lv_obj_set_style_bg_color(obj, lv_color_hex(0x00D26A), 0);
                lv_obj_t *lbl = lv_obj_get_child(obj, 0);
                if (lbl) lv_obj_set_style_text_color(lbl, lv_color_hex(0x000000), 0);
                ESP_LOGI(TAG, "Touch Confirmed: %s", btn_name);
            }
        }
    }
}

static lv_obj_t *create_test_btn(lv_obj_t *parent, const char *label_text, lv_align_t align, int16_t x_ofs, int16_t y_ofs, const char *id_str)
{
    lv_obj_t *btn = lv_btn_create(parent);
    lv_obj_set_size(btn, 110, 52);
    lv_obj_align(btn, align, x_ofs, y_ofs);
    lv_obj_set_style_bg_color(btn, lv_color_hex(0x1F293B), 0);
    lv_obj_set_style_border_width(btn, 2, 0);
    lv_obj_set_style_border_color(btn, lv_color_hex(0x3B82F6), 0);
    lv_obj_set_style_radius(btn, 6, 0);

    lv_obj_t *lbl = lv_label_create(btn);
    lv_label_set_text(lbl, label_text);
    lv_obj_set_style_text_color(lbl, lv_color_hex(0xFFFFFF), 0);
    lv_obj_align(lbl, LV_ALIGN_CENTER, 0, 0);

    lv_obj_add_event_cb(btn, btn_touch_cb, LV_EVENT_CLICKED, (void *)id_str);
    lv_obj_add_event_cb(btn, btn_touch_cb, LV_EVENT_PRESSED, (void *)id_str);
    return btn;
}

void app_main(void)
{
    ESP_LOGI(TAG, "=== RaceSense Calibrated Touch Verification Suite ===");
    init_board_hardware_pins();

    const lvgl_port_cfg_t lv_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    ESP_ERROR_CHECK(lvgl_port_init(&lv_cfg));

    spi_bus_config_t buscfg = {
        .mosi_io_num   = PIN_LCD_MOSI,
        .miso_io_num   = PIN_LCD_MISO,
        .sclk_io_num   = PIN_LCD_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 320 * 80 * sizeof(uint16_t),
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_handle_t io_handle = NULL;
    esp_lcd_panel_io_spi_config_t io_cfg = {
        .dc_gpio_num = PIN_LCD_DC,
        .cs_gpio_num = PIN_LCD_CS,
        .pclk_hz = 15 * 1000 * 1000,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
        .spi_mode = 0,
        .trans_queue_depth = 10,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(SPI2_HOST, &io_cfg, &io_handle));

    esp_lcd_panel_handle_t panel_handle = NULL;
    ili9341_vendor_config_t vendor_config = {
        .init_cmds = mpy_init_cmds,
        .init_cmds_size = sizeof(mpy_init_cmds) / sizeof(ili9341_lcd_init_cmd_t),
    };
    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = PIN_LCD_RST,
        .rgb_endian     = LCD_RGB_ENDIAN_BGR,
        .bits_per_pixel = 16,
        .vendor_config  = &vendor_config,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(io_handle, &panel_cfg, &panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
    
    ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_handle, false));
    esp_lcd_panel_io_tx_param(io_handle, 0x20, NULL, 0);
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));

    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = io_handle,
        .panel_handle = panel_handle,
        .buffer_size = 320 * 50,
        .double_buffer = false,
        .hres = 320,
        .vres = 240,
        .rotation = {0},
        .flags = { .buff_dma = true },
    };
    lv_disp_t *lv_disp = lvgl_port_add_disp(&disp_cfg);
    (void)lv_disp;

    uint8_t verified_madctl = 0x80;
    esp_lcd_panel_io_tx_param(io_handle, 0x36, &verified_madctl, 1);

    esp_lcd_touch_handle_t tp_handle = NULL;
    esp_lcd_panel_io_handle_t tp_io_handle = NULL;
    esp_lcd_panel_io_spi_config_t tp_io_config = ESP_LCD_TOUCH_IO_SPI_XPT2046_CONFIG(PIN_TOUCH_CS);
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)SPI2_HOST, &tp_io_config, &tp_io_handle));

    esp_lcd_touch_config_t tp_cfg = {
        .x_max = 320,
        .y_max = 240,
        .rst_gpio_num = -1,
        .int_gpio_num = PIN_TOUCH_IRQ,
        .levels = {
            .reset = 0,
            .interrupt = 0,
        },
        .flags = {
            /* Zero out basic driver boolean transformations; handled by our precision matrix */
            .swap_xy = 0,
            .mirror_x = 0,
            .mirror_y = 0,
        },
        .process_coordinates = oem_process_coordinates,
    };
    ESP_LOGI(TAG, "Initializing XPT2046 Touch Driver with OEM Affine Calibration Matrix");
    ESP_ERROR_CHECK(esp_lcd_touch_new_spi_xpt2046(tp_io_handle, &tp_cfg, &tp_handle));

    const lvgl_port_touch_cfg_t touch_port_cfg = {
        .disp = lv_disp,
        .handle = tp_handle,
    };
    lv_indev_t *lv_touch = lvgl_port_add_touch(&touch_port_cfg);
    (void)lv_touch;

    if (lvgl_port_lock(0)) {
        lv_obj_t *scr = lv_obj_create(NULL);
        lv_obj_set_style_bg_color(scr, lv_color_hex(0x0B0F19), LV_PART_MAIN | LV_STATE_DEFAULT);
        lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);
        
        lv_obj_add_event_cb(scr, scr_touch_cb, LV_EVENT_PRESSED, NULL);
        lv_obj_add_event_cb(scr, scr_touch_cb, LV_EVENT_PRESSING, NULL);

        create_test_btn(scr, "TOP LEFT",  LV_ALIGN_TOP_LEFT,     10, 10, "TOP LEFT");
        create_test_btn(scr, "TOP RIGHT", LV_ALIGN_TOP_RIGHT,   -10, 10, "TOP RIGHT");
        create_test_btn(scr, "BTM LEFT",  LV_ALIGN_BOTTOM_LEFT,  10, -10, "BOTTOM LEFT");
        create_test_btn(scr, "BTM RIGHT", LV_ALIGN_BOTTOM_RIGHT,-10, -10, "BOTTOM RIGHT");

        lv_obj_t *box_center = lv_obj_create(scr);
        lv_obj_set_size(box_center, 236, 88);
        lv_obj_align(box_center, LV_ALIGN_CENTER, 0, 0);
        lv_obj_set_style_bg_color(box_center, lv_color_hex(0x151E2E), 0);
        lv_obj_set_style_border_width(box_center, 2, 0);
        lv_obj_set_style_border_color(box_center, lv_color_hex(0x00E5FF), 0);
        lv_obj_set_style_radius(box_center, 8, 0);
        lv_obj_add_event_cb(box_center, scr_touch_cb, LV_EVENT_PRESSED, NULL);
        lv_obj_add_event_cb(box_center, scr_touch_cb, LV_EVENT_PRESSING, NULL);

        lbl_status = lv_label_create(box_center);
        lv_label_set_text(lbl_status, "TAP A CORNER BUTTON...");
        lv_obj_set_style_text_color(lbl_status, lv_color_hex(0xFFD700), 0);
        lv_obj_align(lbl_status, LV_ALIGN_TOP_MID, 0, 4);

        lbl_coords = lv_label_create(box_center);
        lv_label_set_text(lbl_coords, "Calibrated -> Waiting...");
        lv_obj_set_style_text_color(lbl_coords, lv_color_hex(0xAAAAAA), 0);
        lv_obj_align(lbl_coords, LV_ALIGN_BOTTOM_MID, 0, -4);

        /* Visual Floating Cursor Marker for immediate visual feedback */
        cursor_marker = lv_obj_create(scr);
        lv_obj_set_size(cursor_marker, 12, 12);
        lv_obj_set_style_bg_color(cursor_marker, lv_color_hex(0xFF0055), 0);
        lv_obj_set_style_border_width(cursor_marker, 2, 0);
        lv_obj_set_style_border_color(cursor_marker, lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_radius(cursor_marker, LV_RADIUS_CIRCLE, 0);
        lv_obj_add_flag(cursor_marker, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(cursor_marker, LV_OBJ_FLAG_FLOATING);
        lv_obj_clear_flag(cursor_marker, LV_OBJ_FLAG_CLICKABLE);

        lv_scr_load(scr);
        lvgl_port_unlock();
    }

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
