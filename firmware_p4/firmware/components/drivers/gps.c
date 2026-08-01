/**
 * @file gps.c
 * @brief Neo-M8N GPS driver — UBX init + NMEA GPRMC/GPGGA parser
 *
 * Ported from firmware_s3/firmware/drivers/gps.py.
 * Uses ESP-IDF UART driver with RX FIFO interrupts.
 */

#include "gps.h"

#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "gps";

/* ──────────────────────────────────────────────────────────────────────────
 * Module state
 * ────────────────────────────────────────────────────────────────────────*/
static gps_fix_t    s_fix    = {0};
static gps_health_t s_health = {0};
static bool         s_initialized = false;

/* ──────────────────────────────────────────────────────────────────────────
 * UBX framing
 * ────────────────────────────────────────────────────────────────────────*/
void gps_send_ubx(uint8_t msg_class, uint8_t msg_id,
                  const uint8_t *payload, int len)
{
    /* Header + class + ID + length (LE) + payload + checksum */
    int total = 2 + 2 + 2 + len + 2;
    uint8_t *frame = (uint8_t *)alloca(total);
    frame[0] = 0xB5;
    frame[1] = 0x62;
    frame[2] = msg_class;
    frame[3] = msg_id;
    frame[4] = (uint8_t)(len & 0xFF);
    frame[5] = (uint8_t)((len >> 8) & 0xFF);
    memcpy(&frame[6], payload, len);

    uint8_t ck_a = 0, ck_b = 0;
    for (int i = 2; i < 6 + len; i++) {
        ck_a += frame[i];
        ck_b += ck_a;
    }
    frame[6 + len]     = ck_a;
    frame[6 + len + 1] = ck_b;

    uart_write_bytes(GPS_UART_NUM, (const char *)frame, total);
}

/* ──────────────────────────────────────────────────────────────────────────
 * UBX configuration commands
 * ────────────────────────────────────────────────────────────────────────*/
static void _ubx_set_baudrate(int baud)
{
    /* CFG-PRT payload for UART port 1, pre-calculated for common rates */
    uint8_t payload[20];
    memset(payload, 0, sizeof(payload));
    payload[0] = 0x01;  /* Port ID: UART1 */
    payload[4] = 0xD0;  payload[5] = 0x08;  /* UART mode: 8N1 */
    payload[8]  = (uint8_t)(baud & 0xFF);
    payload[9]  = (uint8_t)((baud >> 8) & 0xFF);
    payload[10] = (uint8_t)((baud >> 16) & 0xFF);
    payload[11] = (uint8_t)((baud >> 24) & 0xFF);
    payload[12] = 0x07;  payload[13] = 0x00;  /* inProtoMask: UBX+NMEA+RTCM */
    payload[14] = 0x03;  payload[15] = 0x00;  /* outProtoMask: UBX+NMEA */
    gps_send_ubx(UBX_CLASS_CFG, UBX_ID_CFG_PRT, payload, sizeof(payload));
}

static void _ubx_set_rate_hz(int hz)
{
    uint16_t interval_ms = (uint16_t)(1000 / hz);
    uint8_t payload[6] = {
        (uint8_t)(interval_ms & 0xFF), (uint8_t)((interval_ms >> 8) & 0xFF),
        0x01, 0x00,  /* navRate = 1 */
        0x01, 0x00,  /* timeRef = 1 (UTC) */
    };
    gps_send_ubx(UBX_CLASS_CFG, UBX_ID_CFG_RATE, payload, sizeof(payload));

    /* Disable unused NMEA sentences to reduce UART bandwidth */
    uint8_t gsv[] = { 0xF0, 0x03, 0x00 };  /* GSV */
    uint8_t gll[] = { 0xF0, 0x01, 0x00 };  /* GLL */
    uint8_t vtg[] = { 0xF0, 0x05, 0x00 };  /* VTG */
    uint8_t gsa[] = { 0xF0, 0x02, 0x00 };  /* GSA */
    gps_send_ubx(UBX_CLASS_CFG, UBX_ID_CFG_MSG, gsv, sizeof(gsv));
    gps_send_ubx(UBX_CLASS_CFG, UBX_ID_CFG_MSG, gll, sizeof(gll));
    gps_send_ubx(UBX_CLASS_CFG, UBX_ID_CFG_MSG, vtg, sizeof(vtg));
    gps_send_ubx(UBX_CLASS_CFG, UBX_ID_CFG_MSG, gsa, sizeof(gsa));
}

