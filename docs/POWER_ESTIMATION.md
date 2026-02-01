# Power Estimation Guide

This document provides a breakdown of power consumption and battery life expectations for the datalogger.

## 1. Component Power Breakdown (Estimated)

| Component | Operation Mode | Typical Current | Peak Current |
| :--- | :--- | :--- | :--- |
| **ESP32** | Active + **WiFi ON** | **160 mA** | 240 mA (TX Bursts) |
| **GPS (Neo-M8N)** | Tracking (10Hz) | 45 mA | 67 mA (Acquisition) |
| **SD Card** | Logging (Periodic) | 10 mA (avg) | 100 mA (Burst write) |
| **IMU (MPU6050)** | Continuous | 4 mA | 5 mA |
| **Status LED** | Pulsing / Blinking | 5 mA | 15 mA (Solid ON) |
| **Total Consumption** | | **~224 mA** | **~427 mA** |

---

## 2. Battery Life Calculation

**Setup:**
*   **Battery:** 18650 Li-ion (3.7V, 2000mAh)
*   **Converter:** 5V Boost (assumed 85% efficiency)

### Runtime Estimates:

| Scenario | Load Current | Estimated Runtime |
| :--- | :--- | :--- |
| **Typical (Logging + WiFi ON)** | 224 mA | **~5.5 Hours** |
| **Peak (WiFi Activity + Write)** | 427 mA | **~3 Hours** |


---

## 3. Optimization Tips

To extend battery life beyond 10 hours:
1.  **Disable WiFi:** Ensure WiFi is completely disabled during active logging.
2.  **Lower GPS Rate:** Change GPS update rate from 10Hz to 1Hz if speed/precision isn't critical.
3.  **Low-Power SD:** Some SD cards consume significantly more power than others. Quality cards (SanDisk/Samsung) are usually better optimized.
4.  **CPU Frequency:** If high calculation isn't needed, drop the ESP32 clock from 240MHz to 80MHz.
