# RS-Core Enclosure v1 — Mechanical Specification

**Document:** `enclosure_v1_spec.md`  
**Version:** 1.0  
**Date:** 2026-02-09  
**Author:** Racesense Mechanical Engineering  

---

## 1. Overview

This document specifies a 3D-printable enclosure for the **RS-Core** motorsport datalogger. The design uses a two-shell clamshell construction with an integrated GoPro-style mounting system.

### Design Philosophy
- **Sandwich Stack Architecture:** Battery (bottom) → PCB (middle) → GPS (top)
- **Signal-First:** Thin-wall GPS dome ensures unobstructed sky view
- **Motorsport-Ready:** Vibration-resistant, secure GoPro mount integration
- **Print-Friendly:** No supports required, standard FDM tolerances

---

## 2. Component Dimensions

| Component | Dimensions (mm) | Notes |
|-----------|-----------------|-------|
| RS-Core PCB | 69.2 × 30.6 × 1.6 | Main board, ~12mm component height |
| LiPo Battery | 40 × 25 × 10 | Positioned under PCB |
| GPS Module | 25 × 25 × 8 | Neo-M8N ceramic patch antenna |
| USB-C Port | 9 × 3.5 | Located on PCB short edge |
| MicroSD Slot | 12 × 2.5 | Located on PCB short edge |
| NeoPixel LEDs | 8 × 5 | Status indicators on PCB |

---

## 3. Enclosure Specifications

### 3.1 External Dimensions
| Parameter | Value |
|-----------|-------|
| Length | 85 mm |
| Width | 42 mm |
| Height (total) | 38 mm |
| Wall Thickness | 2.0 mm |
| Corner Radius | 3.0 mm |

### 3.2 Internal Stack Heights
```
┌─────────────────────────────┐ ← Top Shell (GPS Dome)
│      GPS Module (8mm)       │
├─────────────────────────────┤
│      PCB + Components       │
│         (14mm)              │
├─────────────────────────────┤
│      Battery (10mm)         │
├─────────────────────────────┤
│   GoPro Mount (6mm fins)    │
└─────────────────────────────┘ ← Bottom Shell
```

### 3.3 Shell Split
- **Split Plane:** 20mm from bottom (at PCB mid-height)
- **Bottom Shell:** Battery bay + lower PCB support + GoPro mount
- **Top Shell:** Upper PCB cavity + GPS dome

---

## 4. Feature Specifications

### 4.1 GoPro Mount (Bottom Shell)
- **Type:** Dual-fin ("2-prong") GoPro-compatible
- **Fin Dimensions:** 15mm wide × 6mm deep × 3mm thick each
- **Fin Spacing:** 3mm gap (standard GoPro)
- **Hole Diameter:** 5.0mm (for GoPro thumb screw)
- **Position:** Centered on bottom face

### 4.2 Port Cutouts (Side Wall)
Located on the **short edge** of the enclosure:
- **USB-C Cutout:** 10mm × 4mm, centered at 10mm from bottom
- **MicroSD Cutout:** 14mm × 3mm, positioned 8mm from USB-C

### 4.3 LED Light Window
- **Position:** Long edge, near USB-C end
- **Dimensions:** 10mm × 6mm
- **Wall Thickness:** 1.0mm (translucent when printed in light-colored PETG/PLA)

### 4.4 GPS Dome (Top Shell)
- **Type:** Raised dome area with thin walls
- **Dome Dimensions:** 28mm × 28mm internal
- **Wall Thickness:** 1.0mm (critical for RF transparency)
- **Material Note:** Print in ABS, PETG, or PLA — avoid carbon-filled filaments

### 4.5 Screw Bosses
- **Quantity:** 4× corner bosses
- **Screw Type:** M2.5 × 12mm (or M3 × 12mm)
- **Boss OD:** 6mm
- **Hole ID:** 2.2mm (self-tap) or 2.5mm (heat-set insert)
- **Position:** 4mm inset from each corner

---

## 5. Assembly