/* ──────────────────────────────────────────────────────────────────────────
 * NMEA parsing helpers
 * ────────────────────────────────────────────────────────────────────────*/

/** NMEA checksum verify: XOR of all chars between '$' and '*' */
static bool _nmea_checksum_ok(const char *line)
{
    const char *star = strchr(line, '*');
    if (!star || star == line + 1) return false;
    uint8_t calc = 0;
    for (const char *p = line + 1; p < star; p++) {
        calc ^= (uint8_t)*p;
    }
    char hex[3] = { star[1], star[2], 0 };
    uint8_t received = (uint8_t)strtol(hex, NULL, 16);
    return calc == received;
}

/** Convert NMEA ddmm.mmmm + hemisphere to decimal degrees */
static double _dm_to_dd(const char *val, const char *hemi)
{
    if (!val || !hemi || val[0] == '\0') return 0.0;
    const char *dot = strchr(val, '.');
    if (!dot || dot < val + 3) return 0.0;

    int deg_digits = (int)(dot - val) - 2;
    char deg_str[8] = {0};
    strncpy(deg_str, val, deg_digits);
    double degrees = atof(deg_str);
    double minutes = atof(val + deg_digits);
    double dd = degrees + minutes / 60.0;

    if (hemi[0] == 'S' || hemi[0] == 'W') dd = -dd;
    return dd;
}

/** Split a NMEA sentence into fields (modifies in-place) */
#define MAX_FIELDS 16
static int _split_nmea(char *line, char *fields[], int max_fields)
{
    int n = 0;
    char *p = line;
    while (n < max_fields) {
        fields[n++] = p;
        p = strchr(p, ',');
        if (!p) break;
        *p++ = '\0';
    }
    return n;
}

static void _parse_gprmc(char *fields[], int n)
{
    if (n < 10) return;
    s_health.rmc_received++;

    /* Timestamp (always update — shows UART is live even without fix) */
    if (fields[1][0]) {
        strncpy(s_fix.timestamp, fields[1], sizeof(s_fix.timestamp) - 1);
    }

    s_fix.valid = (fields[2][0] == 'A');

    if (s_fix.valid) {
        s_fix.lat = _dm_to_dd(fields[3], fields[4]);
        s_fix.lon = _dm_to_dd(fields[5], fields[6]);
        if (fields[7][0]) {
            float knots = (float)atof(fields[7]);
            s_fix.speed_kmh = knots * 1.852f;
        }
    }

    if (n > 9 && fields[9][0]) {
        strncpy(s_fix.date, fields[9], sizeof(s_fix.date) - 1);
    }

    /* Build combined GPS timestamp for CSV */
    if (s_fix.timestamp[0] && s_fix.date[0]) {
        snprintf(s_fix.gps_ts, sizeof(s_fix.gps_ts), "%s_%s",
                 s_fix.date, s_fix.timestamp);
    }
}

static void _parse_gpgga(char *fields[], int n)
{
    if (n < 10) return;
    s_health.gga_received++;
    if (fields[7][0]) {
        s_fix.satellites = atoi(fields[7]);
    }
    if (fields[9][0]) {
        s_fix.altitude_m = (float)atof(fields[9]);
    }
}

static void _parse_nmea_line(char *line)
{
    if (!_nmea_checksum_ok(line)) {
        s_health.checksum_failures++;
        return;
    }

    /* Strip '*xx' checksum suffix before splitting */
    char *star = strchr(line, '*');
    if (star) *star = '\0';

    char *fields[MAX_FIELDS];
    int n = _split_nmea(line, fields, MAX_FIELDS);
    if (n < 1) return;

    /* Message type is field[0] with $GN or $GP prefix — skip 3 chars */
    const char *msg_id = fields[0];
    if (msg_id[0] == '$' && strlen(msg_id) >= 6) {
        msg_id += 3;  /* Skip $GP or $GN */
    } else {
        return;
    }

    if (strcmp(msg_id, "RMC") == 0) {
        _parse_gprmc(fields, n);
    } else if (strcmp(msg_id, "GGA") == 0) {
        _parse_gpgga(fields, n);
    }
}

