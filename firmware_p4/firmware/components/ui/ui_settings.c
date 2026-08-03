/**
 * @file ui_settings.c
 * @brief Wave 3 Implementation: Settings Configuration Grid (Screen 10)
 *
 * Implements an adaptive multi-resolution configuration grid connecting switch toggles
 * and calibration triggers directly to NVS persistent storage and state transition routines.
 */

#include "ui.h"
#include "ui_events.h"
#include <stdio.h>
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "ui_settings";

/* ──────────────────────────────────────────────────────────────────────────
 * Internal Touch & Switch Callback Bridges
 * ────────────────────────────────────────────────────────────────────────*/

static void _on_btn_wifi_setup_cb(lv_event_t *e)
{
    ESP_LOGI(TAG, "[Settings Grid] OPEN CAPTIVE PORTAL button pressed");
    ui_events_on_start_captive_portal();
}

static void _on_btn_calib_wizard_cb(lv_event_t *e)
{
    ESP_LOGI(TAG, "[Settings Grid] START IMU CALIBRATION WIZARD pressed");
    ui_events_dispatch(UI_EVENT_IMU_CALIB_CLICKED, NULL);
}

static void _on_btn_debug_cb(lv_event_t *e)
{
    (void)e;
    ESP_LOGI(TAG, "[Settings Grid] OPEN HARDWARE DEBUG pressed");
    ui_events_on_open_hardware_debug();
}

static void _on_btn_back_cb(lv_event_t *e)
{
    ESP_LOGI(TAG, "[Settings Grid] BACK TO HOME pressed");
    ui_events_on_navigate_home();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 10: Settings Configuration Grid Constructor
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_settings(void)
{
    ui_home_deactivate();
    ui_lock(-1);
    ESP_LOGI(TAG, "Constructing Screen 10: Settings Configuration Grid [%dx%d]", UI_HOR_RES, UI_VER_RES);

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x09090D), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    /* Header Bar */
    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, UI_HOR_RES, UI_HEADER_HEIGHT);
    lv_obj_set_pos(header, 0, 0);
    lv_obj_set_style_bg_color(header, lv_color_hex(0x1A1A22), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_side(header, LV_BORDER_SIDE_BOTTOM, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(header, lv_color_hex(0x2A2A35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(header, 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(header, 0, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *lbl_title = lv_label_create(header);
    lv_label_set_text(lbl_title, "SYSTEM SETTINGS & SETUP");
    lv_obj_set_style_text_color(lbl_title, lv_color_hex(0xFF6B35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_title, LV_ALIGN_CENTER, 0, 0);

    const int margin = UI_RES_CLASS_WIDESCREEN ? 24 : 8;
    const int gap = UI_RES_CLASS_WIDESCREEN ? 20 : 8;
    const int button_w = UI_RES_CLASS_WIDESCREEN ? (UI_HOR_RES - 3 * margin) / 2 : UI_HOR_RES - 2 * margin;
    const int button_h = UI_RES_CLASS_WIDESCREEN ? 110 : (UI_RES_CLASS_MEDIUM ? 62 : 48);
    const int content_y = UI_HEADER_HEIGHT + margin;

    lv_obj_t *btn_wifi = lv_btn_create(scr);
    lv_obj_set_size(btn_wifi, button_w, button_h);
    lv_obj_set_pos(btn_wifi, margin, content_y);
    lv_obj_set_style_bg_color(btn_wifi, lv_color_hex(0x007AFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_wifi, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_wifi, _on_btn_wifi_setup_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn_wifi = lv_label_create(btn_wifi);
    lv_label_set_text(lbl_btn_wifi, "WIFI SETUP PORTAL (QR)");
    lv_obj_set_style_text_color(lbl_btn_wifi, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_wifi, LV_ALIGN_CENTER, 0, 0);

    /* Button 2: IMU Calibration Wizard (Y=100, Height=54) */
    lv_obj_t *btn_calib = lv_btn_create(scr);
    lv_obj_set_size(btn_calib, button_w, button_h);
    lv_obj_set_pos(btn_calib, UI_RES_CLASS_WIDESCREEN ? 2 * margin + button_w : margin,
                   UI_RES_CLASS_WIDESCREEN ? content_y : content_y + button_h + gap);
    lv_obj_set_style_bg_color(btn_calib, lv_color_hex(0x3A3A45), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_calib, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_calib, _on_btn_calib_wizard_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn_calib = lv_label_create(btn_calib);
    lv_label_set_text(lbl_btn_calib, "IMU MOUNT CALIBRATION");
    lv_obj_set_style_text_color(lbl_btn_calib, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_calib, LV_ALIGN_CENTER, 0, 0);

    /* Button 3: Hardware debug */
    const int debug_y = UI_RES_CLASS_WIDESCREEN
                      ? content_y + button_h + gap
                      : content_y + 2 * (button_h + gap);
    const int debug_h = UI_RES_CLASS_WIDESCREEN ? 80 : button_h;
    const int debug_w = UI_RES_CLASS_WIDESCREEN ? UI_HOR_RES - 2 * margin : button_w;
    lv_obj_t *btn_debug = lv_btn_create(scr);
    lv_obj_set_size(btn_debug, debug_w, debug_h);
    lv_obj_set_pos(btn_debug, margin, debug_y);
    lv_obj_set_style_bg_color(btn_debug, lv_color_hex(0x7A3DF0), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_debug, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_debug, _on_btn_debug_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn_debug = lv_label_create(btn_debug);
    lv_label_set_text(lbl_btn_debug, "HARDWARE DEBUG  •  GPS / IMU");
    lv_obj_set_style_text_color(lbl_btn_debug, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_debug, LV_ALIGN_CENTER, 0, 0);

    /* Button 4: Return Home Footer */
    const int back_h = UI_RES_CLASS_WIDESCREEN ? 72 : (UI_RES_CLASS_MEDIUM ? 56 : 32);
    const int back_y = UI_RES_CLASS_WIDESCREEN
                     ? UI_VER_RES - 24 - back_h
                     : debug_y + debug_h + gap;
    lv_obj_t *btn_back = lv_btn_create(scr);
    lv_obj_set_size(btn_back, UI_RES_CLASS_WIDESCREEN ? UI_HOR_RES - 2 * margin : button_w, back_h);
    lv_obj_set_pos(btn_back, margin, back_y);
    lv_obj_set_style_bg_color(btn_back, lv_color_hex(0xFF3B30), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_back, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_back, _on_btn_back_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn_back = lv_label_create(btn_back);
    lv_label_set_text(lbl_btn_back, "← BACK TO HOME");
    lv_obj_set_style_text_color(lbl_btn_back, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_back, LV_ALIGN_CENTER, 0, 0);

    ui_load_screen(scr);
    ui_unlock();
}
