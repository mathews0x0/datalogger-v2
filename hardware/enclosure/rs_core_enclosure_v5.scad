// ============================================================
// RS-CORE ENCLOSURE V5.0
// Racesense Motorsport Datalogger Housing
// PRECISION 9-PORT LAYOUT | CORRECTED GOPRO BUCKLE
// ============================================================
// Version: 5.0 (2026-02-09)
// Architecture: 5-Layer Sandwich Stack
// 
// USAGE: Open in OpenSCAD, adjust parameters in Customizer,
//        then export each layer as STL for 3D printing.
// ============================================================

// ============================================================
// CONFIGURATION BLOCK — ALL USER-ADJUSTABLE PARAMETERS
// ============================================================

/* [1. Display Options] */
show_buckle_base = true;
show_battery_tub = true;
show_pcb_deck = true;
show_gps_deck = true;
show_flat_top = true;
exploded_view = true;
explode_distance = 10;
show_cross_section = false;

/* [2. Wall & Tolerance] */
wall = 2.0;                    // Wall thickness (mm)
corner_r = 3.0;                // Corner radius (mm)
assembly_gap = 0.2;            // Gap between PCB and walls (each side)
port_clearance = 0.5;          // Extra clearance around ports (each side)

/* [3. PCB TRUTH DATA (from DXF)] */
pcb_length = 69.22;            // PCB X dimension (mm)
pcb_width = 30.61;             // PCB Y dimension (mm)
pcb_thick = 1.6;               // PCB thickness (mm)

/* [4. Sandwich Layer Heights] */
buckle_base_h = 10;            // Layer 1: GoPro buckle base
battery_tub_h = 14;            // Layer 2: Battery compartment
pcb_deck_h = 12;               // Layer 3: PCB + ports (reduced from 15)
gps_deck_h = 12;               // Layer 4: GPS antenna bay
flat_top_h = 3;                // Layer 5: Top cover

/* [5. Battery Bay] */
bat_length = 44.0;
bat_width = 29.0;
bat_height = 12.0;

/* [6. GPS Antenna] */
gps_ant_size = 26;
gps_ant_height = 9;

/* [7. GoPro Buckle — Standard Dimensions] */
buckle_length = 42.0;          // Full length
buckle_width = 20.0;           // Rail-to-rail outer width
buckle_rail_w = 2.5;           // Each rail width
buckle_rail_spacing = 15.0;    // Inner channel width
buckle_rail_h = 6.0;           // Rail height
buckle_tab_w = 12.0;           // Locking tab width
buckle_tab_depth = 5.0;        // Tab engagement depth
buckle_tab_angle = 30;         // Tab chamfer angle
buckle_finger_w = 3.0;         // Finger release tab width
buckle_finger_l = 8.0;         // Finger release tab length

/* [8. Snap Fit] */
snap_width = 10;
snap_depth = 1.5;
snap_height = 2.5;

// ============================================================
// DERIVED DIMENSIONS (calculated from config)
// ============================================================

// Enclosure grows exactly around PCB with assembly gap
enc_length = pcb_length + wall*2 + assembly_gap*2;
enc_width = pcb_width + wall*2 + assembly_gap*2;

// PCB offset inside enclosure
pcb_offset_x = wall + assembly_gap;
pcb_offset_y = wall + assembly_gap;

// ============================================================
// PORT TRUTH DATA — From DXF (PCB-relative coordinates)
// ============================================================

// Cutout dimensions
jst4_cut_w = 6.0 + 2*port_clearance;    // 4-pin JST
jst2_cut_w = 4.0 + 2*port_clearance;    // 2-pin JST
usbc_cut_w = 10.0 + 2*port_clearance;   // USB-C
sd_cut_w = 15.0 + 2*port_clearance;     // MicroSD

jst_cutout_h = 6.0;
usbc_cutout_h = 5.0;
sd_cutout_h = 4.0;

// PORT 1: Main USB-C — LEFT wall (X=0)
usb_main_y = 15.87;

// PORTS 2-4: BACK wall (Y=pcb_width)
i2c_x = 40.77;
led_out_x = 60.58;
uart_x = 61.72;

// PORT 5: USBOUT JST — RIGHT wall (X=pcb_length)
usbout_y = 22.86;

