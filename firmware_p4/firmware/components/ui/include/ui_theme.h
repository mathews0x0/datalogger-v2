/**
 * @file ui_theme.h
 * @brief Motorsport Dark Theme Styling Helper for LVGL Widgets
 */

#ifndef UI_THEME_H
#define UI_THEME_H

#include "ui_layout.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize custom RaceSense theme style objects.
 * Call once before constructing UI screens.
 */
void ui_theme_init(void);

#ifdef __cplusplus
}
#endif

#endif /* UI_THEME_H */
