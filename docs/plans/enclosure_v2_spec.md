# RS-Core Enclosure V2 — Mechanical Specification

**Document:** `enclosure_v2_spec.md`  
**Version:** 2.0  
**Date:** 2026-02-09  
**Author:** Racesense Mechanical Engineering  

---

## 1. Overview

This document specifies the **Version 2** 3D-printable enclosure for the **RS-Core** motorsport datalogger. The design features a modular layer-stack architecture with an integrated GoPro Quick Release Buckle (male) for rapid mounting/dismounting.

### 1.1 Key Changes from V1

| Feature | V1 | V2 |
|---------|----|----|
| Mount Type | Dual-fin GoPro prongs | GoPro Quick Release Buckle (male) |
| GPS Layout | Single module (stacked) | Side-by-side module + antenna |
| Shell Design | 2-piece clamshell | Multi-layer stack |
| Port Access | Single USB-C | USB-C (data) + USBOUT (power) + MicroSD |
| Battery Bay | Snug fit | Generous tolerance (+2mm) |

### 1.2 Design Philosophy

- **Layered Stack Architecture:** Buckle → Battery → PCB → GPS → Cover
- **Quick-Release Mounting:** Standard GoPro male buckle for flat adhesive mounts
- **Side-by-Side GPS:** Module (36×26mm) and Antenna (26×26mm) placed horizontally
- **Full Port Exposure:** All connectors accessible without shell removal
- **Premium Finish:** Chamfered edges, integrated branding, and professional aesthetics

---

## 2. Component Dimensions

### 2.1 Core Components

| Component | Dimensions (mm) | Notes |
|-----------|-----------------|-------|
| RS-Core PCB | 69.2 × 30.6 × 1.6 | ~12mm component height |
| LiPo Battery | 40 × 25 × 10 | +2mm tolerance all sides |
| GPS Module | 36 × 26 × 4 | Main GPS receiver |
| GPS Antenna | 26 × 26 × 9 | Ceramic patch (active) |
| USB-C (Data) | 9 × 3.5 | Left side at ~8.8mm from edge |
| USB-C (Power Out) | 9 × 3.5 | Right side at ~63.9mm from edge |
| MicroSD Slot | 14 × 3 | Center-right at ~53.2mm from edge |

### 2.2 GoPro Quick Release Buckle Dimensions

| Parameter | Value | Notes |
|-----------|-------|-------|
| Buckle Length | 42mm | Standard GoPro male |
| Buckle Width | 20mm | Fits standard flat mounts |
| Buckle Height | 10mm | Including locking tab |
| Tab Spring Width | 12mm | Center locking mechanism |
| Interface Slot | 3mm deep | Engagement depth |

---

## 3. Enclosure Architecture

### 3.1 Layer Stack (Bottom to Top)

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
│   │   [USB]                      [μSD]            [USBOUT]  │   │
│   └─────────────────────────────────────────────────────────┘   │
│                      ALL PORTS EXPOSED                          │
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

### 3.2 External Dimensions

| Parameter | Value |
|-----------|-------|
| Length | 78 mm |
| Width | 68 mm |
| Height (total) | 52 mm |
| Wall Thickness | 2.0 mm |
| Corner Radius | 4.0 mm |

### 3.3 Port Cutout Positions

All measurements from enclosure front-left corner (looking at PCB layer from above):

| Port | X Position | Y Position | Cutout Size | Edge |
|------|------------|------------|-------------|------|
| USB-C (Data) | 0mm (left wall) | 13mm | 10 × 4mm | Left |
| MicroSD | 0mm (left wall) | 51mm | 15 × 4mm | Left |
| USB-C (Power) | 68mm (right wall) | 60mm | 10 × 4mm | Right |

---

## 4. Detailed Layer Specifications

### 4.1 Layer 1: GoPro Quick Release Buckle (Base)

The base layer integrates a standard GoPro-compatible male quick release buckle.