### 5.1 Bill of Materials
| Item | Qty | Notes |
|------|-----|-------|
| Bottom Shell | 1 | 3D printed |
| Top Shell | 1 | 3D printed |
| M2.5 × 12mm screws | 4 | Pan head or socket cap |
| M2.5 heat-set inserts | 4 | Optional, for repeated assembly |

### 5.2 Assembly Order
1. Place battery in bottom shell bay
2. Seat PCB on standoffs (component side up)
3. Place GPS module in top shell dome (antenna up)
4. Align shells and insert 4× screws through top into bottom bosses
5. Attach GoPro mount to helmet/chassis

---

## 6. Print Settings

| Parameter | Recommended |
|-----------|-------------|
| Material | PETG (preferred) or PLA |
| Layer Height | 0.2mm |
| Infill | 20-30% |
| Walls | 3 perimeters |
| Supports | None required |
| Orientation | Shells printed open-side-up |

**⚠️ GPS Dome Note:** For best GPS reception, use natural/translucent filament for the top shell or print the dome area with 1mm wall and 0% infill.

---

## 7. OpenSCAD Model

Copy the entire script below into [OpenSCAD](https://openscad.org) or an online viewer like [OpenSCAD Playground](https://ochafik.com/openscad2/).

### 7.1 Complete OpenSCAD Script

```openscad
// ============================================================
// RS-CORE ENCLOSURE V6.1 — "The Ultimate Parametric Housing"
// Racesense Motorsport Datalogger Housing
// 100% CONFIGURABLE PORT ALIGNMENT | HIGH-FIDELITY GOPRO BUCKLE
// ============================================================
// Version: 6.1 (2026-02-09)
// Architecture: 5-Layer Sandwich Stack
// 
// USAGE: Open in OpenSCAD, use Customizer (View → Customizer)
//        to adjust ANY port position, then export each layer as STL.
// ============================================================

// ============================================================
/* [1. Display Options] */
// ============================================================
show_buckle_base = true;        // Layer 1: GoPro mount base
show_battery_tub = true;        // Layer 2: Battery compartment
show_pcb_deck = true;           // Layer 3: PCB + all ports
show_gps_deck = true;           // Layer 4: GPS antenna bay
show_flat_top = true;           // Layer 5: Top cover
exploded_view = true;           // Explode layers for visibility
explode_distance = 10;          // Gap between layers (mm)
show_cross_section = false;     // Cut view for debugging
show_port_labels = false;       // Debug: show port numbers

// ============================================================
/* [2. Global Tolerances] */
// ============================================================
wall = 2.0;                     // Wall thickness (mm)
corner_r = 3.0;                 // Corner radius (mm)
assembly_tol = 0.4;             // Gap between PCB and walls
port_tol = 0.5;                 // Extra clearance around ports
battery_tol = 1.0;              // Gap around battery cell
snap_tol = 0.25;                // Snap-fit clearance
layer_tol = 0.15;               // Between stacked layers

// ============================================================
/* [3. PCB Dimensions] */
// ============================================================
pcb_length = 69.22;             // PCB X dimension (mm)
pcb_width = 30.61;              // PCB Y dimension (mm)
pcb_thick = 1.6;                // PCB thickness (mm)

// ============================================================
/* [4. Layer Heights] */
// ============================================================
buckle_base_h = 10;             // Layer 1: GoPro buckle base
battery_tub_h = 14;             // Layer 2: Battery compartment
pcb_deck_h = 11;                // Layer 3: PCB + ports
gps_deck_h = 12;                // Layer 4: GPS antenna bay
flat_top_h = 3;                 // Layer 5: Top cover

// ============================================================
/* [5. Battery Bay] */
// ============================================================
bat_length = 44.0;              // LiPo length (mm)
bat_width = 29.0;               // LiPo width (mm)
bat_height = 12.0;              // LiPo height (mm)

// ============================================================
/* [6. GPS Antenna] */
// ============================================================
gps_window_size = 28;           // GPS window dimension (mm)

// ============================================================
/* [7. GoPro Buckle (Male Quick-Release)] */
// ============================================================
// Reference: Industry standard GoPro mounting interface
// Orientation: Buckle faces DOWN from base for mounting
buckle_length = 42.0;           // Full extension length (mm)
buckle_main_rail_w = 23.0;      // Main rail body width (mm)
buckle_total_w = 31.0;          // Total width at spring clips (mm)
buckle_rail_h = 6.0;            // Rail height from base (mm)
buckle_base_h_gp = 2.0;         // Base plate thickness (mm)
buckle_slot_w = 3.0;            // Each side slot width (mm)
buckle_slot_depth = 2.5;        // Slot depth for female rails (mm)
buckle_tab_w = 14.0;            // Locking tab width (mm)
buckle_tab_h = 3.0;             // Locking tab height above rail (mm)
buckle_tab_depth = 6.0;         // Tab protrusion (mm)
buckle_tab_chamfer = 35;        // Click-in chamfer angle (degrees)
buckle_spring_w = 4.0;          // Spring clip width (mm)
buckle_spring_l = 15.0;         // Spring clip length (mm)
buckle_spring_thick = 1.2;      // Spring clip thickness (mm)
buckle_finger_w = 8.0;          // Finger release tab width (mm)
buckle_finger_l = 6.0;          // Finger release tab length (mm)

// ============================================================
/* [8. Snap Fit] */
// ============================================================
snap_width = 10;                // Snap clip width (mm)
snap_depth = 1.5;               // Snap clip depth (mm)
snap_height = 2.5;              // Snap clip height (mm)

// ============================================================
// PORT CONFIGURATION — ALL 9 PORTS FULLY PARAMETRIC
// ============================================================

/* [Port 1: Main USB-C (Programming)] */
port1_wall = 0;                 // Wall: 0=LEFT
port1_offset = 15.71;           // Y position (mm)
port1_z = 0.39;                 // Z offset above PCB
port1_width = 11.0;             // width (mm)
port1_height = 5.0;             // height (mm)

/* [Port 2: I2C Connector] */
port2_wall = 3;                 // Wall: 3=BACK
port2_offset = 40.49;           // X position (mm)
port2_z = 0.42;                 // Z offset above PCB
port2_width = 8.0;              // width (mm)
port2_height = 6.0;             // height (mm)

/* [Port 3: LED_OUT USB-C] */
port3_wall = 3;                 // Wall: 3=BACK
port3_offset = 54.00;           // X position (mm)
port3_z = 0.84;                 // Z offset above PCB
port3_width = 11.0;             // width (mm)
port3_height = 6.0;             // height (mm)

/* [Port 4: UART Header] */
port4_wall = 1;                 // Wall: 3=BACK
port4_offset = 28.0;           // X position (mm)
port4_z = 0.5;                 // Z offset above PCB
port4_width = 12.0;             // width (mm)
port4_height = 6.0;             // height (mm)

/* [Port 5: USBOUT JST] */
port5_wall = 1;                 // Wall: 1=RIGHT
port5_offset = 19.51;           // Y position (mm)
port5_z = 0.57;                 // Z offset above PCB
port5_width = 8.0;              // width (mm)
port5_height = 6.0;             // height (mm)

/* [Port 6: Micro-SD Slot] */
port6_wall = 2;                 // Wall: 2=FRONT
port6_offset = 57.09;           // X position (mm)
port6_z = 0.09;                 // Z offset above PCB
port6_width = 20.0;             // width (mm)
port6_height = 4.0;             // height (mm)

/* [Port 7: AUX Connector] */
port7_wall = 2;                 // Wall: 2=FRONT
port7_offset = 14.32;           // X position (mm)
port7_z = 0.52;                 // Z offset above PCB
port7_width = 12.0;              // width (mm)
port7_height = 6.0;             // height (mm)

/* [Port 8: Battery Connector] */
port8_wall = 2;                 // Wall: 2=FRONT
port8_offset = 7.40;            // X position (mm)
port8_z = 0.31;                 // Z offset above PCB
port8_width = 6.0;              // width (mm)
port8_height = 6.0;             // height (mm)

/* [Port 9: Power Switch] */
port9_wall = 2;                 // Wall: 2=FRONT
port9_offset = 4.76;            // X position (mm)
port9_z = 0.67;                 // Z offset above PCB
port9_width = 6.0;              // width (mm)
port9_height = 6.0;             // height (mm)

// ============================================================
// DERIVED DIMENSIONS (calculated from config)
// ============================================================

enc_length = pcb_length + wall*2 + assembly_tol*2;
enc_width = pcb_width + wall*2 + assembly_tol*2;
pcb_offset_x = wall + assembly_tol;
pcb_offset_y = wall + assembly_tol;
floor_t = 2;
support_ledge_h = 2;
pcb_surface_z = floor_t + support_ledge_h;

// ============================================================
// UTILITY MODULES
// ============================================================

module rounded_box(l, w, h, r) {
    hull() {
        for (x = [r, l-r]) {
            for (y = [r, w-r]) {
                translate([x, y, 0])
                    cylinder(h=h, r=r, $fn=32);
            }
        }
    }
}

module snap_clip_male() {
    hull() {
        cube([snap_width, snap_depth * 0.5, snap_height]);
        translate([0, snap_depth, snap_height * 0.5])
            cube([snap_width, 0.1, snap_height * 0.5]);
    }
}

module snap_clip_female() {
    translate([-snap_tol, -snap_tol*2, -snap_tol])
        cube([snap_width + snap_tol*2, snap_depth + snap_tol*4, snap_height + snap_tol*2]);
}

module port_cutout(wall_id, offset, z_offset, cut_w, cut_h) {
    w = cut_w + 2*port_tol;
    h = cut_h;
    z_pos = pcb_surface_z + z_offset;
    
    if (wall_id == 0) {
        translate([-0.1, pcb_offset_y + offset - w/2, z_pos])
            cube([wall + 0.2, w, h]);
    } else if (wall_id == 1) {
        translate([enc_length - wall - 0.1, pcb_offset_y + offset - w/2, z_pos])
            cube([wall + 0.2, w, h]);
    } else if (wall_id == 2) {
        translate([pcb_offset_x + offset - w/2, -0.1, z_pos])
            cube([w, wall + 0.2, h]);
    } else if (wall_id == 3) {
        translate([pcb_offset_x + offset - w/2, enc_width - wall - 0.1, z_pos])
            cube([w, wall + 0.2, h]);
    }
}

module port_label(wall_id, offset, z_offset, label) {
    if (show_port_labels) {
        z_pos = pcb_surface_z + z_offset + 3;
        if (wall_id == 0) {
            translate([-3, pcb_offset_y + offset, z_pos])
                rotate([90, 0, 90])
                    linear_extrude(0.5)
                        text(label, size=3, halign="center");
        } else if (wall_id == 1) {
            translate([enc_length + 3, pcb_offset_y + offset, z_pos])
                rotate([90, 0, -90])
                    linear_extrude(0.5)
                        text(label, size=3, halign="center");
        } else if (wall_id == 2) {
            translate([pcb_offset_x + offset, -3, z_pos])
                rotate([90, 0, 0])
                    linear_extrude(0.5)
                        text(label, size=3, halign="center");
        } else if (wall_id == 3) {
            translate([pcb_offset_x + offset, enc_width + 3, z_pos])
                rotate([90, 0, 180])
                    linear_extrude(0.5)
                        text(label, size=3, halign="center");
        }
    }
}

module gopro_male_buckle_v6() {
    difference() {
        union() {
            translate([-buckle_length/2, -buckle_main_rail_w/2, 0])
                cube([buckle_length, buckle_main_rail_w, buckle_base_h_gp]);
            translate([-buckle_length/2, -buckle_main_rail_w/2, 0])
                cube([buckle_length, buckle_main_rail_w, buckle_rail_h]);
            for (side = [-1, 1]) {
                translate([-buckle_spring_l/2, side * (buckle_main_rail_w/2 + buckle_spring_thick/2), buckle_rail_h - buckle_spring_thick])
                    cube([buckle_spring_l, buckle_spring_w, buckle_spring_thick], center=true);
                translate([-buckle_spring_l/2, side * buckle_main_rail_w/2, buckle_rail_h - buckle_spring_thick])
                    cube([2, side * (buckle_spring_w - buckle_spring_thick), buckle_spring_thick]);
            }
            translate([buckle_length/2 - buckle_tab_depth, -buckle_tab_w/2, buckle_rail_h]) {
                difference() {
                    cube([buckle_tab_depth, buckle_tab_w, buckle_tab_h]);
                    translate([-0.5, -0.5, buckle_tab_h - 1])
                        rotate([0, -buckle_tab_chamfer, 0])
                            cube([buckle_tab_depth + 2, buckle_tab_w + 1, buckle_tab_h]);
                }
            }
            translate([buckle_length/2, 0, buckle_rail_h]) {
                translate([0, -buckle_finger_w/2, 0])
                    cube([buckle_finger_l, buckle_finger_w, 1.5]);
            }
        }
        for (side = [-1, 1]) {
            translate([-buckle_length/2 - 0.5, side * (buckle_main_rail_w/2 - buckle_slot_depth), buckle_base_h_gp])
                cube([buckle_length + 1, buckle_slot_w, buckle_rail_h]);
        }
        translate([-buckle_length/4, -buckle_main_rail_w/4, -0.1])
            cube([buckle_length/2, buckle_main_rail_w/2, buckle_base_h_gp + 0.2]);
    }
}

module buckle_base() {
    base_floor = 2;
    difference() {
        union() {
            rounded_box(enc_length, enc_width, buckle_base_h, corner_r);
            for (x = [wall + 8, enc_length - wall - 8]) {
                for (y = [wall + 6, enc_width - wall - 6]) {
                    translate([x, y, buckle_base_h])
                        cylinder(h = 3, d = 6, $fn = 24);
                }
            }
        }
        translate([wall, wall, base_floor])
            rounded_box(enc_length - 2*wall, enc_width - 2*wall, buckle_base_h, max(corner_r - wall, 0.5));
        for (x = [wall + 8, enc_length - wall - 8]) {
            for (y = [wall + 6, enc_width - wall - 6]) {
                translate([x, y, -1])
                    cylinder(h = buckle_base_h + 5, d = 3.2, $fn = 24);
                translate([x, y, -0.1])
                    cylinder(h = 2, d1 = 6, d2 = 3.2, $fn = 24);
            }
        }
    }
    translate([enc_length/2, enc_width/2, 0])
        rotate([180, 0, 0])
            gopro_male_buckle_v6();
}

module battery_tub() {
    difference() {
        union() {
            rounded_box(enc_length, enc_width, battery_tub_h, corner_r);
            for (x = [enc_length * 0.25, enc_length * 0.75]) {
                for (side = [0, 1]) {
                    y_pos = side == 0 ? wall : enc_width - wall - snap_depth;
                    translate([x - snap_width/2, y_pos, battery_tub_h])
                        snap_clip_male();
                }
            }
        }
        translate([wall, wall, floor_t])
            rounded_box(enc_length - 2*wall, enc_width - 2*wall, battery_tub_h, max(corner_r - wall, 0.5));
        for (x = [wall + 8, enc_length - wall - 8]) {
            for (y = [wall + 6, enc_width - wall - 6]) {
                translate([x, y, -1])
                    cylinder(h = 4, d = 6 + layer_tol*2, $fn = 24);
            }
        }
        translate([enc_length/2, enc_width/2, battery_tub_h - 2])
            cylinder(h = 4, d = 8, $fn = 24);
    }
    bat_x = (enc_length - bat_length - battery_tol) / 2;
    bat_y = (enc_width - bat_width - battery_tol) / 2;
    for (dx = [0, bat_length + battery_tol - 6]) {
        for (dy = [0, bat_width + battery_tol - 6]) {
            translate([bat_x + dx, bat_y + dy, floor_t])
                cube([6, 6, 3]);
        }
    }
}

module pcb_deck() {
    difference() {
        union() {
            rounded_box(enc_length, enc_width, pcb_deck_h, corner_r);
            for (x = [enc_length * 0.25, enc_length * 0.75]) {
                for (side = [0, 1]) {
                    y_pos = side == 0 ? wall : enc_width - wall - snap_depth;
                    translate([x - snap_width/2, y_pos, pcb_deck_h])
                        snap_clip_male();
                }
            }
        }
        translate([pcb_offset_x - assembly_tol, pcb_offset_y - assembly_tol, floor_t])
            rounded_box(pcb_length + assembly_tol*2, pcb_width + assembly_tol*2, pcb_deck_h, 1.0);
        for (x = [enc_length * 0.25, enc_length * 0.75]) {
            for (side = [0, 1]) {
                y_pos = side == 0 ? wall - snap_tol : enc_width - wall - snap_depth + snap_tol;
                translate([x - snap_width/2, y_pos, -0.1])
                    snap_clip_female();
            }
        }
        port_cutout(port1_wall, port1_offset, port1_z, port1_width, port1_height);
        port_cutout(port2_wall, port2_offset, port2_z, port2_width, port2_height);
        port_cutout(port3_wall, port3_offset, port3_z, port3_width, port3_height);
        port_cutout(port4_wall, port4_offset, port4_z, port4_width, port4_height);
        port_cutout(port5_wall, port5_offset, port5_z, port5_width, port5_height);
        port_cutout(port6_wall, port6_offset, port6_z, port6_width, port6_height);
        port_cutout(port7_wall, port7_offset, port7_z, port7_width, port7_height);
        port_cutout(port8_wall, port8_offset, port8_z, port8_width, port8_height);
        port_cutout(port9_wall, port9_offset, port9_z, port9_width, port9_height);
        translate([enc_length/3 - 8, -0.1, pcb_surface_z + 2])
            cube([16, wall - 0.5, 5]);
    }
    difference() {
        translate([pcb_offset_x - 1, pcb_offset_y - 1, floor_t])
            rounded_box(pcb_length + 2, pcb_width + 2, support_ledge_h, 1.5);
        translate([pcb_offset_x + 1, pcb_offset_y + 1, floor_t - 0.1])
            rounded_box(pcb_length - 2, pcb_width - 2, support_ledge_h + 0.2, 1.5);
    }
    if (show_port_labels) {
        color("Red") {
            port_label(port1_wall, port1_offset, port1_z, "1:USB");
            port_label(port2_wall, port2_offset, port2_z, "2:I2C");
            port_label(port3_wall, port3_offset, port3_z, "3:LED");
            port_label(port4_wall, port4_offset, port4_z, "4:UART");
            port_label(port5_wall, port5_offset, port5_z, "5:OUT");
            port_label(port6_wall, port6_offset, port6_z, "6:SD");
            port_label(port7_wall, port7_offset, port7_z, "7:AUX");
            port_label(port8_wall, port8_offset, port8_z, "8:BATT");
            port_label(port9_wall, port9_offset, port9_z, "9:PWR");
        }
    }
}

module gps_deck() {
    difference() {
        union() {
            rounded_box(enc_length, enc_width, gps_deck_h, corner_r);
            translate([wall - layer_tol, wall - layer_tol, gps_deck_h])
                difference() {
                    rounded_box(enc_length - 2*wall + layer_tol*2, enc_width - 2*wall + layer_tol*2, 2, max(corner_r - wall, 0.5));
                    translate([1.5, 1.5, -0.1])
                        rounded_box(enc_length - 2*wall - 2, enc_width - 2*wall - 2, 2.2, max(corner_r - wall - 1, 0.5));
                }
        }
        translate([wall, wall, floor_t])
            rounded_box(enc_length - 2*wall, enc_width - 2*wall, gps_deck_h, max(corner_r - wall, 0.5));
        for (x = [enc_length * 0.25, enc_length * 0.75]) {
            for (side = [0, 1]) {
                y_pos = side == 0 ? wall - snap_tol : enc_width - wall - snap_depth + snap_tol;
                translate([x - snap_width/2, y_pos, -0.1])
                    snap_clip_female();
            }
        }
    }
}

module flat_top() {
    window_x = (enc_length - gps_window_size) / 2;
    window_y = (enc_width - gps_window_size) / 2;
    difference() {
        union() {
            rounded_box(enc_length, enc_width, flat_top_h, corner_r);
            translate([wall + layer_tol, wall + layer_tol, -1.5])
                rounded_box(enc_length - 2*wall - layer_tol*2, enc_width - 2*wall - layer_tol*2, 1.5, max(corner_r - wall - layer_tol, 0.5));
        }
        translate([window_x, window_y, 1])
            cube([gps_window_size, gps_window_size, flat_top_h]);
        for (x = [0, enc_length]) {
            for (y = [0, enc_width]) {
                translate([x, y, flat_top_h])
                    rotate([0, 0, 45])
                        translate([-2, -2, -1.5])
                            cube([4, 4, 2]);
            }
        }
    }
    translate([window_x, window_y, 0])
        cube([gps_window_size, gps_window_size, 0.2]);
    translate([enc_length/3.5, enc_width - 8, flat_top_h - 0.2])
        linear_extrude(0.5)
            text("RS-CORE", size = 3, font = "Liberation Sans:style=Bold", halign = "right", valign = "center");
}

module assembly() {
    z = 0; exp = exploded_view ? explode_distance : 0;
    if (show_buckle_base) color("DimGray", 0.95) translate([0, 0, z]) buckle_base();
    z1 = buckle_base_h + exp;
    if (show_battery_tub) color("SlateGray", 0.9) translate([0, 0, z1]) battery_tub();
    z2 = z1 + battery_tub_h + exp;
    if (show_pcb_deck) color("DarkSlateGray", 0.9) translate([0, 0, z2]) pcb_deck();
    z3 = z2 + pcb_deck_h + exp;
    if (show_gps_deck) color("CadetBlue", 0.9) translate([0, 0, z3]) gps_deck();
    z4 = z3 + gps_deck_h + exp;
    if (show_flat_top) color("White", 0.95) translate([0, 0, z4]) flat_top();
}

if (show_cross_section) {
    difference() {
        assembly();
        translate([enc_length/2, -10, -20])
            cube([enc_length, enc_width + 20, 150]);
    }
} else {
    assembly();
}
```

---

## 8. Rendering the Model

### 8.1 Quick Start (Online)

1. Go to **[OpenSCAD Playground](https://ochafik.com/openscad2/)**
2. Delete any existing code
3. Paste the entire script from Section 7.1
4. Click **Render** (or press F6)
5. Use mouse to rotate/zoom the 3D view

### 8.2 View Options

Modify these variables at the top of the script:

| Variable | Effect |
|----------|--------|
| `show_top = false;` | Hide top shell |
| `show_bottom = false;` | Hide bottom shell |
| `exploded_view = false;` | Stack shells together |
| `show_cross_section = true;` | Cut view to see interior |

### 8.3 Exporting for Printing

1. Set `show_top = false; show_bottom = true;`
2. Render (F6) → Export as STL → `rs-core_bottom_shell.stl`
3. Set `show_top = true; show_bottom = false;`
4. Render (F6) → Export as STL → `rs-core_top_shell.stl`

---

## 9. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-09 | Initial design |

---

## 10. Appendix: Dimensional Drawing

```
                         85mm
    ┌───────────────────────────────────────┐
    │  ○                               ○    │  ← M2.5 screw boss
    │    ┌─────────────────────────┐        │
    │    │                         │        │
    │    │      GPS Dome Area      │   42mm │
    │    │       (28×28mm)         │        │
    │    │                         │        │
    │    └─────────────────────────┘        │
    │  ○                               ○    │
    └───────────────────────────────────────┘
                        TOP VIEW

    ┌───────────────────────────────────────┐
    │░░░░░░░░░░ GPS Dome (1mm) ░░░░░░░░░░░░│ ← Thin wall
    ├───────────────────────────────────────┤
    │           GPS Module                  │  8mm
    ├───────────────────────────────────────┤
    │                                       │
    │     PCB + Components                  │ 14mm
    │                                       │
    ├──┬────────────────────────────────────┤ ← Split line
    │  │ LED  │    Battery                  │ 10mm
    └──┴──────┴─────────────────────────────┘
       ▼▼▼  GoPro Fins  ▼▼▼                   6mm
                    SIDE VIEW
```

---

*End of Specification*
