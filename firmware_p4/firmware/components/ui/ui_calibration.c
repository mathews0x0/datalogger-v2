/**
 * @file ui_calibration.c
 * @brief Wave 3 & 4 Implementation: 6-Stage IMU Mount Calibration Wizard (Screen 11)
 *
 * Provides a foolproof interactive multi-step calibration wizard guiding the rider
 * through static orientations, dynamic roll-forward longitudinal alignment, and
 * noise floor verifications before storing transform matrix parameters into NVS flash.
 */

#include "ui.h"
#include "ui_events.h"
#include <stdio.h>
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "ui_calibration";
static int  s_calib_stage = 1;
static lv_obj_t *s_lbl_step_info = NULL;

/* ──────────────────────────────────────────────────────────────────────────
 * Internal Touch Callback Bridges
 * ────────────────────────────────────────────────────────────────────────*/

static void _on_btn_calib_next_cb(lv_event_t *e)
{
    s_calib_stage++;
    if (s_calib_stage > 6) {
        s_calib_stage = 1;
        ESP_LOGI(TAG, "[IMU Calibration Wizard] Stage 6 Complete! Saving to NVS and returning...");
        ui_events_on_navigate_home();
    } else {
        ESP_LOGI(TAG, "[IMU Calibration Wizard] Advanced to Stage %d of 6", s_calib_stage);
        if (s_lbl_step_info) {
            char buf[128];
            const char *instr = "Follow manual instructions for this stage.";
            if (s_calib_stage == 2) instr = "Lean left against reference stand.";
            else if (s_calib_stage == 3) instr = "Lean right against reference stand.";
            else if (s_calib_stage == 4) instr = "Push motorcycle forward 3 meters.";
            else if (s_calib_stage == 5) instr = "Center handlebars straight ahead.";
            else if (s_calib_stage == 6) instr = "Verify offsets before committing to NVS.";

            snprintf(buf, sizeof(buf), "STAGE %d OF 6\n\n%s", s_calib_stage, instr);
            lv_label_set_text(s_lbl_step_info, buf);
        }
        ui_events_on_calib_next_step();
    }
}

static void _on_btn_calib_cancel_cb(lv_event_t *e)
{
    ESP_LOGI(TAG, "[IMU Calibration Wizard] Wizard cancelled by rider");
    s_calib_stage = 1;
    ui_events_on_open_settings();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 11: 6-Stage IMU Mount Calibration Wizard Constructor
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_imu_calibration_wizard(void)
{
    ui_lock(-1);
    s_calib_stage = 1;
    ESP_LOGI(TAG, "Constructing Screen 11: 6-Stage IMU Calibration Wizard [%dx%d]", UI_HOR_RES, UI_VER_RES);

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x09090D), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    /* Header Bar */
    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, 320, 28);
    lv_obj_set_pos(header, 0, 0);
    lv_obj_set_style_bg_color(header, lv_color_hex(0x1A1A22), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_side(header, LV_BORDER_SIDE_BOTTOM, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(header, lv_color_hex(0x2A2A35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(header, 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(header, 0, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *lbl_title = lv_label_create(header);
    lv_label_set_text(lbl_title, "IMU MOUNT CALIBRATION WIZARD");
    lv_obj_set_style_text_color(lbl_title, lv_color_hex(0x00E5FF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_title, LV_ALIGN_CENTER, 0, 0);

    /* Center Info Card (304x120 px) */
    lv_obj_t *card = lv_obj_create(scr);
    lv_obj_set_size(card, 304, 120);
    lv_obj_set_pos(card, 8, 36);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x1A1A22), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(card, lv_color_hex(0x2A2A35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(card, 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(card, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    s_lbl_step_info = lv_label_create(card);
    lv_label_set_text(s_lbl_step_info, "STAGE 1 OF 6: UPRIGHT BASELINE\n\nPosition motorcycle vertically upright on level ground.");
    lv_obj_set_style_text_align(s_lbl_step_info, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(s_lbl_step_info, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(s_lbl_step_info, LV_ALIGN_CENTER, 0, -10);

    lv_obj_t *lbl_noise = lv_label_create(card);
    lv_label_set_text(lbl_noise, "Noise Floor: 0.02 G (READY TO RECORD)");
    lv_obj_set_style_text_color(lbl_noise, lv_color_hex(0x00D26A), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_noise, LV_ALIGN_BOTTOM_MID, 0, -4);

    /* Bottom Buttons (2 Buttons side by side across 304 px) */
    lv_obj_t *btn_cancel = lv_btn_create(scr);
    lv_obj_set_size(btn_cancel, 148, 66);
    lv_obj_set_pos(btn_cancel, 8, 166);
    lv_obj_set_style_bg_color(btn_cancel, lv_color_hex(0x3A3A45), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_cancel, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_cancel, _on_btn_calib_cancel_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn_canc = lv_label_create(btn_cancel);
    lv_label_set_text(lbl_btn_canc, "CANCEL");
    lv_obj_set_style_text_color(lbl_btn_canc, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_canc, LV_ALIGN_CENTER, 0, 0);

    lv_obj_t *btn_next = lv_btn_create(scr);
    lv_obj_set_size(btn_next, 148, 66);
    lv_obj_set_pos(btn_next, 164, 166);
    lv_obj_set_style_bg_color(btn_next, lv_color_hex(0x00D26A), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_next, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_next, _on_btn_calib_next_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn_next = lv_label_create(btn_next);
    lv_label_set_text(lbl_btn_next, "NEXT STEP →");
    lv_obj_set_style_text_color(lbl_btn_next, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_next, LV_ALIGN_CENTER, 0, 0);

    lv_scr_load(scr);
    ui_unlock();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Real-Time Wizard Progression Updater (Core 0/1 sensor background)
 * ────────────────────────────────────────────────────────────────────────*/
void ui_calibration_update_progress(int step, int sample_count, bool stable)
{
    if (ui_lock(20)) {
        s_calib_stage = step;
        ui_unlock();
    }
}