**Buckle Geometry:**
```
                 42mm
    ┌───────────────────────────┐
    │     ╔═══════════════╗     │
    │     ║  LOCKING TAB  ║     │ ← Spring-loaded tab
    │     ╚═══════════════╝     │
    │  ┌───────────────────┐    │
    │  │                   │    │  20mm
    │  │   RAIL PROFILE    │    │
    │  │                   │    │
    │  └───────────────────┘    │
    └───────────────────────────┘
            BOTTOM VIEW

    Side Profile:
    ┌─────────────────────────────┐
    │ ████████████████████████████│ ← Base plate (2mm)
    │     ║             ║         │
    │     ║  BUCKLE     ║         │ ← Buckle body (8mm)  
    │     ╚═════════════╝         │
    └─────────────────────────────┘
```

**Key Dimensions:**
- Base plate: 78 × 68 × 2mm (matches enclosure footprint)
- Buckle body: 42 × 20 × 8mm (centered on base)
- Rail width: 3mm each side
- Tab slot: 12 × 4mm (spring cutout)
- Engagement depth: 3mm

### 4.2 Layer 2: Battery Compartment

**Internal Bay Dimensions:** 44 × 29 × 12mm (battery: 40×25×10 + 2mm tolerance per axis)

**Features:**
- Retention clips on short edges
- Cable routing channel (3×3mm) to PCB layer
- Ventilation slots (3× 2mm wide) on base
- Foam pad recess (1mm deep) for vibration isolation

### 4.3 Layer 3: PCB Compartment

**Internal Dimensions:** 73 × 34 × 15mm

**Port Cutouts:**
| Port | Wall | Position from Bottom of Layer | Cutout |
|------|------|-------------------------------|--------|
| USB-C (Data) | Left | 4mm up | 10 × 4mm |
| MicroSD | Left | 6mm up | 15 × 4mm |
| USB-C (Power Out) | Right | 4mm up | 10 × 4mm |

**PCB Mounting:**
- 4× corner standoffs (3mm height, M2 holes)
- Edge retention lips (1mm overhang)
- Component clearance zone: 12mm above PCB surface

### 4.4 Layer 4: GPS Compartment

**Layout:** Side-by-side GPS module and antenna

```
    ┌────────────────────────────────────────────────────────────┐
    │                       GPS LAYER (11mm height)               │
    │  ┌────────────────────────────┐ ┌────────────────────────┐ │
    │  │                            │ │                        │ │
    │  │      GPS MODULE            │ │     GPS ANTENNA        │ │
    │  │      36 × 26 × 4mm         │ │     26 × 26 × 9mm      │ │
    │  │                            │ │                        │ │
    │  │                            │ │     ▓▓▓▓▓▓▓▓▓▓▓        │ │
    │  │                            │ │     ▓ CERAMIC ▓        │ │
    │  │                            │ │     ▓  PATCH  ▓        │ │
    │  │                            │ │     ▓▓▓▓▓▓▓▓▓▓▓        │ │
    │  └────────────────────────────┘ └────────────────────────┘ │
    │         3mm gap between module and antenna                  │
    └────────────────────────────────────────────────────────────┘
         Total GPS assembly width: 36 + 3 + 26 = 65mm
```

**Mounting:**
- Module pocket: 38 × 28 × 5mm (with tolerance)
- Antenna pocket: 28 × 28 × 10mm (recessed for antenna height)
- Cable routing: 6mm channel between pockets

### 4.5 Layer 5: Top Cover

**Features:**
- Antenna window cutout: 28 × 28mm (1mm wall thickness)
- Solid cover over GPS module area
- Snap-fit engagement with GPS layer
- Chamfered top edges (2mm × 45°)
- Racesense branding emboss (optional)

---

## 5. Assembly System

### 5.1 Layer Connection Method

**Primary:** Snap-fit with screw backup

| Connection | Method |
|------------|--------|
| Buckle → Battery | 4× M3 screws (countersunk) |
| Battery → PCB | Snap-fit clips (4 corners) |
| PCB → GPS | Snap-fit clips (4 corners) |
| GPS → Cover | Snap-fit perimeter (tool-free) |

### 5.2 Bill of Materials

