# Phase 8: LVGL UI & Touch Driver Implementation Plan (Adaptive Multi-Resolution)

Build and verify the complete 12-screen UI/UX suite for the RaceSense telemetry system, architected for **zero-rewrite multi-device portability** across:
- **Waveshare 4.3" 800×480 IPS** (ST7701 MIPI-DSI — Primary Target)
- **Compact 3.5" 480×320 IPS/TN** (ILI9488 / ST7796 SPI or Parallel)
- **Ultra-Compact 2.8" 320×240 SPI** (ILI9341 / ST7789)

---

## User Review Required & Architecture Revisions

> [!IMPORTANT]
> **Adaptive UI & Multi-Resolution Portability Architecture**
> To ensure the entire 12-screen suite can be ported to smaller displays (such as 3.5" or 2.8" screens on ESP32-S3 or P4) with zero backend rewrite and minimal layout adjustment:
> 1. **Centralized Layout & Token System (`ui_layout.h`)**: All container widths, paddings, gap sizes, and font scale factors will be driven by resolution-relative macros (`UI_SCALE_X()`, `UI_SCALE_Y()`, `UI_FONT_HERO`, `UI_FONT_BODY`) using LVGL flex wrappers rather than hardcoded static pixel constants.
> 2. **Decoupled Event Layer (`ui_events.c`)**: All touch event callbacks (`START LOG`, `SYNC`, `SETTINGS`, `STOP LOG`, `NEXT STAGE`, etc.) will be completely separated from screen rendering C files. Touch callbacks interact exclusively with state machine and backend APIs.
> 3. **Multi-Resolution Web Simulator Harness (`ui_simulator.html`)**: The interactive simulator will include a live **Resolution Switcher toggle** (800×480 Widescreen, 480×320 3.5", 320×240 2.8") allowing instant visual verification of responsive layouts across all display sizes before hardware flashing.

---

## Responsive Layout Rules Across Display Sizes

