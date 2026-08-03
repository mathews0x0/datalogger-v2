/**
 * @file bsp_display_target.h
 * @brief Auto-Detecting Multi-Target Display & Touch Configuration
 *
 * Automatically detects whether the build target is ESP32-S3 or ESP32-P4:
 *
 *   Target 0: Waveshare ESP32-P4 4.3" — ST7701 MIPI-DSI 2-lane 480×800 + GT911 I2C
 *   Target 1: Generic 3.5" — ILI9488 SPI 480×320 + FT6336 I2C
 *   Target 2: RaceSense ESP32-S3 2.8" — ILI9341 SPI 320×240 + XPT2046 SPI
 *
 * Switching platforms is 100% automatic via idf.py:
 *   idf.py set-target esp32s3   -> Selects Target 2 (ILI9341 + S3 pinout)
 *   idf.py set-target esp32p4   -> Selects Target 0 (ST7701 + P4 pinout)
 */

#ifndef BSP_DISPLAY_TARGET_H
#define BSP_DISPLAY_TARGET_H

#include "sdkconfig.h"

/* ── AUTO-SELECT DISPLAY TARGET BASED ON ESP-IDF CHIP TARGET ──────────── */
#ifndef BSP_DISPLAY_TARGET
  #if CONFIG_IDF_TARGET_ESP32S3
    #define BSP_DISPLAY_TARGET   2   /**< ESP32-S3: 2.8" ILI9341 SPI (320x240) */
  #elif CONFIG_IDF_TARGET_ESP32P4
    #define BSP_DISPLAY_TARGET   0   /**< ESP32-P4: 4.3" ST7701 MIPI-DSI (800x480) */
  #else
    #define BSP_DISPLAY_TARGET   0
  #endif
#endif

/* ── Target 0: Waveshare P4 4.3" — ST7701 MIPI-DSI + GT911 ────────────*/
#if BSP_DISPLAY_TARGET == 0
  #define BSP_LCD_H_RES            480
  #define BSP_LCD_V_RES            800
  #define BSP_LCD_COLOR_FORMAT     LV_COLOR_FORMAT_RGB565
  #define BSP_TOUCH_I2C_NUM        I2C_NUM_0
  #define BSP_TOUCH_I2C_ADDR       0x5D       /**< GT911 default addr */
  #define BSP_TOUCH_INT_GPIO       (-1)
  #define BSP_TOUCH_RST_GPIO       23
  #define BSP_LCD_RST_GPIO         27
  #define BSP_LCD_BL_GPIO          26
  #define BSP_MIPI_DSI_LANE_NUM    2
  #define BSP_MIPI_DSI_LANE_MBR    500
  #define BSP_LCD_DRAW_BUF_SIZE    (BSP_LCD_H_RES * BSP_LCD_V_RES / 10)
  #define BSP_LCD_DRAW_BUF_DOUBLE  1

/* ── Target 1: Generic 3.5" SPI — ILI9488 + FT6336 ───────────────────*/
#elif BSP_DISPLAY_TARGET == 1
  #define BSP_LCD_H_RES            480
  #define BSP_LCD_V_RES            320
  #define BSP_LCD_COLOR_FORMAT     LV_COLOR_FORMAT_RGB565
  #define BSP_SPI_HOST             SPI2_HOST
  #define BSP_LCD_SPI_MOSI         11
  #define BSP_LCD_SPI_CLK          12
  #define BSP_LCD_SPI_CS           10
  #define BSP_LCD_DC_GPIO          13
  #define BSP_LCD_RST_GPIO         14
  #define BSP_LCD_BL_GPIO          2
  #define BSP_LCD_SPI_MHZ          40
  #define BSP_TOUCH_I2C_NUM        I2C_NUM_0
  #define BSP_TOUCH_I2C_ADDR       0x38
  #define BSP_TOUCH_INT_GPIO       (-1)
  #define BSP_TOUCH_RST_GPIO       (-1)
  #define BSP_LCD_DRAW_BUF_SIZE    (BSP_LCD_H_RES * 20)
  #define BSP_LCD_DRAW_BUF_DOUBLE  0

/* ── Target 2: RaceSense S3 2.8" SPI — ILI9341 + XPT2046 (RS-Core V4.2) ─*/
#elif BSP_DISPLAY_TARGET == 2
  #define BSP_LCD_H_RES            320
  #define BSP_LCD_V_RES            240
  #define BSP_LCD_COLOR_FORMAT     LV_COLOR_FORMAT_RGB565
  #define BSP_SPI_HOST             SPI2_HOST
  #define BSP_LCD_SPI_MOSI         16         /**< S3 TFT_DIN */
  #define BSP_LCD_SPI_MISO         9          /**< S3 TFT_OUT */
  #define BSP_LCD_SPI_CLK          15         /**< S3 TFT_CLK */
  #define BSP_LCD_SPI_CS           5          /**< S3 TFT_CS  */
  #define BSP_LCD_DC_GPIO          6          /**< S3 TFT_DC  */
  #define BSP_LCD_RST_GPIO         42         /**< S3 TFT_RST */
  #define BSP_LCD_BL_GPIO          (-1)       /**< Tied 3V3   */
  #define BSP_LCD_SPI_MHZ          15
  /* XPT2046 resistive touch on same SPI bus */
  #define BSP_TOUCH_SPI_CS         7          /**< S3 TOUCH_CS  */
  #define BSP_TOUCH_IRQ_GPIO       38         /**< S3 TOUCH_IRQ */
  #define BSP_LCD_DRAW_BUF_SIZE    (BSP_LCD_H_RES * 50)
  #define BSP_LCD_DRAW_BUF_DOUBLE  0

#else
  #error "BSP_DISPLAY_TARGET must be 0, 1, or 2"
#endif

#endif /* BSP_DISPLAY_TARGET_H */
