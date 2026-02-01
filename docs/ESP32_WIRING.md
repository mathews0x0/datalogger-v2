# ESP32 Master Wiring Guide

This document defines the final, unified pin configuration for the Datalogger V2. All connections use **Female-to-Female Jumper Wires**.

---

## 1. GPS Module (Neo-M8N)
| GPS Pin | ESP32 Pin | Signal | Description |
| :--- | :--- | :--- | :--- |
| **VCC** | **3.3V** | Power | Supply Voltage |
| **GND** | **GND** | Ground | Common Ground |
| **TX** | **GPIO 26** | UART RX | Data FROM GPS |
| **RX** | **GPIO 27** | UART TX | Data TO GPS |

---

## 2. SD Card Module (SPI)
| SD Pin | ESP32 Pin | Signal | Description |
| :--- | :--- | :--- | :--- |
| **VCC** | **5V / 3.3V** | Power | Check your module's requirements |
| **GND** | **GND** | Ground | Common Ground |
| **MISO** | **GPIO 33** | SPI MISO | Data FROM SD (Moved for signal quality) |
| **MOSI** | **GPIO 23** | SPI MOSI | Data TO SD |
| **SCK** | **GPIO 18** | SPI CLK | Serial Clock |
| **CS** | **GPIO 5** | SPI CS | Chip Select |

---

## 3. IMU Module (I2C)
| IMU Pin | ESP32 Pin | Signal | Description |
| :--- | :--- | :--- | :--- |
| **VCC** | **3.3V** | Power | Supply Voltage |
| **GND** | **GND** | Ground | Common Ground |
| **SDA** | **GPIO 21** | I2C SDA | Data Line |
| **SCL** | **GPIO 22** | I2C SCL | Clock Line |

---

## 4. Status LED
| LED Pin | ESP32 Pin | Signal | Description |
| :--- | :--- | :--- | :--- |
| **Anode (+)** | **GPIO 4 (D4)** | Output | Status Feedback Signal |
| **Cathode (-)** | **GND** | Ground | Ground (Use a resistor if needed) |

---

## 5. Summary Table (ESP32 View)
| ESP32 Pin | Function | Component |
| :--- | :--- | :--- |
| **GND** | Ground | Common |
| **3.3V** | VCC | GPS, IMU, SD |
| **GPIO 4 (D4)** | LED Out | Feedback LED |
| **GPIO 5** | SPI CS | SD Card |
| **GPIO 18** | SPI SCK | SD Card |++++
| **GPIO 21** | I2C SDA | IMU |
| **GPIO 22** | I2C SCL | IMU |
| **GPIO 23** | SPI MOSI | SD Card |
| **GPIO 26** | UART RX | GPS |
| **GPIO 27** | UART TX | GPS |
| **GPIO 33** | SPI MISO | SD Card |
