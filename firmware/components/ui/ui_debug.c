/**
 * @file ui_debug.c
 * @brief Live GPS and BMI323 hardware diagnostics.
 */

#include "ui.h"
#include "sensors.h"
#include "gps.h"
#include "bmi323.h"

#include <stdio.h>
#include <math.h>
#include "esp_log.h"

static const char *TAG = "ui_debug";

static bool s_debug_active;
static lv_obj_t *s_gps_status;
static lv_obj_t *s_gps_sats;
static lv_obj_t *s_gps_position;
static lv_obj_t *s_gps_time;
static lv_obj_t *s_gps_rate;
static lv_obj_t *s_imu_status;
static lv_obj_t *s_imu_acc;
static lv_obj_t *s_imu_gyro;
static lv_obj_t *s_imu_raw;
static lv_obj_t *s_imu_arena;
static lv_obj_t *s_imu_ball;
static float s_imu_center_x;
static float s_imu_center_y;
static float s_imu_live_x;
static float s_imu_live_y;

#define C(hex) lv_color_hex(hex)

static const lv_font_t *debug_font_body(void)
{
    return UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_20 : &lv_font_montserrat_14;
}

static const lv_font_t *debug_font_small(void)
{
    return UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12;
}

static void debug_label_style(lv_obj_t *obj, uint32_t color, const lv_font_t *font)
{
    lv_obj_set_style_text_color(obj, C(color), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(obj, font, LV_PART_MAIN | LV_STATE_DEFAULT);
}

static void _on_back(lv_event_t *e)
{
    (void)e;
    ui_events_on_navigate_home();
}

static void _on_imu_center(lv_event_t *e)
{
    (void)e;
    s_imu_center_x = s_imu_live_x;
    s_imu_center_y = s_imu_live_y;
    lv_obj_center(s_imu_ball);
    ESP_LOGI(TAG, "IMU dot centered at x=%.3f y=%.3f",
             (double)s_imu_center_x, (double)s_imu_center_y);
}

static lv_obj_t *_make_label(lv_obj_t *parent, const char *text,
                             int x, int y, uint32_t color, const lv_font_t *font)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_pos(label, x, y);
    debug_label_style(label, color, font);
    return label;
}

static void _make_section_title(lv_obj_t *parent, const char *text, int x, int y)
{
    _make_label(parent, text, x, y, UI_COLOR_PRIMARY, debug_font_small());
}

