# 📦 Bill of Materials (BOM)
**Project:** ESP32-S3 Motorcycle Datalogger  
**Date:** 2026-02-07

## 🔌 Semiconductors

| Designator | Qty | Part Number              | Description                                   | Package  |
| :--------- | :-: | :----------------------- | :-------------------------------------------- | :------- |
| **U1**     |  1  | **ESP32-S3-WROOM-1**     | MCU Module, 16MB Flash, 8MB PSRAM             | SMD      |
| **U2**     |  1  | **BMI160**               | 6-Axis IMU (Accel + Gyro)                     | LGA-14   |
| **U3**     |  1  | **TP4054**               | Li-Ion Charger, 500mA                         | SOT-23-5 |
| **U4**     |  1  | **TLV75733PDBVR**        | LDO Regulator, 3.3V, 1A                       | SOT-23-5 |
| **D1**     |  1  | **USBLC6-2SC6**          | USB ESD Protection                            | SOT-23-6 |

## 💡 LEDs

| Designator           | Qty | Part Number                | Description   | Color | Package |
| :------------------- | :-: | :------------------------- | :------------ | :---- | :------ |
| **LED1, LED2, LED3** |  3  | **19-217/BHC-ZL1M2RY/3T**  | Indicator LED | Blue  | 0603    |

## 🔋 Passives (Resistors & Capacitors)

| Designator         | Qty | Value     | Description                  | Package |
| :----------------- | :-: | :-------- | :--------------------------- | :------ |
| **R1, R2, R4, R5** |  4  | **4.7kΩ** | Resistor, ±1%, 1/10W         | 0603    |
| **R7, R8, R9**     |  3  | **220Ω**  | Resistor, ±1%, 1/10W         | 0603    |
| **R6**             |  1  | **1kΩ**   | Resistor, ±1%, 1/10W         | 0603    |
| **R10, R11**       |  2  | **5.1kΩ** | Resistor, ±1%, 1/10W         | 0603    |
| **R13**            |  1  | **10kΩ**  | Resistor, ±1%, 1/10W         | 0603    |
| **R3, R12**        |  2  | **100kΩ** | Resistor, ±1%, 1/10W         | 0603    |
| **C1, C2**         |  2  | **100nF** | Capacitor, X7R, 16V          | 0603    |
| **C3**             |  1  | **1µF**   | Capacitor, X5R, 10V+         | 0603    |
| **C4, C5**         |  2  | **10µF**  | Capacitor, X5R, 10V+         | 0603    |

## 🔌 Connectors & Switches

| Designator       | Qty | Part Number               | Description                 | Package |
| :--------------- | :-: | :------------------------ | :-------------------------- | :------ |
| **J1, J2**       |  2  | **TYPE-C 16PIN 2MD**      | USB-C Receptacle 16-pin     | SMD     |
| **J_SD**         |  1  | **TF PUSH**               | MicroSD Socket Push-Push    | SMD     |
| **J3, J4, J5, J6**|  4  | **SM04B-SRSS-TB**         | JST SH 1.0mm 4-pin Header   | SMD     |
| **J7, J8**       |  2  | **SM02B-SRSS-TB**         | JST SH 1.0mm 2-pin Header   | SMD     |
| **SW1, SW2**     |  2  | **TS-1187A-B-A-B**        | Tactile Button (Boot/Reset) | 4x3mm   |
