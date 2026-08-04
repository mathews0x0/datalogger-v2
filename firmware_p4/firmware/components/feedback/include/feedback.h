/**
 * @file feedback.h
 * @brief Rider Visual Feedback State Machine Component Header
 */

#ifndef FEEDBACK_H
#define FEEDBACK_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Public feedback states used by the application event bridge. */
typedef enum {
    FEEDBACK_STATE_IDLE = 0,
    FEEDBACK_STATE_LOGGING,
    FEEDBACK_STATE_SECTOR_FAST,
    FEEDBACK_STATE_SECTOR_NEUTRAL,
    FEEDBACK_STATE_SECTOR_SLOW,
    FEEDBACK_STATE_LAP_COMPLETE,
    FEEDBACK_STATE_SYNC,
    FEEDBACK_STATE_ERROR,
} feedback_state_t;

/**
 * @brief Initialize feedback state machine and visual indicators.
 *
 * @return esp_err_t ESP_OK on success, or error code.
 */
esp_err_t feedback_init(void);

/**
 * @brief Set main feedback state machine mode.
 *
 * @param state Feedback state enum value.
 */
void feedback_set_state(int state);

/**
 * @brief Trigger temporary visual overlay on screen/LEDs.
 *
 * @param overlay Overlay type enum value.
 * @param duration_ms Overlay display duration in milliseconds.
 */
void feedback_set_overlay(int overlay, int duration_ms);

/**
 * @brief Set global brightness level for visual indicators.
 *
 * @param brightness Brightness level from 0.0 (off) to 1.0 (max).
 */
void feedback_set_brightness(float brightness);

/**
 * @brief Periodic tick handler for feedback animation and timed overlays.
 * Called regularly from UI task loop.
 */
void feedback_tick(void);

#ifdef __cplusplus
}
#endif

#endif /* FEEDBACK_H */
