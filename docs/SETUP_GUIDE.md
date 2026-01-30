# Datalogger Complete Setup Guide

**Hardware:** Raspberry Pi Zero 2 W (PCB v2.1)
**OS:** Raspberry Pi OS Lite (Legacy 32-bit recommended for compatibility)

---

## Phase 1: OS Installation (Raspberry Pi Imager)

1.  **Download & Install:** [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2.  **OS Selection:**
    - Click "Choose OS" -> "Raspberry Pi OS (other)" -> **Raspberry Pi OS Lite (Legacy 32-bit)**.
    - _Why Legacy?_ Better compatibility with `rpi_ws281x` and older GPIO libraries.
3.  **Storage:** Select your SD Card.
4.  **Advanced Options (The Gear Icon):**
    - **Hostname:** `datalogger` (or `pi`)
    - **Enable SSH:** Use password authentication.
    - **Username:** `pi`
    - **Password:** `datalogger` (or your choice)
    - **Configure Wireless LAN:**
      - SSID: `Your_WiFi_Name`
      - Password: `Your_WiFi_Password`
      - Country: `US` (or your country)
5.  **Write:** Burn the image and wait for verification.

---

## Phase 2: First Boot & Connection

1.  Insert SD card into Pi and power up.
2.  Wait 2-3 minutes for first boot resizing.
3.  Open Terminal (Windows: PowerShell / CMD).
4.  **Connect via SSH:**
    ```bash
    ssh pi@datalogger.local
    # (Enter password set in Phase 1)
    ```

---

## Phase 3: Transferring Code (SFTP)

SFTP
Natizyskunk

update the sftp.json
put in correct host/user/path
push


---

## Phase 4: Installation & Configuration

1.  **SSH back into the Pi:**

    ```bash
    ssh pi@datalogger.local
    ```

2.  **Navigate to project directory:**

    ```bash
    cd ~/projects/datalogger
    ```

3.  **Make the installer executable:**

    ```bash
    chmod +x install_services.sh
    ```

4.  **Run the Full Installer:**

    ```bash
    ./install_services.sh
    ```

    - **What this does:**
      - Updates `apt` and installs system dependencies (`git`, `python3-pip`, `i2c-tools`).
      - Enables **I2C** and **Serial** (UART) interfaces.
      - Disables `gpsd` (to free UART for our script).
      - Installs all Python libraries (`RPi.GPIO`, `rpi_ws281x`, `luma.oled`, etc.).
      - Creates and enables Systemd Services:
        - `datalogger.service` (Main App)
        - `gpio_buttons.service` (Buttons)
        - `datalogger-api.service` (Web UI/API)

5.  **Reboot:**
    ```bash
    sudo reboot
    ```

---

## Phase 5: Verification

After reboot, wait 30 seconds for services to start.

1.  **Check Services:**

    ```bash
    sudo systemctl status datalogger
    sudo systemctl status gpio_buttons
    ```

    - Both should say `Active: active (running)`.

2.  **Run Hardware Test:**
    Stop the service momentarily to free up the GPIO/Screen:

    ```bash
    sudo systemctl stop datalogger
    sudo python3 src/scripts/verify_pcb_full.py
    ```

    - Follow the on-screen prompts to test Buttons, LEDs, and Display.

3.  **Restart Service:**
    ```bash
    sudo systemctl start datalogger
    ```

**Ready!** The system is now a clone of your working setup.