// PORTS 6-9: FRONT wall (Y=0)
sd_x = 53.21;      // SD card — CORRECTED to front wall
aux_x = 12.32;
batt_x = 7.11;
pwr_sw_x = 4.95;

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
    translate([-0.25, -0.4, -0.25])
        cube([snap_width + 0.5, snap_depth + 0.8, snap_height + 0.5]);
}

// ============================================================
// LAYER 1: BUCKLE BASE — Standard GoPro Male Quick Release
// ============================================================

module gopro_male_buckle() {
    // Standard GoPro male quick release buckle
    base_h = 2;
    
    difference() {
        union() {
            // Main body (base plate)
            translate([-buckle_length/2, -buckle_width/2, 0])
                cube([buckle_length, buckle_width, base_h]);
            
            // Left rail
            translate([-buckle_length/2, -buckle_width/2, 0])
                cube([buckle_length, buckle_rail_w, buckle_rail_h]);
            
            // Right rail
            translate([-buckle_length/2, buckle_width/2 - buckle_rail_w, 0])
                cube([buckle_length, buckle_rail_w, buckle_rail_h]);
            
            // Locking tab (front, angled for click-in)
            translate([-buckle_tab_w/2, -buckle_width/2 - buckle_tab_depth + buckle_rail_w, base_h]) {
                difference() {
                    cube([buckle_tab_w, buckle_tab_depth, buckle_rail_h - base_h + 2]);
                    // Chamfer for snap-in
                    translate([-0.5, -1, buckle_rail_h - base_h])
                        rotate([buckle_tab_angle, 0, 0])
                            cube([buckle_tab_w + 1, buckle_tab_depth + 2, 5]);
                }
            }
            
            // Finger release tabs (sides)
            for (dx = [-1, 1]) {
                translate([dx * (buckle_tab_w/2 + buckle_finger_w/2 + 1), 
                           -buckle_width/2 - buckle_finger_l/2, 
                           buckle_rail_h - 1])
                    cube([buckle_finger_w, buckle_finger_l, 2], center=true);
            }
        }
        
        // Center channel (for female mount engagement)
        translate([-buckle_length/2 - 1, -buckle_rail_spacing/2, base_h])
            cube([buckle_length + 2, buckle_rail_spacing, buckle_rail_h]);
    }
}

module buckle_base() {
    base_floor = 2;
    difference() {
        union() {
            rounded_box(enc_length, enc_width, buckle_base_h, corner_r);
            // Alignment posts
            for (x = [wall + 8, enc_length - wall - 8]) {
                for (y = [wall + 6, enc_width - wall - 6]) {
                    translate([x, y, buckle_base_h])
                        cylinder(h = 3, d = 6, $fn = 24);
                }
            }
        }
        // Hollow interior
        translate([wall, wall, base_floor])
            rounded_box(enc_length - 2*wall, enc_width - 2*wall, buckle_base_h, max(corner_r - wall, 0.5));
        // Screw holes
        for (x = [wall + 8, enc_length - wall - 8]) {
            for (y = [wall + 6, enc_width - wall - 6]) {
                translate([x, y, -1])
                    cylinder(h = buckle_base_h + 5, d = 3.2, $fn = 24);
                translate([x, y, -0.1])
                    cylinder(h = 2, d1 = 6, d2 = 3.2, $fn = 24);
            }
        }
    }
    // GoPro buckle underneath
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
            // Snap clips on top
            for (x = [enc_length * 0.25, enc_length * 0.75]) {
                for (side = [0, 1]) {
                    y_pos = side == 0 ? wall : enc_width - wall - snap_depth;
                    translate([x - snap_width/2, y_pos, battery_tub_h])
                        snap_clip_male();
                }
            }
        }
        // Hollow interior
        translate([wall, wall, floor_t])
            rounded_box(enc_length - 2*wall, enc_width - 2*wall, battery_tub_h, max(corner_r - wall, 0.5));
        // Alignment recesses
        for (x = [wall + 8, enc_length - wall - 8]) {
            for (y = [wall + 6, enc_width - wall - 6]) {
                translate([x, y, -1])
                    cylinder(h = 4, d = 6.4, $fn = 24);
            }
        }
        // Wire pass-through
        translate([enc_length/2, enc_width/2, battery_tub_h - 2])
            cylinder(h = 4, d = 8, $fn = 24);
    }
    // Battery corner supports
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
// LAYER 3: PCB DECK — 9 Precision Port Cutouts
// ============================================================

module pcb_deck() {
    floor_t = 2;
    support_ledge_h = 2;
    pcb_surface_z = floor_t + support_ledge_h;
    
