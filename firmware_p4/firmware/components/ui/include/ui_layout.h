/**
 * @file ui_layout.h
 * @brief Responsive Layout & Design Token System for RaceSense UI
 *
 * Provides resolution-agnostic scaling macros, layout rules, and font definitions
 * to enable zero-rewrite portability across multiple target displays:
 *   - 800x480 (4.3" Waveshare P4 ST7701 MIPI-DSI) [Primary Target]
 *   - 480x320 (3.5" ILI9488 SPI / Parallel on ESP32-S3 or P4)
 *   - 320x240 (2.8" ILI9341 SPI on ESP32-S3 or P4)
 */

#ifndef UI_LAYOUT_H
#define UI_LAYOUT_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Display Resolution Classes & Config Target Integration
 * ────────────────────────────────────────────────────────────────────────*/
#if defined(CONFIG_UI_DISPLAY_RES_320_240) || defined(CONFIG_IDF_TARGET_ESP32S3)
    #define UI_HOR_RES              320
    #define UI_VER_RES              240
    #define UI_RES_CLASS_COMPACT    1
    #define UI_RES_CLASS_MEDIUM     0
    #define UI_RES_CLASS_WIDESCREEN 0
#elif defined(CONFIG_UI_DISPLAY_RES_480_320)
    #define UI_HOR_RES              480
    #define UI_VER_RES              320
    #define UI_RES_CLASS_COMPACT    0
    #define UI_RES_CLASS_MEDIUM     1
    #define UI_RES_CLASS_WIDESCREEN 0
#else
    /* Default to Flagship ESP32-P4 4.3" Widescreen (800x480) */
    #define UI_HOR_RES              800
    #define UI_VER_RES              480
    #define UI_RES_CLASS_COMPACT    0
    #define UI_RES_CLASS_MEDIUM     0
    #define UI_RES_CLASS_WIDESCREEN 1
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Dynamic Relative Scaling Macros (Based on 800x480 Reference Frame)
 * ────────────────────────────────────────────────────────────────────────*/
/** @brief Scale an X/Width pixel coordinate from reference 800px width */
#define UI_SCALE_X(x)   (((x) * UI_HOR_RES) / 800)

/** @brief Scale a Y/Height pixel coordinate from reference 480px height */
#define UI_SCALE_Y(y)   (((y) * UI_VER_RES) / 480)

/** @brief Percentage of screen horizontal resolution */
#define UI_PCT_X(pct)   (((pct) * UI_HOR_RES) / 100)

/** @brief Percentage of screen vertical resolution */
#define UI_PCT_Y(pct)   (((pct) * UI_VER_RES) / 100)

/* ──────────────────────────────────────────────────────────────────────────
 * Layout Containers & Spacing Tokens
 * ────────────────────────────────────────────────────────────────────────*/
#if UI_RES_CLASS_WIDESCREEN
    /* 800x480: 2-Column Widescreen Grid */
    #define UI_HEADER_HEIGHT        50
    #define UI_FOOTER_HEIGHT        80
    #define UI_CONTENT_HEIGHT       (UI_VER_RES - UI_HEADER_HEIGHT - UI_FOOTER_HEIGHT)
    
    #define UI_GRID_COLS            2
    #define UI_CARD_WIDTH           380
    #define UI_CARD_HEIGHT          165
    #define UI_CARD_GAP             16
    #define UI_CARD_PADDING         16
    #define UI_BTN_RADIUS           12
    #define UI_CARD_RADIUS          16
    
    #define UI_BTN_WIDTH_PRIMARY    340
    #define UI_BTN_WIDTH_SECONDARY  180
    #define UI_BTN_HEIGHT           60
    
    #define UI_FLEX_FLOW_GRID       LV_FLEX_FLOW_ROW_WRAP
    
