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
#include <stdlib.h>
#include <string.h>
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "ui_sync";
static lv_obj_t *s_upload_bar;
static lv_obj_t *s_upload_title;
static lv_obj_t *s_upload_file;
static lv_obj_t *s_upload_remaining;
static lv_obj_t *s_upload_percent;
static lv_obj_t *s_upload_total;
static lv_obj_t *s_upload_eta;
static bool s_upload_active;
static lv_obj_t *s_heartbeat_icon;
static lv_obj_t *s_heartbeat_icon_next;
static lv_obj_t *s_heartbeat_track;
static lv_obj_t *s_heartbeat_screen;
static lv_obj_t *s_heartbeat_title;
static lv_obj_t *s_heartbeat_subtitle;
static lv_obj_t *s_heartbeat_connection;
static lv_color_t s_heartbeat_canvas_buf[560 * 120];
static int32_t s_heartbeat_offset;
static int32_t s_heartbeat_track_width;
static uint32_t s_heartbeat_color;

static void _sync_label_style(lv_obj_t *label, uint32_t color,
                              const lv_font_t *font);
static void _heartbeat_draw(lv_obj_t *canvas, uint32_t color);

static void _heartbeat_move_cb(void *var, int32_t value)
{
    (void)var;
    s_heartbeat_offset = value;
    if (!s_heartbeat_icon || !s_heartbeat_icon_next) return;
    lv_obj_set_x(s_heartbeat_icon, -value);
    lv_obj_set_x(s_heartbeat_icon_next, s_heartbeat_track_width - value);
}

