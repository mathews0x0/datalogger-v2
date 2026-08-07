/**
 * @file imu_calibration.h
 * @brief Mount Profile Calibration Solver Component Header
 */

#ifndef IMU_CALIBRATION_H
#define IMU_CALIBRATION_H

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize IMU calibration solver state.
 *
 * @return esp_err_t ESP_OK on success, or error code.
 */
esp_err_t imu_cal_init(void);

/**
 * @brief Start specific calibration collection stage.
 *
 * Stage index mapping:
 * - 0: STATIC
 * - 1: ENGINE
 * - 2: LEAN_L
 * - 3: LEAN_R
 * - 4: PUSH
 *
 * @param stage Calibration stage enum value.
 * @return esp_err_t ESP_OK on success, or error code.
 */
esp_err_t imu_cal_start_stage(int stage);

/**
 * @brief Collect 6-DOF IMU sensor sample into calibration buffer.
 *
 * @param ax Accelerometer X reading (g).
 * @param ay Accelerometer Y reading (g).
 * @param az Accelerometer Z reading (g).
 * @param gx Gyroscope X reading (deg/s).
 * @param gy Gyroscope Y reading (deg/s).
 * @param gz Gyroscope Z reading (deg/s).
 * @return esp_err_t ESP_OK on success, or error code.
 */
esp_err_t imu_cal_collect_sample(float ax, float ay, float az, float gx, float gy, float gz);

/**
 * @brief Compute mount alignment profile matrix from collected samples.
 *
 * @return esp_err_t ESP_OK on success, or error code.
 */
esp_err_t imu_cal_compute_profile(void);

/**
 * @brief Save computed mount profile to storage with given label.
 *
 * @param label Human-readable profile label string.
 * @return esp_err_t ESP_OK on success, or error code.
 */
esp_err_t imu_cal_save_profile(const char *label);

/**
 * @brief Load mount calibration profiles from JSON file.
 *
 * @param json_path Path to JSON file containing calibration profiles.
 * @return esp_err_t ESP_OK on success, or error code.
 */
esp_err_t imu_cal_load_profiles(const char *json_path);

/**
 * @brief Get calculated mount pitch offset angle.
 *
 * @return float Pitch angle in degrees.
 */
float imu_cal_get_mount_pitch(void);

/**
 * @brief Get calculated mount roll offset angle.
 *
 * @return float Roll angle in degrees.
 */
float imu_cal_get_mount_roll(void);

/**
 * @brief Get quality score of active calibration profile.
 *
 * @return float Quality score (0.0 to 1.0).
 */
float imu_cal_get_quality_score(void);

#ifdef __cplusplus
}
#endif

#endif /* IMU_CALIBRATION_H */
