# Systemd Service Setup

This document tracks the systemd service definitions and management commands for the Pi Datalogger.

## 1. Power LED Service

**File:** `/etc/systemd/system/power-led.service`
**Description:** Turns on a visual indicator (LED) when the Pi is awake.

```ini
[Unit]
Description=Power Authority LED
DefaultDependencies=no
After=local-fs.target
Before=shutdown.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/pi/bin/power_led_on.py
ExecStop=/usr/bin/python3 /home/pi/bin/power_led_off.py
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

## 2. Logger Service (Main Application)

**File:** `/etc/systemd/system/datalogger.service`
**Description:** Runs the main python logger process.

```ini
[Unit]
Description=Motorcycle Data Logger
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=/home/pi/projects/datalogger
ExecStart=/usr/bin/python3 -m src.main
Restart=always
RestartSec=2
User=root

[Install]
WantedBy=multi-user.target
```

## 3. GPIO Button Service (Input Listener)

**File:** `/etc/systemd/system/gpio_buttons.service`
**Description:** Runs the script to listen for physical button presses.

```ini
[Unit]
Description=GPIO Button Control for Logger and Shutdown
After=network.target

[Service]
Type=simple
# Corrected path to scripts folder
ExecStart=/usr/bin/python3 /home/pi/projects/datalogger/src/scripts/gpio_buttons.py
Restart=always
User=root
WorkingDirectory=/home/pi/projects/datalogger/src

[Install]
WantedBy=multi-user.target
```

## 4. Management Commands

### Install / Update Services

```bash
# 1. Edit/Create files
sudo nano /etc/systemd/system/datalogger.service
sudo nano /etc/systemd/system/gpio_buttons.service

# 2. Reload Systemd to see changes
sudo systemctl daemon-reload

# 3. Enable startup on boot
sudo systemctl enable datalogger.service
sudo systemctl enable gpio_buttons.service
```

### Operational Control

```bash
# Restart Services
sudo systemctl restart datalogger
sudo systemctl restart gpio_buttons

# Check Status (View logs and active state)
systemctl status datalogger
systemctl status gpio_buttons

# View Live Logs
journalctl -u datalogger -f
journalctl -u gpio_buttons -f
journalctl -u datalogger-api -f
```

## 5. Companion App API Service

**File:** `/etc/systemd/system/datalogger-api.service`
**Description:** Runs the Flask Web Server for the UI.

```ini
[Unit]
Description=Datalogger Companion API
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/pi/projects/datalogger
ExecStart=/usr/bin/python3 src/api/server.py
Restart=always
RestartSec=5
# Run as root to share access to output/ directory with the main logger
User=root
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Enable API

```bash
sudo nano /etc/systemd/system/datalogger-api.service
sudo systemctl daemon-reload
sudo systemctl enable datalogger-api.service
sudo systemctl start datalogger-api.service
```
