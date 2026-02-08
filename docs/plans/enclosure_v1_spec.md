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
// RS-CORE ENCLOSURE v1.0
// Racesense Motorsport Datalogger Housing
// ============================================================
// Usage: Render with F6, export STL for each shell separately
// Toggle 'show_top' and 'show_bottom' to export individually
// ============================================================

/* [Display Options] */
show_top = true;        // Show top shell
show_bottom = true;     // Show bottom shell  
exploded_view = true;   // Separate shells for visualization
explode_distance = 15;  // Distance between shells in exploded view
show_cross_section = false; // Cut view to see internals

/* [Enclosure Dimensions] */
// External dimensions
enc_length = 85;
enc_width = 42;
enc_height = 38;
wall = 2.0;
corner_r = 3.0;

// Shell split height from bottom
split_z = 20;

/* [Component Dimensions] */
// PCB
pcb_length = 69.2;
pcb_width = 30.6;
pcb_thick = 1.6;
pcb_comp_height = 12;  // Component height above PCB

// Battery
bat_length = 40;
bat_width = 25;
bat_height = 10;

// GPS Module
gps_size = 25;
gps_height = 8;

/* [Features] */
// Screw bosses
boss_od = 6;
boss_id = 2.2;  // For M2.5 self-tap
boss_inset = 4;

// GoPro mount
gopro_fin_width = 15;
gopro_fin_depth = 6;
gopro_fin_thick = 3;
gopro_gap = 3;
gopro_hole = 5;

// USB-C cutout
usbc_width = 10;
usbc_height = 4;
usbc_z = 10;  // Height from bottom

// MicroSD cutout
sd_width = 14;
sd_height = 3;
sd_offset = 12;  // Offset from USB-C

// LED window
led_width = 10;
led_height = 6;
led_wall = 1.0;  // Thin wall for light transmission

// GPS dome
gps_dome_size = 28;
gps_dome_wall = 1.0;  // Thin for RF transparency

// ============================================================
// MODULES
// ============================================================

// Rounded box primitive
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

// Screw boss
module screw_boss(height, od, id) {
    difference() {
        cylinder(h=height, d=od, $fn=24);
        translate([0, 0, -0.1])
            cylinder(h=height+0.2, d=id, $fn=24);
    }
}

// GoPro dual-fin mount
module gopro_mount() {
    fin_total = gopro_fin_width * 2 + gopro_gap;
    
    difference() {
        union() {
            // Left fin
            translate([-fin_total/2, -gopro_fin_depth/2, 0])
                cube([gopro_fin_width, gopro_fin_depth, gopro_fin_thick]);
            // Right fin  
            translate([gopro_gap/2, -gopro_fin_depth/2, 0])
                cube([gopro_fin_width, gopro_fin_depth, gopro_fin_thick]);
        }
        // Mounting hole through both fins
        translate([0, 0, gopro_fin_thick/2])
            rotate([0, 90, 0])
                cylinder(h=fin_total+2, d=gopro_hole, center=true, $fn=24);
    }
}

// Bottom shell
module bottom_shell() {
    difference() {
        union() {
            // Main shell body
            difference() {
                rounded_box(enc_length, enc_width, split_z, corner_r);
                // Hollow interior
                translate([wall, wall, wall])
                    rounded_box(enc_length - wall*2, enc_width - wall*2, 
                               split_z, corner_r - wall/2);
            }
            
            // Screw bosses (extend up for top shell to screw into)
            boss_positions = [
                [boss_inset + boss_od/2, boss_inset + boss_od/2],
                [enc_length - boss_inset - boss_od/2, boss_inset + boss_od/2],
                [boss_inset + boss_od/2, enc_width - boss_inset - boss_od/2],
                [enc_length - boss_inset - boss_od/2, enc_width - boss_inset - boss_od/2]
            ];
            
            for (pos = boss_positions) {
                translate([pos[0], pos[1], wall])
                    screw_boss(split_z - wall + 2, boss_od, boss_id);
            }
            
            // Battery retaining walls
            bat_x = (enc_length - bat_length) / 2;
            bat_y = (enc_width - bat_width) / 2;
            
            // Front and back battery stops
            translate([bat_x - 1.5, bat_y, wall])
                cube([1.5, bat_width, bat_height + 2]);
            translate([bat_x + bat_length, bat_y, wall])
                cube([1.5, bat_width, bat_height + 2]);
                
            // PCB ledge/supports
            pcb_x = (enc_length - pcb_length) / 2;
            pcb_y = (enc_width - pcb_width) / 2;
            pcb_z = wall + bat_height + 1;  // 1mm gap above battery
            
            // PCB support rails
            translate([pcb_x - 1, wall, pcb_z])
                cube([1, enc_width - wall*2, 2]);
            translate([pcb_x + pcb_length, wall, pcb_z])
                cube([1, enc_width - wall*2, 2]);
        }
        
        // USB-C cutout (on short edge, -X side)
        translate([-0.1, enc_width/2 - usbc_width/2, usbc_z])
            cube([wall + 0.2, usbc_width, usbc_height]);
        
        // MicroSD cutout (next to USB-C)
        translate([-0.1, enc_width/2 - usbc_width/2 - sd_offset - sd_width, usbc_z])
            cube([wall + 0.2, sd_width, sd_height]);
        
        // LED window recess (on long edge, near USB end)
        translate([10, -0.1, usbc_z])
            cube([led_width, wall - led_wall + 0.1, led_height]);
    }
    
