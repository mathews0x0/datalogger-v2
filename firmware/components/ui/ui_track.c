/**
 * @file ui_track.c
 * @brief Compact Home track preview and full-screen Track/Info viewer.
 */

#include "ui.h"
#include "ui_events.h"
#include "network.h"
#include "track_engine.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static track_display_layout_t s_layout;
static lv_obj_t *s_content;
static lv_obj_t *s_map_panel;
static lv_obj_t *s_position_halo;
static lv_obj_t *s_position_dot;
static lv_obj_t *s_map_tab_button;
static lv_obj_t *s_info_tab_button;
static bool s_track_view_active;
static bool s_info_tab;
static lv_point_t s_map_points[TRACK_ENGINE_MAX_LAYOUT_POINTS];

static void _style_surface(lv_obj_t *obj, uint32_t color, uint32_t border,
                           int radius)
{
    lv_obj_set_style_bg_color(obj, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(obj, lv_color_hex(border), 0);
    lv_obj_set_style_border_width(obj, UI_RES_CLASS_WIDESCREEN ? 2 : 1, 0);
    lv_obj_set_style_radius(obj, radius, 0);
    lv_obj_clear_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
}

static void _format_seconds(float seconds, char *out, size_t out_len)
{
    if (!out || out_len == 0) return;
    if (!isfinite(seconds) || seconds <= 0.0f) {
        snprintf(out, out_len, "--.---");
        return;
    }
    int total_ms = (int)lroundf(seconds * 1000.0f);
    int minutes = total_ms / 60000;
    int whole_seconds = (total_ms % 60000) / 1000;
    int milliseconds = total_ms % 1000;
    if (minutes > 0) snprintf(out, out_len, "%d:%02d.%03d", minutes,
                              whole_seconds, milliseconds);
    else snprintf(out, out_len, "%d.%03d", whole_seconds, milliseconds);
}

static void _map_point(track_layout_point_t source, int width, int height,
                       lv_point_t *out)
{
    /* Keep the full-size map comfortably inset, but reclaim space for the
     * small Home preview.  A fixed 24 px inset on a 170x115 preview leaves
     * very little usable track area and makes the route look clipped. */
    const int pad = UI_RES_CLASS_WIDESCREEN && (width < 240 || height < 160) ? 10
                    : UI_RES_CLASS_WIDESCREEN ? 24 : 10;
    const int draw_w = width > 2 * pad ? width - 2 * pad : width;
    const int draw_h = height > 2 * pad ? height - 2 * pad : height;
    out->x = pad + (int)((source.x * draw_w) / 1000U);
    out->y = pad + (int)((source.y * draw_h) / 1000U);
}

static void _draw_marker(lv_obj_t *parent, track_layout_point_t source,
                         int width, int height, int size, uint32_t color,
                         bool square)
{
    lv_point_t point;
    _map_point(source, width, height, &point);
    lv_obj_t *marker = lv_obj_create(parent);
    lv_obj_set_size(marker, size, size);
    lv_obj_set_pos(marker, point.x - size / 2, point.y - size / 2);
    lv_obj_set_style_bg_color(marker, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(marker, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(marker, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_set_style_border_width(marker, 1, 0);
    lv_obj_set_style_radius(marker, square ? 2 : LV_RADIUS_CIRCLE, 0);
    lv_obj_clear_flag(marker, LV_OBJ_FLAG_SCROLLABLE);
}

static void _draw_layout(lv_obj_t *parent, int width, int height,
                         bool show_position, bool show_sector_markers)
{
    if (!s_layout.has_layout || s_layout.polyline_count < 2) {
        lv_obj_t *empty = lv_label_create(parent);
        lv_label_set_text(empty, "TRACK LAYOUT\nNOT AVAILABLE");
        lv_obj_set_style_text_color(empty, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
        lv_obj_set_style_text_align(empty, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_center(empty);
        return;
    }

    for (int i = 0; i < s_layout.polyline_count; ++i) {
        _map_point(s_layout.polyline[i], width, height, &s_map_points[i]);
    }

    lv_obj_t *glow = lv_line_create(parent);
    lv_line_set_points(glow, s_map_points, s_layout.polyline_count);
    lv_obj_set_style_line_color(glow, lv_color_hex(0x5C2B18), 0);
    lv_obj_set_style_line_width(glow, UI_RES_CLASS_WIDESCREEN ? 13 : 7, 0);
    lv_obj_set_style_line_rounded(glow, true, 0);

    lv_obj_t *route = lv_line_create(parent);
    lv_line_set_points(route, s_map_points, s_layout.polyline_count);
    lv_obj_set_style_line_color(route, lv_color_hex(UI_COLOR_PRIMARY), 0);
    lv_obj_set_style_line_width(route, UI_RES_CLASS_WIDESCREEN ? 5 : 3, 0);
    lv_obj_set_style_line_rounded(route, true, 0);

    if (s_layout.has_start_marker) {
        _draw_marker(parent, s_layout.start_marker, width, height,
                     UI_RES_CLASS_WIDESCREEN ? 18 : 10,
                     UI_COLOR_TEXT_PRIMARY, true);
    }

    if (show_sector_markers) for (int i = 0; i < s_layout.sector_marker_count; ++i) {
        const track_layout_marker_t *marker = &s_layout.sector_markers[i];
        _draw_marker(parent, marker->point, width, height,
                     UI_RES_CLASS_WIDESCREEN ? 14 : 8,
                     UI_COLOR_PAIRING, false);
        lv_point_t point;
        _map_point(marker->point, width, height, &point);
        lv_obj_t *label = lv_label_create(parent);
        char sector[8];
        snprintf(sector, sizeof(sector), "S%d", marker->sector_index);
        lv_label_set_text(label, sector);
        lv_obj_set_style_text_color(label, lv_color_hex(UI_COLOR_PAIRING), 0);
        lv_obj_set_pos(label, point.x + 5, point.y - 9);
    }

    if (show_position) {
        s_position_halo = lv_obj_create(parent);
        lv_obj_set_size(s_position_halo, UI_RES_CLASS_WIDESCREEN ? 32 : 20,
                        UI_RES_CLASS_WIDESCREEN ? 32 : 20);
        lv_obj_set_style_bg_color(s_position_halo, lv_color_hex(UI_COLOR_PAIRING), 0);
        lv_obj_set_style_bg_opa(s_position_halo, LV_OPA_30, 0);
        lv_obj_set_style_border_width(s_position_halo, 0, 0);
        lv_obj_set_style_radius(s_position_halo, LV_RADIUS_CIRCLE, 0);
        lv_obj_add_flag(s_position_halo, LV_OBJ_FLAG_HIDDEN);

        s_position_dot = lv_obj_create(parent);
        lv_obj_set_size(s_position_dot, UI_RES_CLASS_WIDESCREEN ? 12 : 8,
                        UI_RES_CLASS_WIDESCREEN ? 12 : 8);
        lv_obj_set_style_bg_color(s_position_dot, lv_color_hex(0x00E5FF), 0);
        lv_obj_set_style_border_color(s_position_dot, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
        lv_obj_set_style_border_width(s_position_dot, 1, 0);
        lv_obj_set_style_radius(s_position_dot, LV_RADIUS_CIRCLE, 0);
        lv_obj_add_flag(s_position_dot, LV_OBJ_FLAG_HIDDEN);
    }
}

static void _on_preview_clicked(lv_event_t *event)
{
    (void)event;
    ui_events_on_open_track_view();
}

static void _on_change_track_clicked(lv_event_t *event)
{
    (void)event;
    ui_events_on_open_track_selector();
}

void ui_track_preview_render(lv_obj_t *parent, int x, int y, int width, int height)
{
    if (!parent || width <= 0 || height <= 0) return;

    ui_track_refresh_layout();
    lv_obj_t *panel = lv_obj_create(parent);
    lv_obj_set_size(panel, width, height);
    lv_obj_set_pos(panel, x, y);
    _style_surface(panel, 0x11131A, UI_COLOR_BORDER, UI_CARD_RADIUS);
    lv_obj_set_style_pad_all(panel, 0, 0);
    _draw_layout(panel, width, height, false, false);

    /* A transparent hit target keeps the preview clickable without changing
     * the visual treatment or stealing focus from the Home dashboard. */
    lv_obj_t *hit = lv_btn_create(parent);
    lv_obj_set_size(hit, lv_obj_get_content_width(parent),
                    lv_obj_get_content_height(parent));
    lv_obj_set_pos(hit, 0, 0);
    lv_obj_set_style_bg_opa(hit, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(hit, 0, 0);
    lv_obj_set_style_shadow_width(hit, 0, 0);
    lv_obj_clear_flag(hit, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_SCROLL_CHAIN);
    lv_obj_move_foreground(hit);
    lv_obj_add_event_cb(hit, _on_preview_clicked, LV_EVENT_CLICKED, NULL);
}

void ui_track_refresh_layout(void)
{
    memset(&s_layout, 0, sizeof(s_layout));
    track_engine_get_display_layout(&s_layout);
}

static void _set_tab_style(lv_obj_t *button, bool active)
{
    lv_obj_set_style_bg_color(button,
                              lv_color_hex(active ? UI_COLOR_PRIMARY : 0x242430), 0);
    lv_obj_set_style_border_color(button,
                                  lv_color_hex(active ? UI_COLOR_PRIMARY : UI_COLOR_BORDER), 0);
    lv_obj_set_style_border_width(button, active ? 2 : 1, 0);
    lv_obj_set_style_shadow_width(button, active ? 12 : 0, 0);
    lv_obj_set_style_shadow_color(button, lv_color_hex(UI_COLOR_PRIMARY), 0);
}

static void _render_map_tab(void)
{
    /* Percentage-sized children are resolved by LVGL during layout.  Resolve
     * them before using their dimensions to place the track geometry. */
    lv_obj_update_layout(s_content);
    s_map_panel = lv_obj_create(s_content);
    lv_obj_set_size(s_map_panel, lv_pct(100), lv_pct(100));
    lv_obj_update_layout(s_map_panel);
    _style_surface(s_map_panel, 0x11131A, UI_COLOR_BORDER, UI_CARD_RADIUS);
    const int map_w = lv_obj_get_width(s_map_panel);
    const int map_h = lv_obj_get_height(s_map_panel);
    _draw_layout(s_map_panel, map_w, map_h, true, true);

    /* Use real LVGL shapes instead of Unicode glyphs: the bundled font does
     * not contain all of the old legend symbols, which made the legend look
     * incomplete on the device. */
    lv_obj_t *legend = lv_obj_create(s_map_panel);
    const int legend_h = UI_RES_CLASS_WIDESCREEN ? 42 : 32;
    lv_obj_set_size(legend, lv_pct(100), legend_h);
    lv_obj_align(legend, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(legend, lv_color_hex(0x0B0D12), 0);
    lv_obj_set_style_bg_opa(legend, LV_OPA_90, 0);
    lv_obj_set_style_border_width(legend, 0, 0);
    lv_obj_set_style_radius(legend, 0, 0);
    lv_obj_set_style_pad_all(legend, 0, 0);
    lv_obj_clear_flag(legend, LV_OBJ_FLAG_SCROLLABLE);

    const int legend_icon = UI_RES_CLASS_WIDESCREEN ? 12 : 9;
    const int legend_y = (legend_h - legend_icon) / 2;
    const int legend_x[] = {UI_SCALE_X(18), UI_SCALE_X(180), UI_SCALE_X(390)};
    const char *legend_text[] = {"RIDER", "SECTOR GATES", "START / FINISH"};
    const uint32_t legend_color[] = {0x00E5FF, UI_COLOR_PAIRING, UI_COLOR_TEXT_PRIMARY};
    for (int i = 0; i < 3; ++i) {
        lv_obj_t *icon = lv_obj_create(legend);
        lv_obj_set_size(icon, legend_icon, legend_icon);
        lv_obj_set_pos(icon, legend_x[i], legend_y);
        lv_obj_set_style_bg_color(icon, lv_color_hex(legend_color[i]), 0);
        lv_obj_set_style_bg_opa(icon, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(icon, 1, 0);
        lv_obj_set_style_border_color(icon, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
        lv_obj_set_style_radius(icon, i == 2 ? 2 : LV_RADIUS_CIRCLE, 0);
        lv_obj_clear_flag(icon, LV_OBJ_FLAG_SCROLLABLE);

        lv_obj_t *label = lv_label_create(legend);
        lv_label_set_text(label, legend_text[i]);
        lv_obj_set_style_text_color(label, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
        lv_obj_set_style_text_font(label,
                                   UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_14
                                                           : &lv_font_montserrat_12,
                                   0);
        lv_obj_set_pos(label, legend_x[i] + legend_icon + UI_SCALE_X(8),
                       UI_RES_CLASS_WIDESCREEN ? 12 : 8);
    }
}

static lv_obj_t *_info_panel(lv_obj_t *parent, int x, int y, int width,
                             int height, uint32_t color, int radius)
{
    lv_obj_t *panel = lv_obj_create(parent);
    lv_obj_set_size(panel, width, height);
    lv_obj_set_pos(panel, x, y);
    _style_surface(panel, color, UI_COLOR_BORDER, radius);
    lv_obj_set_style_pad_all(panel, 0, 0);
    return panel;
}

static lv_obj_t *_info_label(lv_obj_t *parent, const char *text, int x, int y,
                             uint32_t color, const lv_font_t *font)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_label_set_text(label, text ? text : "");
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_pos(label, x, y);
    return label;
}

static void _render_info_tab(void)
{
    s_map_panel = NULL;
    lv_obj_set_style_bg_color(s_content, lv_color_hex(UI_COLOR_BG_DARK), 0);
    lv_obj_set_style_bg_opa(s_content, LV_OPA_COVER, 0);

    lv_obj_update_layout(s_content);
    const bool wide = UI_RES_CLASS_WIDESCREEN;
    const int content_w = lv_obj_get_width(s_content);
    const int content_h = lv_obj_get_height(s_content);
    const int margin = wide ? 16 : 10;
    const int summary_h = wide ? 72 : 52;
    const int body_y = summary_h + (wide ? 12 : 8);
    const int footer_h = wide ? 52 : 34;
    const int footer_y = content_h - footer_h;
    const int body_h = footer_y - body_y - (wide ? 12 : 8);
    const int tbl_w = wide ? 220 : 132;
    const int sector_x = tbl_w + (wide ? 16 : 8);
    const int sector_w = content_w - sector_x;

    lv_obj_t *summary = _info_panel(s_content, 0, 0, content_w, summary_h,
                                    0x11131A, UI_CARD_RADIUS);
    lv_obj_t *name = _info_label(summary, track_engine_get_track_name(),
                                 margin, wide ? 9 : 6,
                                 UI_COLOR_TEXT_PRIMARY,
                                 wide ? &lv_font_montserrat_28 : &lv_font_montserrat_16);
    lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);
    lv_obj_set_width(name, content_w - (wide ? 300 : 170));

    char meta_text[80];
    snprintf(meta_text, sizeof(meta_text), "%d SECTORS   •   %s",
             s_layout.sector_count,
             s_layout.has_layout ? "LAYOUT READY" : "LAYOUT UNAVAILABLE");
    _info_label(summary, meta_text, margin, wide ? 43 : 31,
                s_layout.has_layout ? UI_COLOR_SUCCESS : UI_COLOR_WARNING,
                wide ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    _info_label(summary, "ACTIVE TRACK", content_w - (wide ? 150 : 110),
                wide ? 25 : 17, UI_COLOR_PRIMARY,
                wide ? &lv_font_montserrat_14 : &lv_font_montserrat_12);

    lv_obj_t *tbl_card = _info_panel(s_content, 0, body_y, tbl_w, body_h,
                                     0x11131A, UI_CARD_RADIUS);
    _info_label(tbl_card, "THEORETICAL BEST", margin, wide ? 16 : 10,
                UI_COLOR_TEXT_MUTED, wide ? &lv_font_montserrat_14 : &lv_font_montserrat_12);
    _info_label(tbl_card, "LAP TARGET", margin, wide ? 48 : 31,
                UI_COLOR_TEXT_PRIMARY, wide ? &lv_font_montserrat_16 : &lv_font_montserrat_14);
    char lap[24];
    _format_seconds(s_layout.tbl_lap_time, lap, sizeof(lap));
    _info_label(tbl_card, lap, margin, wide ? 76 : 51,
                UI_COLOR_SUCCESS, wide ? &lv_font_montserrat_48 : &lv_font_montserrat_28);
    _info_label(tbl_card, "SECTOR SUM REFERENCE", margin,
                body_h - (wide ? 30 : 23), UI_COLOR_TEXT_MUTED,
                &lv_font_montserrat_12);

    lv_obj_t *sector_card = _info_panel(s_content, sector_x, body_y, sector_w,
                                        body_h, 0x11131A, UI_CARD_RADIUS);
    _info_label(sector_card, "SECTOR BENCHMARKS", margin, wide ? 14 : 9,
                UI_COLOR_TEXT_MUTED, wide ? &lv_font_montserrat_14 : &lv_font_montserrat_12);

    int sector_count = s_layout.sector_count;
    if (sector_count > TRACK_ENGINE_MAX_SECTORS) sector_count = TRACK_ENGINE_MAX_SECTORS;
    const int cols = wide ? 2 : 1;
    const int row_gap = wide ? 8 : 5;
    const int row_h = wide ? 34 : 25;
    const int row_y = wide ? 45 : 32;
    const int col_gap = wide ? 10 : 0;
    const int row_w = (sector_w - 2 * margin - (cols - 1) * col_gap) / cols;
    for (int i = 0; i < sector_count; ++i) {
        const int col = i % cols;
        const int row = i / cols;
        const int x = margin + col * (row_w + col_gap);
        const int y = row_y + row * (row_h + row_gap);
        lv_obj_t *row_card = _info_panel(sector_card, x, y, row_w, row_h,
                                         0x1D202A, 8);
        char sector_name[8];
        char time[20];
        snprintf(sector_name, sizeof(sector_name), "S%d", i + 1);
        _format_seconds(s_layout.tbl_sector_times[i], time, sizeof(time));
        _info_label(row_card, sector_name, 10, wide ? 7 : 5,
                    UI_COLOR_PAIRING, wide ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
        lv_obj_t *time_label = _info_label(row_card, time, 0, 0,
                                           UI_COLOR_TEXT_PRIMARY,
                                           wide ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
        lv_obj_align(time_label, LV_ALIGN_RIGHT_MID, -10, 0);
    }

    lv_obj_t *footer = _info_panel(s_content, 0, footer_y, content_w, footer_h,
                                   0x11131A, UI_CARD_RADIUS);
    char last_text[96];
    snprintf(last_text, sizeof(last_text), "LAST LAP  %s    •    LAST GAP  %s",
             track_engine_get_last_lap_time(), track_engine_get_last_sector_gap());
    _info_label(footer, last_text, margin, wide ? 16 : 9,
                UI_COLOR_WARNING, wide ? &lv_font_montserrat_16 : &lv_font_montserrat_12);
}

static void _render_tab(void)
{
    lv_obj_clean(s_content);
    if (s_info_tab) _render_info_tab();
    else _render_map_tab();
}

static void _on_map_tab(lv_event_t *event)
{
    (void)event;
    if (!ui_lock(20)) return;
    s_info_tab = false;
    _set_tab_style(s_map_tab_button, true);
    _set_tab_style(s_info_tab_button, false);
    _render_tab();
    ui_unlock();
}

static void _on_info_tab(lv_event_t *event)
{
    (void)event;
    if (!ui_lock(20)) return;
    s_info_tab = true;
    _set_tab_style(s_map_tab_button, false);
    _set_tab_style(s_info_tab_button, true);
    _render_tab();
    ui_unlock();
}

static lv_obj_t *_make_tab(lv_obj_t *parent, int x, int width, const char *text,
                           bool active, lv_event_cb_t callback)
{
    lv_obj_t *button = lv_btn_create(parent);
    lv_obj_set_size(button, width, UI_RES_CLASS_WIDESCREEN ? 42 : 30);
    lv_obj_set_pos(button, x, UI_RES_CLASS_WIDESCREEN ? 3 : 4);
    _set_tab_style(button, active);
    lv_obj_set_style_radius(button, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(button, callback, LV_EVENT_CLICKED, NULL);
    lv_obj_t *label = lv_label_create(button);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_color(label, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_set_style_text_font(label,
                               UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16
                                                       : &lv_font_montserrat_12,
                               0);
    lv_obj_align(label, LV_ALIGN_CENTER, 0, 0);
    return button;
}

static void _on_back_home(lv_event_t *event)
{
    (void)event;
    ui_events_on_navigate_home();
}

void ui_show_track_view(void)
{
    ui_home_deactivate();
    ui_lock(-1);
    ui_track_refresh_layout();
    s_track_view_active = true;
    s_info_tab = false;

    lv_obj_t *scr = lv_scr_act();
    lv_obj_clean(scr);
    lv_obj_set_style_bg_color(scr, lv_color_hex(UI_COLOR_BG_DARK), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, UI_HOR_RES, UI_HEADER_HEIGHT);
    _style_surface(header, UI_COLOR_SURFACE, UI_COLOR_BORDER, 0);

    lv_obj_t *back = lv_btn_create(header);
    lv_obj_set_size(back, UI_SCALE_X(92), UI_HEADER_HEIGHT - 8);
    lv_obj_set_pos(back, UI_SCALE_X(8), 4);
    lv_obj_set_style_bg_color(back, lv_color_hex(0x242430), 0);
    lv_obj_set_style_radius(back, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(back, _on_back_home, LV_EVENT_CLICKED, NULL);
    lv_obj_t *back_label = lv_label_create(back);
    lv_label_set_text(back_label, "‹ HOME");
    lv_obj_set_style_text_color(back_label, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_center(back_label);

    lv_obj_t *title = lv_label_create(header);
    lv_label_set_text(title, "ACTIVE TRACK");
    lv_obj_set_style_text_color(title, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_set_style_text_font(title,
                               UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_28
                                                       : &lv_font_montserrat_16,
                               0);
    lv_obj_align(title, LV_ALIGN_CENTER, 0, 0);

    lv_obj_t *change = lv_btn_create(header);
    const int change_w = UI_RES_CLASS_WIDESCREEN ? UI_SCALE_X(122) : UI_SCALE_X(92);
    lv_obj_set_size(change, change_w, UI_HEADER_HEIGHT - UI_SCALE_Y(10));
    lv_obj_align(change, LV_ALIGN_RIGHT_MID, -UI_SCALE_X(8), 0);
    lv_obj_set_style_bg_color(change, lv_color_hex(0x242430), 0);
    lv_obj_set_style_border_color(change, lv_color_hex(UI_COLOR_PRIMARY), 0);
    lv_obj_set_style_border_width(change, 1, 0);
    lv_obj_set_style_radius(change, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(change, _on_change_track_clicked, LV_EVENT_CLICKED, NULL);
    lv_obj_t *change_label = lv_label_create(change);
    lv_label_set_text(change_label, "CHANGE TRACK");
    lv_obj_set_style_text_color(change_label, lv_color_hex(UI_COLOR_PRIMARY), 0);
    lv_obj_set_style_text_font(change_label,
                               UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_12
                                                       : &lv_font_montserrat_12,
                               0);
    lv_obj_center(change_label);

    lv_obj_t *tabs = lv_obj_create(scr);
    lv_obj_set_size(tabs, UI_HOR_RES, UI_RES_CLASS_WIDESCREEN ? 48 : 38);
    lv_obj_set_pos(tabs, 0, UI_HEADER_HEIGHT);
    lv_obj_set_style_bg_color(tabs, lv_color_hex(UI_COLOR_SURFACE), 0);
    lv_obj_set_style_border_width(tabs, 0, 0);
    lv_obj_clear_flag(tabs, LV_OBJ_FLAG_SCROLLABLE);
    const int tab_margin = UI_RES_CLASS_WIDESCREEN ? UI_SCALE_X(12) : UI_SCALE_X(8);
    const int tab_gap = UI_RES_CLASS_WIDESCREEN ? UI_SCALE_X(10) : UI_SCALE_X(6);
    const int tab_width = (UI_HOR_RES - 2 * tab_margin - tab_gap) / 2;
    s_map_tab_button = _make_tab(tabs, tab_margin, tab_width,
                                 "MAP  /  LIVE LAYOUT", true, _on_map_tab);
    s_info_tab_button = _make_tab(tabs, tab_margin + tab_width + tab_gap, tab_width,
                                  "INFO  /  TBL", false, _on_info_tab);

    s_content = lv_obj_create(scr);
    lv_obj_set_size(s_content, UI_HOR_RES - UI_SCALE_X(24),
                    UI_VER_RES - UI_HEADER_HEIGHT - (UI_RES_CLASS_WIDESCREEN ? 48 : 38) - UI_SCALE_Y(16));
    lv_obj_set_pos(s_content, UI_SCALE_X(12),
                   UI_HEADER_HEIGHT + (UI_RES_CLASS_WIDESCREEN ? 48 : 38) + UI_SCALE_Y(8));
    lv_obj_set_style_border_width(s_content, 0, 0);
    lv_obj_set_style_pad_all(s_content, 0, 0);
    lv_obj_set_style_bg_opa(s_content, LV_OPA_TRANSP, 0);
    lv_obj_clear_flag(s_content, LV_OBJ_FLAG_SCROLLABLE);
    _render_tab();

    ui_unlock();
}

static void _on_cached_track_selected(lv_event_t *event)
{
    if (!event || !event->target) return;
    int32_t track_id = (int32_t)(intptr_t)lv_event_get_user_data(event);
    ui_events_on_select_track(track_id);
}

void ui_show_track_selector(void)
{
    ui_home_deactivate();
    ui_track_view_deactivate();
    ui_lock(-1);

    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr, lv_color_hex(UI_COLOR_BG_DARK), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_set_scroll_dir(scr, LV_DIR_VER);

    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, UI_HOR_RES, UI_HEADER_HEIGHT);
    _style_surface(header, UI_COLOR_SURFACE, UI_COLOR_BORDER, 0);
    lv_obj_t *back = lv_btn_create(header);
    lv_obj_set_size(back, UI_SCALE_X(92), UI_HEADER_HEIGHT - 8);
    lv_obj_set_pos(back, UI_SCALE_X(8), 4);
    lv_obj_set_style_bg_color(back, lv_color_hex(0x242430), 0);
    lv_obj_set_style_radius(back, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(back, _on_back_home, LV_EVENT_CLICKED, NULL);
    lv_obj_t *back_label = lv_label_create(back);
    lv_label_set_text(back_label, "‹ BACK");
    lv_obj_set_style_text_color(back_label, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_center(back_label);

    lv_obj_t *title = lv_label_create(header);
    lv_label_set_text(title, "CACHED TRACKS");
    lv_obj_set_style_text_color(title, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_set_style_text_font(title,
                               UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_28
                                                       : &lv_font_montserrat_16,
                               0);
    lv_obj_align(title, LV_ALIGN_CENTER, 0, 0);

    network_cached_track_t cached[NETWORK_TRACK_CATALOG_MAX_TRACKS] = {0};
    int count = 0;
    int32_t active_id = 0;
    esp_err_t list_ret = network_list_cached_tracks(cached,
                                                    NETWORK_TRACK_CATALOG_MAX_TRACKS,
                                                    &count, &active_id);
    const int margin = UI_RES_CLASS_WIDESCREEN ? 24 : 10;
    const int gap = UI_RES_CLASS_WIDESCREEN ? 10 : 6;
    const int button_h = UI_RES_CLASS_WIDESCREEN ? 58 : 38;
    int y = UI_HEADER_HEIGHT + margin;
    if (list_ret != ESP_OK || count == 0) {
        lv_obj_t *empty = lv_label_create(scr);
        lv_label_set_text(empty, "NO CACHED TRACKS\nRUN CLOUD SYNC TO LOAD YOUR TRACKS");
        lv_obj_set_style_text_color(empty, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
        lv_obj_set_style_text_align(empty, LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_set_width(empty, UI_HOR_RES - 2 * margin);
        lv_obj_set_pos(empty, margin, y + UI_SCALE_Y(50));
    } else {
        for (int i = 0; i < count; ++i) {
            lv_obj_t *button = lv_btn_create(scr);
            lv_obj_set_size(button, UI_HOR_RES - 2 * margin, button_h);
            lv_obj_set_pos(button, margin, y);
            bool active = cached[i].track_id == active_id;
            lv_obj_set_style_bg_color(button,
                                      lv_color_hex(active ? 0x173D2A : 0x242430), 0);
            lv_obj_set_style_border_color(button,
                                          lv_color_hex(active ? UI_COLOR_SUCCESS : UI_COLOR_BORDER), 0);
            lv_obj_set_style_border_width(button, active ? 2 : 1, 0);
            lv_obj_set_style_radius(button, UI_BTN_RADIUS, 0);
            lv_obj_add_event_cb(button, _on_cached_track_selected, LV_EVENT_CLICKED,
                                (void *)(intptr_t)cached[i].track_id);
            char label_text[96];
            snprintf(label_text, sizeof(label_text), "%s%s",
                     active ? "ACTIVE  •  " : "", cached[i].track_name);
            lv_obj_t *label = lv_label_create(button);
            lv_label_set_text(label, label_text);
            lv_obj_set_style_text_color(label,
                                        lv_color_hex(active ? UI_COLOR_SUCCESS : UI_COLOR_TEXT_PRIMARY), 0);
            lv_obj_set_style_text_font(label,
                                       UI_RES_CLASS_WIDESCREEN ? &lv_font_montserrat_16
                                                               : &lv_font_montserrat_14,
                                       0);
            lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
            lv_obj_set_width(label, UI_HOR_RES - 2 * margin - UI_SCALE_X(24));
            lv_obj_center(label);
            y += button_h + gap;
        }
    }

    ui_load_screen(scr);
    ui_unlock();
}

void ui_track_view_deactivate(void)
{
    s_track_view_active = false;
    s_content = NULL;
    s_map_panel = NULL;
    s_position_halo = NULL;
    s_position_dot = NULL;
}

void ui_track_update_position(double lat, double lon, bool valid)
{
    if (!s_track_view_active || s_info_tab || !s_map_panel ||
        !s_position_halo || !s_position_dot || !ui_lock(5)) return;

    bool in_bounds = valid && s_layout.has_layout &&
                     isfinite(lat) && isfinite(lon) &&
                     s_layout.max_lat > s_layout.min_lat &&
                     s_layout.max_lon > s_layout.min_lon;
    if (!in_bounds) {
        lv_obj_add_flag(s_position_halo, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_position_dot, LV_OBJ_FLAG_HIDDEN);
        ui_unlock();
        return;
    }

    double fx = (lon - s_layout.min_lon) / (s_layout.max_lon - s_layout.min_lon);
    double fy = (s_layout.max_lat - lat) / (s_layout.max_lat - s_layout.min_lat);
    if (fx < -0.05 || fx > 1.05 || fy < -0.05 || fy > 1.05) {
        lv_obj_add_flag(s_position_halo, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_position_dot, LV_OBJ_FLAG_HIDDEN);
        ui_unlock();
        return;
    }
    if (fx < 0.0) fx = 0.0;
    if (fx > 1.0) fx = 1.0;
    if (fy < 0.0) fy = 0.0;
    if (fy > 1.0) fy = 1.0;

    track_layout_point_t point = {
        .x = (uint16_t)lround(fx * 1000.0),
        .y = (uint16_t)lround(fy * 1000.0),
    };
    lv_point_t mapped;
    _map_point(point, lv_obj_get_width(s_map_panel),
               lv_obj_get_height(s_map_panel), &mapped);
    int halo_size = UI_RES_CLASS_WIDESCREEN ? 32 : 20;
    int dot_size = UI_RES_CLASS_WIDESCREEN ? 12 : 8;
    lv_obj_set_pos(s_position_halo, mapped.x - halo_size / 2, mapped.y - halo_size / 2);
    lv_obj_set_pos(s_position_dot, mapped.x - dot_size / 2, mapped.y - dot_size / 2);
    lv_obj_clear_flag(s_position_halo, LV_OBJ_FLAG_HIDDEN);
    lv_obj_clear_flag(s_position_dot, LV_OBJ_FLAG_HIDDEN);
    ui_unlock();
}
