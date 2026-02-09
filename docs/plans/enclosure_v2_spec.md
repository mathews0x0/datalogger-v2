# RS-Core Enclosure V6.0 — "The Ultimate Parametric Housing"

**Document:** `enclosure_v2_spec.md`  
**Version:** 6.0  
**Date:** 2026-02-09  
**Author:** Racesense Mechanical Engineering (Lead: Pi)  

---

## 1. Overview

This document specifies the **Version 6.0** 3D-printable enclosure for the **RS-Core V2** motorsport datalogger. V6.0 is a major architectural overhaul focused on **100% configurability** — every port can be manually aligned if defaults are slightly off.

### 1.1 Key Changes from V5.0

| Feature | V5.0 | V6.0 |
|---------|------|------|
| **Port Configuration** | Hardcoded positions | **Fully parametric** — wall, offset, Z, width, height per port |
| **GoPro Buckle** | Standard dimensions | **High-fidelity validated** — 42×31×13mm with spring rails |
| **Tolerances** | Scattered | **Consolidated** — all in master config block |
| **PCB Deck Height** | 12mm | **11mm** (further optimized) |
| **Debug Mode** | None | **Port labels** for visualization |
| **Total Stack** | 51mm | **50mm** (collapsed) |

### 1.2 Architecture: 5-Layer Sandwich

```
┌─────────────────────────┐
│     LAYER 5: FLAT TOP   │ ← GPS window, branding (3mm)
├─────────────────────────┤
│     LAYER 4: GPS DECK   │ ← Empty GPS antenna bay (12mm)
├─────────────────────────┤
│     LAYER 3: PCB DECK   │ ← 9 parametric port cutouts (11mm)
├─────────────────────────┤
│    LAYER 2: BATTERY TUB │ ← LiPo cell bay (14mm)
├─────────────────────────┤
│   LAYER 1: BUCKLE BASE  │ ← GoPro male quick release (10mm)
└─────────────────────────┘
         Total: 50mm
```

---

## 2. Parametric Port Configuration

### 2.1 PORT_CONFIG Schema

Every port has **5 adjustable parameters**:

| Parameter | Description | Unit |
|-----------|-------------|------|
| `wall` | Wall assignment: 0=LEFT, 1=RIGHT, 2=FRONT, 3=BACK | enum |
| `offset` | Position along wall (X for FRONT/BACK, Y for LEFT/RIGHT) | mm |
| `z_height` | Height above PCB support surface | mm |
| `width` | Cutout width (parallel to wall) | mm |
| `height` | Cutout height (Z dimension) | mm |

### 2.2 Default Port Configuration

| # | Port Name | Wall | Offset | Z | Width | Height |
|---|-----------|------|--------|---|-------|--------|
| 1 | **Main USB-C** | LEFT (0) | 15.87mm | 0.0 | 10.0mm | 5.0mm |
| 2 | **I2C JST** | BACK (3) | 40.77mm | 0.0 | 6.0mm | 6.0mm |
| 3 | **LED_OUT USB-C** | BACK (3) | 60.58mm | 0.0 | 10.0mm | 5.0mm |
| 4 | **UART JST** | BACK (3) | 61.72mm | 0.0 | 6.0mm | 6.0mm |
| 5 | **USBOUT JST** | RIGHT (1) | 22.86mm | 0.0 | 6.0mm | 6.0mm |
| 6 | **SD Card** | FRONT (2) | 53.21mm | 0.0 | 15.0mm | 4.0mm |
| 7 | **AUX JST** | FRONT (2) | 12.32mm | 0.0 | 6.0mm | 6.0mm |
| 8 | **BATT JST** | FRONT (2) | 7.11mm | 0.0 | 4.0mm | 6.0mm |
| 9 | **PWR SW JST** | FRONT (2) | 4.95mm | 0.0 | 4.0mm | 6.0mm |

### 2.3 Wall Assignment Diagram