#elif UI_RES_CLASS_MEDIUM
    /* 480x320: Medium Stacked / 2-Column Hybrid Grid */
    #define UI_HEADER_HEIGHT        36
    #define UI_FOOTER_HEIGHT        56
    #define UI_CONTENT_HEIGHT       (UI_VER_RES - UI_HEADER_HEIGHT - UI_FOOTER_HEIGHT)
    
    #define UI_GRID_COLS            1
    #define UI_CARD_WIDTH           450
    #define UI_CARD_HEIGHT          110
    #define UI_CARD_GAP             10
    #define UI_CARD_PADDING         10
    #define UI_BTN_RADIUS           8
    #define UI_CARD_RADIUS          12
    
    #define UI_BTN_WIDTH_PRIMARY    220
    #define UI_BTN_WIDTH_SECONDARY  120
    #define UI_BTN_HEIGHT           44
    
    #define UI_FLEX_FLOW_GRID       LV_FLEX_FLOW_COLUMN
    
#else
    /* 320x240: Ultra-Compact Single-Column Stack */
    #define UI_HEADER_HEIGHT        28
    #define UI_FOOTER_HEIGHT        44
    #define UI_CONTENT_HEIGHT       (UI_VER_RES - UI_HEADER_HEIGHT - UI_FOOTER_HEIGHT)
    
    #define UI_GRID_COLS            1
    #define UI_CARD_WIDTH           300
    #define UI_CARD_HEIGHT          85
    #define UI_CARD_GAP             6
    #define UI_CARD_PADDING         8
    #define UI_BTN_RADIUS           6
    #define UI_CARD_RADIUS          8
    
    #define UI_BTN_WIDTH_PRIMARY    150
    #define UI_BTN_WIDTH_SECONDARY  80
    #define UI_BTN_HEIGHT           36
    
    #define UI_FLEX_FLOW_GRID       LV_FLEX_FLOW_COLUMN
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Responsive Typography Tokens
 * ────────────────────────────────────────────────────────────────────────*/
#if UI_RES_CLASS_WIDESCREEN
    #define UI_FONT_HERO_SIZE       140  /**< Live Logging hero lap time font */
    #define UI_FONT_TITLE_SIZE      24   /**< Screen headers and primary titles */
    #define UI_FONT_BODY_SIZE       16   /**< Body telemetry readings and status */
    #define UI_FONT_SMALL_SIZE      12   /**< Subtext and units (Hz, SATS, G) */
#elif UI_RES_CLASS_MEDIUM
    #define UI_FONT_HERO_SIZE       72
    #define UI_FONT_TITLE_SIZE      18
    #define UI_FONT_BODY_SIZE       14
    #define UI_FONT_SMALL_SIZE      10
#else
    #define UI_FONT_HERO_SIZE       48
    #define UI_FONT_TITLE_SIZE      14
    #define UI_FONT_BODY_SIZE       12
    #define UI_FONT_SMALL_SIZE      9
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Master Color Palette Tokens (Motorsport Dark Theme)
 * ────────────────────────────────────────────────────────────────────────*/
#define UI_COLOR_BG_DARK            0x09090D  /**< Deep Asphalt Dark background   */
#define UI_COLOR_SURFACE            0x1A1A22  /**< Glassmorphism card background  */
#define UI_COLOR_BORDER             0x2A2A35  /**< Card border contrast           */
#define UI_COLOR_PRIMARY            0xFF6B35  /**< RaceSense Orange (Primary)     */
#define UI_COLOR_PRIMARY_PRESS      0xE55A25  /**< Active button pressed tint     */
#define UI_COLOR_SUCCESS            0x00D26A  /**< Emerald Neon Green (Ready/Faster)*/
#define UI_COLOR_WARNING            0xFFB800  /**< Warm Amber (Acquiring/Searching) */
#define UI_COLOR_DANGER             0xFF3B30  /**< Apex Red (Error/Slower Delta)  */
#define UI_COLOR_PAIRING            0x007AFF  /**< Electric Blue (WiFi / Captive) */
#define UI_COLOR_TEXT_PRIMARY       0xFFFFFF  /**< High contrast text             */
#define UI_COLOR_TEXT_MUTED         0x8E8E93  /**< Secondary labels and units     */

#ifdef __cplusplus
}
#endif

#endif /* UI_LAYOUT_H */
