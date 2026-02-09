# Racesense RS-Core Enclosure Specification v6.1

**Version:** 6.1  
**Date:** 2026-02-09  
**Author:** Racesense Mechanical Engineering  
**Status:** Production Ready

---

## 1. Overview

The RS-Core enclosure is a "Sandwich Stack" design optimized for motorcycle trackday use:

```
┌─────────────────────────────────┐
│         GPS Window              │  ← Layer 5: Flat Top
├─────────────────────────────────┤
│       GPS Antenna Bay           │  ← Layer 4: GPS Deck
├─────────────────────────────────┤
│   RS-Core PCB (69.2×30.6mm)     │  ← Layer 3: PCB Deck (9 ports)
├─────────────────────────────────┤
│    LiPo Battery (1100mAh)       │  ← Layer 2: Battery Tub
├─────────────────────────────────┤
│      Alignment + Hollow         │  ← Layer 1: Buckle Base
├─────────────────────────────────┤
│   GoPro Male Buckle (DOWN)      │  ← Mount
└─────────────────────────────────┘
```

### Key Features
- **9 fully parametric port cutouts** with OpenSCAD Customizer support
- **GoPro Quick-Release Buckle** (male, 2-prong) mounted UNDERNEATH, facing DOWN
- **5-layer snap-fit assembly** for easy maintenance
- **GPS-transparent window** for antenna reception
- **Precision port alignment** from DXF-extracted coordinates

---

## 2. PCB Reference

| Parameter | Value |
|-----------|-------|
| Board Dimensions | 69.22 × 30.61 mm |
| Board Thickness | 1.6 mm |
| Reference Point | Bottom-Left Corner (0, 0) |
| Source | EasyEDA Gerber export |

---

## 3. Port Truth Map (from hardware_precision_map.txt)

All coordinates reference the PCB origin (bottom-left corner at 0,0).

| # | Port | X (mm) | Y (mm) | Z (mm) | Wall | Description |
|---|------|--------|--------|--------|------|-------------|
| 1 | USB | — | 15.71 | 0.39 | LEFT (0) | Main USB-C (Programming) |
| 2 | I2C | 40.49 | — | 1.42 | BACK (3) | Primary I2C Connector |
| 3 | LED_OUT | 61.00 | — | 0.84 | BACK (3) | LED USB-C Output |
| 4 | UART | 59.25 | — | 2.69 | BACK (3) | Debug UART Header |
| 5 | USBOUT | — | 21.51 | 1.57 | RIGHT (1) | External USB Output |
| 6 | MICRO-SD | 53.09 | — | 2.09 | FRONT (2) | SD Card Slot |
| 7 | AUX | 13.09 | — | 1.52 | FRONT (2) | Auxiliary Connector |
| 8 | BATT | 7.40 | — | 0.31 | FRONT (2) | JST Battery Connector |
| 9 | PWR-SW | 4.76 | — | 0.67 | FRONT (2) | Power Switch |

### Wall Reference
```
                 BACK (Wall 3, Y = 30.61mm)
           ┌─────────────────────────────┐
           │                             │
LEFT       │                             │       RIGHT
(Wall 0)   │          RS-Core            │      (Wall 1)
(X = 0)    │           PCB               │      (X = 69.22mm)
           │                             │
           │                             │
           └─────────────────────────────┘
                FRONT (Wall 2, Y = 0)
```

---

## 4. Layer Dimensions

| Layer | Height | Description |
|-------|--------|-------------|
| 1. Buckle Base | 10 mm | GoPro mount + alignment posts |
| 2. Battery Tub | 14 mm | LiPo compartment |
| 3. PCB Deck | 11 mm | PCB + all port cutouts |
| 4. GPS Deck | 12 mm | Antenna bay (empty volume) |
| 5. Flat Top | 3 mm | Cover with GPS window |
| **Total** | **50 mm** | Assembled height |

---

## 5. Battery Specifications

| Parameter | Value |
|-----------|-------|
| LiPo Model | WLY102540 (Robu) |
| Dimensions | 40 × 25 × 10 mm |
| Capacity | 1100mAh |
| Price | ₹399 |
| Tolerance | 1.0 mm all around |

**Safety Notes:**
- Pad bottom with 2-3mm foam
- Verify JST polarity (Robu may swap red/black)
- Wire pass-through hole (Ø8mm) in center

---

## 6. GoPro Quick-Release Buckle (Male)

The enclosure uses a **GoPro-compatible Male Quick-Release Buckle** mounted on the **bottom of Layer 1, facing DOWNWARD**.

