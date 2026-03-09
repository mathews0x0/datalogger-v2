import machine, time, math
import neopixel

PIN_NEOPIXEL_1 = 4
PIN_NEOPIXEL_2 = 6
PIN_BUTTON = 5
NUM_PIXELS = 16

np1 = neopixel.NeoPixel(machine.Pin(PIN_NEOPIXEL_1), NUM_PIXELS)
np2 = neopixel.NeoPixel(machine.Pin(PIN_NEOPIXEL_2), NUM_PIXELS)
button = machine.Pin(PIN_BUTTON, machine.Pin.IN, machine.Pin.PULL_UP)

def write_pixels():
    np1.write()
    np2.write()

# --- ANIMATION DEFINITIONS ---
# Animations are called non-blocking continuously in the main loop
num_anims = 3
anim_idx = 0
tick = 0

def anim_chaser(tick):
    # A single dot chasing around the square
    np1.fill((0, 0, 0))
    np2.fill((0, 0, 0))
    pos = tick % NUM_PIXELS
    tail1 = (pos - 1) % NUM_PIXELS
    tail2 = (pos - 2) % NUM_PIXELS
    
    np1[pos] = np2[pos] = (50, 0, 0) # Head
    np1[tail1] = np2[tail1] = (20, 0, 0)
    np1[tail2] = np2[tail2] = (5, 0, 0)
    write_pixels()

def anim_pulse(tick):
    # Breathing blue pulse
    intensity = int(25 * (math.sin(tick / 10.0) + 1)) # Range 0 to 50
    np1.fill((0, 0, intensity))
    np2.fill((0, 0, intensity))
    write_pixels()

def wheel(pos):
    # Input a value 0 to 255 to get a color value.
    if pos < 0 or pos > 255: return (0, 0, 0)
    if pos < 85: return (int(255 - pos * 3), int(pos * 3), 0)
    if pos < 170:
        pos -= 85
        return (0, int(255 - pos * 3), int(pos * 3))
    pos -= 170
    return (int(pos * 3), 0, int(255 - pos * 3))

def anim_rainbow(tick):
    # Rainbow sweep
    for i in range(NUM_PIXELS):
        pixel_index = (i * 256 // NUM_PIXELS) + (tick * 5)
        color = wheel(pixel_index & 255)
        # Scale down brightness
        scaled_color = (color[0]//10, color[1]//10, color[2]//10)
        np1[i] = np2[i] = scaled_color
    write_pixels()

print("\nStarting Animation Cycle...")
last_state = button.value()

try:
    while True:
        # Check Button state (Trigger on Press, ignore Release)
        current_state = button.value()
        if last_state == 1 and current_state == 0:
            anim_idx = (anim_idx + 1) % num_anims
            print(f"Switched to Animation: {anim_idx}")
            time.sleep_ms(200) # Soft debounce
            current_state = button.value() # Update state after sleep
            
        last_state = current_state
        
        # Run Current Animation Frame
        if anim_idx == 0:
            anim_chaser(tick)
        elif anim_idx == 1:
            anim_pulse(tick)
        elif anim_idx == 2:
            anim_rainbow(tick)
            
        tick += 1
        time.sleep_ms(30) # Animation speed control

except KeyboardInterrupt:
    print("Done")
    np1.fill((0,0,0)); np2.fill((0,0,0)); write_pixels()