```
                BACK WALL (wall=3, Y = 30.61mm)
         ┌─────────────────────────────────┐
         │  [2: I2C]  [3: LED]  [4: UART]  │
         │                                 │
LEFT     │                                 │     RIGHT
WALL     │ [1: USB-C]           [5: USBOUT]│     WALL
(wall=0) │                                 │   (wall=1)
         │                                 │
         │ [9:PWR][8:BAT][7:AUX]    [6:SD] │
         └─────────────────────────────────┘
               FRONT WALL (wall=2, Y = 0mm)
```

### 2.4 How to Adjust Ports

In OpenSCAD Customizer, modify any port's parameters:

```openscad
/* [9a. PORT 1: Main USB-C (LEFT)] */
port1_wall = 0;                 // LEFT wall
port1_offset = 15.87;           // ← Adjust Y position
port1_z = 0.0;                  // ← Adjust height
port1_width = 10.0;             // ← Adjust cutout width
port1_height = 5.0;             // ← Adjust cutout height
```

**Example:** If Main USB-C is 0.5mm too high, change `port1_z = -0.5;`

---

## 3. Global Tolerances — Master Control

All tolerances consolidated in one configuration block:

| Tolerance | Default | Purpose |
|-----------|---------|---------|
| `assembly_tol` | 0.2mm | Gap between PCB and walls |
| `port_tol` | 0.5mm | Extra clearance around port cutouts |
| `battery_tol` | 1.0mm | Gap around battery cell |
| `snap_tol` | 0.25mm | Snap-fit clip clearance |
| `layer_tol` | 0.15mm | Between stacked layers |

---

## 4. GoPro Male Quick Release — High-Fidelity Design

### 4.1 Validated Dimensions

Based on genuine GoPro hardware measurements:

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Overall Length** | 42.0mm | Full extension |
| **Main Rail Width** | 23.0mm | Central rail body |
| **Total Width** | 31.0mm | Including spring clips |
| **Total Height** | ~13mm | From base to tab top |
| **Base Plate** | 2.0mm | Thickness |
| **Rail Height** | 6.0mm | From base |
| **Side Slot Width** | 3.0mm | For female rails |
| **Side Slot Depth** | 2.5mm | Engagement depth |
| **Locking Tab Width** | 14.0mm | Center engagement |
| **Locking Tab Height** | 3.0mm | Above rail surface |
| **Locking Tab Depth** | 6.0mm | Protrusion |
| **Tab Chamfer** | 35° | Click-in angle |
| **Spring Clip Width** | 4.0mm | Each side |
| **Spring Clip Length** | 15.0mm | Extension |
| **Spring Thickness** | 1.2mm | Flexibility |
| **Finger Tab** | 8×6mm | Release mechanism |

### 4.2 Cross-Section Profile

```
       ◀────────── 31mm ──────────▶
       
    ┌──┐                        ┌──┐   ← Spring clips (4mm each)
    │  │  ┌──────────────────┐  │  │
    └──┘  │                  │  └──┘   
          │   ◀── 23mm ──▶   │         ▲
          │                  │         │ 6mm rails
          │    ┌────────┐    │         │
          │    │ SLOTS  │    │         ▼
          └────┴────────┴────┘
          ▲                  ▲
          └── 3mm slots ─────┘
```

### 4.3 Locking Tab Detail

```
                    ┌─────┐  ← 3mm above rail
           ╱╲       │ TAB │    
         ╱35°╲      │ 14mm│
       ╱──────╲     └─────┘
       ▲ chamfer    ▲
       └──────── 6mm depth
```

---

## 5. Layer Dimensions

| Layer | Height | Purpose |
|-------|--------|---------|
| 1: Buckle Base | 10.0mm | GoPro mount + floor |
| 2: Battery Tub | 14.0mm | LiPo cell bay |
| 3: PCB Deck | **11.0mm** | PCB + ports (optimized) |
| 4: GPS Deck | 12.0mm | Empty volume for GPS antenna |
| 5: Flat Top | 3.0mm | GPS window + branding |

**Total Stack Height:** 50.0mm (collapsed)

---

## 6. PCB Truth Data

From DXF analysis of `PCB_esplogger_2_2026-02-09.dxf`:

| Parameter | Value | Source |
|-----------|-------|--------|
| PCB Length | 69.22mm | BoardOutLine X delta |
| PCB Width | 30.61mm | BoardOutLine Y delta |
| PCB Thickness | 1.6mm | Standard 4-layer |
| Board Origin | (9.78, 55.63) | DXF coordinates |

