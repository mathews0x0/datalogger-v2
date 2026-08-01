/**
 * @file ui_home.c
 * @brief Wave 1 Implementation: Boot Splash (Screen 1) & Adaptive Home Dashboard (Screen 2)
 *
 * Provides responsive multi-resolution layouts and connects touch buttons
 * directly to the resolution-agnostic ui_events dispatcher layer.
 */

#include "ui.h"
#include "lvgl.h"
#include <stdio.h>
#include <string.h>
#include "esp_log.h"

static const char *TAG = "ui_home";

/* ──────────────────────────────────────────────────────────────────────────
 * Internal Static Widget References for Zero-Flicker Live Telemetry Updates
 * ────────────────────────────────────────────────────────────────────────*/
static volatile bool s_home_active = false;
static lv_obj_t     *s_lbl_bat     = NULL;
static lv_obj_t     *s_lbl_gps     = NULL;
static lv_obj_t     *s_lbl_status  = NULL;
static lv_obj_t     *s_lbl_track   = NULL;
static lv_obj_t     *s_lbl_store   = NULL;

/* ──────────────────────────────────────────────────────────────────────────
 * Internal Touch Callback Bridges (Invoked upon widget click events)
 * ────────────────────────────────────────────────────────────────────────*/

/* ──────────────────────────────────────────────────────────────────────────
 * Internal Touch Callback Bridges (Invoked upon widget click events)
 * ────────────────────────────────────────────────────────────────────────*/