### Orientation Diagram
```
                    ┌────────────┐
                    │  Enclosure │
                    │    Base    │
                    ├────────────┤
                    │   ┌──┐┌──┐ │  ← GoPro prongs
                    │   │  ││  │ │     facing DOWN
                    │   │  ││  │ │
                    │   └──┘└──┘ │
                    └────────────┘
                          ↓
                   [Female GoPro mount
                    on motorcycle/helmet]
```

### Buckle Dimensions (V6.1)
| Parameter | Value |
|-----------|-------|
| Total Length | 42.0 mm |
| Main Rail Width | 23.0 mm |
| Total Width (w/ springs) | 31.0 mm |
| Rail Height | 6.0 mm |
| Base Thickness | 2.0 mm |
| Locking Tab Width | 14.0 mm |
| Tab Chamfer Angle | 35° |
| Spring Clip Length | 15.0 mm |
| Spring Clip Width | 4.0 mm |

### Why Male Buckle?
- **Universal compatibility** — works with all female GoPro mounts
- **Quick detach** — press finger tab to release
- **Secure lock** — chamfered tab clicks into female rails
- **Standard interface** — industry-proven design

---

## 7. OpenSCAD Customizer Sections

The script organizes all parameters into Customizer sections:

| Section | Parameters |
|---------|------------|
| `[1. Display Options]` | Show/hide layers, explode view, debug |
| `[2. Global Tolerances]` | Wall, corner, assembly gaps |
| `[3. PCB Dimensions]` | Board size |
| `[4. Layer Heights]` | Each layer's Z dimension |
| `[5. Battery Bay]` | LiPo dimensions |
| `[6. GPS Antenna]` | Window size |
| `[7. GoPro Buckle]` | All buckle dimensions |
| `[8. Snap Fit]` | Clip dimensions |
| `[Port 1-9]` | Individual X/Y/Z, width, height, wall |

### How to Use
1. Open `rs_core_enclosure_v6.scad` in OpenSCAD
2. Enable Customizer: **View → Customizer** (or press F7)
3. Expand sections in the right sidebar
4. Adjust any parameter — model updates live
5. Render (F6) and Export STL (F7) when ready

---

## 8. Enclosure Dimensions

| Parameter | Value |
|-----------|-------|
| Outer Length | 73.62 mm |
| Outer Width | 35.01 mm |
| Corner Radius | 3.0 mm |
| Wall Thickness | 2.0 mm |
| Assembly Tolerance | 0.2 mm |

---

## 9. Materials & Printing

| Parameter | Recommendation |
|-----------|----------------|
| Material | PETG or ASA (heat resistant) |
| Layer Height | 0.2 mm |
| Infill | 30-40% |
| Walls | 3 perimeters |
| Supports | Needed for GoPro buckle prongs |
| Print Orientation | Each layer flat on bed |

**Note:** Avoid carbon fiber filament — blocks GPS signal through top layer.

---

## 10. File Locations

| File | Path |
|------|------|
| OpenSCAD Script | `hardware/enclosure/rs_core_enclosure_v6.scad` |
| Specification | `hardware/enclosure/enclosure_v2_spec.md` |
| Precision Map | `hardware_precision_map.txt` (workspace) |

---

## 11. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 5.0 | 2026-02-09 | Initial 9-port layout, basic GoPro |
| 6.0 | 2026-02-09 | Fully parametric ports, high-fidelity buckle |
| 6.1 | 2026-02-09 | Precision map coordinates, validated buckle orientation, full Customizer support |

---

## 12. Quick Reference Card

### Port Cutout Defaults (Copy-Paste for Customizer)

```
Port 1 (USB):    wall=0, offset=15.71, z=0.39, w=10, h=5
Port 2 (I2C):    wall=3, offset=40.49, z=1.42, w=6,  h=6
Port 3 (LED):    wall=3, offset=61.00, z=0.84, w=10, h=5
Port 4 (UART):   wall=3, offset=59.25, z=2.69, w=12, h=6
Port 5 (USBOUT): wall=1, offset=21.51, z=1.57, w=10, h=6
Port 6 (SD):     wall=2, offset=53.09, z=2.09, w=15, h=4
Port 7 (AUX):    wall=2, offset=13.09, z=1.52, w=6,  h=6
Port 8 (BATT):   wall=2, offset=7.40,  z=0.31, w=6,  h=6
Port 9 (PWR):    wall=2, offset=4.76,  z=0.67, w=6,  h=6
```

### Wall IDs
- `0` = LEFT (X = 0)
- `1` = RIGHT (X = max)
- `2` = FRONT (Y = 0)
- `3` = BACK (Y = max)
