/**
 * @file ui_storage_fault.c
 * @brief Rider-facing screen for a latched logging storage failure.
 */

#include "ui.h"
#include "ui_events.h"
#include "lvgl.h"

static void _on_return_home(lv_event_t *event)
{
    (void)event;
    ui_events_on_navigate_home();
}

void ui_show_storage_fault(storage_fault_t fault)
{
    ui_home_deactivate();
    ui_lock(-1);

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(UI_COLOR_SURFACE), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    lv_obj_t *header = lv_label_create(scr);
    lv_label_set_text(header, "LOGGING STOPPED");
    lv_obj_set_style_text_color(header, lv_color_hex(UI_COLOR_DANGER), 0);
    lv_obj_set_style_text_font(header,
                               UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_28
                                                       : &lv_font_montserrat_16,
                               0);
    lv_obj_align(header, LV_ALIGN_TOP_MID, 0, UI_SCALE_Y(34));

    lv_obj_t *title = lv_label_create(scr);
    lv_label_set_text(title, "STORAGE ERROR");
    lv_obj_set_style_text_color(title, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_set_style_text_font(title,
                               UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_36
                                                       : &lv_font_montserrat_20,
                               0);
    lv_obj_align(title, LV_ALIGN_CENTER, 0, UI_SCALE_Y(-70));

    lv_obj_t *reason = lv_label_create(scr);
    lv_label_set_text(reason, storage_fault_name(fault));
    lv_obj_set_style_text_color(reason, lv_color_hex(UI_COLOR_WARNING), 0);
    lv_obj_set_style_text_align(reason, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(reason, LV_ALIGN_CENTER, 0, UI_SCALE_Y(-25));

    lv_obj_t *detail = lv_label_create(scr);
    lv_label_set_text(detail, "The session was safely closed.\nCHECK SD CARD OR STORAGE");
    lv_obj_set_style_text_color(detail, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
    lv_obj_set_style_text_align(detail, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(detail, LV_ALIGN_CENTER, 0, UI_SCALE_Y(20));

    lv_obj_t *button = lv_btn_create(scr);
    lv_obj_set_size(button, UI_PCT_X(70), UI_SCALE_Y(58));
    lv_obj_align(button, LV_ALIGN_BOTTOM_MID, 0, -UI_SCALE_Y(22));
    lv_obj_set_style_bg_color(button, lv_color_hex(UI_COLOR_PRIMARY), 0);
    lv_obj_set_style_radius(button, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(button, _on_return_home, LV_EVENT_CLICKED, NULL);

    lv_obj_t *button_label = lv_label_create(button);
    lv_label_set_text(button_label, "RETURN HOME");
    lv_obj_set_style_text_color(button_label, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_align(button_label, LV_ALIGN_CENTER, 0, 0);

    ui_load_screen(scr);
    ui_unlock();
}