| Item | Qty | Notes |
|------|-----|-------|
| Base/Buckle Layer | 1 | 3D printed (PETG/ABS) |
| Battery Layer | 1 | 3D printed |
| PCB Layer | 1 | 3D printed |
| GPS Layer | 1 | 3D printed |
| Top Cover | 1 | 3D printed (light color for antenna) |
| M3 × 8mm screws | 4 | Pan head, for base assembly |
| M2 × 5mm screws | 4 | PCB mounting (optional) |
| Foam pad | 1 | 38 × 23 × 1mm, battery cushion |

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

## 7. OpenSCAD Model

### 7.1 Complete OpenSCAD Script

```openscad
// ============================================================
// RS-CORE ENCLOSURE V2.0
// Racesense Motorsport Datalogger Housing
// GoPro Quick Release + Side-by-Side GPS
// ============================================================
// Usage: Render with F6, export STL for each layer separately
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
enc_length = 78;
enc_width = 68;
wall = 2.0;
corner_r = 4.0;

// Layer heights (internal cavity heights)
buckle_layer_h = 10;
battery_layer_h = 13;
pcb_layer_h = 15;
gps_layer_h = 11;
cover_layer_h = 3;

/* [Component Dimensions] */
// PCB
pcb_length = 69.2;
pcb_width = 30.6;
pcb_thick = 1.6;
pcb_comp_height = 12;

// Battery (with tolerance)
bat_length = 44;  // 40 + 4mm tolerance
bat_width = 29;   // 25 + 4mm tolerance  
bat_height = 12;  // 10 + 2mm tolerance

// GPS Module
gps_mod_length = 36;
gps_mod_width = 26;
gps_mod_height = 4;

// GPS Antenna
gps_ant_size = 26;
gps_ant_height = 9;

// Gap between GPS module and antenna
gps_gap = 3;

/* [GoPro Buckle] */
buckle_length = 42;
buckle_width = 20;
buckle_body_h = 8;
buckle_rail_w = 3;
buckle_tab_w = 12;
buckle_tab_h = 4;
buckle_base_h = 2;

/* [Port Cutouts] */
usbc_width = 10;
usbc_height = 4;
sd_width = 15;
sd_height = 4;

// Port positions (Y from front edge of enclosure)
usb_data_y = 13;    // USB-C data port
usb_power_y = 60;   // USB-C power out
sd_slot_y = 51;     // MicroSD slot

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

module chamfer_edge(l, chamfer=2) {
    rotate([0, 0, 0])
        linear_extrude(height=l)
            polygon([[0, 0], [chamfer, 0], [0, chamfer]]);
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
    // The male buckle profile that snaps into GoPro flat mounts
    
    // Rail profile (slides into mount)
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
            // Angle the tab
            translate([-buckle_tab_w/2, -buckle_width/2 + 5, buckle_tab_h])
                rotate([30, 0, 0])
                    cube([buckle_tab_w, 5, 5]);
        }
    }
}

module buckle_layer() {
    difference() {
        union() {
            // Base plate
            rounded_box(enc_length, enc_width, buckle_layer_h, corner_r);
            
            // Screw bosses for connection to battery layer
            for (x = [wall + 5, enc_length - wall - 5]) {
                for (y = [wall + 5, enc_width - wall - 5]) {
                    translate([x, y, buckle_layer_h])
                        cylinder(h=3, d=8, $fn=24);
                }
            }
        }
        
        // Hollow out upper portion (leave solid base for buckle)
        translate([wall, wall, buckle_base_h])
            rounded_box(enc_length - wall*2, enc_width - wall*2, 
                       buckle_layer_h, corner_r - wall/2);
        
        // Screw holes
        for (x = [wall + 5, enc_length - wall - 5]) {
            for (y = [wall + 5, enc_width - wall - 5]) {
                translate([x, y, -1])
                    cylinder(h=buckle_layer_h + 5, d=3.2, $fn=24);
                // Countersink from bottom
                translate([x, y, -0.1])
                    cylinder(h=2, d1=6, d2=3.2, $fn=24);
            }
        }
    }
    
    // Add GoPro buckle on bottom (pointing down)
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
            // Outer shell
            rounded_box(enc_length, enc_width, layer_h, corner_r);
            
            // Snap clips on top (male)
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
        
        // Screw holes from buckle layer
        for (x = [wall + 5, enc_length - wall - 5]) {
            for (y = [wall + 5, enc_width - wall - 5]) {
                translate([x, y, -1])
                    cylinder(h=wall + 2, d=3.2, $fn=24);
            }
        }
        
        // Cable routing hole to PCB layer
        translate([enc_length/2, enc_width/2, layer_h - 1])
            cylinder(h=3, d=8, $fn=24);
    }
    
    // Battery retaining features
    bat_x = (enc_length - bat_length) / 2;
    bat_y = (enc_width - bat_width) / 2;
    
    // Corner retention clips for battery
    for (dx = [0, bat_length - 5]) {
        for (dy = [0, bat_width - 5]) {
            translate([bat_x + dx, bat_y + dy, wall])
                cube([5, 5, 3]);
        }
    }
}

// ============================================================
// LAYER 3: PCB COMPARTMENT
// ============================================================

module pcb_layer() {
    layer_h = pcb_layer_h;
    
    difference() {
        union() {
            // Outer shell  
            rounded_box(enc_length, enc_width, layer_h, corner_r);
            
            // Snap clips on top
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
        
        // Snap clip receivers on bottom
        for (x = [enc_length/4, enc_length*3/4]) {
            for (y = [wall - 0.5, enc_width - wall - snap_depth + 0.5]) {
                translate([x - snap_width/2, y, -0.1])
                    snap_clip_female();
            }
        }
        
        // === PORT CUTOUTS ===
        
        // USB-C Data port (LEFT wall)
        translate([-0.1, usb_data_y - usbc_width/2, wall + 4])
            cube([wall + 0.2, usbc_width, usbc_height]);
        
        // MicroSD slot (LEFT wall)  
        translate([-0.1, sd_slot_y - sd_width/2, wall + 6])
            cube([wall + 0.2, sd_width, sd_height]);
        
        // USB-C Power out (RIGHT wall)
        translate([enc_length - wall - 0.1, usb_power_y - usbc_width/2, wall + 4])
            cube([wall + 0.2, usbc_width, usbc_height]);
        
        // LED viewing window (front face)
        translate([enc_length/2 - 6, -0.1, wall + 6])
            cube([12, wall - 0.5, 6]);
    }
    
    // PCB mounting standoffs
    pcb_x = (enc_length - pcb_length) / 2;
    pcb_y = (enc_width - pcb_width) / 2;
    standoff_h = 3;
    
    for (dx = [3, pcb_length - 3]) {
        for (dy = [3, pcb_width - 3]) {
            translate([pcb_x + dx, pcb_y + dy, wall]) {
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
    
    // Total GPS assembly: module (36) + gap (3) + antenna (26) = 65mm
    gps_total_w = gps_mod_length + gps_gap + gps_ant_size;
    
    difference() {
        union() {
            // Outer shell
            rounded_box(enc_length, enc_width, layer_h, corner_r);
            
            // Snap-fit lip for top cover (continuous perimeter)
            translate([wall - 0.5, wall - 0.5, layer_h])
                difference() {
                    rounded_box(enc_length - wall*2 + 1, enc_width - wall*2 + 1, 2, corner_r - wall/2);
                    translate([1.5, 1.5, -0.1])
                        rounded_box(enc_length - wall*2 - 2, enc_width - wall*2 - 2, 2.2, corner_r - wall);
                }
        }
        
        // Hollow interior
        translate([wall, wall, wall])
            rounded_box(enc_length - wall*2, enc_width - wall*2,
                       layer_h, corner_r - wall/2);
        
        // Snap receivers on bottom
        for (x = [enc_length/4, enc_length*3/4]) {
            for (y = [wall - 0.5, enc_width - wall - snap_depth + 0.5]) {
                translate([x - snap_width/2, y, -0.1])
                    snap_clip_female();
            }
        }
    }
    
    // GPS Module pocket (left side)
    gps_start_x = (enc_length - gps_total_w) / 2;
    gps_y = (enc_width - gps_mod_width) / 2;
    
    // Module retention walls
    module_pocket_d = gps_mod_height + 1;
    translate([gps_start_x - 1, gps_y - 1, wall])
        difference() {
            cube([gps_mod_length + 2, gps_mod_width + 2, module_pocket_d]);
            translate([1, 1, -0.1])
                cube([gps_mod_length, gps_mod_width, module_pocket_d + 0.2]);
        }
    
    // Antenna pocket (right side, deeper due to 9mm height)
    ant_x = gps_start_x + gps_mod_length + gps_gap;
    ant_y = (enc_width - gps_ant_size) / 2;
    ant_pocket_d = gps_ant_height + 1;
    
    translate([ant_x - 1, ant_y - 1, wall])
        difference() {
            cube([gps_ant_size + 2, gps_ant_size + 2, ant_pocket_d]);
            translate([1, 1, -0.1])
                cube([gps_ant_size, gps_ant_size, ant_pocket_d + 0.2]);
        }
    
    // Cable channel between module and antenna
    translate([gps_start_x + gps_mod_length, enc_width/2 - 3, wall])
        cube([gps_gap, 6, 3]);
}

// ============================================================
// LAYER 5: TOP COVER (with Antenna Window)
// ============================================================

module top_cover() {
    layer_h = cover_layer_h;
    
    // Antenna window position (centered over antenna in GPS layer)
    gps_total_w = gps_mod_length + gps_gap + gps_ant_size;
    ant_x = (enc_length - gps_total_w) / 2 + gps_mod_length + gps_gap;
    ant_y = (enc_width - gps_ant_size) / 2;
    
    // Window is slightly smaller than antenna for retention
    window_size = 28;
    window_x = ant_x + (gps_ant_size - window_size) / 2;
    window_y = ant_y + (gps_ant_size - window_size) / 2;
    
    difference() {
        union() {
            // Main cover plate
            rounded_box(enc_length, enc_width, layer_h, corner_r);
            
            // Snap-fit lip (goes inside GPS layer rim)
            translate([wall + 0.3, wall + 0.3, -1.5])
                rounded_box(enc_length - wall*2 - 0.6, enc_width - wall*2 - 0.6, 
                           1.5, corner_r - wall/2 - 0.3);
        }
        
        // Antenna window cutout (thin floor, 1mm)
        translate([window_x, window_y, 1])
            cube([window_size, window_size, layer_h]);
        
        // Chamfer top edges
        translate([0, 0, layer_h])
            for (angle = [0, 90, 180, 270]) {
                rotate([0, 0, angle])
                    translate([-1, -1, -2])
                        rotate([0, 0, 45])
                            cube([3, enc_length*2, 3]);
            }
    }
    
    // Thin antenna window floor (1mm for RF transparency)
    translate([window_x, window_y, 0])
        cube([window_size, window_size, 1]);
    
    // Branding emboss (optional - Racesense logo area)
    logo_x = (enc_length - gps_total_w) / 2 + gps_mod_length/2;
    logo_y = enc_width / 2;
    
    translate([logo_x - 15, logo_y - 4, layer_h - 0.3])
        linear_extrude(0.5)
            text("RACESENSE", size=5, font="Liberation Sans:style=Bold", halign="center");
}

// ============================================================
// ASSEMBLY
// ============================================================

module cross_section() {
    translate([enc_length/2, -10, -20])
        cube([enc_length, enc_width + 20, 120]);
}

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
// EXPORT INSTRUCTIONS  
// ============================================================
// To export individual STL files:
//
// 1. Buckle Layer:
//    show_buckle_layer=true, all others=false
//    Render (F6) → Export → rs-core-v2_buckle.stl
//
// 2. Battery Layer:
//    show_battery_layer=true, all others=false  
//    Render (F6) → Export → rs-core-v2_battery.stl
//
// 3. PCB Layer:
//    show_pcb_layer=true, all others=false
//    Render (F6) → Export → rs-core-v2_pcb.stl
//
// 4. GPS Layer:
//    show_gps_layer=true, all others=false
//    Render (F6) → Export → rs-core-v2_gps.stl
//
// 5. Top Cover:
//    show_top_cover=true, all others=false
//    Render (F6) → Export → rs-core-v2_cover.stl
//    ⚠️ Print in WHITE or TRANSLUCENT material!
//
// Print all layers with open side facing UP
// ============================================================
```

