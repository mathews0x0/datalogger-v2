/**
 * @file ui_sync.c
 * @brief Wave 4 Implementation: Cloud Sync Suite (Screens 6, 7, 8, 9) and
 *        Captive Portal WiFi Provisioning (Screen 12)
 *
 * Provides responsive user interfaces for wireless network discovery, secure MbedTLS
 * chunked telemetry uploads, summary reporting, and smartphone SoftAP QR pairing.
 */

#include "ui.h"
#include "ui_events.h"
#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "ui_sync";
static lv_obj_t *s_upload_bar;
static lv_obj_t *s_upload_title;
static lv_obj_t *s_upload_file;
static bool s_upload_active;

static void _make_title(lv_obj_t *scr, const char *left, const char *right, uint32_t color)
{
    lv_obj_t *h = lv_obj_create(scr);
    lv_obj_set_size(h, UI_HOR_RES, UI_HEADER_HEIGHT);
    lv_obj_set_pos(h, 0, 0);
    lv_obj_set_style_bg_color(h, lv_color_hex(UI_COLOR_SURFACE), 0);
    lv_obj_set_style_radius(h, 0, 0);
    lv_obj_clear_flag(h, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *a = lv_label_create(h); lv_label_set_text(a, left);
    lv_obj_set_style_text_color(a, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0); lv_obj_align(a, LV_ALIGN_LEFT_MID, 8, 0);
    lv_obj_t *b = lv_label_create(h); lv_label_set_text(b, right);
    lv_obj_set_style_text_color(b, lv_color_hex(color), 0); lv_obj_align(b, LV_ALIGN_RIGHT_MID, -8, 0);
}

/* ──────────────────────────────────────────────────────────────────────────
 * Internal Touch Callback Bridges
 * ────────────────────────────────────────────────────────────────────────*/

static void _on_btn_sync_cancel_cb(lv_event_t *e)
{
    ESP_LOGI(TAG, "[Cloud Sync] CANCEL / EXIT button pressed");
    ui_events_on_cancel_sync();
}

static void _on_btn_sync_complete_exit_cb(lv_event_t *e)
{
    ESP_LOGI(TAG, "[Cloud Sync Complete] RETURN TO HOME button pressed");
    ui_events_on_navigate_home();
}

static void _on_btn_portal_exit_cb(lv_event_t *e)
{
    ESP_LOGI(TAG, "[Captive Portal] EXIT PORTAL button pressed -> Disabling SoftAP");
    ui_events_on_close_captive_portal();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 6: WiFi Searching & Scanning
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_sync_searching(const char *target_ssid)
{
    ui_home_deactivate();
    ui_lock(-1);
    ESP_LOGI(TAG, "Constructing Screen 6: WiFi Searching & Scanning [%dx%d]", UI_HOR_RES, UI_VER_RES);

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
    lv_label_set_text(lbl_title, "● CLOUD SYNC ACTIVE");
    lv_obj_set_style_text_color(lbl_title, lv_color_hex(0x007AFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_title, LV_ALIGN_CENTER, 0, 0);

    /* Center Status Card (304x120 px) */
    lv_obj_t *card = lv_obj_create(scr);
    const int card_w = UI_RES_CLASS_WIDESCREEN ? 640 : UI_HOR_RES - 16;
    const int card_h = UI_RES_CLASS_WIDESCREEN ? 220 : 120;
    lv_obj_set_size(card, card_w, card_h);
    lv_obj_set_pos(card, (UI_HOR_RES - card_w) / 2, UI_HEADER_HEIGHT + 28);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x1A1A22), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(card, lv_color_hex(0x2A2A35), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(card, 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(card, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    char buf[64];
    snprintf(buf, sizeof(buf), "CLOUD SYNC READY\n'%s'", target_ssid ? target_ssid : "RaceSense_AP");
    lv_obj_t *lbl_info = lv_label_create(card);
    lv_label_set_text(lbl_info, buf);
    lv_obj_set_style_text_align(lbl_info, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(lbl_info, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_info, LV_ALIGN_CENTER, 0, -10);

    lv_obj_t *lbl_sub = lv_label_create(card);
    lv_label_set_text(lbl_sub, "Wi-Fi 6 transport is not enabled in this P4 build.");
    lv_obj_set_style_text_color(lbl_sub, lv_color_hex(0x8E8E93), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_sub, LV_ALIGN_BOTTOM_MID, 0, -4);

    /* Bottom Cancel / Return Button (304x66 px, Y=166) */
    lv_obj_t *btn_cancel = lv_btn_create(scr);
    lv_obj_set_size(btn_cancel, card_w, UI_RES_CLASS_WIDESCREEN ? 90 : 66);
    lv_obj_set_pos(btn_cancel, (UI_HOR_RES - card_w) / 2,
                   UI_RES_CLASS_WIDESCREEN ? UI_VER_RES - 28 - 90 : 166);
    lv_obj_set_style_bg_color(btn_cancel, lv_color_hex(0xFF3B30), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_cancel, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_cancel, _on_btn_sync_cancel_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn = lv_label_create(btn_cancel);
    lv_label_set_text(lbl_btn, "RETURN TO DASHBOARD");
    lv_obj_set_style_text_color(lbl_btn, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn, LV_ALIGN_CENTER, 0, 0);

    ui_load_screen(scr);
    ui_unlock();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 7: Server Heartbeat & TLS Authentication Handshake
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_sync_heartbeat(void)
{
    ui_home_deactivate();
    ui_lock(-1);
    s_upload_active = false;
    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(UI_COLOR_BG_DARK), 0);
    _make_title(scr, "SYNC MODE", "PROBING SERVER", UI_COLOR_WARNING);
    lv_obj_t *spinner = lv_spinner_create(scr, 1000, 60);
    lv_obj_set_size(spinner, 58, 58); lv_obj_align(spinner, LV_ALIGN_CENTER, 0, -34);
    lv_obj_set_style_arc_color(spinner, lv_color_hex(UI_COLOR_DANGER), LV_PART_INDICATOR);
    lv_obj_t *title = lv_label_create(scr); lv_label_set_text(title, "VERIFYING SERVER HEARTBEAT");
    lv_obj_set_style_text_color(title, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0); lv_obj_align(title, LV_ALIGN_CENTER, 0, 20);
    lv_obj_t *sub = lv_label_create(scr); lv_label_set_text(sub, "TLS heartbeat to racesense.in...");
    lv_obj_set_style_text_color(sub, lv_color_hex(UI_COLOR_TEXT_MUTED), 0); lv_obj_align(sub, LV_ALIGN_CENTER, 0, 43);
    ui_load_screen(scr);
    ui_unlock();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 8: Chunked Batch Telemetry Uploader Progress
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_sync_uploading(int file_idx, int total_files, const char *filename,
                            int progress_pct, const char *speed, const char *eta)
{
    ui_home_deactivate();
    if (ui_lock(20)) {
        if (!s_upload_active) {
            lv_obj_t *scr = lv_obj_create(NULL);
            lv_obj_set_style_bg_color(scr, lv_color_hex(UI_COLOR_BG_DARK), 0);
            _make_title(scr, "SYNC MODE", "CLOUD ONLINE", UI_COLOR_SUCCESS);
            s_upload_title = lv_label_create(scr);
            lv_obj_set_style_text_color(s_upload_title, lv_color_hex(UI_COLOR_SUCCESS), 0);
            lv_obj_align(s_upload_title, LV_ALIGN_CENTER, 0, -48);
            s_upload_file = lv_label_create(scr);
            lv_obj_set_style_text_color(s_upload_file, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
            lv_obj_align(s_upload_file, LV_ALIGN_CENTER, 0, -20);
            s_upload_bar = lv_bar_create(scr); lv_obj_set_size(s_upload_bar, UI_PCT_X(80), 14);
            lv_obj_align(s_upload_bar, LV_ALIGN_CENTER, 0, 12);
            lv_obj_set_style_bg_color(s_upload_bar, lv_color_hex(UI_COLOR_BORDER), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_upload_bar, lv_color_hex(UI_COLOR_PRIMARY), LV_PART_INDICATOR);
            lv_obj_t *cancel = lv_btn_create(scr); lv_obj_set_size(cancel, UI_PCT_X(80), UI_SCALE_Y(44)); lv_obj_align(cancel, LV_ALIGN_BOTTOM_MID, 0, -8);
            lv_obj_add_event_cb(cancel, _on_btn_sync_cancel_cb, LV_EVENT_CLICKED, NULL);
            lv_obj_t *cl = lv_label_create(cancel); lv_label_set_text(cl, "CANCEL & EXIT"); lv_obj_align(cl, LV_ALIGN_CENTER, 0, 0);
            ui_load_screen(scr); s_upload_active = true;
        }
        char buf[80]; snprintf(buf, sizeof(buf), "UPLOADING FILE %d OF %d", file_idx, total_files);
        lv_label_set_text(s_upload_title, buf); lv_label_set_text(s_upload_file, filename ? filename : "session.csv");
        lv_bar_set_value(s_upload_bar, progress_pct, LV_ANIM_ON);
        ui_unlock();
    }
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 9: Sync Complete & Summary Report
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_sync_complete(int files_synced, float mb_total, int seconds)
{
    ui_home_deactivate();
    ui_lock(-1);
    ESP_LOGI(TAG, "Constructing Screen 9: Sync Complete Summary Report [%dx%d]", UI_HOR_RES, UI_VER_RES);

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x09090D), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    lv_obj_t *card = lv_obj_create(scr);
    const int card_w = UI_RES_CLASS_WIDESCREEN ? 640 : UI_HOR_RES - 16;
    const int card_h = UI_RES_CLASS_WIDESCREEN ? 220 : 120;
    lv_obj_set_size(card, card_w, card_h);
    lv_obj_set_pos(card, (UI_HOR_RES - card_w) / 2, UI_RES_CLASS_WIDESCREEN ? 80 : 36);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x1A1A22), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(card, lv_color_hex(0x00D26A), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(card, 2, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(card, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    char summary_buf[128];
    snprintf(summary_buf, sizeof(summary_buf), "✓ SYNC SUCCESSFUL!\n\nFiles Synced: %d\nTransferred: %.1f MB (%ds)",
             files_synced, mb_total, seconds);
    lv_obj_t *lbl_sum = lv_label_create(card);
    lv_label_set_text(lbl_sum, summary_buf);
    lv_obj_set_style_text_align(lbl_sum, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(lbl_sum, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_sum, LV_ALIGN_CENTER, 0, 0);

    lv_obj_t *btn_exit = lv_btn_create(scr);
    lv_obj_set_size(btn_exit, card_w, UI_RES_CLASS_WIDESCREEN ? 90 : 66);
    lv_obj_set_pos(btn_exit, (UI_HOR_RES - card_w) / 2,
                   UI_RES_CLASS_WIDESCREEN ? UI_VER_RES - 28 - 90 : 166);
    lv_obj_set_style_bg_color(btn_exit, lv_color_hex(0x00D26A), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_exit, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_exit, _on_btn_sync_complete_exit_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn = lv_label_create(btn_exit);
    lv_label_set_text(lbl_btn, "FINISHED (RETURN HOME)");
    lv_obj_set_style_text_color(lbl_btn, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn, LV_ALIGN_CENTER, 0, 0);

    ui_load_screen(scr);
    ui_unlock();
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 12: Captive Portal WiFi Provisioning
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_captive_portal(const char *ap_name)
{
    ui_home_deactivate();
    ui_lock(-1);
    ESP_LOGI(TAG, "Constructing Screen 12: Captive Portal Provisioning [%dx%d]", UI_HOR_RES, UI_VER_RES);

    const char *ssid = ap_name ? ap_name : "RaceSense_Setup";

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x09090D), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, LV_PART_MAIN | LV_STATE_DEFAULT);

    lv_obj_t *card = lv_obj_create(scr);
    const int card_w = UI_RES_CLASS_WIDESCREEN ? 640 : UI_HOR_RES - 16;
    const int card_h = UI_RES_CLASS_WIDESCREEN ? 220 : 120;
    lv_obj_set_size(card, card_w, card_h);
    lv_obj_set_pos(card, (UI_HOR_RES - card_w) / 2, UI_RES_CLASS_WIDESCREEN ? 80 : 36);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x1A1A22), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_color(card, lv_color_hex(0x00E5FF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_border_width(card, 1, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(card, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    char portal_buf[256];
#if CONFIG_IDF_TARGET_ESP32P4 && !CONFIG_ESP_WIFI_REMOTE_ENABLED
    snprintf(portal_buf, sizeof(portal_buf),
             "WIFI SETUP READY\n\nSSID: %s\nGateway IP: 192.168.4.1\n\nC6 Wi-Fi transport is disabled in this build",
             ssid);
#else
    snprintf(portal_buf, sizeof(portal_buf),
             "WIFI SETUP PORTAL\n\nSSID: %s\nGateway IP: 192.168.4.1\n\nJoin the AP, then open the setup link",
             ssid);
#endif
    lv_obj_t *lbl_portal = lv_label_create(card);
    lv_label_set_text(lbl_portal, portal_buf);
    lv_obj_set_style_text_align(lbl_portal, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_text_color(lbl_portal, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_portal, LV_ALIGN_CENTER, 0, 0);

    lv_obj_t *btn_exit = lv_btn_create(scr);
    lv_obj_set_size(btn_exit, card_w, UI_RES_CLASS_WIDESCREEN ? 90 : 66);
    lv_obj_set_pos(btn_exit, (UI_HOR_RES - card_w) / 2,
                   UI_RES_CLASS_WIDESCREEN ? UI_VER_RES - 28 - 90 : 166);
    lv_obj_set_style_bg_color(btn_exit, lv_color_hex(0x3A3A45), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_radius(btn_exit, 8, LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_add_event_cb(btn_exit, _on_btn_portal_exit_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *lbl_btn = lv_label_create(btn_exit);
    lv_label_set_text(lbl_btn, "EXIT PORTAL & RETURN");
    lv_obj_set_style_text_color(lbl_btn, lv_color_hex(0xFFFFFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_align(lbl_btn, LV_ALIGN_CENTER, 0, 0);

    ui_load_screen(scr);
    ui_unlock();
}
