/* BMI323 is not fitted to the Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3 board. */

#include "bmi323.h"

esp_err_t bmi323_init(void) { return ESP_ERR_NOT_FOUND; }
esp_err_t bmi323_read_raw(bmi323_raw_t *raw) { (void)raw; return ESP_ERR_INVALID_STATE; }
esp_err_t bmi323_read_accel_gyro(float *ax, float *ay, float *az,
                                 float *gx, float *gy, float *gz)
{
    (void)ax; (void)ay; (void)az; (void)gx; (void)gy; (void)gz;
    return ESP_ERR_INVALID_STATE;
}
esp_err_t bmi323_read_if_ready(bmi323_raw_t *raw) { (void)raw; return ESP_ERR_INVALID_STATE; }
esp_err_t bmi323_read_fifo(bmi323_fifo_frame_t *frames, int max_frames, int *count)
{
    (void)frames; (void)max_frames;
    if (count) *count = 0;
    return ESP_ERR_INVALID_STATE;
}
esp_err_t bmi323_flush_fifo(void) { return ESP_ERR_INVALID_STATE; }
esp_err_t bmi323_soft_reset(void) { return ESP_ERR_INVALID_STATE; }
bool bmi323_is_ok(void) { return false; }
void bmi323_raw_to_si(const bmi323_raw_t *raw, bmi323_data_t *data)
{
    (void)raw;
    if (data) *data = (bmi323_data_t){0};
}
