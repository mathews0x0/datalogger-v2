# Wiring Diagram: CJMCU-2812B-8 (WS2812B) to Raspberry Pi

**Note:** WS2812B LEDs are 5V devices. Raspberry Pi GPIO is 3.3V. While strictly required, a Level Shifter is often omitted for small strips/short wires. This diagram assumes "Direct Drive".

## Pinout Mapping

| CJMCU Pin     | Function | Raspberry Pi Pin | Physical Pin #  | Notes                                    |
| :------------ | :------- | :--------------- | :-------------- | :--------------------------------------- |
| **VCC / 5V**  | Power    | 5V Power         | Pin 2 or 4      | Max ~500mA draw for 8 LEDs @ 100% White. |
| **GND**       | Ground   | Ground           | Pin 6, 9, 14... | **CRITICAL:** Must share common ground.  |
| **DI / DIN**  | Data In  | GPIO 18 (PWM0)   | Pin 12          | Requires `rpi_ws281x` / `sudo`.          |
| **DO / DOUT** | Data Out | (Not Connected)  | -               | Only used to chain more strips.          |

## Visual Schematic (Direct Drive)

```text
       Raspberry Pi Zero/3/4 Header
      +-----------------------------+
      |  (1) 3.3V      5V (2)       |---------------------> [ VCC ] CJMCU
      |  (3) SDA       5V (4)       |
      |  (5) SCL      GND (6)       |---------------------> [ GND ] CJMCU
      |  (7) G4       TXD (8)       |
      |  (9) GND      RXD (10)      |
      | (11) G17      G18 (12)      |----[ 470Ω Res ]-----> [ DI  ] CJMCU
      | (13) G27      GND (14)      |
      | ...                         |
      +-----------------------------+
               (Optional 470Ω Resistor helps signal integrity)
```

## Troubleshooting (Flickering / No Color)

1.  **Level Shifter:** If LEDs display random colors or don't light up, the 3.3V signal might be too weak.
    - **Fix:** Use a 74AHCT125 logic shifter.
    - **Hack:** Connect LED VCC to 3.3V (Pin 1)? **NO.** WS2812B needs >3.5V to operate reliably.
    - **Hack:** Put a 1N4001 diode on the LED VCC line (Drops VCC to 4.3V, making 3.3V logic valid).
2.  **Audio Interference:** GPIO 18 is shared with PWM Audio.
    - **Fix:** Add `dtparam=audio=off` to `/boot/config.txt`.
    - **Fix:** Blacklist `snd_bcm2835` in `/etc/modprobe.d/snd-blacklist.conf`.

## Testing

Run the test script:

```bash
sudo python3 src/scripts/test_led_patterns.py
```

_(Must run as root/sudo for direct hardware access)_
