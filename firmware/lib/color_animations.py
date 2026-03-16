# lib/color_animations.py - Pre-allocated LED Theme Engine for RS-Core
# Bypasses tuple creation for Zero-Allocation rendering.

class ColorAnimations:
    """
    Pre-allocated hardware-native (GRB) color bytes and animation sequences.
    """
    # --- GRB CORE COLORS ---
    OFF = b'\x00\x00\x00'
    RED = b'\x00\xFF\x00'
    GREEN = b'\xFF\x00\x00'
    BLUE = b'\x00\x00\xFF'
    YELLOW = b'\xFF\xFF\x00'
    AMBER = b'\x80\xFF\x00'
    PURPLE = b'\x00\xA0\xA0'
    WHITE = b'\xFF\xFF\xFF'
    ORANGE = b'\xA5\xFF\x00'
    CYAN = b'\xFF\x00\xFF'
    MAGENTA = b'\x00\xFF\xFF'
    LIME = b'\xFF\x60\x00'
    
    # --- PULSE SEQUENCES (10 frames, 50Hz) ---
    P_YEL = (
        b'\x04\x10\x00', b'\x0C\x30\x00', b'\x18\x60\x00', b'\x24\x90\x00', b'\x30\xC0\x00',
        b'\x40\xFF\x00', b'\x30\xC0\x00', b'\x24\x90\x00', b'\x18\x60\x00', b'\x0C\x30\x00'
    )
    P_BLU = (
        b'\x00\x00\x10', b'\x00\x00\x30', b'\x00\x00\x60', b'\x00\x00\x90', b'\x00\x00\xC0',
        b'\x00\x00\xF0', b'\x00\x00\xC0', b'\x00\x00\x90', b'\x00\x00\x60', b'\x00\x00\x30'
    )
    P_PURP = (
        b'\x00\x10\x10', b'\x00\x30\x30', b'\x00\x60\x60', b'\x00\x90\x90', b'\x00\xC0\xC0',
        b'\x00\xF0\xF0', b'\x00\xC0\xC0', b'\x00\x90\x90', b'\x00\x60\x60', b'\x00\x30\x30'
    )
    
    # --- HEARTBEAT SEQUENCES (20 frames, 2s cycle) ---
    HB_RED = (
        RED, OFF, RED, OFF, OFF, OFF, OFF, OFF, OFF, OFF,
        OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF
    )
    HB_GRN = (
        GREEN, OFF, GREEN, OFF, OFF, OFF, OFF, OFF, OFF, OFF,
        OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF
    )

    # --- THEMES & GROUPS ---
    RAINBOW = (ORANGE, YELLOW, AMBER, PURPLE, CYAN, MAGENTA, LIME)
    