    difference() {
        union() {
            rounded_box(enc_length, enc_width, pcb_deck_h, corner_r);
            // Snap clips on top
            for (x = [enc_length * 0.25, enc_length * 0.75]) {
                for (side = [0, 1]) {
                    y_pos = side == 0 ? wall : enc_width - wall - snap_depth;
                    translate([x - snap_width/2, y_pos, pcb_deck_h])
                        snap_clip_male();
                }
            }
        }
        
        // ─── PI-STYLE SNUG FIT HOLLOW ───
        translate([pcb_offset_x - assembly_gap, pcb_offset_y - assembly_gap, floor_t])
            rounded_box(pcb_length + assembly_gap*2, pcb_width + assembly_gap*2, pcb_deck_h, 1.0);
        
        // ─── SNAP RECEIVERS (from battery tub) ───
        for (x = [enc_length * 0.25, enc_length * 0.75]) {
            for (side = [0, 1]) {
                y_pos = side == 0 ? wall - 0.5 : enc_width - wall - snap_depth + 0.5;
                translate([x - snap_width/2, y_pos, -0.1])
                    snap_clip_female();
            }
        }
        
        // ═══════════════════════════════════════════════════════
        // 9 PRECISION PORT CUTOUTS (Clockwise from Main USB-C)
        // ═══════════════════════════════════════════════════════
        
        // PORT 1: Main USB-C — LEFT WALL (X = 0)
        translate([-0.1, pcb_offset_y + usb_main_y - usbc_cut_w/2, pcb_surface_z])
            cube([wall + 0.2, usbc_cut_w, usbc_cutout_h]);
        
        // PORT 2: I2C JST — BACK WALL (Y = enc_width)
        translate([pcb_offset_x + i2c_x - jst4_cut_w/2, enc_width - wall - 0.1, pcb_surface_z])
            cube([jst4_cut_w, wall + 0.2, jst_cutout_h]);
        
        // PORT 3: LED OUT Type-C — BACK WALL
        translate([pcb_offset_x + led_out_x - usbc_cut_w/2, enc_width - wall - 0.1, pcb_surface_z])
            cube([usbc_cut_w, wall + 0.2, usbc_cutout_h]);
        
        // PORT 4: UART JST — BACK WALL
        translate([pcb_offset_x + uart_x - jst4_cut_w/2, enc_width - wall - 0.1, pcb_surface_z])
            cube([jst4_cut_w, wall + 0.2, jst_cutout_h]);
        
        // PORT 5: USBOUT JST — RIGHT WALL (X = enc_length)
        translate([enc_length - wall - 0.1, pcb_offset_y + usbout_y - jst4_cut_w/2, pcb_surface_z])
            cube([wall + 0.2, jst4_cut_w, jst_cutout_h]);
        
        // PORT 6: SD CARD — FRONT WALL (Y = 0) ★ CORRECTED
        translate([pcb_offset_x + sd_x - sd_cut_w/2, -0.1, pcb_surface_z])
            cube([sd_cut_w, wall + 0.2, sd_cutout_h]);
        
        // PORT 7: AUX JST — FRONT WALL
        translate([pcb_offset_x + aux_x - jst4_cut_w/2, -0.1, pcb_surface_z])
            cube([jst4_cut_w, wall + 0.2, jst_cutout_h]);
        
        // PORT 8: BATT JST — FRONT WALL
        translate([pcb_offset_x + batt_x - jst2_cut_w/2, -0.1, pcb_surface_z])
            cube([jst2_cut_w, wall + 0.2, jst_cutout_h]);
        
        // PORT 9: PWR SW JST — FRONT WALL
        translate([pcb_offset_x + pwr_sw_x - jst2_cut_w/2, -0.1, pcb_surface_z])
            cube([jst2_cut_w, wall + 0.2, jst_cutout_h]);
        
        // ─── LED STATUS WINDOW ───
        translate([enc_length/3 - 8, -0.1, pcb_surface_z + 2])
            cube([16, wall - 0.5, 5]);
    }
    
    // ─── SUPPORT LEDGE (continuous perimeter) ───
    difference() {
        translate([pcb_offset_x - 1, pcb_offset_y - 1, floor_t])
            rounded_box(pcb_length + 2, pcb_width + 2, support_ledge_h, 1.5);
        translate([pcb_offset_x + 1, pcb_offset_y + 1, floor_t - 0.1])
            rounded_box(pcb_length - 2, pcb_width - 2, support_ledge_h + 0.2, 1.5);
    }
}

