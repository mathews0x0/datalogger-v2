#pragma once
#include <stdbool.h>
#include <stdint.h>

bool touch_calibration_start_if_needed(void);
void touch_calibration_process(uint16_t *x, uint16_t *y, uint8_t points);
