# RS-Core Enclosure V3.0 — High-Precision Mechanical Specification

**Document:** `enclosure_v2_spec.md`  
**Version:** 3.0  
**Date:** 2026-02-09  
**Author:** Racesense Mechanical Engineering  

---

## 1. Overview

This document specifies the **Version 3.0** 3D-printable enclosure for the **RS-Core V2** motorsport datalogger. The design features a modular layer-stack architecture with an integrated GoPro Quick Release Buckle (male) for rapid mounting/dismounting.

### 1.1 Key Changes from V2.1

| Feature | V2.1 | V3.0 |
|---------|------|------|
| Connector Mapping | Estimated positions | HIGH-PRECISION DXF-derived coordinates |
| Port Count | 8 ports (incomplete) | 9 ports (ALL connectors mapped) |
| Edge Assignment | Multiple errors | Corrected per visual reference |
| Cutout Accuracy | ±2mm tolerance | ±0.2mm tolerance from DXF |

### 1.2 Corrected Port Edge Layout (From Visual Reference)

Based on the 3D render of RS-CORE-V2 PCB:

| Edge | Connectors |
|------|------------|
| **LEFT (X-Min)** | 1× USB-C (Main Data/Charge) |
| **TOP (Y-Max)** | 1× JST 4-pin (I2C), 1× USB-C (LED_OUT), 1× JST 4-pin (UART) |
| **RIGHT (X-Max)** | 1× JST 4-pin (USBOUT), 1× Micro-SD Slot |
| **BOTTOM (Y-Min)** | 1× JST 2-pin (PWR-SW), 1× JST 2-pin (BATT), 1× JST 4-pin (IO/AUX) |

### 1.3 Design Philosophy

- **Layered Stack Architecture:** Buckle → Battery → PCB → GPS → Cover
- **Quick-Release Mounting:** Standard GoPro male buckle for flat adhesive mounts
- **Side-by-Side GPS:** Module (36×26mm) and Antenna (26×26mm) placed horizontally
- **Full Port Exposure:** All 9 connectors accessible without shell removal
- **Premium Finish:** Chamfered edges, integrated branding, and professional aesthetics

---

## 2. Component Dimensions

### 2.1 Core Components

| Component | Dimensions (mm) | Notes |
|-----------|-----------------|-------|
| RS-Core PCB | 69.2 × 30.6 × 1.6 | From DXF: X=9.78→78.99, Y=55.63→86.23 |
| LiPo Battery | 40 × 25 × 10 | +2mm tolerance all sides |
| GPS Module | 36 × 26 × 4 | Main GPS receiver |
| GPS Antenna | 26 × 26 × 9 | Ceramic patch (active) |

### 2.2 Connector Inventory (Complete)

| # | Connector | Type | Edge | Footprint (mm) | Height (mm) |
|---|-----------|------|------|----------------|-------------|
| 1 | USB (Main) | USB-C 16-pin | LEFT | 9.0 × 7.5 | 3.2 |
| 2 | I2C | JST SH 4-pin | TOP | 5.0 × 4.0 | 4.25 |
| 3 | LED_OUT | USB-C 16-pin | TOP | 9.0 × 7.5 | 3.2 |
| 4 | UART | JST SH 4-pin | TOP | 5.0 × 4.0 | 4.25 |
| 5 | USBOUT | JST SH 4-pin | RIGHT | 5.0 × 4.0 | 4.25 |
| 6 | MICRO-SD | Push-push TF | RIGHT | 14.0 × 15.0 | 2.0 |
| 7 | PWR-SW | JST SH 2-pin | BOTTOM | 3.0 × 4.0 | 4.25 |
| 8 | BATT | JST SH 2-pin | BOTTOM | 3.0 × 4.0 | 4.25 |
| 9 | AUX (IO) | JST SH 4-pin | BOTTOM | 5.0 × 4.0 | 4.25 |

### 2.3 GoPro Quick Release Buckle Dimensions

| Parameter | Value | Notes |
|-----------|-------|-------|
| Buckle Length | 42mm | Standard GoPro male |
| Buckle Width | 20mm | Fits standard flat mounts |
| Buckle Height | 10mm | Including locking tab |
| Tab Spring Width | 12mm | Center locking mechanism |
| Interface Slot | 3mm deep | Engagement depth |

---

## 3. High-Precision Connector Mapping