    // GoPro mount on bottom
    translate([enc_length/2, enc_width/2, 0])
        rotate([180, 0, 0])
            translate([0, 0, 0])
                gopro_mount();
}

// Top shell  
module top_shell() {
    top_height = enc_height - split_z;
    
    difference() {
        union() {
            // Main shell body
            difference() {
                rounded_box(enc_length, enc_width, top_height, corner_r);
                // Hollow interior
                translate([wall, wall, -0.1])
                    rounded_box(enc_length - wall*2, enc_width - wall*2,
                               top_height - wall + 0.1, corner_r - wall/2);
            }
            
            // Lip to overlap bottom shell
            lip_height = 2;
            lip_inset = 0.3;  // Clearance
            translate([wall + lip_inset, wall + lip_inset, -lip_height])
                difference() {
                    rounded_box(enc_length - wall*2 - lip_inset*2,
                               enc_width - wall*2 - lip_inset*2,
                               lip_height, corner_r - wall);
                    translate([wall, wall, -0.1])
                        rounded_box(enc_length - wall*4 - lip_inset*2,
                                   enc_width - wall*4 - lip_inset*2,
                                   lip_height + 0.2, corner_r - wall*1.5);
                }
        }
        
        // Screw holes through top
        boss_positions = [
            [boss_inset + boss_od/2, boss_inset + boss_od/2],
            [enc_length - boss_inset - boss_od/2, boss_inset + boss_od/2],
            [boss_inset + boss_od/2, enc_width - boss_inset - boss_od/2],
            [enc_length - boss_inset - boss_od/2, enc_width - boss_inset - boss_od/2]
        ];
        
        for (pos = boss_positions) {
            translate([pos[0], pos[1], -0.1])
                cylinder(h=top_height + 0.2, d=2.8, $fn=24);  // M2.5 clearance
            // Countersink for screw head
            translate([pos[0], pos[1], top_height - 2])
                cylinder(h=2.1, d=5.5, $fn=24);
        }
        
        // GPS dome recess (thinner walls for RF)
        gps_x = enc_length/2;
        gps_y = enc_width/2;
        
        // Remove material to create thin dome
        translate([gps_x - gps_dome_size/2, gps_y - gps_dome_size/2, 
                  top_height - wall])
            cube([gps_dome_size, gps_dome_size, wall - gps_dome_wall + 0.1]);
    }
    
    // GPS module pocket (raised floor inside)
    gps_x = enc_length/2;
    gps_y = enc_width/2;
    gps_pocket_z = wall + 2;  // Floor height inside top shell
    
    // Corner posts to hold GPS module
    post_size = 2;
    for (dx = [-1, 1]) {
        for (dy = [-1, 1]) {
            translate([gps_x + dx*(gps_size/2 + post_size/2), 
                      gps_y + dy*(gps_size/2 + post_size/2), 0])
                cube([post_size, post_size, gps_pocket_z], center=true);
        }
    }
}

// ============================================================
// ASSEMBLY
// ============================================================

// Cross section cut
module cross_section() {
    translate([enc_length/2, -1, -10])
        cube([enc_length, enc_width + 2, enc_height + 30]);
}

// Render assembly
module assembly() {
    if (show_bottom) {
        color("DimGray", 0.9)
            bottom_shell();
    }
    
    if (show_top) {
        explode_z = exploded_view ? explode_distance : 0;
        
        color("SlateGray", 0.9)
            translate([0, 0, split_z + explode_z])
                top_shell();
    }
}

// Final render
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
// To export STL files for printing:
// 1. Set show_top=false, show_bottom=true → Render (F6) → Export STL
//    Save as: rs-core_bottom_shell.stl
//
// 2. Set show_top=true, show_bottom=false → Render (F6) → Export STL  
//    Save as: rs-core_top_shell.stl
//
// Print both shells with open side facing UP (no supports needed)
// ============================================================
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
