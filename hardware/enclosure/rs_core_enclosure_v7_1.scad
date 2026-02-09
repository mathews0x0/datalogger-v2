/*
 * RACESENSE RS-CORE ENCLOSURE v7.1
 * "The Ultimate Parametric Housing" - Production Edition (Standalone)
 * 
 * Features:
 * - 5-Layer Sandwich Stack Architecture
 * - 100% Configurable XYZ Port Alignment
 * - Industry Standard GoPro Mount (Integrated library)
 * - Snap-fit assembly
 * 
 * Author: Racesense Team (Jane + Mathews)
 * Date: 2026-02-09
 */

// ============================================================
/* [1. Display Options] */
// ============================================================
show_buckle_base    = true;     // Layer 1: GoPro mount base
show_battery_tub    = true;     // Layer 2: Battery compartment
show_pcb_deck       = true;     // Layer 3: PCB + all ports
show_gps_deck       = true;     // Layer 4: GPS antenna bay
show_flat_top       = true;     // Layer 5: Top cover

exploded_view       = true;     // Explode layers for visibility
explode_distance    = 15;       // Gap between layers (mm)
show_cross_section  = false;    // Cut view for debugging
show_port_labels    = true;     // Debug: show port numbers

// ============================================================
/* [2. Global Tolerances] */
// ============================================================
wall                = 2.0;      // Wall thickness (mm)
corner_r            = 3.0;      // Corner radius (mm)
assembly_tol        = 0.3;      // Gap between PCB and walls
port_tol            = 0.6;      // Extra clearance around ports
layer_tol           = 0.15;     // Between stacked layers
snap_tol            = 0.2;      // Snap-fit clearance

// ============================================================
/* [3. PCB Dimensions] */
// ============================================================
pcb_length          = 69.22;    // PCB X dimension (mm)
pcb_width           = 30.61;    // PCB Y dimension (mm)
pcb_thick           = 1.6;      // PCB thickness (mm)

// ============================================================
/* [4. Layer Heights] */
// ============================================================
buckle_base_h       = 6;        // Layer 1: GoPro buckle base (plate height)
battery_tub_h       = 14;       // Layer 2: Battery compartment
pcb_deck_h          = 10;       // Layer 3: PCB + ports
gps_deck_h          = 10;       // Layer 4: GPS antenna bay
flat_top_h          = 3;        // Layer 5: Top cover

// ============================================================
/* [5. Battery Bay] */
// ============================================================
bat_length          = 44.0;     
bat_width           = 29.0;     
bat_height          = 12.0;     

// ============================================================
/* [6. GPS Antenna] */
// ============================================================
gps_window_size     = 28;       // GPS window dimension (mm)

// ============================================================
// PORT CONFIGURATION (Parametric XYZ)
// ============================================================
/* [Port 1: Main USB-C (Programming)] */
port1_wall   = 0;               // 0=LEFT, 1=RIGHT, 2=FRONT, 3=BACK
port1_offset = 15.71;           // Distance along the wall from corner
port1_z      = 0.39;            // Height above PCB surface
port1_w      = 12.0;            
port1_h      = 5.5;             

/* [Port 2: I2C Connector] */
port2_wall   = 3;               
port2_offset = 40.49;           
port2_z      = 1.42;            
port2_w      = 8.0;             
port2_h      = 6.0;             

/* [Port 3: LED_OUT USB-C] */
port3_wall   = 3;               
port3_offset = 61.00;           
port3_z      = 0.84;            
port3_w      = 12.0;            
port3_h      = 5.5;             

/* [Port 4: UART Header] */
port4_wall   = 3;               
port4_offset = 59.25;           
port4_z      = 2.69;            
port4_w      = 14.0;            
port4_h      = 7.0;             

/* [Port 5: USBOUT JST] */
port5_wall   = 1;               
port5_offset = 21.51;           
port5_z      = 1.57;            
port5_w      = 8.0;             
port5_h      = 6.0;             

/* [Port 6: Micro-SD Slot] */
port6_wall   = 2;               
port6_offset = 53.09;           
port6_z      = 2.09;            
port6_w      = 16.0;            
port6_h      = 4.5;             

/* [Port 7: AUX Connector] */
port7_wall   = 2;               
port7_offset = 12.32;           
port7_z      = 1.52;            
port7_w      = 8.0;             
port7_h      = 6.0;             

/* [Port 8: Battery Connector] */
port8_wall   = 2;               
port8_offset = 7.40;            
port8_z      = 0.31;            
port8_w      = 8.0;             
port8_h      = 6.0;             