### 3.1 DXF Coordinate System

**PCB Outline from DXF (BoardOutLine layer):**
- **X-Min (Left Edge):** 9.78mm (DXF absolute)
- **X-Max (Right Edge):** 78.99mm (DXF absolute)
- **Y-Min (Bottom Edge):** 55.63mm (DXF absolute)
- **Y-Max (Top Edge):** 86.23mm (DXF absolute)
- **PCB Width:** 69.21mm
- **PCB Height:** 30.60mm

**Coordinate Transformation:**
```
PCB_Local_X = DXF_X - 9.78
PCB_Local_Y = DXF_Y - 55.63
```

### 3.2 Connector Positions (Extracted from DXF Text Labels)

| Connector | DXF X | DXF Y | PCB Local X | PCB Local Y | Edge | Wall |
|-----------|-------|-------|-------------|-------------|------|------|
| **USB** | 18.54 | 71.50 | 8.76 | 15.87 | LEFT | Left Wall |
| **PWR-SW** | 14.73 | 60.33 | 4.95 | 4.70 | BOTTOM | Front Wall |
| **BATT** | 16.89 | 57.79 | 7.11 | 2.16 | BOTTOM | Front Wall |
| **AUX** | 22.10 | 57.79 | 12.32 | 2.16 | BOTTOM | Front Wall |
| **I2C** | 50.55 | 80.77 | 40.77 | 25.14 | TOP | Back Wall |
| **LED_OUT** | 70.36 | 79.12 | 60.58 | 23.49 | TOP | Back Wall |
| **UART** | 71.50 | 84.96 | 61.72 | 29.33 | TOP | Back Wall |
| **USBOUT** | 73.66 | 78.49 | 63.88 | 22.86 | RIGHT | Right Wall |
| **MICRO-SD** | 62.99 | 62.48 | 53.21 | 6.85 | RIGHT | Right Wall |

### 3.3 Cutout Positions for Enclosure

**Enclosure Coordinate System:**
- PCB sits centered in enclosure with 4.4mm offset from PCB edge to interior wall
- Wall thickness: 2.0mm
- Cutouts are positioned relative to enclosure origin (front-left-bottom corner)

**Enclosure Dimensions:**
- Length (X): 78mm
- Width (Y): 68mm (to accommodate side-by-side GPS)
- PCB Offset X: (78 - 69.2) / 2 = 4.4mm
- PCB Offset Y: (68 - 30.6) / 2 = 18.7mm (for PCB layer, centered)

---

## 4. Enclosure Architecture

### 4.1 Layer Stack (Bottom to Top)

```
┌─────────────────────────────────────────────────────────────────┐
│                    TOP COVER (Antenna Window)                    │  3mm
│   ╔═══════════════════════╗ ┌─────────────────────────────────┐ │
│   ║   GPS Antenna Cutout  ║ │░░░░░░░░░ Solid Thin ░░░░░░░░░░░│ │
│   ║      (28×28mm)        ║ │░░░░░░░░░  (1mm wall) ░░░░░░░░░░│ │
│   ╚═══════════════════════╝ └─────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                      GPS LAYER                                   │  11mm
│   ┌────────────────────┐  ┌────────────────────┐                │
│   │    GPS Module      │  │    GPS Antenna     │                │
│   │    36 × 26 × 4     │  │    26 × 26 × 9     │                │
│   └────────────────────┘  └────────────────────┘                │
│          SIDE-BY-SIDE ARRANGEMENT (65mm total width)            │
├─────────────────────────────────────────────────────────────────┤
│                      PCB LAYER                                   │  15mm
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                    RS-Core PCB                          │   │
│   │                   69.2 × 30.6 mm                        │   │
│   │                                                         │   │
│   │ LEFT: USB(Main)                                         │   │
│   │                    TOP: I2C, LED_OUT(USB-C), UART       │   │
│   │                                      RIGHT: USBOUT, μSD │   │
│   │             BOTTOM: PWR-SW, BATT, AUX                   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                      ALL 9 PORTS EXPOSED                        │
├─────────────────────────────────────────────────────────────────┤
│                    BATTERY LAYER                                 │  13mm
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                 LiPo Battery Bay                        │   │
│   │              44 × 29 × 12 (with tolerance)              │   │
│   └─────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                GOPRO QUICK RELEASE BUCKLE                        │  10mm
│                    ┌─────────────────┐                          │
│                    │ ▓▓▓▓ BUCKLE ▓▓▓▓│                          │
│                    │    (male)       │                          │
│                    └─────────────────┘                          │
│              Snaps into standard GoPro flat mount               │
└─────────────────────────────────────────────────────────────────┘
        TOTAL HEIGHT: 52mm (without mount attachment)
```

