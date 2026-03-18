# Running a Pygame Game Solo on a Seeed Studio reTerminal

A step-by-step guide to running a Python/Pygame game as the only application on a reTerminal — no desktop, no distractions.

-----

## Hardware Overview

The reTerminal is based on a **Raspberry Pi Compute Module 4 (CM4)** and includes:

- Quad-Core Cortex-A72 CPU @ 1.5GHz
- 4GB RAM / 32GB eMMC
- 5-inch IPS capacitive touchscreen (1280×720)
- Micro-HDMI output (up to 4K@60fps)
- 4 physical buttons
- Built-in accelerometer, light sensor, RTC
- Wi-Fi 2.4/5GHz + Bluetooth 5.0

-----

## Step 1: Flash the reTerminal System Image

Use **Seeed’s official image** (not stock Raspberry Pi OS) to ensure the internal display drivers are included.

1. Download the latest image from [Seeed’s reTerminal wiki](https://wiki.seeedstudio.com/reTerminal/)
1. Flash it to the eMMC using `rpiboot` and the Raspberry Pi Imager:
- Remove the reTerminal back shell
- Set the boot switch to **USB boot mode**
- Connect via USB-C to your PC
- Flash using Raspberry Pi Imager
1. Reconnect power normally after flashing

-----

## Step 2: Boot to Console (No Desktop)

Skip the desktop environment to free up RAM and CPU for your game.

```bash
sudo raspi-config
```

Navigate to:

```
System Options → Boot / Auto Login → Console Autologin
```

Reboot after saving.

-----

## Step 3: Install Pygame

```bash
sudo apt update
sudo apt install python3-pygame -y
```

Verify the installation:

```bash
python3 -c "import pygame; print(pygame.ver)"
```

-----

## Step 4: Configure the Display

### Option A — Internal 5-inch touchscreen

Use KMS/DRM (recommended for modern Raspberry Pi OS):

```bash
export SDL_VIDEODRIVER=kmsdrm
python3 your_game.py
```

Or target the framebuffer directly:

```bash
export SDL_VIDEODRIVER=fbcon
export SDL_FBDEV=/dev/fb0
python3 your_game.py
```

> **Tip:** If `/dev/fb0` shows a blank screen, try `/dev/fb1` — the internal and HDMI outputs may be swapped depending on what’s connected.

### Option B — External display via micro-HDMI

Connect your monitor or TV to the micro-HDMI port. The HDMI output is typically the default display when connected. Run:

```bash
export SDL_VIDEODRIVER=kmsdrm
python3 your_game.py
```

To turn off the internal backlight and save power when using an external display:

```bash
echo 1 | sudo tee /sys/class/backlight/*/bl_power
```

-----

## Step 5: Handle Input

### Touchscreen

SDL handles touch input natively — no extra configuration needed. Use `pygame.MOUSEBUTTONDOWN` events, which SDL maps from touch events automatically.

### Physical Buttons

The reTerminal has 4 physical buttons accessible as keyboard or GPIO input. Map them in your game:

```python
for event in pygame.event.get():
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_F1:  # adjust key codes to match your buttons
            # handle button press
            pass
```

> Check `/dev/input/` and use `evtest` to identify which key codes your buttons emit.

### Gamepad / USB Controller

USB gamepads are supported via SDL’s joystick API out of the box.

-----

## Step 6: Auto-Launch on Boot

Create a systemd service so your game starts automatically on power-on.

```bash
sudo nano /etc/systemd/system/mygame.service
```

Paste the following (adjust paths and username as needed):

```ini
[Unit]
Description=My Pygame Game
After=multi-user.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/game/your_game.py
Environment="SDL_VIDEODRIVER=kmsdrm"
User=pi
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable mygame.service
sudo systemctl start mygame.service
```

Check status or logs if something goes wrong:

```bash
sudo systemctl status mygame.service
journalctl -u mygame.service -f
```

-----

## Step 7: Audio (Optional)

Audio works via ALSA — no PulseAudio needed. Initialize it in your game:

```python
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
```

Set the default output device if needed:

```bash
sudo nano /etc/asound.conf
```

```
defaults.pcm.card 0
defaults.ctl.card 0
```

-----

## Troubleshooting

|Problem                         |Fix                                                                                                                                   |
|--------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
|Black screen on internal display|Try `SDL_FBDEV=/dev/fb1` or ensure Seeed drivers are installed                                                                        |
|Touch input not working         |Add your user to the `input` group: `sudo usermod -aG input pi`                                                                       |
|Game exits immediately          |Check `journalctl -u mygame.service` for Python errors                                                                                |
|Low frame rate                  |Confirm no desktop is running; check CPU governor: `echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`|
|HDMI output blank               |Ensure monitor is connected **before** boot; check `/boot/config.txt` for `hdmi_force_hotplug=1`                                      |

-----

## Quick Reference

```bash
# Run game on internal screen
SDL_VIDEODRIVER=kmsdrm python3 your_game.py

# Run game on HDMI
SDL_VIDEODRIVER=kmsdrm python3 your_game.py  # same command, HDMI auto-detected

# Turn off internal backlight
echo 1 | sudo tee /sys/class/backlight/*/bl_power

# Enable game service on boot
sudo systemctl enable mygame.service

# View game logs
journalctl -u mygame.service -f
```

-----

*Guide covers the Seeed Studio reTerminal (CM4-based). For the reTerminal DM (10-inch industrial variant), the same approach applies but display device paths may differ.*