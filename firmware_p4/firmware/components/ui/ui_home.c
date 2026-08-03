/**
 * @file ui_home.c
 * @brief Simulator-faithful splash and dashboard screens.
 *
 * This file deliberately contains no board/controller knowledge.  Display size
 * comes from ui_layout.h and the BSP is responsible for presenting LVGL.
 */

#include "ui.h"
#include "lvgl.h"
#include "storage.h"
#include <stdio.h>
#include "esp_log.h"

static const char *TAG = "ui_home";

static volatile bool s_home_active;
static lv_obj_t *s_lbl_bat;
static lv_obj_t *s_lbl_gps;
static lv_obj_t *s_lbl_status;
static lv_obj_t *s_lbl_track;
static lv_obj_t *s_lbl_store;
static lv_obj_t *s_storage_bar;

static void storage_free_text(char *buf, size_t size, bool sd_ok)
{
    uint64_t total_bytes = 0;
    uint64_t free_bytes = 0;
    if (!sd_ok) {
        snprintf(buf, size, "NO SD CARD");
    } else if (storage_get_space_bytes(&total_bytes, &free_bytes) == ESP_OK) {
        snprintf(buf, size, "%.1f GB FREE",
                 (double)free_bytes / (1024.0 * 1024.0 * 1024.0));
    } else {
        snprintf(buf, size, "SD READY");
    }
}

#define C(hex) lv_color_hex(hex)

static int ui_margin(void) { return UI_RES_CLASS_WIDESCREEN ? 16 : (UI_RES_CLASS_MEDIUM ? 10 : 8); }
static const lv_font_t *font_small(void) { return UI_RES_CLASS_COMPACT ? &lv_font_montserrat_12 : &lv_font_montserrat_14; }
static const lv_font_t *font_body(void) { return UI_RES_CLASS_COMPACT ? &lv_font_montserrat_14 : &lv_font_montserrat_20; }
static const lv_font_t *font_value(void) { return UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_36 : (UI_RES_CLASS_MEDIUM ? &lv_font_montserrat_28 : &lv_font_montserrat_14); }