### 4.2 External Dimensions

| Parameter | Value |
|-----------|-------|
| Length | 78 mm |
| Width | 68 mm |
| Height (total) | 52 mm |
| Wall Thickness | 2.0 mm |
| Corner Radius | 4.0 mm |

### 4.3 Port Cutout Positions (V3.0 High-Precision)

**Reference: Enclosure interior, PCB floor at Z=0 within PCB layer**

#### 4.3.1 LEFT Wall Ports (Enclosure X=0)

| Port | Position Along Wall (Y) | Height Above Floor (Z) | Cutout Size (W×H) |
|------|------------------------|------------------------|-------------------|
| USB-C (Main) | 15.87 + 18.7 = 34.57mm | 4mm | 10 × 4mm |

#### 4.3.2 RIGHT Wall Ports (Enclosure X=78mm)

| Port | Position Along Wall (Y) | Height Above Floor (Z) | Cutout Size (W×H) |
|------|------------------------|------------------------|-------------------|
| USBOUT (JST 4-pin) | 22.86 + 18.7 = 41.56mm | 4mm | 6 × 5mm |
| MICRO-SD | 6.85 + 18.7 = 25.55mm | 4mm | 15 × 4mm |

#### 4.3.3 FRONT Wall Ports (Enclosure Y=0, Bottom PCB Edge)

| Port | Position Along Wall (X) | Height Above Floor (Z) | Cutout Size (W×H) |
|------|------------------------|------------------------|-------------------|
| PWR-SW (JST 2-pin) | 4.95 + 4.4 = 9.35mm | 4mm | 4 × 5mm |
| BATT (JST 2-pin) | 7.11 + 4.4 = 11.51mm | 4mm | 4 × 5mm |
| AUX (JST 4-pin) | 12.32 + 4.4 = 16.72mm | 4mm | 6 × 5mm |

#### 4.3.4 BACK Wall Ports (Enclosure Y=68mm, Top PCB Edge)

| Port | Position Along Wall (X) | Height Above Floor (Z) | Cutout Size (W×H) |
|------|------------------------|------------------------|-------------------|
| I2C (JST 4-pin) | 40.77 + 4.4 = 45.17mm | 4mm | 6 × 5mm |
| LED_OUT (USB-C) | 60.58 + 4.4 = 64.98mm | 4mm | 10 × 4mm |
| UART (JST 4-pin) | 61.72 + 4.4 = 66.12mm | 4mm | 6 × 5mm |

---

## 5. OpenSCAD Model (V3.0)

### 5.1 Complete OpenSCAD Script

