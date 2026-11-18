#!/usr/bin/env bash
# Kenwood VFD visualizer: one-shot installer for Raspberry Pi 3B+
# with a 2.8" ILI9341 + XPT2046 SPI screen (MSP2807).
#
# Usage (from this folder, as your normal user):
#   ./install.sh                 Spotify Connect + Bluetooth, sound out of the headphone jack
#   NO_SPOTIFY=1 ./install.sh    Bluetooth only
#   OUTPUT_CARD=Device ./install.sh   send sound to a USB DAC instead (card name from `aplay -l`)
#   ROTATE=270 ./install.sh      flip the screen the other way up (default 90)
#   SPI_MHZ=48 ./install.sh      faster SPI (default 32; drop back if you see garbage)
#
# Safe to run again after changing options.
set -euo pipefail

OUTPUT_CARD="${OUTPUT_CARD:-Headphones}"
ROTATE="${ROTATE:-90}"
SPI_MHZ="${SPI_MHZ:-32}"
DEVICE_NAME="${DEVICE_NAME:-KENWOOD-VIS}"
NO_SPOTIFY="${NO_SPOTIFY:-0}"

HERE="$(cd "$(dirname "$0")" && pwd)"
APP=/opt/kenwood-vis
RUN_USER="${SUDO_USER:-$USER}"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

if [ "$(id -u)" -eq 0 ] && [ -z "${SUDO_USER:-}" ]; then
  echo "Run this as your normal user (it uses sudo itself), not as root."; exit 1
fi
if [ "$RUN_USER" = "root" ]; then
  echo "Couldn't work out which user to run the visualizer as."; exit 1
fi

if [ -f /boot/firmware/config.txt ]; then CONFIG=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then CONFIG=/boot/config.txt
else echo "Can't find config.txt. Is this Raspberry Pi OS?"; exit 1; fi

if systemctl --user is-active --quiet pipewire 2>/dev/null || pgrep -x pipewire >/dev/null; then
  warn "PipeWire is running (Desktop OS). It grabs Bluetooth audio and will fight BlueALSA."
  warn "Raspberry Pi OS Lite is recommended for this build."
fi

# ── 1. packages ───────────────────────────────────────────────────────
say "Installing packages"
sudo apt-get update
sudo apt-get install -y \
  python3-pygame python3-numpy python3-evdev python3-alsaaudio python3-dbus python3-lgpio \
  alsa-utils bluez bluez-tools bluez-alsa-utils curl

# ── 2. app files ──────────────────────────────────────────────────────
say "Copying the visualizer to $APP"
sudo mkdir -p "$APP"
sudo install -m 0755 "$HERE/kenwood_vis.py" "$HERE/spotify_event.py" "$APP/"
sudo install -m 0644 "$HERE/vfd_font.py" "$APP/"
if [ ! -f /etc/kenwood-vis.json ]; then
  printf '{\n  "bt_name": "%s",\n  "spotify_name": "%s"\n}\n' "$DEVICE_NAME" "$DEVICE_NAME" \
    | sudo tee /etc/kenwood-vis.json >/dev/null
fi
for g in video input audio gpio bluetooth; do
  getent group "$g" >/dev/null && sudo usermod -aG "$g" "$RUN_USER" || true
done

# ── 3. screen + touch overlays ───────────────────────────────────────
say "Enabling the SPI screen and touch in $CONFIG"
sudo cp -n "$CONFIG" "$CONFIG.before-kenwood" || true
sudo sed -i '/# >>> kenwood-vis >>>/,/# <<< kenwood-vis <<</d' "$CONFIG"
sudo tee -a "$CONFIG" >/dev/null <<EOF
# >>> kenwood-vis >>>
[all]
dtparam=spi=on
dtparam=audio=on
# ILI9341 display on SPI0 CE0: DC=GPIO24, RESET=GPIO25
dtoverlay=fbtft,spi0-0,ili9341,bgr,rotate=${ROTATE},dc_pin=24,reset_pin=25,speed=${SPI_MHZ}000000,fps=100
# XPT2046 touch on SPI0 CE1, pen interrupt GPIO17
dtoverlay=ads7846,cs=1,penirq=17,penirq_pull=2,speed=1000000,xohms=100,pmax=255
# <<< kenwood-vis <<<
EOF

# ── 4. audio routing: player -> speakers + loopback ──────────────────
say "Setting up the audio loopback (sound out: $OUTPUT_CARD)"
echo "snd-aloop" | sudo tee /etc/modules-load.d/kenwood-vis.conf >/dev/null
sudo modprobe snd-aloop || true
[ -f /etc/asound.conf ] && sudo cp -n /etc/asound.conf /etc/asound.conf.before-kenwood || true
sed "s/@OUTPUT_CARD@/${OUTPUT_CARD}/g" "$HERE/system/asound.conf" | sudo tee /etc/asound.conf >/dev/null
if ! aplay -l 2>/dev/null | grep -q "\[${OUTPUT_CARD}\]\|: ${OUTPUT_CARD} "; then
  warn "No sound card called '${OUTPUT_CARD}' right now. Cards found:"
  aplay -l 2>/dev/null | grep '^card' || true
  warn "Re-run with OUTPUT_CARD=<name> if sound doesn't come out."