static void _heartbeat_start_animation(lv_obj_t *obj)
{
    if (!obj) return;

    lv_anim_t anim;
    lv_anim_init(&anim);
    lv_anim_set_var(&anim, s_heartbeat_track);
    lv_anim_set_values(&anim, 0, s_heartbeat_track_width);
    lv_anim_set_time(&anim, 2600);
    lv_anim_set_repeat_count(&anim, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_exec_cb(&anim, _heartbeat_move_cb);
    lv_anim_start(&anim);
}

static void _heartbeat_stop_animation(void)
{
    if (s_heartbeat_track) {
        lv_anim_del(s_heartbeat_track, _heartbeat_move_cb);
    }
    s_heartbeat_icon = NULL;
    s_heartbeat_icon_next = NULL;
    s_heartbeat_track = NULL;
    s_heartbeat_title = NULL;
    s_heartbeat_subtitle = NULL;
    s_heartbeat_connection = NULL;
}

typedef struct {
    int x;
    int y;
} ecg_point_t;

static void _ecg_pixel(lv_obj_t *canvas, int x, int y, lv_color_t color,
                       int radius)
{
    const int width = lv_obj_get_width(canvas);
    const int height = lv_obj_get_height(canvas);
    for (int oy = -radius; oy <= radius; oy++) {
        for (int ox = -radius; ox <= radius; ox++) {
            const int px = x + ox;
            const int py = y + oy;
            if (px >= 0 && px < width && py >= 0 && py < height) {
                lv_canvas_set_px_color(canvas, px, py, color);
            }
        }
    }
}

static void _ecg_line(lv_obj_t *canvas, int x0, int y0, int x1, int y1,
                      lv_color_t color, int radius)
{
    const int dx = x1 - x0;
    const int dy = y1 - y0;
    const int steps = (abs(dx) > abs(dy)) ? abs(dx) : abs(dy);
    if (steps == 0) {
        _ecg_pixel(canvas, x0, y0, color, radius);
        return;
    }
    for (int step = 0; step <= steps; step++) {
        const int x = x0 + (dx * step) / steps;
        const int y = y0 + (dy * step) / steps;
        _ecg_pixel(canvas, x, y, color, radius);
    }
}

static void _heartbeat_draw(lv_obj_t *canvas, uint32_t color)
{
    if (!canvas) return;

    const int width = lv_obj_get_width(canvas);
    const int height = lv_obj_get_height(canvas);
    const lv_color_t bg = lv_color_hex(UI_COLOR_SURFACE);
    const lv_color_t grid = lv_color_hex(0x25252B);
    const lv_color_t baseline = lv_color_hex(0x3A3A42);
    const lv_color_t glow = lv_color_hex(color == UI_COLOR_SUCCESS ? 0x064A2A : 0x4A1512);
    const lv_color_t trace = lv_color_hex(color);
    lv_canvas_fill_bg(canvas, bg, LV_OPA_COVER);

    /* Dark monitor-grid background with a sampled ECG waveform. The sharp
     * QRS spike makes this read as telemetry rather than a heart icon. */
    for (int x = 0; x < width; x += 30) {
        _ecg_line(canvas, x, 0, x, height - 1, grid, 0);
    }
    for (int y = 0; y < height; y += 22) {
        _ecg_line(canvas, 0, y, width - 1, y, grid, 0);
    }
    const int baseline_y = (height * 55) / 110;
    _ecg_line(canvas, 0, baseline_y, width - 1, baseline_y, baseline, 0);

    static const ecg_point_t waveform[] = {
        {0, 55}, {16, 55}, {23, 52}, {30, 55}, {42, 55},
        {52, 55}, {58, 18}, {67, 92}, {76, 55}, {88, 55},
        {96, 55}, {103, 52}, {110, 55}, {124, 55}, {140, 55},
        {146, 18}, {155, 92}, {164, 55}, {176, 55}, {184, 52},
        {192, 55}, {207, 55}, {222, 55}, {228, 18}, {237, 92},
        {246, 55}, {258, 55}, {270, 55}, {282, 54}, {300, 55}
    };
    const int count = sizeof(waveform) / sizeof(waveform[0]);
    for (int i = 1; i < count; i++) {
        const int x0 = waveform[i - 1].x * width / 300;
        const int y0 = waveform[i - 1].y * height / 110;
        const int x1 = waveform[i].x * width / 300;
        const int y1 = waveform[i].y * height / 110;
        _ecg_line(canvas, x0, y0, x1, y1, glow, 3);
    }
    for (int i = 1; i < count; i++) {
        const int x0 = waveform[i - 1].x * width / 300;
        const int y0 = waveform[i - 1].y * height / 110;
        const int x1 = waveform[i].x * width / 300;
        const int y1 = waveform[i].y * height / 110;
        _ecg_line(canvas, x0, y0, x1, y1, trace, 1);
    }
    lv_obj_invalidate(canvas);
    if (s_heartbeat_icon_next) lv_obj_invalidate(s_heartbeat_icon_next);
}

static void _heartbeat_set_color(uint32_t color)
{
    s_heartbeat_color = color;
    _heartbeat_draw(s_heartbeat_icon, s_heartbeat_color);
}

static void _heartbeat_set_state(bool acknowledged, bool failed)
{
    if (!s_heartbeat_title || !s_heartbeat_subtitle || !s_heartbeat_connection) return;

    if (acknowledged) {
        _heartbeat_set_color(UI_COLOR_SUCCESS);
        lv_label_set_text(s_heartbeat_title, "SERVER ACKNOWLEDGED");
        lv_label_set_text(s_heartbeat_subtitle, "CLOUD ONLINE  •  HEARTBEAT OK");
        lv_label_set_text(s_heartbeat_connection, "server connection established");
        _sync_label_style(s_heartbeat_title, UI_COLOR_SUCCESS,
                          UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_20 : &lv_font_montserrat_14);
        _sync_label_style(s_heartbeat_connection, UI_COLOR_SUCCESS,
                          UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    } else if (failed) {
        _heartbeat_set_color(UI_COLOR_DANGER);
        lv_label_set_text(s_heartbeat_title, "SERVER NOT ACKNOWLEDGED");
        lv_label_set_text(s_heartbeat_subtitle, "NO VALID RESPONSE FROM RACESENSE CLOUD");
        lv_label_set_text(s_heartbeat_connection, "server connection failed");
        _sync_label_style(s_heartbeat_title, UI_COLOR_DANGER,
                          UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_20 : &lv_font_montserrat_14);
        _sync_label_style(s_heartbeat_connection, UI_COLOR_DANGER,
                          UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    } else {
        _heartbeat_set_color(UI_COLOR_DANGER);
        lv_label_set_text(s_heartbeat_title, "PINGING SERVER HEARTBEAT");
        lv_label_set_text(s_heartbeat_subtitle, "WAITING FOR AUTHENTICATED ACKNOWLEDGEMENT...");
        lv_label_set_text(s_heartbeat_connection, "checking server connection");
        _sync_label_style(s_heartbeat_title, UI_COLOR_DANGER,
                          UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_20 : &lv_font_montserrat_14);
        _sync_label_style(s_heartbeat_connection, UI_COLOR_TEXT_MUTED,
                          UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    }
}

static const lv_font_t *_sync_title_font(void)
{
    return UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_28 : &lv_font_montserrat_16;
}

static const lv_font_t *_sync_body_font(void)
{
    return UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12;
}

static void _sync_label_style(lv_obj_t *label, uint32_t color,
                              const lv_font_t *font)
{
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_set_style_text_font(label, font, 0);
}

static void _make_title(lv_obj_t *scr, const char *left, const char *right, uint32_t color)
{
    lv_obj_t *h = lv_obj_create(scr);
    lv_obj_set_size(h, UI_HOR_RES, UI_HEADER_HEIGHT);
    lv_obj_set_pos(h, 0, 0);
    lv_obj_set_style_bg_color(h, lv_color_hex(UI_COLOR_SURFACE), 0);
    lv_obj_set_style_radius(h, 0, 0);
    lv_obj_clear_flag(h, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *a = lv_label_create(h); lv_label_set_text(a, left);
    _sync_label_style(a, UI_COLOR_TEXT_PRIMARY, _sync_title_font());
    lv_obj_align(a, LV_ALIGN_LEFT_MID, UI_SCALE_X(14), 0);
    lv_obj_t *b = lv_label_create(h); lv_label_set_text(b, right);
    _sync_label_style(b, color, _sync_body_font());
    lv_obj_align(b, LV_ALIGN_RIGHT_MID, -UI_SCALE_X(14), 0);
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
    lv_label_set_text(lbl_title, "CLOUD SYNC ACTIVE");
    lv_obj_set_style_text_color(lbl_title, lv_color_hex(0x007AFF), LV_PART_MAIN | LV_STATE_DEFAULT);
    lv_obj_set_style_text_font(lbl_title, _sync_title_font(), LV_PART_MAIN | LV_STATE_DEFAULT);
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
    s_heartbeat_icon = NULL;
    s_heartbeat_icon_next = NULL;
    s_heartbeat_track = NULL;
    s_heartbeat_screen = NULL;
    s_heartbeat_title = NULL;
    s_heartbeat_subtitle = NULL;
    s_heartbeat_connection = NULL;
    s_heartbeat_offset = 0;
    s_heartbeat_track_width = 0;
    s_heartbeat_color = UI_COLOR_DANGER;

    lv_obj_t *scr = lv_obj_create(NULL);
    s_heartbeat_screen = scr;
    lv_obj_set_style_bg_color(scr, lv_color_hex(UI_COLOR_BG_DARK), 0);
    _make_title(scr, "SYNC MODE", "PROBING SERVER", UI_COLOR_WARNING);

    const int margin = UI_RES_CLASS_WIDESCREEN ? 24 : 10;
    const int card_y = UI_HEADER_HEIGHT + (UI_RES_CLASS_WIDESCREEN ? 18 : 10);
    const int card_h = UI_RES_CLASS_WIDESCREEN ? 320 : (UI_RES_CLASS_MEDIUM ? 210 : 160);
    lv_obj_t *card = lv_obj_create(scr);
    lv_obj_set_size(card, UI_HOR_RES - 2 * margin, card_h);
    lv_obj_set_pos(card, margin, card_y);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x11131A), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(card, lv_color_hex(UI_COLOR_BORDER), 0);
    lv_obj_set_style_border_width(card, 2, 0);
    lv_obj_set_style_radius(card, UI_CARD_RADIUS, 0);
    lv_obj_set_style_pad_all(card, 0, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    s_heartbeat_title = lv_label_create(card);
    lv_label_set_text(s_heartbeat_title, "PINGING SERVER HEARTBEAT");
    _sync_label_style(s_heartbeat_title, UI_COLOR_DANGER,
                      UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_20 : &lv_font_montserrat_14);
    lv_obj_set_style_text_align(s_heartbeat_title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(s_heartbeat_title, LV_ALIGN_TOP_MID, 0,
                 UI_RES_CLASS_WIDESCREEN ? 18 : 12);

    const int ecg_w = UI_RES_CLASS_WIDESCREEN ? 560 : (UI_RES_CLASS_MEDIUM ? 390 : 280);
    const int ecg_h = UI_RES_CLASS_WIDESCREEN ? 120 : (UI_RES_CLASS_MEDIUM ? 84 : 68);
    s_heartbeat_track_width = ecg_w;
    lv_obj_t *track = lv_obj_create(card);
    lv_obj_set_size(track, ecg_w, ecg_h);
    lv_obj_align(track, LV_ALIGN_TOP_MID, 0,
                 UI_RES_CLASS_WIDESCREEN ? 66 : (UI_RES_CLASS_MEDIUM ? 45 : 36));
    lv_obj_set_style_bg_color(track, lv_color_hex(UI_COLOR_SURFACE), 0);
    lv_obj_set_style_bg_opa(track, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(track, 0, 0);
    lv_obj_set_style_pad_all(track, 0, 0);
    lv_obj_clear_flag(track, LV_OBJ_FLAG_SCROLLABLE);
    s_heartbeat_track = track;

    lv_obj_t *ecg = lv_canvas_create(track);
    lv_obj_set_size(ecg, ecg_w, ecg_h);
    lv_obj_set_pos(ecg, 0, 0);
    lv_obj_set_style_bg_opa(ecg, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(ecg, 0, 0);
    lv_obj_set_style_pad_all(ecg, 0, 0);
    lv_obj_clear_flag(ecg, LV_OBJ_FLAG_SCROLLABLE);
    lv_canvas_set_buffer(ecg, s_heartbeat_canvas_buf, ecg_w, ecg_h,
                         LV_IMG_CF_TRUE_COLOR);
    s_heartbeat_icon = ecg;

    lv_obj_t *ecg_next = lv_canvas_create(track);
    lv_obj_set_size(ecg_next, ecg_w, ecg_h);
    lv_obj_set_pos(ecg_next, ecg_w, 0);
    lv_obj_set_style_bg_opa(ecg_next, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(ecg_next, 0, 0);
    lv_obj_set_style_pad_all(ecg_next, 0, 0);
    lv_obj_clear_flag(ecg_next, LV_OBJ_FLAG_SCROLLABLE);
    lv_canvas_set_buffer(ecg_next, s_heartbeat_canvas_buf, ecg_w, ecg_h,
                         LV_IMG_CF_TRUE_COLOR);
    s_heartbeat_icon_next = ecg_next;
    _heartbeat_set_color(UI_COLOR_DANGER);

    s_heartbeat_subtitle = lv_label_create(card);
    lv_label_set_text(s_heartbeat_subtitle, "WAITING FOR AUTHENTICATED ACKNOWLEDGEMENT...");
    lv_obj_set_style_text_color(s_heartbeat_subtitle, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
    lv_obj_set_style_text_align(s_heartbeat_subtitle, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(s_heartbeat_subtitle, LV_ALIGN_TOP_MID, 0,
                 UI_RES_CLASS_WIDESCREEN ? 205 : (UI_RES_CLASS_MEDIUM ? 137 : 111));

    s_heartbeat_connection = lv_label_create(card);
    lv_label_set_text(s_heartbeat_connection, "checking server connection");
    _sync_label_style(s_heartbeat_connection, UI_COLOR_TEXT_MUTED,
                      UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    lv_obj_set_style_text_align(s_heartbeat_connection, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(s_heartbeat_connection, LV_ALIGN_TOP_MID, 0,
                 UI_RES_CLASS_WIDESCREEN ? 238 : (UI_RES_CLASS_MEDIUM ? 168 : 137));

    ui_load_screen(scr);
    /* The first red ECG is drawn before screen load. Start the sweep and
     * force exactly one complete frame so the trace is present with the ping
     * label, without showing an intermediate pre-animation frame. */
    _heartbeat_start_animation(track);
    lv_refr_now(NULL);
    ui_unlock();
}

void ui_sync_heartbeat_pinging(void)
{
    if (ui_lock(-1)) {
        _heartbeat_set_state(false, false);
        ui_unlock();
    }
}

void ui_sync_heartbeat_acknowledged(void)
{
    if (ui_lock(-1)) {
        _heartbeat_set_state(true, false);
        ui_unlock();
    }
}

void ui_sync_heartbeat_failed(void)
{
    if (ui_lock(-1)) {
        _heartbeat_set_state(false, true);
        ui_unlock();
    }
}

/* ──────────────────────────────────────────────────────────────────────────
 * Screen 8: Chunked Batch Telemetry Uploader Progress
 * ────────────────────────────────────────────────────────────────────────*/
void ui_show_sync_uploading(int file_idx, int total_files, const char *filename,
                            int progress_pct, size_t global_sent_bytes,
                            size_t global_total_bytes, int files_remaining,
                            const char *speed, const char *eta)
{
    ui_home_deactivate();
    /* The first upload frame must not be dropped if LVGL is finishing the
     * heartbeat frame.  Wait for the UI lock so the handoff is deterministic
     * instead of leaving the green acknowledgment visible until a later
     * progress callback. */
    if (ui_lock(-1)) {
        /* The heartbeat screen is about to be deleted. Stop its animation
         * before the screen switch so no callback can invalidate or move the
         * old canvases during the upload handoff. */
        _heartbeat_stop_animation();
        lv_obj_t *new_scr = NULL;
        if (!s_upload_active) {
            const bool reuse_heartbeat_screen =
                s_heartbeat_screen && lv_scr_act() == s_heartbeat_screen;
            lv_obj_t *scr = reuse_heartbeat_screen
                          ? lv_obj_create(s_heartbeat_screen) : lv_obj_create(NULL);
            if (reuse_heartbeat_screen) {
                /* Keep the same active root screen, but build the upload view
                 * as a fully opaque child overlay. This keeps the scan frame
                 * covered until every upload widget is ready; cleaning the
                 * active root first can expose a blank intermediate frame. */
                lv_obj_set_size(scr, UI_HOR_RES, UI_VER_RES);
                lv_obj_set_pos(scr, 0, 0);
                lv_obj_set_style_border_width(scr, 0, 0);
                lv_obj_set_style_pad_all(scr, 0, 0);
                lv_obj_clear_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
            }
            lv_obj_set_style_bg_color(scr, lv_color_hex(UI_COLOR_BG_DARK), 0);
            lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
            _make_title(scr, "SYNC MODE", "CLOUD ONLINE", UI_COLOR_SUCCESS);

            const int margin = UI_RES_CLASS_WIDESCREEN ? 24 : 10;
            const int card_y = UI_HEADER_HEIGHT + (UI_RES_CLASS_WIDESCREEN ? 18 : 10);
            const int card_h = UI_RES_CLASS_WIDESCREEN ? 300 : 180;
            lv_obj_t *card = lv_obj_create(scr);
            lv_obj_set_size(card, UI_HOR_RES - 2 * margin, card_h);
            lv_obj_set_pos(card, margin, card_y);
            lv_obj_set_style_bg_color(card, lv_color_hex(0x11131A), 0);
            lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
            lv_obj_set_style_border_color(card, lv_color_hex(UI_COLOR_BORDER), 0);
            lv_obj_set_style_border_width(card, 2, 0);
            lv_obj_set_style_radius(card, UI_CARD_RADIUS, 0);
            lv_obj_set_style_pad_all(card, 0, 0);
            lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

            s_upload_title = lv_label_create(scr);
            _sync_label_style(s_upload_title, UI_COLOR_SUCCESS,
                              UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_20 : &lv_font_montserrat_16);
            lv_obj_set_pos(s_upload_title, margin + UI_SCALE_X(22), card_y + UI_SCALE_Y(18));
            s_upload_file = lv_label_create(scr);
            _sync_label_style(s_upload_file, UI_COLOR_TEXT_PRIMARY,
                              UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_20 : &lv_font_montserrat_14);
            lv_obj_set_pos(s_upload_file, margin + UI_SCALE_X(22), card_y + UI_SCALE_Y(54));

            s_upload_remaining = lv_label_create(scr);
            _sync_label_style(s_upload_remaining, UI_COLOR_WARNING,
                              UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
            lv_obj_align(s_upload_remaining, LV_ALIGN_TOP_RIGHT,
                         -margin - UI_SCALE_X(22), card_y + UI_SCALE_Y(22));

            s_upload_bar = lv_bar_create(scr);
            lv_obj_set_size(s_upload_bar, UI_HOR_RES - 2 * margin - UI_SCALE_X(44),
                            UI_RES_CLASS_WIDESCREEN ? 18 : 12);
            lv_obj_set_pos(s_upload_bar, margin + UI_SCALE_X(22), card_y + UI_SCALE_Y(104));
            lv_bar_set_range(s_upload_bar, 0, 100);
            lv_obj_set_style_bg_color(s_upload_bar, lv_color_hex(UI_COLOR_BORDER), LV_PART_MAIN);
            lv_obj_set_style_bg_color(s_upload_bar, lv_color_hex(UI_COLOR_PRIMARY), LV_PART_INDICATOR);
            lv_obj_set_style_radius(s_upload_bar, LV_RADIUS_CIRCLE, LV_PART_MAIN);
            lv_obj_set_style_radius(s_upload_bar, LV_RADIUS_CIRCLE, LV_PART_INDICATOR);

            s_upload_percent = lv_label_create(scr);
            _sync_label_style(s_upload_percent, UI_COLOR_TEXT_PRIMARY,
                              UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_36 : &lv_font_montserrat_28);
            lv_obj_align(s_upload_percent, LV_ALIGN_TOP_RIGHT,
                         -margin - UI_SCALE_X(22), card_y + UI_SCALE_Y(128));

            s_upload_total = lv_label_create(scr);
            _sync_label_style(s_upload_total, UI_COLOR_TEXT_MUTED,
                              UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
            lv_obj_set_pos(s_upload_total, margin + UI_SCALE_X(22), card_y + UI_SCALE_Y(136));

            s_upload_eta = lv_label_create(scr);
            _sync_label_style(s_upload_eta, UI_COLOR_TEXT_MUTED,
                              UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
            lv_obj_set_pos(s_upload_eta, margin + UI_SCALE_X(22), card_y + UI_SCALE_Y(170));

            lv_obj_t *cancel = lv_btn_create(scr);
            lv_obj_set_size(cancel, UI_HOR_RES - 2 * margin,
                            UI_RES_CLASS_WIDESCREEN ? 62 : 48);
            lv_obj_align(cancel, LV_ALIGN_BOTTOM_MID, 0, -UI_SCALE_Y(14));
            lv_obj_set_style_bg_color(cancel, lv_color_hex(UI_COLOR_DANGER), 0);
            lv_obj_set_style_radius(cancel, UI_BTN_RADIUS, 0);
            lv_obj_add_event_cb(cancel, _on_btn_sync_cancel_cb, LV_EVENT_CLICKED, NULL);
            lv_obj_t *cl = lv_label_create(cancel);
            lv_label_set_text(cl, "CANCEL & EXIT");
            _sync_label_style(cl, UI_COLOR_TEXT_PRIMARY,
                              UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
            lv_obj_center(cl);
            if (!reuse_heartbeat_screen) new_scr = scr;
            s_upload_active = true;
        }
        char buf[80];
        if (total_files <= 0) {
            lv_label_set_text(s_upload_title, "PREPARING CLOUD SYNC");
            lv_label_set_text(s_upload_file, filename ? filename : "CHECKING FOR PENDING DATA");
            lv_label_set_text(s_upload_remaining, "WAITING");
        } else {
            snprintf(buf, sizeof(buf), "FILE %d OF %d", file_idx, total_files);
            lv_label_set_text(s_upload_title, buf);
            lv_label_set_text(s_upload_file, filename ? filename : "session.csv");
            snprintf(buf, sizeof(buf), "%d FILE%s REMAINING", files_remaining,
                     files_remaining == 1 ? "" : "S");
            lv_label_set_text(s_upload_remaining, buf);
        }
        snprintf(buf, sizeof(buf), "%d%%", progress_pct);
        lv_label_set_text(s_upload_percent, buf);
        char total_text[96];
        snprintf(total_text, sizeof(total_text), "TOTAL  %.1f / %.1f MB",
                 (double)global_sent_bytes / (1024.0 * 1024.0),
                 (double)global_total_bytes / (1024.0 * 1024.0));
        lv_label_set_text(s_upload_total, total_text);
        char eta_text[128];
        snprintf(eta_text, sizeof(eta_text), "ETA  %s    •    %s",
                 eta && eta[0] ? eta : "calculating", speed && speed[0] ? speed : "measuring speed");
        lv_label_set_text(s_upload_eta, eta_text);
        /* Progress callbacks can arrive back-to-back; animate only the ECG,
         * never the entire upload handoff or its progress bar. */
        lv_bar_set_value(s_upload_bar, progress_pct, LV_ANIM_OFF);
        if (new_scr) {
            /* Populate the complete first frame before replacing the heartbeat
             * screen so the handoff cannot flash a blank/default page. */
            ui_load_screen(new_scr);
        }
        /* Let the LVGL task present the complete opaque overlay as one normal
         * refresh after the lock is released; a synchronous refresh here can
         * tear while the scan frame is being replaced. */
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