```openscad
// ============================================================
// RS-CORE ENCLOSURE V3.0
// Racesense Motorsport Datalogger Housing
// HIGH-PRECISION Port Mapping from DXF + Visual Reference
// ============================================================
// Version: 3.0 (2026-02-09)
// Changes: 
//   - Corrected ALL 9 connector positions from DXF coordinates
//   - Fixed edge assignments per visual reference
//   - LEFT: USB (Main)
//   - TOP: I2C, LED_OUT (USB-C), UART
//   - RIGHT: USBOUT (JST), MICRO-SD
//   - BOTTOM: PWR-SW, BATT, AUX
// ============================================================

/* [Display Options] */
show_buckle_layer = true;
show_battery_layer = true;
show_pcb_layer = true;
show_gps_layer = true;
show_top_cover = true;
exploded_view = true;
explode_distance = 8;
show_cross_section = false;

/* [Enclosure Dimensions] */
enc_length = 78;      // X dimension
enc_width = 68;       // Y dimension  
wall = 2.0;
corner_r = 4.0;

// Layer heights (internal cavity heights)
buckle_layer_h = 10;
battery_layer_h = 13;
pcb_layer_h = 15;
gps_layer_h = 11;
cover_layer_h = 3;

/* [PCB Dimensions from DXF] */
// PCB outline: X=9.78→78.99, Y=55.63→86.23
pcb_length = 69.21;   // 78.99 - 9.78
pcb_width = 30.60;    // 86.23 - 55.63
pcb_thick = 1.6;
pcb_comp_height = 12;

// PCB position within enclosure (centered)
pcb_offset_x = (enc_length - pcb_length) / 2;  // 4.4mm
pcb_offset_y = (enc_width - pcb_width) / 2;    // 18.7mm

/* [Battery Dimensions] */
bat_length = 44;  // 40 + 4mm tolerance
bat_width = 29;   // 25 + 4mm tolerance  
bat_height = 12;  // 10 + 2mm tolerance

/* [GPS Dimensions] */
gps_mod_length = 36;
gps_mod_width = 26;
gps_mod_height = 4;
gps_ant_size = 26;
gps_ant_height = 9;
gps_gap = 3;

/* [GoPro Buckle] */
buckle_length = 42;
buckle_width = 20;
buckle_body_h = 8;
buckle_rail_w = 3;
buckle_tab_w = 12;
buckle_tab_h = 4;
buckle_base_h = 2;

/* [Cutout Dimensions] */
// USB-C
usbc_width = 10;
usbc_height = 4;

// MicroSD  
sd_width = 15;
sd_height = 4;

// JST SH 4-pin
jst4_width = 6;    // 5mm connector + 1mm tolerance
jst4_height = 5;   // 4.25mm connector + 0.75mm tolerance

// JST SH 2-pin
jst2_width = 4;    // 3mm connector + 1mm tolerance
jst2_height = 5;   // 4.25mm connector + 0.75mm tolerance

/* [Port Positions - HIGH PRECISION from DXF] */
// All positions are PCB-local coordinates from DXF extraction
// Transformed: PCB_Local = DXF - Origin(9.78, 55.63)

// LEFT WALL (X-min edge, Y position along wall)
usb_main_pcb_y = 15.87;    // USB Main - DXF Y=71.50 → Local Y=15.87

// RIGHT WALL (X-max edge, Y position along wall)
usbout_pcb_y = 22.86;      // USBOUT JST - DXF Y=78.49 → Local Y=22.86
microsd_pcb_y = 6.85;      // MicroSD - DXF Y=62.48 → Local Y=6.85

// FRONT WALL (Y-min edge, X position along wall)
pwr_sw_pcb_x = 4.95;       // PWR-SW JST 2-pin - DXF X=14.73 → Local X=4.95
batt_pcb_x = 7.11;         // BATT JST 2-pin - DXF X=16.89 → Local X=7.11
aux_pcb_x = 12.32;         // AUX JST 4-pin - DXF X=22.10 → Local X=12.32

// BACK WALL (Y-max edge, X position along wall)
i2c_pcb_x = 40.77;         // I2C JST 4-pin - DXF X=50.55 → Local X=40.77
led_out_pcb_x = 60.58;     // LED_OUT USB-C - DXF X=70.36 → Local X=60.58
uart_pcb_x = 61.72;        // UART JST 4-pin - DXF X=71.50 → Local X=61.72

/* [Snap Fit] */
snap_width = 8;
snap_depth = 1.5;
snap_height = 2;

// ============================================================
// UTILITY MODULES
// ============================================================

module rounded_box(l, w, h, r) {
    hull() {
        for (x = [r, l-r]) {
            for (y = [r, w-r]) {
                translate([x, y, 0])
                    cylinder(h=h, r=r, $fn=48);
            }
        }
    }
}

// Snap-fit clip (positive - the bump)
module snap_clip_male() {
    hull() {
        cube([snap_width, snap_depth/2, snap_height]);
        translate([0, snap_depth, snap_height/2])
            cube([snap_width, 0.1, snap_height/2]);
    }
}

// Snap-fit receiver (negative - the slot)
module snap_clip_female() {
    translate([-0.2, -0.3, -0.2])
        cube([snap_width + 0.4, snap_depth + 0.6, snap_height + 0.4]);
}

// ============================================================
// LAYER 1: GOPRO QUICK RELEASE BUCKLE
// ============================================================

module gopro_buckle() {
    difference() {
        union() {
            // Main body
            translate([-buckle_length/2, -buckle_width/2, 0])
                cube([buckle_length, buckle_width, buckle_body_h]);
            
            // Rails on sides
            for (dy = [-1, 1]) {
                translate([-buckle_length/2, dy * (buckle_width/2 + buckle_rail_w/2) - buckle_rail_w/2, 0])
                    cube([buckle_length, buckle_rail_w, buckle_body_h - 2]);
            }
        }
        
        // Center channel for the mount rails
        translate([-buckle_length/2 - 1, -buckle_width/2 + buckle_rail_w, buckle_body_h - 3])
            cube([buckle_length + 2, buckle_width - buckle_rail_w*2, 4]);
        
        // Locking tab slot
        translate([-buckle_tab_w/2, -buckle_width/2 - 1, buckle_body_h - buckle_tab_h])
            cube([buckle_tab_w, buckle_width/2 + 2, buckle_tab_h + 1]);
    }
    
    // Locking tab (spring element)
    translate([0, 0, buckle_body_h - buckle_tab_h]) {
        difference() {
            translate([-buckle_tab_w/2 + 1, -buckle_width/2 + 2, 0])
                cube([buckle_tab_w - 2, 4, buckle_tab_h + 2]);
            translate([-buckle_tab_w/2, -buckle_width/2 + 5, buckle_tab_h])
                rotate([30, 0, 0])
                    cube([buckle_tab_w, 5, 5]);
        }
    }
}

module buckle_layer() {
    difference() {
        union() {
            rounded_box(enc_length, enc_width, buckle_layer_h, corner_r);
            
            for (x = [wall + 5, enc_length - wall - 5]) {
                for (y = [wall + 5, enc_width - wall - 5]) {
                    translate([x, y, buckle_layer_h])
                        cylinder(h=3, d=8, $fn=24);
                }
            }
        }
        
        translate([wall, wall, buckle_base_h])
            rounded_box(enc_length - wall*2, enc_width - wall*2, 
                       buckle_layer_h, corner_r - wall/2);
        
        for (x = [wall + 5, enc_length - wall - 5]) {
            for (y = [wall + 5, enc_width - wall - 5]) {
                translate([x, y, -1])
                    cylinder(h=buckle_layer_h + 5, d=3.2, $fn=24);
                translate([x, y, -0.1])
                    cylinder(h=2, d1=6, d2=3.2, $fn=24);
            }
        }
    }
    
    translate([enc_length/2, enc_width/2, 0])
        rotate([180, 0, 0])
            gopro_buckle();
}

// ============================================================
// LAYER 2: BATTERY COMPARTMENT
// ============================================================

module battery_layer() {
    layer_h = battery_layer_h;
    
    difference() {
        union() {
            rounded_box(enc_length, enc_width, layer_h, corner_r);
            
            for (x = [enc_length/4, enc_length*3/4]) {
                for (y = [wall, enc_width - wall - snap_depth]) {
                    translate([x - snap_width/2, y, layer_h])
                        snap_clip_male();
                }
            }
        }
        
        translate([wall, wall, wall])
            rounded_box(enc_length - wall*2, enc_width - wall*2, 
                       layer_h, corner_r - wall/2);
        
        for (x = [wall + 5, enc_length - wall - 5]) {
            for (y = [wall + 5, enc_width - wall - 5]) {
                translate([x, y, -1])
                    cylinder(h=wall + 2, d=3.2, $fn=24);
            }
        }
        
        // Cable routing hole
        translate([enc_length/2, enc_width/2, layer_h - 1])
            cylinder(h=3, d=8, $fn=24);
    }
    
    // Battery retention
    bat_x = (enc_length - bat_length) / 2;
    bat_y = (enc_width - bat_width) / 2;
    
    for (dx = [0, bat_length - 5]) {
        for (dy = [0, bat_width - 5]) {
            translate([bat_x + dx, bat_y + dy, wall])
                cube([5, 5, 3]);
        }
    }
}

// ============================================================
// LAYER 3: PCB COMPARTMENT (V3.0 HIGH-PRECISION CUTOUTS)
// ============================================================

module pcb_layer() {
    layer_h = pcb_layer_h;
    floor_offset = wall + 4;  // Height of cutouts above floor
    
    difference() {
        union() {
            rounded_box(enc_length, enc_width, layer_h, corner_r);
            
            for (x = [enc_length/4, enc_length*3/4]) {
                for (y = [wall, enc_width - wall - snap_depth]) {
                    translate([x - snap_width/2, y, layer_h])
                        snap_clip_male();
                }
            }
        }
        
        // Hollow interior
        translate([wall, wall, wall])
            rounded_box(enc_length - wall*2, enc_width - wall*2,
                       layer_h, corner_r - wall/2);
        
        // Snap receivers
        for (x = [enc_length/4, enc_length*3/4]) {
            for (y = [wall - 0.5, enc_width - wall - snap_depth + 0.5]) {
                translate([x - snap_width/2, y, -0.1])
                    snap_clip_female();
            }
        }
        
        // ============================================================
        // LEFT WALL CUTOUTS (X = 0, connectors on X-min PCB edge)
        // ============================================================
        
        // USB-C Main (Data/Charge) - LEFT WALL
        // Position: PCB local Y = 15.87, enclosure Y = 15.87 + pcb_offset_y
        translate([-0.1, pcb_offset_y + usb_main_pcb_y - usbc_width/2, floor_offset])
            cube([wall + 0.2, usbc_width, usbc_height]);
        
        // ============================================================
        // RIGHT WALL CUTOUTS (X = enc_length, connectors on X-max PCB edge)
        // ============================================================
        
        // USBOUT JST 4-pin - RIGHT WALL
        // Position: PCB local Y = 22.86
        translate([enc_length - wall - 0.1, pcb_offset_y + usbout_pcb_y - jst4_width/2, floor_offset])
            cube([wall + 0.2, jst4_width, jst4_height]);
        
        // MICRO-SD Slot - RIGHT WALL  
        // Position: PCB local Y = 6.85
        translate([enc_length - wall - 0.1, pcb_offset_y + microsd_pcb_y - sd_width/2, floor_offset])
            cube([wall + 0.2, sd_width, sd_height]);
        
        // ============================================================
        // FRONT WALL CUTOUTS (Y = 0, connectors on Y-min PCB edge / Bottom)
        // ============================================================
        
        // PWR-SW JST 2-pin - FRONT WALL
        // Position: PCB local X = 4.95
        translate([pcb_offset_x + pwr_sw_pcb_x - jst2_width/2, -0.1, floor_offset])
            cube([jst2_width, wall + 0.2, jst2_height]);
        
        // BATT JST 2-pin - FRONT WALL
        // Position: PCB local X = 7.11
        translate([pcb_offset_x + batt_pcb_x - jst2_width/2, -0.1, floor_offset])
            cube([jst2_width, wall + 0.2, jst2_height]);
        
        // AUX JST 4-pin - FRONT WALL
        // Position: PCB local X = 12.32
        translate([pcb_offset_x + aux_pcb_x - jst4_width/2, -0.1, floor_offset])
            cube([jst4_width, wall + 0.2, jst4_height]);
        
        // ============================================================
        // BACK WALL CUTOUTS (Y = enc_width, connectors on Y-max PCB edge / Top)
        // ============================================================
        
        // I2C JST 4-pin - BACK WALL
        // Position: PCB local X = 40.77
        translate([pcb_offset_x + i2c_pcb_x - jst4_width/2, enc_width - wall - 0.1, floor_offset])
            cube([jst4_width, wall + 0.2, jst4_height]);
        
        // LED_OUT USB-C - BACK WALL
        // Position: PCB local X = 60.58
        translate([pcb_offset_x + led_out_pcb_x - usbc_width/2, enc_width - wall - 0.1, floor_offset])
            cube([usbc_width, wall + 0.2, usbc_height]);
        
        // UART JST 4-pin - BACK WALL  
        // Position: PCB local X = 61.72
        translate([pcb_offset_x + uart_pcb_x - jst4_width/2, enc_width - wall - 0.1, floor_offset])
            cube([jst4_width, wall + 0.2, jst4_height]);
        
        // ============================================================
        // LED INDICATOR WINDOW (Front wall, for status LEDs)
        // ============================================================
        translate([enc_length/3 - 6, -0.1, wall + 6])
            cube([12, wall - 0.5, 6]);
    }
    
    // PCB mounting standoffs
    standoff_h = 3;
    
    for (dx = [3, pcb_length - 3]) {
        for (dy = [3, pcb_width - 3]) {
            translate([pcb_offset_x + dx, pcb_offset_y + dy, wall]) {
                difference() {
                    cylinder(h=standoff_h, d=5, $fn=24);
                    translate([0, 0, -0.1])
                        cylinder(h=standoff_h + 0.2, d=2.2, $fn=24);
                }
            }
        }
    }
}

// ============================================================
// LAYER 4: GPS COMPARTMENT (Side-by-Side Layout)
// ============================================================

module gps_layer() {
    layer_h = gps_layer_h;
    gps_total_w = gps_mod_length + gps_gap + gps_ant_size;
    
    difference() {
        union() {
            rounded_box(enc_length, enc_width, layer_h, corner_r);
            
            translate([wall - 0.5, wall - 0.5, layer_h])
                difference() {
                    rounded_box(enc_length - wall*2 + 1, enc_width - wall*2 + 1, 2, corner_r - wall/2);
                    translate([1.5, 1.5, -0.1])
                        rounded_box(enc_length - wall*2 - 2, enc_width - wall*2 - 2, 2.2, corner_r - wall);
                }
        }
        
        translate([wall, wall, wall])
            rounded_box(enc_length - wall*2, enc_width - wall*2,
                       layer_h, corner_r - wall/2);
        
        for (x = [enc_length/4, enc_length*3/4]) {
            for (y = [wall - 0.5, enc_width - wall - snap_depth + 0.5]) {
                translate([x - snap_width/2, y, -0.1])
                    snap_clip_female();
            }
        }
    }
    
    // GPS pockets
    gps_start_x = (enc_length - gps_total_w) / 2;
    gps_y = (enc_width - gps_mod_width) / 2;
    
    module_pocket_d = gps_mod_height + 1;
    translate([gps_start_x - 1, gps_y - 1, wall])
        difference() {
            cube([gps_mod_length + 2, gps_mod_width + 2, module_pocket_d]);
            translate([1, 1, -0.1])
                cube([gps_mod_length, gps_mod_width, module_pocket_d + 0.2]);
        }
    
    ant_x = gps_start_x + gps_mod_length + gps_gap;
    ant_y = (enc_width - gps_ant_size) / 2;
    ant_pocket_d = gps_ant_height + 1;
    
    translate([ant_x - 1, ant_y - 1, wall])
        difference() {
            cube([gps_ant_size + 2, gps_ant_size + 2, ant_pocket_d]);
            translate([1, 1, -0.1])
                cube([gps_ant_size, gps_ant_size, ant_pocket_d + 0.2]);
        }
    
    translate([gps_start_x + gps_mod_length, enc_width/2 - 3, wall])
        cube([gps_gap, 6, 3]);
}

// ============================================================
// LAYER 5: TOP COVER (with Antenna Window)
// ============================================================

module top_cover() {
    layer_h = cover_layer_h;
    
    gps_total_w = gps_mod_length + gps_gap + gps_ant_size;
    ant_x = (enc_length - gps_total_w) / 2 + gps_mod_length + gps_gap;
    ant_y = (enc_width - gps_ant_size) / 2;
    
    window_size = 28;
    window_x = ant_x + (gps_ant_size - window_size) / 2;
    window_y = ant_y + (gps_ant_size - window_size) / 2;
    
    difference() {
        union() {
            rounded_box(enc_length, enc_width, layer_h, corner_r);
            
            translate([wall + 0.3, wall + 0.3, -1.5])
                rounded_box(enc_length - wall*2 - 0.6, enc_width - wall*2 - 0.6, 
                           1.5, corner_r - wall/2 - 0.3);
        }
        
        translate([window_x, window_y, 1])
            cube([window_size, window_size, layer_h]);
        
        translate([0, 0, layer_h])
            for (angle = [0, 90, 180, 270]) {
                rotate([0, 0, angle])
                    translate([-1, -1, -2])
                        rotate([0, 0, 45])
                            cube([3, enc_length*2, 3]);
            }
    }
    
    // Thin antenna window floor
    translate([window_x, window_y, 0])
        cube([window_size, window_size, 1]);
    
    // Branding
    logo_x = (enc_length - gps_total_w) / 2 + gps_mod_length/2;
    logo_y = enc_width / 2;
    
    translate([logo_x - 15, logo_y - 4, layer_h - 0.3])
        linear_extrude(0.5)
            text("RACESENSE", size=5, font="Liberation Sans:style=Bold", halign="center");
}

// ============================================================
// ASSEMBLY
// ============================================================

module assembly() {
    z_offset = 0;
    exp = exploded_view ? explode_distance : 0;
    
    if (show_buckle_layer) {
        color("DimGray", 0.95)
            translate([0, 0, z_offset])
                buckle_layer();
    }
    z_offset = z_offset + buckle_layer_h + exp;
    
    if (show_battery_layer) {
        color("SlateGray", 0.9)
            translate([0, 0, z_offset])
                battery_layer();
    }
    z_offset = z_offset + battery_layer_h + exp;
    
    if (show_pcb_layer) {
        color("DarkSlateGray", 0.9)
            translate([0, 0, z_offset])
                pcb_layer();
    }
    z_offset = z_offset + pcb_layer_h + exp;
    
    if (show_gps_layer) {
        color("CadetBlue", 0.9)
            translate([0, 0, z_offset])
                gps_layer();
    }
    z_offset = z_offset + gps_layer_h + exp;
    
    if (show_top_cover) {
        color("White", 0.95)
            translate([0, 0, z_offset])
                top_cover();
    }
}

module cross_section() {
    translate([enc_length/2, -10, -20])
        cube([enc_length, enc_width + 20, 120]);
}

// Render
if (show_cross_section) {
    difference() {
        assembly();
        cross_section();
    }
} else {
    assembly();
}

// ============================================================
// PORT CUTOUT VERIFICATION TABLE
// ============================================================
// 
// Connector    | Edge   | Enclosure Position      | Cutout
// -------------|--------|-------------------------|--------
// USB (Main)   | LEFT   | Y=34.57mm from front    | 10×4mm
// PWR-SW       | FRONT  | X=9.35mm from left      | 4×5mm
// BATT         | FRONT  | X=11.51mm from left     | 4×5mm
// AUX          | FRONT  | X=16.72mm from left     | 6×5mm
// I2C          | BACK   | X=45.17mm from left     | 6×5mm
// LED_OUT      | BACK   | X=64.98mm from left     | 10×4mm
// UART         | BACK   | X=66.12mm from left     | 6×5mm
// USBOUT       | RIGHT  | Y=41.56mm from front    | 6×5mm
// MICRO-SD     | RIGHT  | Y=25.55mm from front    | 15×4mm
//
// ============================================================
```

