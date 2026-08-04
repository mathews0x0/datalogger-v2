/**
 * @file ui_events.h
 * @brief Resolution-Agnostic UI Touch Event & Backend Dispatch Layer
 *
 * Provides decoupled event handlers that route UI touch interactions (button clicks,
 * switch toggles, modal confirms) to system state transitions, storage operations,
 * wireless networking functions, and non-volatile device configurations.
 */

#ifndef UI_EVENTS_H
#define UI_EVENTS_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief System UI Action Event Types
 */
typedef enum {
    UI_EVENT_START_LOG_CLICKED = 0,   /**< User triggered 'START LOG' from Home     */
    UI_EVENT_STOP_LOG_HELD,           /**< User held 'STOP LOG' for 2s on Logging   */
    UI_EVENT_SYNC_CLICKED,            /**< User triggered 'SYNC' mode from Home     */
    UI_EVENT_SETTINGS_CLICKED,        /**< User clicked gear icon from Home         */
    UI_EVENT_BACK_CLICKED,            /**< User clicked 'BACK' / 'CANCEL' to return */
    UI_EVENT_WIFI_SETUP_CLICKED,      /**< User triggered Captive Portal from Setup */
    UI_EVENT_TRACK_SELECT_CLICKED,    /**< User opened track selection menu         */
    UI_EVENT_TRACK_VIEW_CLICKED,      /**< User opened active-track viewer         */
    UI_EVENT_IMU_CALIB_CLICKED,       /**< User started IMU Calibration Wizard      */
    UI_EVENT_CALIB_NEXT_STAGE_CLICKED,/**< User advanced calibration stage in wizard*/
    UI_EVENT_AUTO_LOG_TOGGLED,        /**< User toggled Auto-Logging switch         */
    UI_EVENT_SYNC_CANCEL_CLICKED,     /**< User cancelled active cloud upload sync  */
    UI_EVENT_SYNC_DONE_CLICKED,       /**< User dismissed sync complete screen      */
    UI_EVENT_HARDWARE_DEBUG_CLICKED,  /**< User opened GPS/IMU hardware debug       */
    UI_EVENT_DATA_CLICKED,            /**< User opened pending session data browser */
} ui_event_type_t;

/**
 * @brief Prototype for general application state machine event listener
 * @param event The triggered UI event type
 * @param param Optional integer or pointer parameter (e.g., toggle state boolean)
 */
typedef void (*ui_event_listener_cb_t)(ui_event_type_t event, void *param);

/**
 * @brief Register a system-wide listener callback for UI touch events.
 *
 * Typically invoked by `main.c` during application boot to bind UI actions
 * directly into the top-level application state machine.
 *
 * @param cb Listener function callback pointer.
 * @return ESP_OK on successful registration.
 */
esp_err_t ui_events_register_listener(ui_event_listener_cb_t cb);

/**
 * @brief Dispatch a touch action event to the registered application listener.
 *
 * Safe to call directly from LVGL widget callback handlers within UI screen files.
 *
 * @param event The event identifier to emit.
 * @param param Optional payload argument (e.g., bool state for switches).
 */
void ui_events_dispatch(ui_event_type_t event, void *param);

/* ──────────────────────────────────────────────────────────────────────────
 * Direct Event Trigger Convenience Helpers (Called from LVGL Event Callbacks)
 * ────────────────────────────────────────────────────────────────────────*/

/** @brief Helper: Start Logging button clicked */
void ui_events_on_start_log(void);

/** @brief Helper: Stop Logging button held and confirmed */
void ui_events_on_stop_log(void);

/** @brief Helper: Sync mode button clicked */
void ui_events_on_sync_start(void);

/** @brief Helper: Settings screen button clicked */
void ui_events_on_open_settings(void);

/** @brief Open live GPS/IMU hardware diagnostics */
void ui_events_on_open_hardware_debug(void);

/** @brief Open the pending session file browser and sync controls. */
void ui_events_on_open_data(void);

/** @brief Helper: Navigate Back / Cancel to Home dashboard */
void ui_events_on_navigate_home(void);

/** @brief Open the active-track viewer from the Home preview. */
void ui_events_on_open_track_view(void);

/** @brief Helper: Captive portal provisioning started */
void ui_events_on_start_captive_portal(void);

/** @brief Helper: Auto-log setting toggle switch modified */
void ui_events_on_toggle_autolog(bool enabled);

/** @brief Helper: Advance IMU calibration step */
void ui_events_on_calib_next_step(void);

/** @brief Helper: Cancel active sync */
void ui_events_on_cancel_sync(void);

/** @brief Helper: Close captive portal */
void ui_events_on_close_captive_portal(void);

/** @brief Helper: Trigger sector flash overlay */
void ui_events_on_sector_flash(int color_type, const char *label);

#ifdef __cplusplus
}
#endif

#endif /* UI_EVENTS_H */
