/**
 * @file gps.h
 * @brief Neo-M8N GPS driver — UBX init + NMEA GPRMC/GPGGA parser
 *
 * Boot sequence:
 *  1. UART starts at 9600 baud (module power-on default)
 *  2. Send UBX CFG-PRT to shift to 38400 baud
 *  3. Re-init UART at 38400
 *  4. Send UBX CFG-RATE for 10Hz measurement rate
 *  5. Disable GSV, GLL, VTG, GSA via CFG-MSG to reduce UART bandwidth
 *  6. Parse $GPRMC and $GPGGA in background, calling gps_update() from sensor task
 *
 * UART: assigned to UART1 on ESP32-P4. TX/RX pins defined per breakout harness.
 * Health metrics are tracked per the S3 firmware contract.
 */

#ifndef GPS_H
#define GPS_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ──────────────────────────────────────────────────────────────────────────
 * Pin Constants (GPS breakout on Waveshare P4 expansion header)
 * Adjust to match the actual header pins used on your harness.
 * ────────────────────────────────────────────────────────────────────────*/
#define GPS_UART_NUM        1        /**< ESP32-P4 UART1               */
#define GPS_PIN_TX          17       /**< UART1 TX (expansion header)  — VERIFY */
#define GPS_PIN_RX          18       /**< UART1 RX (expansion header)  — VERIFY */
#define GPS_UART_RX_BUF_SZ  4096    /**< RX buffer for NMEA at 10Hz   */

/* Baud rates */
#define GPS_BAUD_BOOT       9600     /**< Module power-on default      */
#define GPS_BAUD_TARGET     38400    /**< Target after CFG-PRT         */

/* UBX class/ID constants */
#define UBX_CLASS_CFG       0x06
#define UBX_ID_CFG_PRT      0x00
#define UBX_ID_CFG_RATE     0x08
#define UBX_ID_CFG_MSG      0x01

/* ──────────────────────────────────────────────────────────────────────────
 * Data types
 * ────────────────────────────────────────────────────────────────────────*/

/** Last valid GPS fix */
typedef struct {
    double   lat;           /**< Decimal degrees, + = N, - = S        */
    double   lon;           /**< Decimal degrees, + = E, - = W        */
    float    altitude_m;    /**< Altitude above sea level (meters)     */
    float    speed_kmh;     /**< Ground speed (km/h)                   */
    int      satellites;    /**< Satellites in use                     */
    char     timestamp[16]; /**< HHMMSS.SS from $GPRMC                 */
    char     date[8];       /**< DDMMYY from $GPRMC                    */
    char     gps_ts[28];    /**< Combined "DDMMYY_HHMMSS.SS" string    */
    bool     valid;         /**< True if RMC status == 'A'             */
} gps_fix_t;

/** Parser health counters */
typedef struct {
    uint32_t lines_processed;
    uint32_t checksum_failures;
    uint32_t decode_failures;
    uint32_t parse_failures;
    uint32_t update_calls;
    uint32_t rmc_received;
    uint32_t gga_received;
    int      max_lines_per_update;
} gps_health_t;

/* ──────────────────────────────────────────────────────────────────────────
 * Public API
 * ────────────────────────────────────────────────────────────────────────*/

/**
 * @brief Initialize the GPS module via UART + UBX binary configuration.
 *
 * Steps:
 *  1. Open UART1 at 9600 (module boot baud)
 *  2. Send UBX CFG-PRT → shift to 38400
 *  3. Re-init UART at 38400
 *  4. Send UBX CFG-RATE → 10Hz measurements
 *  5. Disable GSV, GLL, VTG, GSA via UBX CFG-MSG
 *
 * @return ESP_OK on success.
 */
esp_err_t gps_init(void);

/**
 * @brief Drain the UART RX buffer and parse available NMEA sentences.
 *
 * Call from the sensor task on every GPS tick (10Hz = every 100ms).
 * Bounded by max_lines to prevent overrunning the 100Hz IMU loop budget.
 *
 * @param max_lines  Maximum NMEA sentences to parse (0 = unlimited).
 * @return true if a fresh $GPRMC sentence was processed.
 */
bool gps_update(int max_lines);

/**
 * @brief Get a copy of the latest GPS fix.
 * @param[out] fix  Destination struct (must not be NULL).
 */
void gps_get_fix(gps_fix_t *fix);

/**
 * @brief Quick check for valid GPS position.
 * @return true if last fix was valid (GPRMC status == 'A').
 */
bool gps_has_fix(void);

/**
 * @brief Get position and motion fields.
 * @param[out] lat,lon   Decimal degrees (may be 0.0 if no fix).
 * @param[out] alt       Altitude in meters.
 * @param[out] speed     Speed in km/h.
 * @param[out] sats      Satellite count.
 * @return ESP_OK always (caller checks gps_has_fix() for validity).
 */
esp_err_t gps_get_position(double *lat, double *lon,
                            float *alt, float *speed, int *sats);

/**
 * @brief Get parser health counters.
 * @param[out] health  Destination struct.
 */
void gps_get_health(gps_health_t *health);

/**
 * @brief Send a UBX binary frame with automatic checksum.
 *
 * Used internally during init. Exposed for testing/debugging.
 *
 * @param msg_class  UBX class byte.
 * @param msg_id     UBX ID byte.
 * @param payload    Payload bytes.
 * @param len        Payload length.
 */
void gps_send_ubx(uint8_t msg_class, uint8_t msg_id,
                  const uint8_t *payload, int len);

#ifdef __cplusplus
}
#endif

#endif /* GPS_H */
