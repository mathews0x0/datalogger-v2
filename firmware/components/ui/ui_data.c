/**
 * @file ui_data.c
 * @brief Pending session browser and manual cloud-sync controls.
 */

#include "ui.h"
#include "ui_events.h"

#include <stdio.h>
#include <string.h>
#include "esp_log.h"

#define DATA_MAX_VISIBLE_FILES 32
static const char *TAG = "ui_data";

/* This screen can be opened directly from the LVGL touch callback. Keep the
 * file catalogue out of that callback's stack; 32 entries are several KB. */
static storage_pending_file_t s_files[DATA_MAX_VISIBLE_FILES];
static lv_obj_t *s_data_queued_label;
static lv_obj_t *s_data_count_label;
static lv_obj_t *s_data_detail_label;
static lv_obj_t *s_data_list;
static lv_obj_t *s_data_empty_label;
static lv_obj_t *s_data_file_label;
static lv_obj_t *s_data_sync_button;
static lv_obj_t *s_data_sync_label;
static bool s_data_active;
static bool s_data_loaded;
static char s_data_file_text[DATA_MAX_VISIBLE_FILES * 96];

static lv_color_t _color(uint32_t value)
{
    return lv_color_hex(value);
}

static void _format_bytes(char *out, size_t out_len, uint64_t bytes)
{
    if (bytes >= (1024ULL * 1024ULL * 1024ULL)) {
        snprintf(out, out_len, "%.1f GB", (double)bytes / (1024.0 * 1024.0 * 1024.0));
    } else if (bytes >= (1024ULL * 1024ULL)) {
        snprintf(out, out_len, "%.1f MB", (double)bytes / (1024.0 * 1024.0));
    } else if (bytes >= 1024ULL) {
        snprintf(out, out_len, "%.1f KB", (double)bytes / 1024.0);
    } else {
        snprintf(out, out_len, "%llu B", (unsigned long long)bytes);
    }
}

static void _label_style(lv_obj_t *label, uint32_t color, const lv_font_t *font)
{
    lv_obj_set_style_text_color(label, _color(color), 0);
    lv_obj_set_style_text_font(label, font, 0);
}