/* [Port 9: Power Switch] */
port9_wall   = 2;               
port9_offset = 4.76;            
port9_z      = 0.67;            
port9_w      = 8.0;             
port9_h      = 6.0;             

// ============================================================
// CALCULATED CONSTANTS
// ============================================================
enc_length    = pcb_length + wall*2 + assembly_tol*2;
enc_width     = pcb_width + wall*2 + assembly_tol*2;
pcb_offset_x  = wall + assembly_tol;
pcb_offset_y  = wall + assembly_tol;
floor_t       = 2.0;            // Layer bottom thickness
pcb_surface_z = floor_t + 2.0;  // Standoff height (support ledge)
snap_w        = 10;
snap_h        = 3;

// ============================================================
// GOPRO LIBRARY INTEGRATION (ridercz/GoProScad)
// ============================================================
__gopro_outer_diameter = 15;
__gopro_leg_width = 3;
__gopro_slit_width = 3.5;
__gopro_hole_diameter = 5;
__gopro_hole_tolerance = .5;

module gopro_mount_m(base_height = 3, base_width = 20, leg_height = 17, center = false) {
    base_depth = __gopro_leg_width * 2 + __gopro_slit_width;
    hole_offset = [base_height + leg_height - __gopro_outer_diameter / 2, base_width / 2];

    translate(center ? [0, -base_depth / 2] : [0, 0]) {
        translate([-base_width / 2, 0]) cube([base_width, __gopro_leg_width * 2 + __gopro_slit_width, base_height]);
        translate([0, __gopro_leg_width + __gopro_slit_width / 2]) rotate(90) translate([base_depth / 2, -hole_offset[1]]) rotate([0, -90, 0]) for(z_offset = [0, __gopro_leg_width + __gopro_slit_width]) translate([0, 0, z_offset]) linear_extrude(__gopro_leg_width) difference() {
            hull() {
                square([base_height, base_width]);
                translate(hole_offset) circle(d = __gopro_outer_diameter, $fn = 64);
            }
            translate(hole_offset) circle(d = __gopro_hole_diameter + __gopro_hole_tolerance, $fn = 32);
        }
    }
}

// ============================================================
// CORE MODULES
// ============================================================

module rounded_box(l, w, h, r) {
    hull() {
        for (x = [r, l-r]) {
            for (y = [r, w-r]) {
                translate([x, y, 0]) cylinder(h=h, r=r, $fn=64);
            }
        }
    }
}

module port_cutout(wall_id, offset, z_offset, cut_w, cut_h) {
    cw = cut_w + port_tol;
    ch = cut_h + port_tol;
    z_pos = pcb_surface_z + z_offset;
    d = wall * 3; 
    
    if (wall_id == 0) { // LEFT
        translate([-d/2, pcb_offset_y + offset, z_pos + ch/2]) 
            cube([d, cw, ch], center=true);
    } else if (wall_id == 1) { // RIGHT
        translate([enc_length + d/2 - wall, pcb_offset_y + offset, z_pos + ch/2]) 
            cube([d, cw, ch], center=true);
    } else if (wall_id == 2) { // FRONT
        translate([pcb_offset_x + offset, -d/2, z_pos + ch/2]) 
            cube([cw, d, ch], center=true);
    } else if (wall_id == 3) { // BACK
        translate([pcb_offset_x + offset, enc_width + d/2 - wall, z_pos + ch/2]) 
            cube([cw, d, ch], center=true);
    }
}

module port_label(wall_id, offset, z_offset, label) {
    if (show_port_labels) {
        z_pos = pcb_surface_z + z_offset + 5;
        color("Red")
        if (wall_id == 0) translate([-5, pcb_offset_y + offset, z_pos]) rotate([90,0,90]) text(label, 3, halign="center");
        else if (wall_id == 1) translate([enc_length+5, pcb_offset_y + offset, z_pos]) rotate([90,0,-90]) text(label, 3, halign="center");
        else if (wall_id == 2) translate([pcb_offset_x + offset, -5, z_pos]) rotate([90,0,0]) text(label, 3, halign="center");
        else if (wall_id == 3) translate([pcb_offset_x + offset, enc_width+5, z_pos]) rotate([90,0,180]) text(label, 3, halign="center");
    }
}

// ============================================================
// LAYER DEFINITIONS
// ============================================================