// ============================================================
// LAYER 4: GPS DECK — Empty Volume (No Dividers)
// ============================================================

module gps_deck() {
    floor_t = 2;
    difference() {
        union() {
            rounded_box(enc_length, enc_width, gps_deck_h, corner_r);
            // Lip for top layer engagement
            translate([wall - 0.5, wall - 0.5, gps_deck_h])
                difference() {
                    rounded_box(enc_length - 2*wall + 1, enc_width - 2*wall + 1, 2, max(corner_r - wall, 0.5));
                    translate([1.5, 1.5, -0.1])
                        rounded_box(enc_length - 2*wall - 2, enc_width - 2*wall - 2, 2.2, max(corner_r - wall - 1, 0.5));
                }
        }
        
        // ─── EMPTY INTERIOR (no dividers/pockets) ───
        translate([wall, wall, floor_t])
            rounded_box(enc_length - 2*wall, enc_width - 2*wall, gps_deck_h, max(corner_r - wall, 0.5));
        
        // Snap receivers
        for (x = [enc_length * 0.25, enc_length * 0.75]) {
            for (side = [0, 1]) {
                y_pos = side == 0 ? wall - 0.5 : enc_width - wall - snap_depth + 0.5;
                translate([x - snap_width/2, y_pos, -0.1])
                    snap_clip_female();
            }
        }
    }
    
    // Note: Antenna pocket REMOVED per V5.0 spec
    // GPS bay is now one large empty volume
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
            // Engagement lip
            translate([wall + 0.3, wall + 0.3, -1.5])
                rounded_box(enc_length - 2*wall - 0.6, enc_width - 2*wall - 0.6, 1.5, max(corner_r - wall - 0.3, 0.5));
        }
        
        // GPS window (open for signal)
        translate([window_x, window_y, 1])
            cube([window_size, window_size, flat_top_h]);
        
        // Corner chamfers
        for (x = [0, enc_length]) {
            for (y = [0, enc_width]) {
                translate([x, y, flat_top_h])
                    rotate([0, 0, 45])
                        translate([-2, -2, -1.5])
                            cube([4, 4, 2]);
            }
        }
    }
    
    // Thin GPS window cover (RF transparent)
    translate([window_x, window_y, 0])
        cube([window_size, window_size, 0.8]);
    
    // Branding
    translate([enc_length/2, enc_width - 8, flat_top_h - 0.3])
        linear_extrude(0.5)
            text("RACESENSE", size = 4, font = "Liberation Sans:style=Bold", halign = "center", valign = "center");
}

// ============================================================
// ASSEMBLY
// ============================================================

module assembly() {
    z = 0;
    exp = exploded_view ? explode_distance : 0;
    
    if (show_buckle_base) 
        color("DimGray", 0.95) 
            translate([0, 0, z]) 
                buckle_base();
    
    z1 = buckle_base_h + exp;
    if (show_battery_tub) 
        color("SlateGray", 0.9) 
            translate([0, 0, z1]) 
                battery_tub();
    
    z2 = z1 + battery_tub_h + exp;
    if (show_pcb_deck) 
        color("DarkSlateGray", 0.9) 
            translate([0, 0, z2]) 
                pcb_deck();
    
    z3 = z2 + pcb_deck_h + exp;
    if (show_gps_deck) 
        color("CadetBlue", 0.9) 
            translate([0, 0, z3]) 
                gps_deck();
    
    z4 = z3 + gps_deck_h + exp;
    if (show_flat_top) 
        color("White", 0.95) 
            translate([0, 0, z4]) 
                flat_top();
}

// ============================================================
// RENDER
// ============================================================

if (show_cross_section) {
    difference() {
        assembly();
        translate([enc_length/2, -10, -20])
            cube([enc_length, enc_width + 20, 150]);
    }
} else {
    assembly();
}

// ============================================================
// V5.0 CHANGE LOG
// ============================================================
// - 9 port cutouts with clockwise mapping from Main USB-C
// - SD card moved to FRONT wall (Y=0) per DXF truth data
// - GoPro buckle redesigned to standard dimensions
// - PCB deck height reduced to 12mm (from 15mm)
// - GPS bay now empty volume (no internal dividers)
// - All parameters moved to top configuration block
// ============================================================