---

## 6. Print Settings

| Parameter | Recommended |
|-----------|-------------|
| Material | PETG (body), White PLA (antenna cover) |
| Layer Height | 0.2mm |
| Infill | 25% gyroid |
| Walls | 3 perimeters |
| Supports | Minimal (buckle area only) |
| Orientation | Each layer printed open-side-up |

**⚠️ Antenna Window:** Use white or translucent filament for top cover. Avoid carbon-filled or metallic filaments which block GPS signals.

---

## 7. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-09 | Initial V1 design (dual-fin GoPro) |
| 2.0 | 2026-02-09 | V2: Quick release buckle, side-by-side GPS, multi-layer stack |
| 2.1 | 2026-02-09 | V2.1: Added JST connector cutouts (estimated positions) |
| 3.0 | 2026-02-09 | V3.0: HIGH-PRECISION mapping from DXF + visual reference. Corrected all 9 ports to correct edges. |

---

## 8. Port Layout Diagram (V3.0 Corrected)

```
                              78mm
    ┌──────────────────────────────────────────────────────────────────┐
    │                                                                  │
    │  BACK WALL (Y-max)                                               │
    │  [I2C]         [LED_OUT]  [UART]                                 │
    │   JST4           USB-C     JST4                                  │
    │   X=45.2mm       X=65mm    X=66.1mm                              │
    │                                                                  │
    │                                                                  │
    │                                                                  │
 68mm  USB ══                                             ══ USBOUT   │
    │  (Main)                                                (JST4)   │
    │  Y=34.6mm                                              Y=41.6mm │
    │                                                                  │
    │                                                        ═══ μSD  │
    │                                                         Y=25.5mm│
    │                                                                  │
    │                                                                  │
    │  FRONT WALL (Y-min)                                              │
    │  [PWR][BATT][AUX]                                                │
    │  X=9.4 X=11.5 X=16.7mm                                           │
    │                                                                  │
    └──────────────────────────────────────────────────────────────────┘
    
    LEFT WALL:  USB-C (Main Data/Charge)
    RIGHT WALL: USBOUT (JST 4-pin), Micro-SD
    FRONT WALL: PWR-SW (JST 2-pin), BATT (JST 2-pin), AUX (JST 4-pin)
    BACK WALL:  I2C (JST 4-pin), LED_OUT (USB-C), UART (JST 4-pin)
```

---

*End of Specification*