| Resolution / Display | Grid Strategy | Hero Clock Font | Button Layout | Card Arrangement |
|---|---|---|---|---|
| **800×480 (4.3" P4)** | 2-Column Widescreen Grid | `140pt` (Full-width hero) | 3-Target Horizontal Dock (320px / 80px / 360px) | 2×2 Side-by-side Cards |
| **480×320 (3.5" S3/P4)**| 2-Row Stacked Grid | `72pt` (Top hero) | 2-Target Main Dock + Gear Icon | Single Column Stacked Cards |
| **320×240 (2.8" S3/P4)**| Single Column Stacked | `48pt` (Compact top hero) | Full-Width Stacked Thumb Targets (100% W) | Tabview / Swipeable Single Card |

---

## Touch Action & Event Routing Matrix (Shared Across All Devices)

| Screen | Touch Target / Event | Action / Backend Callback | Target State |
|---|---|---|---|
| **1. Boot Splash** | 2s auto-timer / init finish | Checks `storage_has_flash_sessions()` | `AUTO_COPY` or `HOME_IDLE` |
| **2. Home Dashboard** | `START LOG` button | Validates SD & GPS lock → starts 100Hz logging | `LOGGING_ACTIVE` |
| | `SYNC` button | Triggers WiFi STA scan / connect | `SYNC_WIFI_SEARCH` |
| | `⚙️ SETTINGS` button | Opens configuration grid | `SETTINGS` |
| **3. Live Logging** | `STOP LOG` button (hold 2s) | Flushes storage, stops session, disables logging | `HOME_IDLE` |
| | Sector gate trigger (Core 0) | Overlays 3s trackside delta banner | `SECTOR_FLASH` (overlay) |
| **4. IMU Validation** | 5s auto-timer | Checks YAW/PITCH alignment | `LOGGING_ACTIVE` |
| **5. Sector Flash** | 3s auto-timer | Restores live telemetry view | `LOGGING_ACTIVE` |
| **6. WiFi Search** | `EXIT` button | Cancels WiFi scan, disables radio | `HOME_IDLE` |
| | Network found & connected | Triggers HTTP `/heartbeat` ping | `SYNC_HEARTBEAT` |
| **7. Sync Heartbeat** | Ping 200 OK | Scans pending CSV files → starts batch upload | `SYNC_UPLOADING` |
| | Ping Fail | Retries 3x or shows error alert | `SYNC_WIFI_SEARCH` |
| **8. Upload Progress**| `CANCEL SYNC` button | Aborts HTTP stream, closes socket | `HOME_IDLE` |
| | All files complete | Triggers sync summary card | `SYNC_COMPLETE` |
| **9. Sync Complete** | `DONE` button | Disables WiFi radio, returns home | `HOME_IDLE` |
| **10. Settings** | `BACK` button | Saves modified settings → returns home | `HOME_IDLE` |
| | `CHANGE WIFI` | Launches softAP provisioning portal | `CAPTIVE_PORTAL` |
| | `SELECT TRACK` | Opens track picker modal | `SETTINGS` |
| | `RE-CALIBRATE IMU` | Launches 5-stage calibration wizard | `IMU_CALIBRATION` |
| | `AUTO-LOG TOGGLE` | Updates `device.json` (`auto_log: true/false`) | `SETTINGS` |
| **11. IMU Calibration**| `CANCEL` button | Aborts calibration, discards matrix | `SETTINGS` |
| | `NEXT STAGE` button | Samples 100 IMU readings → solves matrix | Stage 1→5 → `SETTINGS` |
| **12. Captive Portal** | `EXIT` button | Stops DNS hijack task, shuts down AP | `HOME_IDLE` |
| | Provisioned POST | Saves `device.json`, displays 15s countdown | Reboot |

---

## Proposed Component Architecture

### Component 1: Adaptive LVGL Core & Theme (`firmware/components/ui/`)

#### [NEW] [ui_layout.h](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/include/ui_layout.h)
- Centralized adaptive layout engine. Defines display resolution detection (`LV_HOR_RES`, `LV_VER_RES`), scaling macros (`UI_SCALE_X`, `UI_SCALE_Y`), font size aliases (`UI_FONT_HERO`, `UI_FONT_TITLE`, `UI_FONT_BODY`), and flexible flex layout rules.

#### [NEW] [ui_events.h](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/include/ui_events.h) & [ui_events.c](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui_events.c)
- Resolution-agnostic touch event dispatchers. Decouples UI buttons from system state transitions, NVS config updates, storage flushing, and sensor tasks.

#### [MODIFY] [ui.h](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/include/ui.h)
- Public rendering API for all 12 screens. Incorporates `ui_layout.h` and target driver initialization.

#### [NEW] [ui_theme.c](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui_theme.c)
- Motorsport Dark Theme color tokens (`#0D0D11` background, `#FF6B35` orange, `#00D26A` green, `#FF3B30` red, `#007AFF` blue) and glassmorphic card styles.

#### [MODIFY] [ui.c](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui.c)
- Multi-driver initialization (ST7701 MIPI-DSI default for P4, expandable to SPI/RGB for S3). GT911 / capacitive touch registration via `esp_lvgl_port`.

---

### Component 2: Screen Implementation Waves

#### Wave 1: Boot & Home
- #### [MODIFY] [ui_home.c](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui_home.c)
  - Screen 1 (Boot Splash) and Screen 2 (Adaptive Home Dashboard).
  - Uses `ui_layout.h` flex rules to render 2-column on 800×480 or stacked column on 320×240/480×320.
  - Connects `ui_events.c` callbacks for `START LOG`, `SYNC`, `SETTINGS`.

#### Wave 2: Telemetry & Trackside Feedback
- #### [MODIFY] [ui_logging.c](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui_logging.c)
  - Screen 3 (v4 Hero Live Logging), Screen 4 (IMU Validation), Screen 5 (3s Sector Flash Overlay).
  - Dynamic 140pt/72pt/48pt lap clock scaling, 30Hz IMU lean angle arc, and 2-second hold `STOP LOG` target.

#### Wave 3: Settings & Calibration
- #### [MODIFY] [ui_settings.c](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui_settings.c)
  - Screen 10 (Settings Grid) with Auto-Log switch mapped to `ui_events.c` → `device.json`.
- #### [MODIFY] [ui_calibration.c](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui_calibration.c)
  - Screen 11 (5-Stage IMU Mount Calibration Wizard).

#### Wave 4: Sync & Provisioning
- #### [MODIFY] [ui_sync.c](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui_sync.c)
  - Screen 6 (WiFi Search), Screen 7 (Heartbeat), Screen 8 (Upload Progress), Screen 9 (Sync Complete), Screen 12 (Captive Portal with QR code widget).

---

### Component 3: Multi-Resolution Web Simulator Harness

#### [NEW] [ui_simulator.html](file:///Users/mj/Documents/datalogger-v2/firmware/components/ui/ui_simulator.html)
- Interactive HTML5 Canvas / SVG simulator harness for all 12 screens.
- **Features a Live Resolution Switcher**:
  - `[800×480 - 4.3" P4]`
  - `[480×320 - 3.5" S3/P4]`
  - `[320×240 - 2.8" S3/P4]`
- Allows live interactive testing of touch targets, state navigation, responsive layout scaling, and animations directly in the browser!

---

## Verification Plan

### Automated & Interactive Verification
1. **Multi-Resolution Web Simulator Test**: Open `ui_simulator.html` in browser, toggle resolution modes (`800x480`, `480x320`, `320x240`), test responsive layout scaling, and click through touch targets across all 12 screens.
2. **ESP-IDF Header & Component Check**: Verify C compilation dependencies (`idf_component_register` in `components/ui/CMakeLists.txt`).

### Manual Hardware Verification
1. **Waveshare 4.3" 800×480 Display Test**: Flash built firmware to P4 board, verify ST7701 MIPI-DSI frame rate (target 60fps) and GT911 touch input.
2. **Event Dispatch Logging**: Verify serial monitor outputs for touch callbacks routed via `ui_events.c`.