/* ══════════════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ══════════════════════════════════════════════════════════════════════════*/

esp_err_t gps_init(void)
{
    if (s_initialized) return ESP_OK;

    /* 1. Open UART at module boot baud (9600) */
    uart_config_t uart_cfg = {
        .baud_rate  = GPS_BAUD_BOOT,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_param_config(GPS_UART_NUM, &uart_cfg));
    ESP_ERROR_CHECK(uart_set_pin(GPS_UART_NUM, GPS_PIN_TX, GPS_PIN_RX,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(GPS_UART_NUM, GPS_UART_RX_BUF_SZ, 0, 0, NULL, 0));
    ESP_LOGI(TAG, "GPS UART1 open at %d baud (TX:%d RX:%d)", GPS_BAUD_BOOT, GPS_PIN_TX, GPS_PIN_RX);

    /* 2. Send UBX CFG-PRT to shift baud rate to target */
    _ubx_set_baudrate(GPS_BAUD_TARGET);
    vTaskDelay(pdMS_TO_TICKS(100));

    /* 3. Re-init UART at target baud */
    uart_cfg.baud_rate = GPS_BAUD_TARGET;
    ESP_ERROR_CHECK(uart_param_config(GPS_UART_NUM, &uart_cfg));
    /* Flush any pending bytes from old baud */
    uart_flush(GPS_UART_NUM);
    vTaskDelay(pdMS_TO_TICKS(20));

    /* 4. Set measurement rate to 10Hz + disable unused sentences */
    _ubx_set_rate_hz(10);
    vTaskDelay(pdMS_TO_TICKS(50));

    ESP_LOGI(TAG, "GPS Neo-M8N ready: %d baud / 10Hz", GPS_BAUD_TARGET);
    s_initialized = true;
    return ESP_OK;
}

bool gps_update(int max_lines)
{
    if (!s_initialized) return false;
    s_health.update_calls++;
    bool got_rmc = false;
    int  processed = 0;
    char line[128];

    while (true) {
        if (max_lines > 0 && processed >= max_lines) break;

        /* Read one byte at a time looking for '\n' */
        int idx = 0;
        bool found_line = false;
        while (idx < (int)sizeof(line) - 1) {
            uint8_t c;
            int n = uart_read_bytes(GPS_UART_NUM, &c, 1, 0);
            if (n <= 0) break;
            if (c == '\n') { found_line = true; break; }
            if (c != '\r') line[idx++] = (char)c;
        }
        if (!found_line && idx == 0) break;
        line[idx] = '\0';

        if (line[0] != '$') continue;

        uint32_t rmc_before = s_health.rmc_received;
        s_health.lines_processed++;
        processed++;

        _parse_nmea_line(line);

        if (s_health.rmc_received > rmc_before) got_rmc = true;
    }

    if (processed > s_health.max_lines_per_update) {
        s_health.max_lines_per_update = processed;
    }
    return got_rmc;
}

void gps_get_fix(gps_fix_t *fix)
{
    if (fix) memcpy(fix, &s_fix, sizeof(*fix));
}

bool gps_has_fix(void)
{
    return s_fix.valid;
}

esp_err_t gps_get_position(double *lat, double *lon,
                            float *alt, float *speed, int *sats)
{
    if (lat)   *lat   = s_fix.lat;
    if (lon)   *lon   = s_fix.lon;
    if (alt)   *alt   = s_fix.altitude_m;
    if (speed) *speed = s_fix.speed_kmh;
    if (sats)  *sats  = s_fix.satellites;
    return ESP_OK;
}

void gps_get_health(gps_health_t *health)
{
    if (health) memcpy(health, &s_health, sizeof(*health));
}