// Layer 1: GoPro Base
module layer_buckle_base() {
    difference() {
        rounded_box(enc_length, enc_width, buckle_base_h, corner_r);
        translate([wall, wall, floor_t]) 
            rounded_box(enc_length-wall*2, enc_width-wall*2, buckle_base_h, corner_r-wall);
    }
    translate([enc_length/2, enc_width/2, 0]) 
        rotate([180, 0, 90]) 
        gopro_mount_m(base_height=buckle_base_h, base_width=25, leg_height=18, center=true);
}

// Layer 2: Battery Tub
module layer_battery_tub() {
    difference() {
        rounded_box(enc_length, enc_width, battery_tub_h, corner_r);
        translate([wall, wall, floor_t]) 
            rounded_box(enc_length-wall*2, enc_width-wall*2, battery_tub_h, corner_r-wall);
        
        translate([(enc_length-bat_length)/2, (enc_width-bat_width)/2, floor_t])
            cube([bat_length, bat_width, bat_height+1]);
    }
}

// Layer 3: PCB Deck
module layer_pcb_deck() {
    difference() {
        union() {
            rounded_box(enc_length, enc_width, pcb_deck_h, corner_r);
        }
        
        translate([pcb_offset_x - assembly_tol, pcb_offset_y - assembly_tol, floor_t])
            rounded_box(pcb_length + assembly_tol*2, pcb_width + assembly_tol*2, pcb_deck_h, 1);
            
        port_cutout(port1_wall, port1_offset, port1_z, port1_w, port1_h);
        port_cutout(port2_wall, port2_offset, port2_z, port2_w, port2_h);
        port_cutout(port3_wall, port3_offset, port3_z, port3_w, port3_h);
        port_cutout(port4_wall, port4_offset, port4_z, port4_w, port4_h);
        port_cutout(port5_wall, port5_offset, port5_z, port5_w, port5_h);
        port_cutout(port6_wall, port6_offset, port6_z, port6_w, port6_h);
        port_cutout(port7_wall, port7_offset, port7_z, port7_w, port7_h);
        port_cutout(port8_wall, port8_offset, port8_z, port8_w, port8_h);
        port_cutout(port9_wall, port9_offset, port9_z, port9_w, port9_h);
    }
    
    difference() {
        translate([pcb_offset_x-1, pcb_offset_y-1, floor_t]) 
            rounded_box(pcb_length+2, pcb_width+2, pcb_surface_z-floor_t, 1.5);
        translate([pcb_offset_x+1, pcb_offset_y+1, floor_t-0.1]) 
            rounded_box(pcb_length-2, pcb_width-2, pcb_surface_z, 1);
    }

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

// Layer 4: GPS Deck
module layer_gps_deck() {
    difference() {
        rounded_box(enc_length, enc_width, gps_deck_h, corner_r);
        translate([wall, wall, floor_t]) 
            rounded_box(enc_length-wall*2, enc_width-wall*2, gps_deck_h, corner_r-wall);
    }
}

// Layer 5: Top Cover
module layer_flat_top() {
    difference() {
        rounded_box(enc_length, enc_width, flat_top_h, corner_r);
        
        translate([(enc_length-gps_window_size)/2, (enc_width-gps_window_size)/2, -1])
            cube([gps_window_size, gps_window_size, flat_top_h+2]);
        
        translate([enc_length/2, enc_width/2, flat_top_h-0.5])
            linear_extrude(1) text("RS-CORE", size=5, halign="center", valign="center", font="Liberation Sans:style=Bold");
    }
}

// ============================================================
// ASSEMBLY
// ============================================================

module full_assembly() {
    z0 = 0;
    if (show_buckle_base) color("DimGray") translate([0, 0, z0]) layer_buckle_base();
    
    z1 = z0 + buckle_base_h + (exploded_view ? explode_distance : 0);
    if (show_battery_tub) color("SlateGray") translate([0, 0, z1]) layer_battery_tub();
    
    z2 = z1 + battery_tub_h + (exploded_view ? explode_distance : 0);
    if (show_pcb_deck) color("DarkSlateGray") translate([0, 0, z2]) layer_pcb_deck();
    
    z3 = z2 + pcb_deck_h + (exploded_view ? explode_distance : 0);
    if (show_gps_deck) color("CadetBlue") translate([0, 0, z3]) layer_gps_deck();
    
    z4 = z3 + gps_deck_h + (exploded_view ? explode_distance : 0);
    if (show_flat_top) color("LightGray") translate([0, 0, z4]) layer_flat_top();
}

if (show_cross_section) {
    difference() {
        full_assembly();
        translate([enc_length/2, -1, -50]) cube([enc_length, enc_width+2, 200]);
    }
} else {
    full_assembly();
}