fi
amixer -c "$OUTPUT_CARD" -q sset PCM 0dB 2>/dev/null || amixer -c "$OUTPUT_CARD" -q sset PCM 100% 2>/dev/null || true

# ── 5. Bluetooth speaker ─────────────────────────────────────────────
say "Setting up Bluetooth speaker mode as '$DEVICE_NAME'"
sudo python3 - "$DEVICE_NAME" <<'PY'
import re, sys
path, name = "/etc/bluetooth/main.conf", sys.argv[1]
want = {"General": {"Name": name, "Class": "0x200414", "DiscoverableTimeout": "180",
                    "PairableTimeout": "0", "JustWorksRepairing": "always"},
        "Policy": {"AutoEnable": "true"}}
lines = open(path).read().splitlines()
section, seen = None, set()
for i, line in enumerate(lines):
    m = re.match(r"\s*\[(\w+)\]", line)
    if m:
        section = m.group(1); continue
    m = re.match(r"\s*#?\s*(\w+)\s*=", line)
    if m and section in want and m.group(1) in want[section] and (section, m.group(1)) not in seen:
        lines[i] = f"{m.group(1)} = {want[section][m.group(1)]}"
        seen.add((section, m.group(1)))
for sec, kv in want.items():
    missing = [k for k in kv if (sec, k) not in seen]
    if not missing: continue
    idx = next((i for i, l in enumerate(lines) if l.strip() == f"[{sec}]"), None)
    if idx is None:
        lines += ["", f"[{sec}]"]; idx = len(lines) - 1
    for k in missing:
        lines.insert(idx + 1, f"{k} = {kv[k]}")
open(path, "w").write("\n".join(lines) + "\n")
PY

BLUEALSA_BIN="$(command -v bluealsad || command -v bluealsa || true)"
if [ -z "$BLUEALSA_BIN" ]; then echo "bluez-alsa daemon not found after install"; exit 1; fi
for s in bluealsa.service bluealsad.service bluealsa-aplay.service; do
  sudo systemctl disable --now "$s" 2>/dev/null || true
done
sed "s#@BLUEALSA@#${BLUEALSA_BIN}#" "$HERE/system/kenwood-bluealsa.service" \
  | sudo tee /etc/systemd/system/kenwood-bluealsa.service >/dev/null
sudo install -m 0644 "$HERE/system/kenwood-bluealsa-aplay.service" "$HERE/system/kenwood-bt-agent.service" \
  /etc/systemd/system/

# ── 6. Spotify Connect (raspotify / librespot) ───────────────────────
if [ "$NO_SPOTIFY" != "1" ]; then
  say "Installing Spotify Connect (raspotify). Needs Spotify Premium."
  if ! dpkg -s raspotify >/dev/null 2>&1; then
    curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
  fi
  CONF=/etc/raspotify/conf
  sudo touch "$CONF"
  sudo sed -i '/# >>> kenwood-vis >>>/,/# <<< kenwood-vis <<</d' "$CONF"
  sudo tee -a "$CONF" >/dev/null <<EOF
# >>> kenwood-vis >>>
LIBRESPOT_NAME="${DEVICE_NAME}"
LIBRESPOT_DEVICE_TYPE="avr"
LIBRESPOT_BACKEND="alsa"
LIBRESPOT_DEVICE="kenwood_out"
LIBRESPOT_BITRATE="320"
LIBRESPOT_FORMAT="S16"
LIBRESPOT_ONEVENT="${APP}/spotify_event.py"
# <<< kenwood-vis <<<
EOF
  sudo systemctl enable raspotify
  sudo systemctl restart raspotify || true
fi

# ── 7. visualizer service ────────────────────────────────────────────
say "Installing the visualizer service (runs as $RUN_USER)"
sed "s/@USER@/${RUN_USER}/" "$HERE/system/kenwood-vis.service" \
  | sudo tee /etc/systemd/system/kenwood-vis.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable bluetooth kenwood-bluealsa kenwood-bluealsa-aplay kenwood-bt-agent kenwood-vis
sudo systemctl restart bluetooth || true

say "Done!"
cat <<EOF

Reboot to switch the screen on:   sudo reboot

After the reboot:
  * Spotify: open Spotify on your phone > Devices > pick "${DEVICE_NAME}"
  * Bluetooth: hold your finger on the screen ~1 s > PAIR BT, then pick
    "${DEVICE_NAME}" in your phone's Bluetooth list (3 minute window)
  * Tap the screen to change mode. Hold for brightness / pairing.
  * Touch buttons in the wrong place? Run once:
        sudo systemctl stop kenwood-vis
        sudo python3 ${APP}/kenwood_vis.py --calibrate
        sudo systemctl start kenwood-vis
EOF