---

## 8. Rendering Instructions

### 8.1 Quick Start

1. Open **[OpenSCAD](https://openscad.org)** or **[OpenSCAD Playground](https://ochafik.com/openscad2/)**
2. Paste the complete script from Section 7.1
3. Press **F5** (Preview) or **F6** (Render)
4. Use mouse to rotate and zoom

### 8.2 View Modes

| Setting | Description |
|---------|-------------|
| `exploded_view = true` | Separates layers for visualization |
| `exploded_view = false` | Shows assembled stack |
| `show_cross_section = true` | Cuts view to show internals |

### 8.3 Exporting for Print

Set only one layer `= true` at a time, render (F6), then export STL.

---

## 9. Assembly Guide

### 9.1 Assembly Order

```
1. Insert LiPo battery into Battery Layer
   └── Connect JST cable, route through center hole
   
2. Stack PCB Layer onto Battery Layer
   └── Snap-fit clicks into place
   └── PCB sits on standoffs, secure with M2 screws if desired
   
3. Connect GPS module and antenna cables to PCB
   └── Route cables neatly
   
4. Place GPS module and antenna in GPS Layer
   └── Module on left, Antenna on right (side-by-side)
   
5. Stack GPS Layer onto PCB Layer
   └── Snap-fit engagement
   
6. Attach Top Cover
   └── Antenna window aligns over antenna
   └── Snap-fit perimeter
   
7. Mount Buckle Layer (base) to rest of assembly
   └── 4× M3 screws from bottom
   
8. Mount to vehicle using GoPro flat adhesive mount
   └── Slide buckle into mount until it clicks
```

### 9.2 Disassembly

- Top Cover: Pry gently at corners to release snap-fit
- Layers: Squeeze snap clips while pulling layers apart
- Buckle: Remove 4× M3 screws from bottom

---

## 10. Technical Notes

### 10.1 GPS Signal Considerations

- **Antenna Window:** 1mm wall thickness ensures RF transparency
- **Material:** Use white/natural PLA or PETG for top cover
- **⚠️ Avoid:** Carbon fiber, metallic, or heavily pigmented filaments
- **Orientation:** Antenna ceramic patch faces UP (toward sky)

### 10.2 Thermal Management

- Battery compartment includes ventilation slots
- PCB layer has 15mm height for component clearance and airflow
- Recommend PETG for better heat resistance than PLA

### 10.3 Vibration Resistance

- Snap-fit connections dampen vibration transmission
- Optional foam pad in battery bay isolates LiPo from impacts
- GoPro buckle provides additional isolation from mount

---

## 11. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-09 | Initial V1 design (dual-fin GoPro) |
| 2.0 | 2026-02-09 | V2: Quick release buckle, side-by-side GPS, multi-layer stack |

---

## 12. Appendix: Dimensional Summary

```
                         78mm
    ┌───────────────────────────────────────────────────┐
    │                   TOP COVER                        │
    │    ┌─────────────────────────────────────────┐    │
    │    │  GPS Module    │ gap │   GPS Antenna    │    │
    │    │   36×26mm      │ 3mm │    26×26mm       │    │  68mm
    │    │                │     │   ╔═══════════╗  │    │
    │    │                │     │   ║  WINDOW   ║  │    │
    │    │                │     │   ║  28×28mm  ║  │    │
    │    └────────────────┴─────┴───╚═══════════╝──┘    │
    │  ○                                           ○    │ ← M3 screw
    └───────────────────────────────────────────────────┘
                        TOP VIEW

    Side Elevation (Cross-Section at Center):
    
         Cover  ░░░░░▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░    3mm
                ▓ = Antenna window (1mm thin)
         ─────────────────────────────────────────────
         GPS    │  GPS MOD  │     │   ANTENNA   │        11mm
         ─────────────────────────────────────────────
         PCB    │ USB │           │ μSD │   │ USBOUT │   15mm
                │◄───►│           │◄───►│   │◄──────►│
         ─────────────────────────────────────────────
         BATT   │        BATTERY BAY        │            13mm
         ─────────────────────────────────────────────
         BUCKLE │          ▓▓▓▓▓▓▓▓         │            10mm
                           GOPRO BUCKLE                  ────
                                                        52mm total
```

---

*End of Specification*