static void label_style(lv_obj_t *obj, uint32_t color, const lv_font_t *font)
{
    lv_obj_set_style_text_color(obj, C(color), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(obj, font, LV_PART_MAIN | LV_STATE_DEFAULT);
}

static lv_obj_t *make_card(lv_obj_t *parent, int x, int y, int w, int h)
{
    lv_obj_t *card = lv_obj_create(parent);
    lv_obj_set_size(card, w, h);
    lv_obj_set_pos(card, x, y);
    lv_obj_set_style_bg_color(card, C(UI_COLOR_SURFACE), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(card, LV_OPA_90, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(card, C(UI_COLOR_BORDER), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(card, UI_RES_CLASS_WIDESCREEN ? 2 : 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(card, UI_CARD_RADIUS, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_pad_all(card, UI_CARD_PADDING, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);
    return card;
}

static void card_text(lv_obj_t *card, const char *title, const char *value,
                      const char *sub, uint32_t value_color,
                      lv_obj_t **value_out)
{
    lv_obj_t *lbl = lv_label_create(card);
    lv_label_set_text(lbl, title);
    label_style(lbl, UI_COLOR_TEXT_MUTED, font_small());
    lv_obj_align(lbl, LV_ALIGN_TOP_LEFT, 0, 0);

    lbl = lv_label_create(card);
    lv_label_set_text(lbl, value);
    label_style(lbl, value_color, font_value());
    lv_obj_align(lbl, LV_ALIGN_CENTER, 0, UI_RES_CLASS_COMPACT ? 0 : 3);
    if (value_out) *value_out = lbl;

    lbl = lv_label_create(card);
    lv_label_set_text(lbl, sub);
    label_style(lbl, UI_COLOR_TEXT_MUTED, font_small());
    lv_obj_align(lbl, LV_ALIGN_BOTTOM_LEFT, 0, 0);
}

static void on_sync(lv_event_t *e)
{
    (void)e;
    ui_events_on_sync_start();
}

static void on_settings(lv_event_t *e)
{
    (void)e;
    ui_events_on_open_settings();
}

static void on_start(lv_event_t *e)
{
    (void)e;
    ui_events_on_start_log();
}

static lv_obj_t *make_button(lv_obj_t *parent, int x, int y, int w, int h,
                             const char *text, uint32_t color, lv_event_cb_t cb)
{
    lv_obj_t *btn = lv_btn_create(parent);
    lv_obj_set_size(btn, w, h);
    lv_obj_set_pos(btn, x, y);
    lv_obj_set_style_bg_color(btn, C(color), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(btn, C(color), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(btn, UI_RES_CLASS_WIDESCREEN ? 2 : 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn, UI_BTN_RADIUS, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn, cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *label = lv_label_create(btn);
    lv_label_set_text(label, text);
    label_style(label, UI_COLOR_TEXT_PRIMARY, font_body());
    lv_obj_align(label, LV_ALIGN_CENTER, 0, 0);
    return btn;
}

void ui_show_boot_splash(void)
{
    ui_lock(-1);
    s_home_active = false;
    /* Reuse the active root for Home <-> Logging.  Root-screen swaps on the
     * software-rotated MIPI display expose a blue intermediate frame. */
    lv_obj_t *scr = lv_scr_act();
    lv_obj_clean(scr);
    lv_obj_set_style_bg_color(scr, C(UI_COLOR_BG_DARK), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    lv_obj_t *logo = lv_label_create(scr);
    lv_label_set_text(logo, "RaceSense");
    label_style(logo, UI_COLOR_TEXT_PRIMARY,
                UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_48 : &lv_font_montserrat_28);
    lv_obj_align(logo, LV_ALIGN_CENTER, 0, -UI_SCALE_Y(38));

    lv_obj_t *bar = lv_bar_create(scr);
    lv_obj_set_size(bar, UI_PCT_X(60), UI_SCALE_Y(10));
    lv_bar_set_range(bar, 0, 100);
    lv_bar_set_value(bar, 75, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar, C(UI_COLOR_BORDER), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_color(bar, C(UI_COLOR_SUCCESS), LV_PART_INDICATOR | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(bar, LV_RADIUS_CIRCLE, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(bar, LV_RADIUS_CIRCLE, LV_PART_INDICATOR | LV_STATE_DEFAULT);
    lv_obj_align(bar, LV_ALIGN_CENTER, 0, UI_SCALE_Y(12));

    lv_obj_t *detail = lv_label_create(scr);
    lv_label_set_text(detail, "Initializing SDIO...  Calibrating IMU...");
    label_style(detail, UI_COLOR_TEXT_MUTED, font_body());
    lv_obj_align(detail, LV_ALIGN_CENTER, 0, UI_SCALE_Y(38));

    ui_load_screen(scr);
    ui_unlock();
}

void ui_show_home(bool sd_ok, bool imu_ok, bool gps_ok, int sats,
                  const char *track_name, const char *mount_label, int storage_pct)
{
    ui_lock(-1);
    const int m = ui_margin();
    const int header_h = UI_HEADER_HEIGHT;
    const int dock_h = UI_FOOTER_HEIGHT;
    const int content_y = header_h + m;
    const int content_h = UI_VER_RES - content_y - dock_h - m;
    const int gap = UI_CARD_GAP;
    const int card_w = (UI_HOR_RES - (3 * m)) / 2;
    const int card_h = (content_h - gap) / 2;
    const char *state = (!sd_ok) ? "SD ERROR" : (!imu_ok) ? "IMU ERROR" : (!gps_ok || sats < 4) ? "GPS WAIT" : "READY";
    const uint32_t state_color = (!sd_ok || !imu_ok) ? UI_COLOR_DANGER : (!gps_ok || sats < 4) ? UI_COLOR_WARNING : UI_COLOR_SUCCESS;

    /* Reuse the active root for Home <-> Logging.  Root-screen swaps on the
     * software-rotated MIPI display expose a blue intermediate frame. */
    lv_obj_t *scr = lv_scr_act();
    lv_obj_clean(scr);
    lv_obj_set_style_bg_color(scr, C(UI_COLOR_BG_DARK), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, UI_HOR_RES, header_h);
    lv_obj_set_pos(header, 0, 0);
    lv_obj_set_style_bg_color(header, C(UI_COLOR_SURFACE), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_side(header, LV_BORDER_SIDE_BOTTOM, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(header, C(UI_COLOR_BORDER), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(header, UI_RES_CLASS_WIDESCREEN ? 2 : 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(header, 0, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

    s_lbl_bat = lv_label_create(header);
    lv_label_set_text(s_lbl_bat, "BATTERY 88%");
    label_style(s_lbl_bat, UI_COLOR_SUCCESS, font_small());
    lv_obj_align(s_lbl_bat, LV_ALIGN_LEFT_MID, m, 0);
    lv_obj_t *title = lv_label_create(header);
    lv_label_set_text(title, "RACESENSE DASHBOARD");
    label_style(title, UI_COLOR_TEXT_PRIMARY, font_body());
    lv_obj_align(title, LV_ALIGN_CENTER, 0, 0);
    s_lbl_gps = lv_label_create(header);
    char satellites[24]; snprintf(satellites, sizeof(satellites), "%d SATS LOCK", sats);
    lv_label_set_text(s_lbl_gps, satellites);
    label_style(s_lbl_gps, gps_ok ? UI_COLOR_SUCCESS : UI_COLOR_WARNING, font_small());
    lv_obj_align(s_lbl_gps, LV_ALIGN_RIGHT_MID, -m, 0);

    lv_obj_t *card = make_card(scr, m, content_y, card_w, card_h);
    card_text(card, "SYSTEM STATUS", state, sd_ok && imu_ok ? "SD mounted  |  100Hz IMU online" : "Check hardware before riding", state_color, &s_lbl_status);
    card = make_card(scr, 2 * m + card_w, content_y, card_w, card_h);
    char track[48]; snprintf(track, sizeof(track), "%s", track_name ? track_name : "NO TRACK");
    card_text(card, "ACTIVE CIRCUIT", track, "TBL Best: 1:54.320", UI_COLOR_TEXT_PRIMARY, &s_lbl_track);
    card = make_card(scr, m, content_y + card_h + gap, card_w, card_h);
    card_text(card, "IMU PROFILE", mount_label ? mount_label : "TANK MOUNT", "Pitch -10.7 / Roll +5.0", UI_COLOR_TEXT_PRIMARY, NULL);
    card = make_card(scr, 2 * m + card_w, content_y + card_h + gap, card_w, card_h);
    char storage_text[32];
    storage_free_text(storage_text, sizeof(storage_text), sd_ok);
    card_text(card, "SD STORAGE", storage_text, "High-speed card", UI_COLOR_TEXT_PRIMARY, &s_lbl_store);
    s_storage_bar = lv_bar_create(card);
    lv_obj_set_size(s_storage_bar, card_w - 2 * UI_CARD_PADDING, UI_RES_CLASS_COMPACT ? 4 : 7);
    lv_bar_set_range(s_storage_bar, 0, 100);
    lv_bar_set_value(s_storage_bar, storage_pct, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(s_storage_bar, C(UI_COLOR_BORDER), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_color(s_storage_bar, C(UI_COLOR_PAIRING), LV_PART_INDICATOR | LV_STATE_DEFAULT);
    lv_obj_align(s_storage_bar, LV_ALIGN_BOTTOM_MID, 0, -UI_SCALE_Y(18));

    const int dock_y = UI_VER_RES - dock_h;
    const int button_gap = UI_RES_CLASS_COMPACT ? 5 : gap;
    const int settings_w = UI_RES_CLASS_WIDESCREEN ? UI_SCALE_X(84) : UI_SCALE_X(70);
    const int primary_w = (UI_HOR_RES - 2 * m - settings_w - 2 * button_gap) / 2;
    make_button(scr, m, dock_y + UI_SCALE_Y(8), primary_w, dock_h - UI_SCALE_Y(16), "SYNC CLOUD", UI_COLOR_PAIRING, on_sync);
    make_button(scr, m + primary_w + button_gap, dock_y + UI_SCALE_Y(8), settings_w, dock_h - UI_SCALE_Y(16), "SET", 0x3A3A45, on_settings);
    make_button(scr, m + primary_w + button_gap + settings_w + button_gap, dock_y + UI_SCALE_Y(8), primary_w, dock_h - UI_SCALE_Y(16), "START LOG", UI_COLOR_PRIMARY, on_start);

    s_home_active = true;
    lv_obj_invalidate(scr);
    ESP_LOGI(TAG, "Simulator-faithful home rendered at %dx%d", UI_HOR_RES, UI_VER_RES);
    ui_unlock();
}

void ui_home_deactivate(void)
{
    /* Screen constructors delete the prior active screen.  Never allow the
     * background Home updater to retain and write its old object pointers. */
    s_home_active = false;
}

void ui_home_update(bool sd_ok, bool imu_ok, bool gps_ok, int sats, int bat_pct,
                    int storage_pct, const char *track_name)
{
    if (!s_home_active || !ui_lock(20)) return;
    char buf[64];
    snprintf(buf, sizeof(buf), "BATTERY %d%%", bat_pct);
    lv_label_set_text(s_lbl_bat, buf);
    label_style(s_lbl_bat, bat_pct > 20 ? UI_COLOR_SUCCESS : UI_COLOR_DANGER, font_small());
    snprintf(buf, sizeof(buf), "%d SATS %s", sats, gps_ok ? "LOCK" : "SEARCH");
    lv_label_set_text(s_lbl_gps, buf);
    label_style(s_lbl_gps, gps_ok ? UI_COLOR_SUCCESS : UI_COLOR_WARNING, font_small());
    const char *state = (!sd_ok) ? "SD ERROR" : (!imu_ok) ? "IMU ERROR" : (!gps_ok || sats < 4) ? "GPS WAIT" : "READY";
    const uint32_t color = (!sd_ok || !imu_ok) ? UI_COLOR_DANGER : (!gps_ok || sats < 4) ? UI_COLOR_WARNING : UI_COLOR_SUCCESS;
    lv_label_set_text(s_lbl_status, state);
    label_style(s_lbl_status, color, font_value());
    lv_label_set_text(s_lbl_track, track_name ? track_name : "NO TRACK");
    storage_free_text(buf, sizeof(buf), sd_ok);
    lv_label_set_text(s_lbl_store, buf);
    lv_bar_set_value(s_storage_bar, storage_pct, LV_ANIM_OFF);
    ui_unlock();
}