### 6.1 Component Centers (PCB-Relative)

```
USB (Main)      X=  8.76mm  Y= 15.87mm  → LEFT wall
I2C             X= 40.77mm  Y= 25.14mm  → BACK wall
LED_OUT         X= 60.58mm  Y= 23.49mm  → BACK wall
UART            X= 61.72mm  Y= 29.33mm  → BACK wall
USBOUT          X= 63.88mm  Y= 22.86mm  → RIGHT wall
MICRO-SD        X= 53.21mm  Y=  6.85mm  → FRONT wall
AUX             X= 12.32mm  Y=  2.16mm  → FRONT wall
BATT            X=  7.11mm  Y=  2.16mm  → FRONT wall
PWR-SW          X=  4.95mm  Y=  4.70mm  → FRONT wall
```

---

## 7. OpenSCAD Model V6.0

### 7.1 File Location

```
hardware/enclosure/rs_core_enclosure_v6.scad
```

### 7.2 Key Features

1. **Fully Parametric Ports** — Each of 9 ports has individual wall/offset/z/width/height controls
2. **High-Fidelity GoPro Buckle** — Validated spring rails and locking tab geometry
3. **Consolidated Tolerances** — Single config section for all fit parameters
4. **Debug Mode** — `show_port_labels = true` to visualize port numbers
5. **Optimized Height** — 50mm total stack (1mm reduction from V5.0)

### 7.3 Customizer Workflow

1. Open `rs_core_enclosure_v6.scad` in OpenSCAD
2. Press F5 to preview
3. Use Customizer panel (View → Hide Customizer to toggle)
4. Adjust any port's `offset`, `z`, `width`, or `height`
5. Re-render (F5) to verify alignment
6. Export each layer as STL for printing

---

## 8. Printing Recommendations

| Parameter | Value |
|-----------|-------|
| Material | PETG or ASA (heat resistant) |
| Layer Height | 0.2mm |
| Infill | 20-30% |
| Walls | 3 perimeters minimum |
| Support | Not required (self-supporting design) |
| Orientation | Print each layer flat (Z-up) |

---

## 9. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 4.1 | 2026-02-09 | Pi-style snug fit, removed standoffs |
| 5.0 | 2026-02-09 | 9-port precision layout, SD card to front, standard GoPro |
| **6.0** | **2026-02-09** | **Ultimate Parametric** — fully configurable ports, high-fidelity GoPro buckle, consolidated tolerances, 50mm stack |

---

## 10. AI Image Generation Prompt

For generating photorealistic renders of this enclosure:

### Midjourney / DALL-E Prompt

```
Professional product photography of a compact motorsport datalogger enclosure, 
3D printed in dark matte charcoal gray PETG plastic with subtle layer lines 
visible, featuring an integrated GoPro male quick-release buckle mount on the 
bottom surface, precision-cut ports on all four sides including two visible 
USB Type-C connectors (brushed silver receptacles), multiple JST connector 
cutouts, and a microSD card slot, orange "RACESENSE" logo embossed on the 
top surface, translucent GPS antenna window centered on top lid, rounded 
corners with 3mm radius, 5-layer modular sandwich construction with snap-fit 
clips visible between layers, overall dimensions approximately 75mm x 35mm x 
50mm, shot on white seamless background with soft studio lighting, shallow 
depth of field, 85mm lens, 8K resolution, photorealistic product render 
--ar 4:3 --v 6 --style raw
```

### Stable Diffusion / Flux Prompt

```
(masterpiece, best quality, photorealistic:1.4), product photography, 
compact electronics enclosure, 3D printed dark matte gray plastic, 
motorsport datalogger housing, GoPro mount buckle on bottom, USB-C ports 
visible on sides, orange RACESENSE text logo, GPS window on top, rounded 
corners, modular snap-fit layers, precision port cutouts, white background, 
studio lighting, professional product shot, 8k uhd, sharp focus
```

---

*End of Specification V6.0 — "The Ultimate Parametric Housing"*