static lv_obj_t *_panel(lv_obj_t *parent, int x, int y, int width, int height,
                        uint32_t color)
{
    lv_obj_t *panel = lv_obj_create(parent);
    lv_obj_set_size(panel, width, height);
    lv_obj_set_pos(panel, x, y);
    lv_obj_set_style_bg_color(panel, _color(color), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(panel, _color(UI_COLOR_BORDER), 0);
    lv_obj_set_style_border_width(panel, UI_RES_CLASS_WIDESCREEN ? 2 : 1, 0);
    lv_obj_set_style_radius(panel, UI_CARD_RADIUS, 0);
    lv_obj_set_style_pad_all(panel, 0, 0);
    lv_obj_clear_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    return panel;
}

static void _on_back(lv_event_t *event)
{
    (void)event;
    ui_events_on_navigate_home();
}

static void _on_sync(lv_event_t *event)
{
    (void)event;
    ui_events_on_sync_start();
}

static void _populate_file_rows(size_t file_count)
{
    if (!s_data_list) return;
    lv_obj_clean(s_data_list);
    s_data_empty_label = NULL;
    s_data_file_label = NULL;

    if (file_count == 0) {
        s_data_empty_label = lv_label_create(s_data_list);
        lv_label_set_text(s_data_empty_label, "ALL SESSION FILES ARE SYNCED");
        _label_style(s_data_empty_label, UI_COLOR_SUCCESS,
                     UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
        lv_obj_center(s_data_empty_label);
        return;
    }

    /* Keep the catalogue as one scrollable label.  A row container plus two
     * labels per file consumes a surprisingly large amount of LVGL's internal
     * object/buffer pool on this target, especially when a card contains many
     * old sessions. */
    s_data_file_text[0] = '\0';
    size_t used = 0;
    for (size_t i = 0; i < file_count; ++i) {
        char size_text[24];
        _format_bytes(size_text, sizeof(size_text), s_files[i].size_bytes);
        int written = snprintf(s_data_file_text + used,
                               sizeof(s_data_file_text) - used,
                               "%02u  %s\n     %s  |  PENDING%s",
                               (unsigned)(i + 1), s_files[i].filename,
                               size_text, i + 1 < file_count ? "\n\n" : "");
        if (written < 0) break;
        if ((size_t)written >= sizeof(s_data_file_text) - used) {
            used = sizeof(s_data_file_text) - 1;
            break;
        }
        used += (size_t)written;
    }

    s_data_file_label = lv_label_create(s_data_list);
    lv_label_set_text(s_data_file_label, s_data_file_text);
    lv_label_set_long_mode(s_data_file_label, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(s_data_file_label, lv_pct(100));
    _label_style(s_data_file_label, UI_COLOR_TEXT_PRIMARY,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
    lv_obj_set_style_text_line_space(s_data_file_label,
                                     UI_RES_CLASS_WIDESCREEN ? 4 : 2, 0);
    lv_obj_set_pos(s_data_file_label, UI_SCALE_X(12), UI_SCALE_Y(8));
}

void ui_data_deactivate(void)
{
    s_data_active = false;
    s_data_loaded = false;
}

void ui_data_update(void)
{
    if (!s_data_active || s_data_loaded || !ui_lock(20)) return;

    ESP_LOGI(TAG, "Loading pending file catalogue");

    storage_pending_summary_t summary = {0};
    storage_get_pending_summary(&summary);
    memset(s_files, 0, sizeof(s_files));
    size_t file_count = storage_list_pending_files(s_files, DATA_MAX_VISIBLE_FILES);

    uint64_t total_bytes = 0;
    uint64_t free_bytes = 0;
    (void)storage_get_space_bytes(&total_bytes, &free_bytes);

    char queued_text[32];
    snprintf(queued_text, sizeof(queued_text), "%d FILE%s QUEUED",
             summary.count, summary.count == 1 ? "" : "S");
    lv_label_set_text(s_data_queued_label, queued_text);
    _label_style(s_data_queued_label,
                 summary.count ? UI_COLOR_WARNING : UI_COLOR_SUCCESS,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12);

    char count_text[24];
    snprintf(count_text, sizeof(count_text), "%d FILE%s",
             summary.count, summary.count == 1 ? "" : "S");
    lv_label_set_text(s_data_count_label, count_text);
    _label_style(s_data_count_label,
                 summary.count ? UI_COLOR_WARNING : UI_COLOR_SUCCESS,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_36 : &lv_font_montserrat_28);

    char bytes_text[64];
    char free_text[24];
    _format_bytes(bytes_text, sizeof(bytes_text), summary.total_bytes);
    _format_bytes(free_text, sizeof(free_text), free_bytes);
    char detail_text[112];
    snprintf(detail_text, sizeof(detail_text), "TOTAL %s   |   %s FREE", bytes_text, free_text);
    lv_label_set_text(s_data_detail_label, detail_text);

    _populate_file_rows(file_count);
    lv_obj_set_style_bg_color(s_data_sync_button,
                              _color(summary.count ? UI_COLOR_PAIRING : 0x30303A), 0);
    lv_obj_set_style_border_color(s_data_sync_button,
                                  _color(summary.count ? UI_COLOR_PAIRING : UI_COLOR_BORDER), 0);
    lv_label_set_text(s_data_sync_label, summary.count ? "SYNC NOW" : "NOTHING TO SYNC");
    if (summary.count) lv_obj_clear_state(s_data_sync_button, LV_STATE_DISABLED);
    else lv_obj_add_state(s_data_sync_button, LV_STATE_DISABLED);

    s_data_loaded = true;
    ESP_LOGI(TAG, "Pending file catalogue loaded: %d file(s)", summary.count);
    ui_unlock();
}

void ui_show_data(void)
{
    ESP_LOGI(TAG, "Constructing Data screen shell");
    ui_home_deactivate();
    ui_data_deactivate();
    ui_lock(-1);
    s_data_active = true;

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, _color(UI_COLOR_BG_DARK), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    lv_obj_t *header = _panel(scr, 0, 0, UI_HOR_RES, UI_HEADER_HEIGHT,
                              UI_COLOR_SURFACE);
    lv_obj_t *back = lv_btn_create(header);
    lv_obj_set_size(back, UI_RES_CLASS_WIDESCREEN ? 112 : 82,
                    UI_HEADER_HEIGHT - UI_SCALE_Y(10));
    lv_obj_set_pos(back, UI_SCALE_X(12), UI_SCALE_Y(5));
    lv_obj_set_style_bg_color(back, _color(0x242430), 0);
    lv_obj_set_style_radius(back, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(back, _on_back, LV_EVENT_CLICKED, NULL);
    lv_obj_t *back_label = lv_label_create(back);
    lv_label_set_text(back_label, "‹ HOME");
    _label_style(back_label, UI_COLOR_TEXT_PRIMARY,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
    lv_obj_center(back_label);

    lv_obj_t *title = lv_label_create(header);
    lv_label_set_text(title, "DATA");
    _label_style(title, UI_COLOR_TEXT_PRIMARY,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_28 : &lv_font_montserrat_16);
    lv_obj_align(title, LV_ALIGN_CENTER, 0, 0);

    s_data_queued_label = lv_label_create(header);
    lv_label_set_text(s_data_queued_label, "READING SD CARD");
    _label_style(s_data_queued_label, UI_COLOR_TEXT_MUTED,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    lv_obj_align(s_data_queued_label, LV_ALIGN_RIGHT_MID, -UI_SCALE_X(18), 0);

    const int margin = UI_RES_CLASS_WIDESCREEN ? 24 : 10;
    const int gap = UI_RES_CLASS_WIDESCREEN ? 14 : 8;
    const int content_y = UI_HEADER_HEIGHT + margin;
    const int content_w = UI_HOR_RES - 2 * margin;
    const int summary_h = UI_RES_CLASS_WIDESCREEN ? 84 : 62;
    const int list_y = content_y + summary_h + gap;
    const int footer_h = UI_RES_CLASS_WIDESCREEN ? 62 : 48;
    const int footer_y = UI_VER_RES - margin - footer_h;
    const int list_h = footer_y - list_y - gap;

    lv_obj_t *summary_card = _panel(scr, margin, content_y, content_w, summary_h,
                                     0x11131A);
    lv_obj_t *summary_title = lv_label_create(summary_card);
    lv_label_set_text(summary_title, "PENDING UPLOADS");
    _label_style(summary_title, UI_COLOR_TEXT_MUTED,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    lv_obj_set_pos(summary_title, UI_SCALE_X(18), UI_SCALE_Y(12));

    s_data_count_label = lv_label_create(summary_card);
    lv_label_set_text(s_data_count_label, "LOADING");
    _label_style(s_data_count_label, UI_COLOR_TEXT_MUTED,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_36 : &lv_font_montserrat_28);
    lv_obj_set_pos(s_data_count_label, UI_SCALE_X(18), UI_RES_CLASS_WIDESCREEN ? UI_SCALE_Y(31) : UI_SCALE_Y(26));

    s_data_detail_label = lv_label_create(summary_card);
    lv_label_set_text(s_data_detail_label, "Reading storage details...");
    _label_style(s_data_detail_label, UI_COLOR_TEXT_MUTED,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
    lv_obj_align(s_data_detail_label, LV_ALIGN_RIGHT_MID, -UI_SCALE_X(18), 0);

    lv_obj_t *list_card = _panel(scr, margin, list_y, content_w, list_h, 0x11131A);
    lv_obj_t *list_title = lv_label_create(list_card);
    lv_label_set_text(list_title, "SESSION FILES");
    _label_style(list_title, UI_COLOR_TEXT_MUTED,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    lv_obj_set_pos(list_title, UI_SCALE_X(18), UI_SCALE_Y(10));

    const int list_margin = UI_RES_CLASS_WIDESCREEN ? 14 : 8;
    const int list_top = UI_RES_CLASS_WIDESCREEN ? 38 : 30;
    const int list_bottom = UI_RES_CLASS_WIDESCREEN ? 12 : 8;
    s_data_list = lv_obj_create(list_card);
    lv_obj_set_size(s_data_list, content_w - 2 * list_margin,
                    list_h - list_top - list_bottom);
    lv_obj_set_pos(s_data_list, list_margin, list_top);
    lv_obj_set_style_bg_color(s_data_list, _color(0x0B0D12), 0);
    lv_obj_set_style_bg_opa(s_data_list, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(s_data_list, 0, 0);
    lv_obj_set_style_radius(s_data_list, UI_BTN_RADIUS, 0);
    lv_obj_set_style_pad_all(s_data_list, 0, 0);
    lv_obj_set_scroll_dir(s_data_list, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(s_data_list, LV_SCROLLBAR_MODE_AUTO);
    s_data_empty_label = lv_label_create(s_data_list);
    lv_label_set_text(s_data_empty_label, "READING SESSION FILES...");
    _label_style(s_data_empty_label, UI_COLOR_TEXT_MUTED,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
    lv_obj_center(s_data_empty_label);

    const int button_gap = UI_RES_CLASS_WIDESCREEN ? 14 : 8;
    const int back_w = UI_RES_CLASS_WIDESCREEN ? 170 : 100;
    const int sync_w = content_w - back_w - button_gap;
    s_data_sync_button = lv_btn_create(scr);
    lv_obj_set_size(s_data_sync_button, sync_w, footer_h);
    lv_obj_set_pos(s_data_sync_button, margin, footer_y);
    lv_obj_set_style_bg_color(s_data_sync_button, _color(0x30303A), 0);
    lv_obj_set_style_border_color(s_data_sync_button, _color(UI_COLOR_BORDER), 0);
    lv_obj_set_style_border_width(s_data_sync_button, 2, 0);
    lv_obj_set_style_radius(s_data_sync_button, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(s_data_sync_button, _on_sync, LV_EVENT_CLICKED, NULL);
    lv_obj_add_state(s_data_sync_button, LV_STATE_DISABLED);
    s_data_sync_label = lv_label_create(s_data_sync_button);
    lv_label_set_text(s_data_sync_label, "LOADING FILES");
    _label_style(s_data_sync_label, UI_COLOR_TEXT_MUTED,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_20 : &lv_font_montserrat_14);
    lv_obj_center(s_data_sync_label);

    lv_obj_t *home = lv_btn_create(scr);
    lv_obj_set_size(home, back_w, footer_h);
    lv_obj_set_pos(home, margin + sync_w + button_gap, footer_y);
    lv_obj_set_style_bg_color(home, _color(0x242430), 0);
    lv_obj_set_style_border_color(home, _color(UI_COLOR_BORDER), 0);
    lv_obj_set_style_border_width(home, 1, 0);
    lv_obj_set_style_radius(home, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(home, _on_back, LV_EVENT_CLICKED, NULL);
    lv_obj_t *home_label = lv_label_create(home);
    lv_label_set_text(home_label, "HOME");
    _label_style(home_label, UI_COLOR_TEXT_PRIMARY,
                 UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
    lv_obj_center(home_label);

    ui_load_screen(scr);
    ESP_LOGI(TAG, "Data screen shell ready");
    ui_unlock();
}