static void _on_btn_sync_clicked_cb(lv_event_t * e)
{
    ESP_LOGI(TAG, "[Home Dashboard] SYNC touch target pressed");
    lv_obj_t *lbl_status = (lv_obj_t *)lv_event_get_user_data(e);
    if (lbl_status) {
        lv_label_set_text(lbl_status, "STATUS: SEARCHING WIFI...");
        lv_obj_set_style_text_color(lbl_status, lv_color_hex(0x007AFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    }
    ui_events_on_sync_start();
}

static void _on_btn_settings_clicked_cb(lv_event_t * e)
{
    ESP_LOGI(TAG, "[Home Dashboard] SETTINGS touch target pressed");
    lv_obj_t *lbl_status = (lv_obj_t *)lv_event_get_user_data(e);
    if (lbl_status) {
        lv_label_set_text(lbl_status, "STATUS: SETTINGS MENU OPEN");
        lv_obj_set_style_text_color(lbl_status, lv_color_hex(0xFFB800), LV_PART_MAIN | LV_STATE_DEFAULT);
    }
    ui_events_on_open_settings();
}

static void _on_btn_start_log_clicked_cb(lv_event_t * e)
{
    ESP_LOGI(TAG, "[Home Dashboard] START LOG touch target pressed");
    lv_obj_t *lbl_status = (lv_obj_t *)lv_event_get_user_data(e);
    if (lbl_status) {
        lv_label_set_text(lbl_status, "STATUS: LOGGING ACTIVE (100Hz)");
        lv_obj_set_style_text_color(lbl_status, lv_color_hex(0xFF3B30), LV_PART_MAIN | LV_STATE_DEFAULT);
    }
    ui_events_on_start_log();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 1: Boot Splash Loading Screen
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_boot_splash(void)
{
    ui_lock(-1);
    s_home_active = false;
    ESP_LOGI(TAG, "Constructing Screen 1: Boot Splash [%dx%d]", UI_HOR_RES, UI_VER_RES);

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x09090D), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    lv_obj_t *lbl_title = lv_label_create(scr);
    lv_label_set_text(lbl_title, "RACESENSE");
    lv_obj_set_style_text_color(lbl_title, lv_color_hex(0xFF6B35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_title, LV_ALIGN_CENTER, 0, -10);

    lv_obj_t *lbl_sub = lv_label_create(scr);
    lv_label_set_text(lbl_sub, "INITIALIZING CORE V4.2...");
    lv_obj_set_style_text_color(lbl_sub, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_sub, LV_ALIGN_CENTER, 0, 20);

    lv_scr_load(scr);

    ESP_LOGI(TAG, "Screen 1 rendered: RaceSense wordmark centered, background set to #09090D");
    ui_unlock();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 2: Home Dashboard Landing Page (Responsive Interactive Dashboard)
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_home(bool sd_ok, bool imu_ok, bool gps_ok, int sats,
                  const char *track_name, const char *mount_label, int storage_pct)
{
    ui_lock(-1);
    ESP_LOGI(TAG, "Constructing Screen 2: Interactive Home Dashboard [%dx%d]", UI_HOR_RES, UI_VER_RES);

    const char *status_text = "STATUS: SYSTEM READY";
    uint32_t    status_color = 0x00D26A;

    if (!sd_ok) {
        status_text  = "STATUS: ERROR (NO SD CARD)";
        status_color = 0xFF3B30;
    } else if (!imu_ok) {
        status_text  = "STATUS: ERROR (IMU FAULT)";
        status_color = 0xFF3B30;
    } else if (!gps_ok || sats < 4) {
        status_text  = "STATUS: ACQUIRING GPS LOCK...";
        status_color = 0xFFB800;
    }

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x09090D), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    /* 1. Top Header Bar (320x28 px) */
    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, 320, 28);
    lv_obj_set_pos(header, 0, 0);
    lv_obj_set_style_bg_color(header, lv_color_hex(0x1A1A22), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_side(header, LV_BORDER_SIDE_BOTTOM, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(header, lv_color_hex(0x2A2A35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(header, 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(header, 0, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *lbl_bat = lv_label_create(header);
    lv_label_set_text(lbl_bat, "BAT: 88%");
    lv_obj_set_style_text_color(lbl_bat, lv_color_hex(0x00D26A), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_bat, LV_ALIGN_LEFT_MID, 0, 0);

    lv_obj_t *lbl_title = lv_label_create(header);
    lv_label_set_text(lbl_title, "RACESENSE V4.2");
    lv_obj_set_style_text_color(lbl_title, lv_color_hex(0xFF6B35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_title, LV_ALIGN_CENTER, 0, 0);

    char sat_buf[32];
    snprintf(sat_buf, sizeof(sat_buf), "GPS: %d SAT", sats);
    lv_obj_t *lbl_gps = lv_label_create(header);
    lv_label_set_text(lbl_gps, sat_buf);
    lv_obj_set_style_text_color(lbl_gps, lv_color_hex(0x00E5FF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_gps, LV_ALIGN_RIGHT_MID, 0, 0);

    /* 2. Middle Telemetry & Status Card (304x118 px) */
    lv_obj_t *card = lv_obj_create(scr);
    lv_obj_set_size(card, 304, 118);
    lv_obj_set_pos(card, 8, 34);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x1A1A22), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(card, lv_color_hex(0x2A2A35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(card, 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(card, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *lbl_status = lv_label_create(card);
    lv_label_set_text(lbl_status, status_text);
    lv_obj_set_style_text_color(lbl_status, lv_color_hex(status_color), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_status, LV_ALIGN_TOP_MID, 0, 4);

    char track_buf[64];
    snprintf(track_buf, sizeof(track_buf), "TRACK: %s\nBEST TBL: 1:54.320", track_name ? track_name : "SILVERSTONE");
    lv_obj_t *lbl_track = lv_label_create(card);
    lv_label_set_text(lbl_track, track_buf);
    lv_obj_set_style_text_color(lbl_track, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_text_align(lbl_track, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_track, LV_ALIGN_CENTER, 0, 2);

    char store_buf[64];
    snprintf(store_buf, sizeof(store_buf), "STORAGE: %s (%d%% USED)", sd_ok ? "SD MOUNTED" : "NO SD", storage_pct);
    lv_obj_t *lbl_store = lv_label_create(card);
    lv_label_set_text(lbl_store, store_buf);
    lv_obj_set_style_text_color(lbl_store, lv_color_hex(0x8E8E93), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_store, LV_ALIGN_BOTTOM_MID, 0, -2);

    /* 3. Bottom Interactive Touch Dock (3 Buttons across 320 px) */
    
    /* Button 1: START LOG (Width 130, X=8, Y=160, Height 70) */
    lv_obj_t *btn_start = lv_btn_create(scr);
    lv_obj_set_size(btn_start, 130, 70);
    lv_obj_set_pos(btn_start, 8, 160);
    lv_obj_set_style_bg_color(btn_start, lv_color_hex(0xFF6B35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_start, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_start, _on_btn_start_log_clicked_cb, LV_EVENT_CLICKED, lbl_status);

    lv_obj_t *lbl_btn_start = lv_label_create(btn_start);
    lv_label_set_text(lbl_btn_start, "START LOG");
    lv_obj_set_style_text_color(lbl_btn_start, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_start, LV_ALIGN_CENTER, 0, 0);

    /* Button 2: SYNC (Width 78, X=146, Y=160, Height 70) */
    lv_obj_t *btn_sync = lv_btn_create(scr);
    lv_obj_set_size(btn_sync, 78, 70);
    lv_obj_set_pos(btn_sync, 146, 160);
    lv_obj_set_style_bg_color(btn_sync, lv_color_hex(0x007AFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_sync, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_sync, _on_btn_sync_clicked_cb, LV_EVENT_CLICKED, lbl_status);

    lv_obj_t *lbl_btn_sync = lv_label_create(btn_sync);
    lv_label_set_text(lbl_btn_sync, "SYNC");
    lv_obj_set_style_text_color(lbl_btn_sync, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_sync, LV_ALIGN_CENTER, 0, 0);

    /* Button 3: SETUP (Width 80, X=232, Y=160, Height 70) */
    lv_obj_t *btn_setup = lv_btn_create(scr);
    lv_obj_set_size(btn_setup, 80, 70);
    lv_obj_set_pos(btn_setup, 232, 160);
    lv_obj_set_style_bg_color(btn_setup, lv_color_hex(0x3A3A45), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_setup, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_setup, _on_btn_settings_clicked_cb, LV_EVENT_CLICKED, lbl_status);

    lv_obj_t *lbl_btn_setup = lv_label_create(btn_setup);
    lv_label_set_text(lbl_btn_setup, "SETUP");
    lv_obj_set_style_text_color(lbl_btn_setup, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn_setup, LV_ALIGN_CENTER, 0, 0);

    /* Save widget references for zero-flicker live telemetry updates */
    s_lbl_bat     = lbl_bat;
    s_lbl_gps     = lbl_gps;
    s_lbl_status  = lbl_status;
    s_lbl_track   = lbl_track;
    s_lbl_store   = lbl_store;
    s_home_active = true;

    lv_scr_load(scr);

    ui_unlock();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Live Dashboard Telemetry Update API (Resolution & Hardware Agnostic)
 * ────────────────────────────────────────────────────────────────────────*/
void ui_home_update(bool sd_ok, bool imu_ok, bool gps_ok, int sats, int bat_pct,
                    int storage_pct, const char *track_name)
{
    if (!s_home_active) {
        return;
    }

    if (ui_lock(20)) {
        if (!s_lbl_status || !s_lbl_bat || !s_lbl_gps || !s_lbl_track || !s_lbl_store) {
            ui_unlock();
            return;
        }

        /* 1. Update Battery Display & Color Indicator */
        char bat_buf[32];
        snprintf(bat_buf, sizeof(bat_buf), "BAT: %d%%", bat_pct);
        lv_label_set_text(s_lbl_bat, bat_buf);
        uint32_t bat_color = (bat_pct > 20) ? 0x00D26A : 0xFF3B30;
        lv_obj_set_style_text_color(s_lbl_bat, lv_color_hex(bat_color), LV_PART_MAIN | LV_STATE_DEFAULT);

        /* 2. Update GPS Satellite Count */
        char sat_buf[32];
        snprintf(sat_buf, sizeof(sat_buf), "GPS: %d SAT", sats);
        lv_label_set_text(s_lbl_gps, sat_buf);
        uint32_t gps_color = gps_ok ? 0x00D26A : 0x00E5FF;
        lv_obj_set_style_text_color(s_lbl_gps, lv_color_hex(gps_color), LV_PART_MAIN | LV_STATE_DEFAULT);

        /* 3. Update System Health Status */
        const char *status_text = "STATUS: SYSTEM READY";
        uint32_t    status_color = 0x00D26A;
        if (!sd_ok) {
            status_text  = "STATUS: ERROR (NO SD CARD)";
            status_color = 0xFF3B30;
        } else if (!imu_ok) {
            status_text  = "STATUS: ERROR (IMU FAULT)";
            status_color = 0xFF3B30;
        } else if (!gps_ok || sats < 4) {
            status_text  = "STATUS: ACQUIRING GPS LOCK...";
            status_color = 0xFFB800;
        }
        lv_label_set_text(s_lbl_status, status_text);
        lv_obj_set_style_text_color(s_lbl_status, lv_color_hex(status_color), LV_PART_MAIN | LV_STATE_DEFAULT);

        /* 4. Update Track Information */
        char track_buf[64];
        snprintf(track_buf, sizeof(track_buf), "TRACK: %s\nBEST TBL: 1:54.320", track_name ? track_name : "SILVERSTONE");
        lv_label_set_text(s_lbl_track, track_buf);

        /* 5. Update SD Card Storage Usage */
        char store_buf[64];
        snprintf(store_buf, sizeof(store_buf), "STORAGE: %s (%d%% USED)", sd_ok ? "SD MOUNTED" : "NO SD", storage_pct);
        lv_label_set_text(s_lbl_store, store_buf);
        uint32_t store_color = (storage_pct < 90 && sd_ok) ? 0x8E8E93 : 0xFF3B30;
        lv_obj_set_style_text_color(s_lbl_store, lv_color_hex(store_color), LV_PART_MAIN | LV_STATE_DEFAULT);

        ui_unlock();
    }
}