void ui_show_hardware_debug(void)
{
    ui_home_deactivate();
    ui_lock(-1);
    s_debug_active = false;
    s_imu_center_x = 0.0f;
    s_imu_center_y = 0.0f;
    s_imu_live_x = 0.0f;
    s_imu_live_y = 0.0f;

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, C(UI_COLOR_BG_DARK), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, UI_HOR_RES, UI_HEADER_HEIGHT);
    lv_obj_set_pos(header, 0, 0);
    lv_obj_set_style_bg_color(header, C(UI_COLOR_SURFACE), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(header, C(UI_COLOR_BORDER), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(header, 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *title = _make_label(header, "HARDWARE DEBUG", UI_SCALE_X(18), 0,
                                  UI_COLOR_TEXT_PRIMARY,
                                  UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_28 : debug_font_body());
    lv_obj_align(title, LV_ALIGN_LEFT_MID, UI_SCALE_X(18), 0);

    lv_obj_t *back = lv_btn_create(header);
    lv_obj_set_size(back, UI_SCALE_X(100), UI_HEADER_HEIGHT - UI_SCALE_Y(10));
    lv_obj_align(back, LV_ALIGN_RIGHT_MID, -UI_SCALE_X(12), 0);
    lv_obj_set_style_bg_color(back, C(UI_COLOR_DANGER), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(back, UI_BTN_RADIUS, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(back, _on_back, LV_EVENT_CLICKED, NULL);
    lv_obj_t *back_label = lv_label_create(back);
    lv_label_set_text(back_label, "BACK");
    debug_label_style(back_label, UI_COLOR_TEXT_PRIMARY, debug_font_small());
    lv_obj_center(back_label);

    lv_obj_t *tabs = lv_tabview_create(scr, LV_DIR_TOP, UI_RES_CLASS_WIDESCREEN ? 42 : 32);
    lv_obj_set_size(tabs, UI_HOR_RES, UI_VER_RES - UI_HEADER_HEIGHT);
    lv_obj_set_pos(tabs, 0, UI_HEADER_HEIGHT);
    lv_obj_set_style_bg_color(tabs, C(UI_COLOR_BG_DARK), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(tabs, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    lv_obj_t *gps_tab = lv_tabview_add_tab(tabs, "GPS");
    lv_obj_t *imu_tab = lv_tabview_add_tab(tabs, "IMU");
    lv_obj_set_style_bg_color(gps_tab, C(UI_COLOR_BG_DARK), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_color(imu_tab, C(UI_COLOR_BG_DARK), LV_PART_MAIN | LV_STATE_DEFAULT);

    const int margin = UI_RES_CLASS_WIDESCREEN ? 24 : 10;
    const int col_gap = UI_RES_CLASS_WIDESCREEN ? 18 : 8;
    const int col_w = (UI_HOR_RES - 2 * margin - col_gap) / 2;

    _make_section_title(gps_tab, "RECEIVER STATUS", margin, 18);
    s_gps_status = _make_label(gps_tab, "SEARCHING", margin, 48,
                               UI_COLOR_WARNING, UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_36 : debug_font_body());
    s_gps_sats = _make_label(gps_tab, "SATELLITES: 0", margin, 104,
                             UI_COLOR_TEXT_PRIMARY, debug_font_body());
    s_gps_rate = _make_label(gps_tab, "RMC RATE: --", margin, 140,
                             UI_COLOR_TEXT_MUTED, debug_font_small());

    _make_section_title(gps_tab, "POSITION", margin, 184);
    s_gps_position = _make_label(gps_tab, "LAT --\nLON --", margin, 214,
                                 UI_COLOR_TEXT_PRIMARY, debug_font_body());
    s_gps_time = _make_label(gps_tab, "TIME --", margin, 286,
                             UI_COLOR_TEXT_PRIMARY, debug_font_body());
    _make_label(gps_tab, "ERROR means checksum/configuration failure", margin,
                UI_VER_RES > 400 ? 338 : 198, UI_COLOR_TEXT_MUTED, debug_font_small());

    _make_section_title(imu_tab, "BMI323 MOTION", margin, 18);
    s_imu_status = _make_label(imu_tab, "IMU SEARCHING", margin, 48,
                               UI_COLOR_WARNING, debug_font_body());

    s_imu_arena = lv_obj_create(imu_tab);
    lv_obj_set_size(s_imu_arena, col_w, UI_RES_CLASS_WIDESCREEN ? 240 : 120);
    lv_obj_set_pos(s_imu_arena, margin, UI_RES_CLASS_WIDESCREEN ? 92 : 82);
    lv_obj_set_style_bg_color(s_imu_arena, C(0x111118), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(s_imu_arena, C(UI_COLOR_BORDER), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(s_imu_arena, 2, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(s_imu_arena, UI_CARD_RADIUS, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(s_imu_arena, LV_OBJ_FLAG_SCROLLABLE);

    s_imu_ball = lv_obj_create(s_imu_arena);
    const int ball_d = UI_RES_CLASS_WIDESCREEN ? 34 : 22;
    lv_obj_set_size(s_imu_ball, ball_d, ball_d);
    lv_obj_set_style_bg_color(s_imu_ball, C(UI_COLOR_PRIMARY), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(s_imu_ball, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(s_imu_ball, LV_RADIUS_CIRCLE, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(s_imu_ball, C(UI_COLOR_TEXT_PRIMARY), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(s_imu_ball, 2, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_center(s_imu_ball);

    lv_obj_t *center_btn = lv_btn_create(imu_tab);
    lv_obj_set_size(center_btn, col_w, UI_RES_CLASS_WIDESCREEN ? 40 : 30);
    lv_obj_set_pos(center_btn, margin, UI_RES_CLASS_WIDESCREEN ? 340 : 208);
    lv_obj_set_style_bg_color(center_btn, C(UI_COLOR_PRIMARY), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(center_btn, UI_BTN_RADIUS, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(center_btn, _on_imu_center, LV_EVENT_CLICKED, NULL);
    lv_obj_t *center_label = lv_label_create(center_btn);
    lv_label_set_text(center_label, "CENTER");
    debug_label_style(center_label, UI_COLOR_TEXT_PRIMARY, debug_font_small());
    lv_obj_center(center_label);

    const int value_x = margin + col_w + col_gap;
    _make_section_title(imu_tab, "INTEGER VALUES", value_x, 18);
    s_imu_acc = _make_label(imu_tab, "ACC g\nX 0  Y 0  Z 0", value_x, 56,
                            UI_COLOR_TEXT_PRIMARY, debug_font_body());
    s_imu_gyro = _make_label(imu_tab, "GYRO dps\nX 0  Y 0  Z 0", value_x, 132,
                             UI_COLOR_TEXT_PRIMARY, debug_font_body());
    s_imu_raw = _make_label(imu_tab, "RAW\nA 0 0 0\nG 0 0 0", value_x, 214,
                            UI_COLOR_TEXT_MUTED, debug_font_small());

    ui_load_screen(scr);
    s_debug_active = true;
    ui_unlock();
    ESP_LOGI(TAG, "Hardware debug screen opened with GPS and IMU tabs");
}

void ui_hardware_debug_update(void)
{
    if (!s_debug_active || !ui_lock(20)) return;

    gps_fix_t fix = {0};
    gps_health_t health = {0};
    bmi323_raw_t raw = {0};
    bmi323_data_t data = {0};
    sensors_get_latest_gps(&fix);
    gps_get_health(&health);
    sensors_get_latest_imu(&raw);
    bmi323_raw_to_si(&raw, &data);

    bool gps_error = !health.config_ok || health.checksum_failures > 0;
    const char *gps_state = gps_error ? "ERROR" : (fix.valid ? "LOCKED" : "SEARCHING");
    uint32_t gps_color = gps_error ? UI_COLOR_DANGER : (fix.valid ? UI_COLOR_SUCCESS : UI_COLOR_WARNING);
    lv_label_set_text(s_gps_status, gps_state);
    debug_label_style(s_gps_status, gps_color,
                      UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_36 : debug_font_body());

    char buf[160];
    snprintf(buf, sizeof(buf), "SATELLITES: %d", fix.satellites);
    lv_label_set_text(s_gps_sats, buf);
    snprintf(buf, sizeof(buf), "RMC RATE: %.2f Hz  (%lu ACK / %lu ERR)",
             health.rmc_rate_hz,
             (unsigned long)health.ubx_ack_ok,
             (unsigned long)health.ubx_ack_fail);
    lv_label_set_text(s_gps_rate, buf);
    snprintf(buf, sizeof(buf), "LAT %s\nLON %s",
             fix.valid ? "" : "--",
             fix.valid ? "" : "--");
    if (fix.valid) {
        snprintf(buf, sizeof(buf), "LAT %+0.6f\nLON %+0.6f", fix.lat, fix.lon);
    }
    lv_label_set_text(s_gps_position, buf);
    snprintf(buf, sizeof(buf), "TIME %s", fix.gps_ts[0] ? fix.gps_ts : "--");
    lv_label_set_text(s_gps_time, buf);

    bool imu_ok = sensors_imu_ok();
    lv_label_set_text(s_imu_status, imu_ok ? "IMU ONLINE" : "IMU ERROR");
    debug_label_style(s_imu_status, imu_ok ? UI_COLOR_SUCCESS : UI_COLOR_DANGER, debug_font_body());

    int acc_x = (int)lroundf(data.ax);
    int acc_y = (int)lroundf(data.ay);
    int acc_z = (int)lroundf(data.az);
    int gyr_x = (int)lroundf(data.gx);
    int gyr_y = (int)lroundf(data.gy);
    int gyr_z = (int)lroundf(data.gz);
    snprintf(buf, sizeof(buf), "ACC g\nX %+d  Y %+d  Z %+d", acc_x, acc_y, acc_z);
    lv_label_set_text(s_imu_acc, buf);
    snprintf(buf, sizeof(buf), "GYRO dps\nX %+d  Y %+d  Z %+d", gyr_x, gyr_y, gyr_z);
    lv_label_set_text(s_imu_gyro, buf);
    snprintf(buf, sizeof(buf), "RAW\nA %d %d %d\nG %d %d %d",
             raw.ax, raw.ay, raw.az, raw.gx, raw.gy, raw.gz);
    lv_label_set_text(s_imu_raw, buf);

    int arena_w = lv_obj_get_width(s_imu_arena);
    int arena_h = lv_obj_get_height(s_imu_arena);
    s_imu_live_x = data.ax * 0.35f + data.gx * 0.0015f;
    s_imu_live_y = data.ay * 0.35f + data.gy * 0.0015f;
    float x_norm = s_imu_live_x - s_imu_center_x;
    float y_norm = s_imu_live_y - s_imu_center_y;
    if (x_norm > 0.45f) x_norm = 0.45f;
    if (x_norm < -0.45f) x_norm = -0.45f;
    if (y_norm > 0.45f) y_norm = 0.45f;
    if (y_norm < -0.45f) y_norm = -0.45f;
    int ball_w = lv_obj_get_width(s_imu_ball);
    int ball_h = lv_obj_get_height(s_imu_ball);
    int ball_x = (arena_w - ball_w) / 2 + (int)(x_norm * arena_w);
    int ball_y = (arena_h - ball_h) / 2 - (int)(y_norm * arena_h);
    /* ball_x/ball_y are absolute offsets from the arena's top-left corner.
     * lv_obj_center() leaves LV_ALIGN_CENTER active, so lv_obj_set_pos() would
     * incorrectly apply these values from the center and push the ball down/right. */
    lv_obj_align(s_imu_ball, LV_ALIGN_TOP_LEFT, ball_x, ball_y);

    ui_unlock();
}
