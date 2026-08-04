/**
 * @file ui_track.c
 * @brief Compact Home track preview and full-screen Track/Info viewer.
 */

#include "ui.h"
#include "ui_events.h"
#include "track_engine.h"

#include <math.h>
#include <stdio.h>

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
                         bool show_position)
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

    for (int i = 0; i < s_layout.sector_marker_count; ++i) {
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

void ui_track_preview_render(lv_obj_t *parent, int x, int y, int width, int height)
{
    if (!parent || width <= 0 || height <= 0) return;

    track_engine_get_display_layout(&s_layout);
    lv_obj_t *panel = lv_obj_create(parent);
    lv_obj_set_size(panel, width, height);
    lv_obj_set_pos(panel, x, y);
    _style_surface(panel, 0x11131A, UI_COLOR_BORDER, UI_CARD_RADIUS);
    lv_obj_set_style_pad_all(panel, 0, 0);
    _draw_layout(panel, width, height, false);

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

static void _set_tab_style(lv_obj_t *button, bool active)
{
    lv_obj_set_style_bg_color(button,
                              lv_color_hex(active ? UI_COLOR_PRIMARY : 0x242430), 0);
    lv_obj_set_style_border_color(button,
                                  lv_color_hex(active ? UI_COLOR_PRIMARY : UI_COLOR_BORDER), 0);
}

static void _render_map_tab(void)
{
    s_map_panel = lv_obj_create(s_content);
    lv_obj_set_size(s_map_panel, lv_pct(100), lv_pct(100));
    _style_surface(s_map_panel, 0x11131A, UI_COLOR_BORDER, UI_CARD_RADIUS);
    _draw_layout(s_map_panel, lv_obj_get_width(s_map_panel),
                 lv_obj_get_height(s_map_panel), true);

    lv_obj_t *legend = lv_label_create(s_map_panel);
    lv_label_set_text(legend, "● RIDER   ◆ SECTORS   ■ START / FINISH");
    lv_obj_set_style_text_color(legend, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
    lv_obj_align(legend, LV_ALIGN_BOTTOM_LEFT, UI_SCALE_X(14), -UI_SCALE_Y(10));
}

static void _render_info_tab(void)
{
    s_map_panel = NULL;
    lv_obj_set_style_bg_color(s_content, lv_color_hex(UI_COLOR_BG_DARK), 0);
    lv_obj_set_style_bg_opa(s_content, LV_OPA_COVER, 0);

    lv_obj_t *summary = lv_obj_create(s_content);
    lv_obj_set_size(summary, lv_pct(100), UI_RES_CLASS_WIDESCREEN ? 86 : 58);
    _style_surface(summary, 0x11131A, UI_COLOR_BORDER, UI_CARD_RADIUS);

    lv_obj_t *name = lv_label_create(summary);
    lv_label_set_text(name, track_engine_get_track_name());
    lv_obj_set_style_text_color(name, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
    lv_obj_align(name, LV_ALIGN_LEFT_MID, UI_SCALE_X(16), -UI_SCALE_Y(12));
    lv_obj_t *meta = lv_label_create(summary);
    char meta_text[64];
    snprintf(meta_text, sizeof(meta_text), "%d SECTORS  •  %s",
             s_layout.sector_count,
             s_layout.has_layout ? "LAYOUT READY" : "LAYOUT UNAVAILABLE");
    lv_label_set_text(meta, meta_text);
    lv_obj_set_style_text_color(meta, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
    lv_obj_align(meta, LV_ALIGN_LEFT_MID, UI_SCALE_X(16), UI_SCALE_Y(16));

    lv_obj_t *tbl_title = lv_label_create(s_content);
    lv_label_set_text(tbl_title, "THEORETICAL BEST LAP");
    lv_obj_set_style_text_color(tbl_title, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
    lv_obj_align(tbl_title, LV_ALIGN_TOP_LEFT, UI_SCALE_X(16),
                 UI_RES_CLASS_WIDESCREEN ? UI_SCALE_Y(104) : UI_SCALE_Y(70));

    lv_obj_t *tbl = lv_label_create(s_content);
    char lap[24];
    _format_seconds(s_layout.tbl_lap_time, lap, sizeof(lap));
    lv_label_set_text(tbl, lap);
    lv_obj_set_style_text_color(tbl, lv_color_hex(UI_COLOR_SUCCESS), 0);
    lv_obj_align(tbl, LV_ALIGN_TOP_LEFT, UI_SCALE_X(16),
                 UI_RES_CLASS_WIDESCREEN ? UI_SCALE_Y(124) : UI_SCALE_Y(88));

    lv_obj_t *sector_title = lv_label_create(s_content);
    lv_label_set_text(sector_title, "SECTOR BENCHMARKS");
    lv_obj_set_style_text_color(sector_title, lv_color_hex(UI_COLOR_TEXT_MUTED), 0);
    lv_obj_align(sector_title, LV_ALIGN_TOP_LEFT, UI_SCALE_X(190),
                 UI_RES_CLASS_WIDESCREEN ? UI_SCALE_Y(104) : UI_SCALE_Y(70));

    int sector_count = s_layout.sector_count;
    if (sector_count > TRACK_ENGINE_MAX_SECTORS) sector_count = TRACK_ENGINE_MAX_SECTORS;
    const int cols = UI_RES_CLASS_WIDESCREEN ? 2 : 1;
    const int row_h = UI_RES_CLASS_WIDESCREEN ? 34 : 24;
    const int start_y = UI_RES_CLASS_WIDESCREEN ? 128 : 92;
    const int col_w = UI_RES_CLASS_WIDESCREEN ? 250 : 140;
    for (int i = 0; i < sector_count; ++i) {
        int col = i % cols;
        int row = i / cols;
        char text[40];
        char time[20];
        _format_seconds(s_layout.tbl_sector_times[i], time, sizeof(time));
        snprintf(text, sizeof(text), "S%d     %s", i + 1, time);
        lv_obj_t *label = lv_label_create(s_content);
        lv_label_set_text(label, text);
        lv_obj_set_style_text_color(label, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
        lv_obj_set_pos(label, UI_SCALE_X(190) + col * UI_SCALE_X(col_w),
                       UI_SCALE_Y(start_y + row * row_h));
    }

    lv_obj_t *last = lv_label_create(s_content);
    char last_text[80];
    snprintf(last_text, sizeof(last_text), "LAST LAP  %s     LAST GAP  %s",
             track_engine_get_last_lap_time(), track_engine_get_last_sector_gap());
    lv_label_set_text(last, last_text);
    lv_obj_set_style_text_color(last, lv_color_hex(UI_COLOR_WARNING), 0);
    lv_obj_align(last, LV_ALIGN_BOTTOM_LEFT, UI_SCALE_X(16), -UI_SCALE_Y(12));
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
    lv_obj_set_size(button, width, UI_RES_CLASS_WIDESCREEN ? 38 : 30);
    lv_obj_set_pos(button, x, UI_RES_CLASS_WIDESCREEN ? 5 : 4);
    _set_tab_style(button, active);
    lv_obj_set_style_radius(button, UI_BTN_RADIUS, 0);
    lv_obj_add_event_cb(button, callback, LV_EVENT_CLICKED, NULL);
    lv_obj_t *label = lv_label_create(button);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_color(label, lv_color_hex(UI_COLOR_TEXT_PRIMARY), 0);
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
    track_engine_get_display_layout(&s_layout);
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
    lv_obj_align(title, LV_ALIGN_CENTER, 0, 0);

    lv_obj_t *track = lv_label_create(header);
    lv_label_set_text(track, track_engine_get_track_name());
    lv_obj_set_style_text_color(track, lv_color_hex(UI_COLOR_PRIMARY), 0);
    lv_obj_align(track, LV_ALIGN_RIGHT_MID, -UI_SCALE_X(14), 0);

    lv_obj_t *tabs = lv_obj_create(scr);
    lv_obj_set_size(tabs, UI_HOR_RES, UI_RES_CLASS_WIDESCREEN ? 48 : 38);
    lv_obj_set_pos(tabs, 0, UI_HEADER_HEIGHT);
    lv_obj_set_style_bg_color(tabs, lv_color_hex(UI_COLOR_SURFACE), 0);
    lv_obj_set_style_border_width(tabs, 0, 0);
    lv_obj_clear_flag(tabs, LV_OBJ_FLAG_SCROLLABLE);
    int tab_width = UI_RES_CLASS_WIDESCREEN ? 190 : 120;
    s_map_tab_button = _make_tab(tabs, UI_SCALE_X(12), tab_width,
                                 "TRACK MAP", true, _on_map_tab);
    s_info_tab_button = _make_tab(tabs, UI_SCALE_X(16) + tab_width, tab_width,
                                  "INFO / TBL", false, _on_info_tab);

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
