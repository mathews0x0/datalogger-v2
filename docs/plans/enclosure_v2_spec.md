# RS-Core Enclosure V4.1 — Pi-Style Fit Precision Specification

**Document:** `enclosure_v2_spec.md`  
**Version:** 4.1  
**Date:** 2026-02-09  
**Author:** Racesense Mechanical Engineering  

---

## 1. Overview

This document specifies the **Version 4.1** 3D-printable enclosure for the **RS-Core V2** motorsport datalogger. 

### 1.1 Key Changes from V4.0

| Feature | V4.0 | V4.1 |
|---------|------|------|
| **PCB Mounting** | Individual Standoffs (4 corners) | **Pi-Style Snug Fit** — Board fits end-to-end against internal walls. |
| **Support Method** | Standoffs | **Continuous Internal Ledge** around the perimeter. |
| **Enclosure Footprint** | 78 × 40 mm | **Optimized for Snug Fit** (73.22 × 34.61 mm internal cavity). |

---

## 2. OpenSCAD Model V4.1

### 2.1 Complete OpenSCAD Script

```openscad
// ============================================================
// RS-CORE ENCLOSURE V4.1
// Racesense Motorsport Datalogger Housing
// MATHEMATICAL PRECISION - Truth Data from DXF
// PI-STYLE SNUG FIT (No Standoffs)
// ============================================================
// Version: 4.1 (2026-02-09)
// Architecture: Sandwich Layer Stack
// ============================================================

/* [Display Options] */
show_buckle_base = true;
show_battery_tub = true;
show_pcb_deck = true;
show_gps_deck = true;
show_flat_top = true;
exploded_view = true;
explode_distance = 10;
show_cross_section = false;

/* [Enclosure Dimensions] */
wall = 2.0;
corner_r = 3.0;

/* [PCB TRUTH DATA] */
pcb_length = 69.22;
pcb_width = 30.61;
pcb_thick = 1.6;

// Pi-Style Snug Fit: Enclosure grows exactly around the PCB
enc_length = pcb_length + wall*2 + 0.4; // 0.2mm assembly gap each side
enc_width = pcb_width + wall*2 + 0.4;   

// PCB position (centered in the wall-to-wall cavity)
pcb_offset_x = wall + 0.2;
pcb_offset_y = wall + 0.2;

// Sandwich Layer Heights
buckle_base_h = 10;
battery_tub_h = 14;
pcb_deck_h = 15;
gps_deck_h = 12;
flat_top_h = 3;

/* [Battery Bay] */
bat_length = 44.0;
bat_width = 29.0;
bat_height = 12.0;

/* [GPS Antenna] */
gps_ant_size = 26;
gps_ant_height = 9;

/* [GoPro Buckle] */
buckle_length = 42;
buckle_width = 20;
buckle_body_h = 8;
buckle_rail_w = 3;
buckle_tab_w = 12;
buckle_tab_h = 4;

/* [Clearance] */
port_clearance = 0.5;

/* ============================================================
   PORT TRUTH DATA (PCB-relative)
   ============================================================ */
jst_cutout_h = 6.0;
usbc_cutout_h = 5.0;
sd_cutout_h = 3.5;

usbc_cut_w = 9.0 + 2*port_clearance;
jst4_cut_w = 5.0 + 2*port_clearance;
jst2_cut_w = 3.0 + 2*port_clearance;
sd_cut_w = 14.0 + 2*port_clearance;

// LEFT (X=0)
usb_main_y = 15.71;
// RIGHT (X=69.22)
micro_sd_y = 8.94;
usbout_y = 21.51;
// FRONT (Y=0)
pwr_sw_x = 4.76;
batt_x = 7.40;
aux_x = 13.09;
// BACK (Y=30.61)
i2c_x = 40.49;
led_out_x = 61.00;
uart_x = 59.25;

/* [Snap Fit] */
snap_width = 10;
snap_depth = 1.5;
snap_height = 2.5;

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

// Snap-fit clip (male)
module snap_clip_male() {
    hull() {
        cube([snap_width, snap_depth * 0.5, snap_height]);
        translate([0, snap_depth, snap_height * 0.5])
            cube([snap_width, 0.1, snap_height * 0.5]);
    }
}

// Snap-fit receiver (female)
module snap_clip_female() {
    translate([-0.25, -0.4, -0.25])
        cube([snap_width + 0.5, snap_depth + 0.8, snap_height + 0.5]);
}

// ============================================================
// LAYER 1: BUCKLE BASE (GoPro Male Buckle Integrated)
// ============================================================

module gopro_male_buckle() {
    difference() {
        union() {
            translate([-buckle_length/2, -buckle_width/2, 0])
                cube([buckle_length, buckle_width, buckle_body_h]);
            for (dy = [-1, 1]) {
                translate([-buckle_length/2, dy * (buckle_width/2 + buckle_rail_w/2) - buckle_rail_w/2, 0])
                    cube([buckle_length, buckle_rail_w, buckle_body_h - 2]);
            }
        }
        translate([-buckle_length/2 - 1, -buckle_width/2 + buckle_rail_w, buckle_body_h - 3])
            cube([buckle_length + 2, buckle_width - buckle_rail_w * 2, 4]);
        translate([-buckle_tab_w/2, -buckle_width/2 - 1, buckle_body_h - buckle_tab_h])
            cube([buckle_tab_w, buckle_width/2 + 2, buckle_tab_h + 1]);
    }
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
            gopro_male_buckle();
}

// ============================================================
// LAYER 2: BATTERY TUB
// ============================================================

module battery_tub() {
    floor_t = 2;
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
                    cylinder(h = 4, d = 6.4, $fn = 24);
            }
        }
        translate([enc_length/2, enc_width/2, battery_tub_h - 2])
            cylinder(h = 4, d = 8, $fn = 24);
    }
    bat_x = (enc_length - bat_length) / 2;
    bat_y = (enc_width - bat_width) / 2;
    for (dx = [0, bat_length - 6]) {
        for (dy = [0, bat_width - 6]) {
            translate([bat_x + dx, bat_y + dy, floor_t])
                cube([6, 6, 3]);
        }
    }
}

// ============================================================
// LAYER 3: PCB DECK (Snug End-to-End Fit)
// ============================================================

module pcb_deck() {
    floor_t = 2;
    support_ledge_h = 2;
    pcb_surface_z = floor_t + support_ledge_h;
    
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
        
        // --- PI-STYLE SNUG FIT HOLLOW ---
        // Hollow out the entire PCB size + 0.4mm tolerance
        translate([pcb_offset_x - 0.2, pcb_offset_y - 0.2, floor_t])
            rounded_box(pcb_length + 0.4, pcb_width + 0.4, pcb_deck_h, 1.0);
        
        // Snap receivers (from battery tub)
        for (x = [enc_length * 0.25, enc_length * 0.75]) {
            for (side = [0, 1]) {
                y_pos = side == 0 ? wall - 0.5 : enc_width - wall - snap_depth + 0.5;
                translate([x - snap_width/2, y_pos, -0.1])
                    snap_clip_female();
            }
        }
        
        // --- PRECISION PORT CUTOUTS ---
        
        // LEFT WALL (X = 0)
        translate([-0.1, pcb_offset_y + usb_main_y - usbc_cut_w/2, pcb_surface_z])
            cube([wall + 0.2, usbc_cut_w, usbc_cutout_h]);
        
        // RIGHT WALL (X = enc_length)
        translate([enc_length - wall - 0.1, pcb_offset_y + micro_sd_y - sd_cut_w/2, pcb_surface_z])
            cube([wall + 0.2, sd_cut_w, sd_cutout_h]);
        translate([enc_length - wall - 0.1, pcb_offset_y + usbout_y - jst4_cut_w/2, pcb_surface_z])
            cube([wall + 0.2, jst4_cut_w, jst_cutout_h]);
        
        // FRONT/BOTTOM WALL (Y = 0)
        translate([pcb_offset_x + pwr_sw_x - jst2_cut_w/2, -0.1, pcb_surface_z])
            cube([jst2_cut_w, wall + 0.2, jst_cutout_h]);
        translate([pcb_offset_x + batt_x - jst2_cut_w/2, -0.1, pcb_surface_z])
            cube([jst2_cut_w, wall + 0.2, jst_cutout_h]);
        translate([pcb_offset_x + aux_x - jst4_cut_w/2, -0.1, pcb_surface_z])
            cube([jst4_cut_w, wall + 0.2, jst_cutout_h]);
        
        // BACK/TOP WALL (Y = enc_width)
        translate([pcb_offset_x + i2c_x - jst4_cut_w/2, enc_width - wall - 0.1, pcb_surface_z])
            cube([jst4_cut_w, wall + 0.2, jst_cutout_h]);
        translate([pcb_offset_x + led_out_x - usbc_cut_w/2, enc_width - wall - 0.1, pcb_surface_z])
            cube([usbc_cut_w, wall + 0.2, usbc_cutout_h]);
        translate([pcb_offset_x + uart_x - jst4_cut_w/2, enc_width - wall - 0.1, pcb_surface_z])
            cube([jst4_cut_w, wall + 0.2, jst_cutout_h]);
        
        // LED window
        translate([enc_length/3 - 8, -0.1, pcb_surface_z + 2])
            cube([16, wall - 0.5, 5]);
    }
    
    // --- SUPPORT LEDGE ---
    // Continuous inner ledge to support the PCB perimeter
    difference() {
        translate([pcb_offset_x - 1, pcb_offset_y - 1, floor_t])
            rounded_box(pcb_length + 2, pcb_width + 2, support_ledge_h, 1.5);
        translate([pcb_offset_x + 1, pcb_offset_y + 1, floor_t - 0.1])
            rounded_box(pcb_length - 2, pcb_width - 2, support_ledge_h + 0.2, 1.5);
    }
}

// ============================================================
// LAYER 4: GPS DECK
// ============================================================

module gps_deck() {
    floor_t = 2;
    difference() {
        union() {
            rounded_box(enc_length, enc_width, gps_deck_h, corner_r);
            translate([wall - 0.5, wall - 0.5, gps_deck_h])
                difference() {
                    rounded_box(enc_length - 2*wall + 1, enc_width - 2*wall + 1, 2, max(corner_r - wall, 0.5));
                    translate([1.5, 1.5, -0.1])
                        rounded_box(enc_length - 2*wall - 2, enc_width - 2*wall - 2, 2.2, max(corner_r - wall - 1, 0.5));
                }
        }
        translate([wall, wall, floor_t])
            rounded_box(enc_length - 2*wall, enc_width - 2*wall, gps_deck_h, max(corner_r - wall, 0.5));
        for (x = [enc_length * 0.25, enc_length * 0.75]) {
            for (side = [0, 1]) {
                y_pos = side == 0 ? wall - 0.5 : enc_width - wall - snap_depth + 0.5;
                translate([x - snap_width/2, y_pos, -0.1])
                    snap_clip_female();
            }
        }
    }
    ant_x = (enc_length - gps_ant_size) / 2;
    ant_y = (enc_width - gps_ant_size) / 2;
    translate([ant_x - 1, ant_y - 1, floor_t])
        difference() {
            cube([gps_ant_size + 2, gps_ant_size + 2, gps_ant_height + 1]);
            translate([1, 1, -0.1])
                cube([gps_ant_size, gps_ant_size, gps_ant_height + 1.2]);
        }
}

// ============================================================
// LAYER 5: FLAT TOP
// ============================================================

module flat_top() {
    window_size = 28;
    window_x = (enc_length - window_size) / 2;
    window_y = (enc_width - window_size) / 2;
    difference() {
        union() {
            rounded_box(enc_length, enc_width, flat_top_h, corner_r);
            translate([wall + 0.3, wall + 0.3, -1.5])
                rounded_box(enc_length - 2*wall - 0.6, enc_width - 2*wall - 0.6, 1.5, max(corner_r - wall - 0.3, 0.5));
        }
        translate([window_x, window_y, 1])
            cube([window_size, window_size, flat_top_h]);
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
        cube([window_size, window_size, 0.8]);
    translate([enc_length/2, enc_width - 8, flat_top_h - 0.3])
        linear_extrude(0.5)
            text("RACESENSE", size = 4, font = "Liberation Sans:style=Bold", halign = "center", valign = "center");
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

if (show_cross_section) { difference() { assembly(); translate([enc_length/2, -10, -20]) cube([enc_length, enc_width + 20, 150]); } } else { assembly(); }
```

---

## 3. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 4.1 | 2026-02-09 | **V4.1: PI-STYLE SNUG FIT** — Removed individual standoffs. PCB now fits wall-to-wall (69.22 × 30.61mm internal) and sits on a continuous internal perimeter ledge. Enclosure footprint tightened to match snug internal fit. |

---

*End of Specification V4.1*
