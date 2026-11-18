# Kenwood-Style Music Visualizer: Project Handoff

> **To Claude:** I'm handing you a project I worked on earlier in other chats. This file has the background, the full version history, what the latest version does, its known gaps, and the full source of the important versions. Read all of it before answering. After the file I'll tell you what I want to do next.

---

## 1. What this project is

A music visualizer that copies the look of the **VFD (vacuum fluorescent display) spectrum analyzer on Kenwood car stereo head units**, mainly the **DPX-5021M** and **DPX-6200M** double-DIN models. That means segmented, glowing, slightly slanted bars, a peak-hold line, and several animated display modes you tap through.

**Target hardware:** Raspberry Pi 3B+ with a **4.3" 800×480 HDMI + USB touch display**. Everything is built for that exact 800×480 screen.

**Audio source (intended):** music streamed to the Pi over **Bluetooth**. The Python version reads audio from an ALSA loopback device (`hw:Loopback,1,0`) and checks the Bluetooth connection with `bluetoothctl info`. The Pi-side audio routing (Bluetooth sink → loopback) is **not** in any of these files.

There are **two separate implementations**:

| | Python / pygame (`visualizer.py`) | Browser HTML / canvas (`kenwood_*.html`) |
|---|---|---|
| Runs | Natively on the Pi (SDL framebuffer `fbcon` → `/dev/fb0`, fullscreen) | In a browser |
| Audio in | `sounddevice` from ALSA loopback, falls back to the default input | Microphone via `getUserMedia` |
| Look | Green VFD with amber and red peaks, scanlines | Latest: 6-colour VFD (blue → cyan → green → yellow → orange → red), slanted segments |
| Modes | 5: Spectrum, Level Meter, Oscilloscope, Combo, Peak Hold | Latest: 7: SPEANA, MAGNET, STADIUM, LASER, SEASHORE, RAIN DROP, VIBROSCOPE |

The browser versions are the newest work. The Python version came first and was never updated to the newer DPX-6200M look.

---

## 2. Latest version: `kenwood_dramatic.html` (2026-04-18 10:21)

Title: **"Kenwood DPX-6200M Dramatic Edition"**. Full source is in section 6A.

**How to use:** open it in a browser. The **first click** starts audio and the browser asks for the microphone. **Each click after that** cycles through the modes.

**How it works:**
- Fixed `800×480` canvas, black background, centred on the page.
- Web Audio `AnalyserNode` with `fftSize = 2048` and `smoothingTimeConstant = 0.8`, fed by the mic.
- **32 bands.** Each band picks a sample from the FFT on a power curve: `sampleIdx = floor((i/BANDS)^1.4 * (bins * 0.7))`.
- Bar height is `(val/255)^1.4 * 420 * 2.8 * (1 + (i/BANDS)*0.5)`, capped at 420 px. The last factor boosts the high bands so they don't look dead.
- Smoothing: rises with a lerp of 0.35 and falls with a lerp of 0.18. Peaks hold for 900 ms, then drop 4 px per frame.
- Segments are 14 px tall with 3 px gaps. Each segment shifts right by `SLANT = 2.8` px to fake the hardware's ~12.5° perspective.
- Segment colour by index: 0–5 blue `#0033FF`, 6–11 cyan `#00F0FF`, 12–17 green `#00FF66`, 18–21 yellow `#FFFF00`, 22–24 orange `#FF9900`, 25+ red `#FF0033`. Everything has a cyan `shadowBlur` glow.
- HUD: a fixed `"BLUETOOTH AUDIO"` label bottom-left, a 24-hour clock bottom-right, and the mode name bottom-centre.

**Modes:**
| Mode | What it draws |
|---|---|
| SPEANA | Standard spectrum bars rising from y=400, with peak lines |
| MAGNET | Half-height bars growing down from the top and up from the bottom |
| STADIUM | Half-height bars mirrored up and down from the centre line |
| LASER | Spectrum, plus full-width horizontal cyan "laser" lines when a band goes over 195 |
| SEASHORE | Spectrum whose baseline moves in a sine wave across the bands |
| RAIN DROP | Short bars (30% height) plus cyan "drops" drawn high up when a band goes over 210 |
| VIBROSCOPE | Smoothed oscilloscope trace (lerp 0.25, `AMP_BOOST = 3.5`), thick cyan line with heavy glow |

**Known gaps and loose ends** (found by reading the code, not by testing):
- The song title is hard-coded as `"BLUETOOTH AUDIO"`. An earlier version (`automotive_custom_vfd.html`, section 6E) read real track info from `navigator.mediaSession` and from a WebSocket at `ws://localhost:8765`, meant for a Python Bluetooth metadata bridge. **That bridge script doesn't exist** in any of the files, and the newest versions dropped the metadata code.
- It listens to the **microphone**, not the Bluetooth audio directly. On the Pi it would need the loopback device set as the default input, or a different way to capture audio.
- The canvas is fixed at 800×480 and doesn't scale to the window.
- There's **no start screen**. The version saved 10 minutes earlier (`kenwood_ultimate_web.html`) had a "TAP TO INITIALIZE AUDIO" overlay; this one shows a black screen until you click.
- There's no error handling if microphone access is denied. `audioCtx` gets created before `getUserMedia` fails, so later clicks only change the mode variable and nothing ever draws.
- The two implementations have drifted apart. The Python version has a long-press brightness slider and a Bluetooth status header; none of the HTML versions have those.

---

## 3. Full version history

All files were in `~/Downloads`. Times are local file save times.

### April 14, 2026: Python original and first browser port
| Time | File | Title / what changed |
|---|---|---|
| 01:08 | `visualizer.py` | **Python/pygame original** for the Pi. 5 modes, 16 bands (20 Hz–22 kHz), long press for brightness, Bluetooth status, scanlines. *(full source in 6C)* |
| 01:29 | `kenwood_visualizer.html` | First browser port of the Python version |
| 01:38–02:09 | `kenwood_visualizer-2.html` … `-11.html` | Repeated revisions of that port (the `-N` suffix comes from downloading the same filename again) |
| 02:13 | `kenwood_visualizer-12.html` | **Most complete version of the first design.** 7 modes: SPECTRUM, LEVEL METER, OSCILLOSCOPE, COMBO, PEAK HOLD, **BASS REACTOR** (8 named bands from SUB to AIR), and **DPX 3D** (cyan, in the DPX-5021M style). Has a demo mode with canned patterns, a MIC IN button, a green/amber VFD theme toggle, and a responsive canvas. *(full source in 6D)* |

### April 14, early morning: new direction, copying the DPX-5021M at 800×480
| Time | File | Title / what changed |
|---|---|---|
| 02:27 | `kenwood_vfd_visualizer.html` | "Kenwood DPX-5021M Visualizer". Started over at a fixed 800×480 with 4 modes: SPEANA, MAGNET, SPARK, AMOEBA |
| 02:33 | `kenwood_tuned_800x480.html` | "DPX-5021M Tuned Simulation", 24 bands |
| 02:36 | `kenwood_liquid_vfd_800x480.html` | "DPX-5021M Liquid VFD", 32 bands |
| 02:38 | `kenwood_dynamic_variation.html` | "DPX-5021M Dynamic VFD" |
| 02:42 | `automotive_custom_vfd.html` | "Custom Automotive VFD Visualizer". **Added track info** from MediaSession plus a WebSocket bridge on port 8765 *(snippet in 6E)* |

### April 14, morning: switched to the DPX-6200M look
| Time | File | Title / what changed |
|---|---|---|
| 09:53 | `kenwood_dpx6200m_absolute_1to1.html` | "DPX-6200M Ultra-High Fidelity". 22 bands, modes SPEANA, MAGNET, STADIUM, AMOEBA, SPARK |
| 09:58 | `kenwood_master_vfd_emulator.html` | "DPX-6200M Master Emulation". 32 bands, 6 modes: SPEANA, MAGNET, STADIUM, LASER, SEASHORE, RAIN DROP |
| 10:15 | `kenwood_absolute_emulation.html` | "DPX-6200M Absolute 1:1 Emulation". **Added VIBROSCOPE**, making the final 7 modes |
| 10:18 | `kenwood_fixed_bands.html` | "…(Fixed High-Bands)". Fixed the high bands, which barely moved |
| 10:23 | `kenwood_styled_sub_spectrum.html` | "…(Styled Sub-Spectrum)" |
| 10:26 | `kenwood_clean_emulation.html` | "DPX-6200M Clean 1:1 Emulation" |
| 10:29 | `kenwood_pure_black_1to1.html` | "DPX-6200M Pure Black 1:1" |

### April 18, 2026: final polish
| Time | File | Title / what changed |
|---|---|---|
| 09:34 | `kenwood_dpx5021m_pro.html` | "DPX-5021M Digital Twin". Went back to the 5021M style: 4 modes, 24 bands |
| 09:35 | `kenwood_deep_black_pure.html` | "DPX-6200M Pure Black 1:1 (No Haze)" |
| 09:36 | `kenwood_dpx6200m_hud_fix.html` | "DPX-6200M Absolute 1:1 HUD Fix". Fixed the clock, title and mode HUD |
| 10:11 | `kenwood_ultimate_web.html` | "Kenwood Next-Gen Web Visualizer". Built from `hud_fix` (its comments say `[cite: uploaded:kenwood_dpx6200m_hud_fix.html]`). Adds a "TAP TO INITIALIZE AUDIO" overlay and a gentler oscilloscope *(snippet in 6B)* |
| 10:21 | `kenwood_dramatic.html` | **"DPX-6200M Dramatic Edition": LATEST.** Same as `ultimate_web` but with no overlay, plus a punchier oscilloscope (`AMP_BOOST = 3.5`, thicker line, more glow) *(full source in 6A)* |

---

## 4. Design ideas that stayed the same across versions

- Make it look like **real VFD hardware**: glowing segments, a black "no haze" background, slanted segments for perspective, and the mode names Kenwood actually uses (SPEANA, MAGNET, STADIUM, LASER, SEASHORE, RAIN DROP, VIBROSCOPE, SPARK, AMOEBA).
- **Make the high bands lively.** Real music has little energy up high, so later versions boost higher bands and use a power-curve bin mapping.
- **Bars rise fast and fall slowly**, with a short peak hold, so it feels like hardware.
- Built for **800×480 and tapping**: one tap goes to the next mode, and there are no other on-screen controls.

---

## 5. Things not done yet

- A real Bluetooth audio and track-info pipeline on the Pi (the WebSocket bridge on 8765 was never written).
- Choosing one implementation for the Pi: pygame (`visualizer.py`) or the HTML version in a fullscreen/kiosk browser.
- Bringing the Python version up to the DPX-6200M look and 7 modes, or bringing its brightness and BT status features to the HTML version.

---

## 6. Source code

### 6A. `kenwood_dramatic.html`: LATEST (2026-04-18 10:21)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Kenwood DPX-6200M Dramatic Edition</title>
    <style>
        body {
            background: #000;
            margin: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            overflow: hidden;
            font-family: 'Courier New', Courier, monospace;
            cursor: pointer;
        }
        canvas {
            background: #000;
            image-rendering: pixelated;
        }
    </style>
</head>
<body>
    <canvas id="vfd" width="800" height="480"></canvas>
<script>
    const canvas = document.getElementById('vfd');
    const ctx = canvas.getContext('2d');
    let audioCtx, analyser, dataArray, timeDataArray;
    let mode = 0;
    const modes = ['SPEANA', 'MAGNET', 'STADIUM', 'LASER', 'SEASHORE', 'RAIN DROP', 'VIBROSCOPE'];
    const BANDS = 32;
    const BAR_GAP = 2;
    const BAR_WIDTH = (800 / BANDS) - BAR_GAP;
    const SEG_H = 14;
    const SEG_GAP = 3;
    const SLANT = 2.8; 
    const PEAK_HOLD_MS = 900;
    const LERP_UP = 0.35;
    const LERP_DOWN = 0.18;
    const AMP_BOOST = 3.5; 
    let currentHeights = new Array(BANDS).fill(0);
    let peaks = new Array(BANDS).fill(0);
    let peakTimes = new Array(BANDS).fill(0);
    let waveSmooth = new Array(1024).fill(128); 
    let songTitle = "BLUETOOTH AUDIO";
    const vfdColors = ["#0033FF", "#00F0FF", "#00FF66", "#FFFF00", "#FF9900", "#FF0033"];
    function getVFDColor(s) {
        if (s < 6) return vfdColors[0];
        if (s < 12) return vfdColors[1];
        if (s < 18) return vfdColors[2];
        if (s < 22) return vfdColors[3];
        if (s < 25) return vfdColors[4];
        return vfdColors[5];
    }
    document.body.addEventListener('click', async () => {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const source = audioCtx.createMediaStreamSource(stream);
            analyser = audioCtx.createAnalyser();
            analyser.fftSize = 2048;
            analyser.smoothingTimeConstant = 0.8;
            source.connect(analyser);
            dataArray = new Uint8Array(analyser.frequencyBinCount);
            timeDataArray = new Uint8Array(analyser.frequencyBinCount);
            draw();
        } else {
            mode = (mode + 1) % modes.length;
        }
    });
    function drawUI() {
        ctx.shadowBlur = 0;
        ctx.fillStyle = "#00F0FF";
        ctx.shadowBlur = 10;
        ctx.shadowColor = "#00F0FF";
        ctx.font = "bold 20px monospace";
        ctx.textAlign = "left";
        ctx.fillText(songTitle, 20, 450);
        const now = new Date();
        const timeStr = now.getHours().toString().padStart(2, '0') + ":" + now.getMinutes().toString().padStart(2, '0');
        ctx.textAlign = "right";
        ctx.fillText(timeStr, 780, 450);
        ctx.textAlign = "center";
        ctx.font = "bold 14px monospace";
        ctx.fillText(modes[mode], 400, 470);
    }
    function draw() {
        requestAnimationFrame(draw);
        analyser.getByteFrequencyData(dataArray);
        analyser.getByteTimeDomainData(timeDataArray);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        drawUI();
        if (modes[mode] === 'VIBROSCOPE') {
            renderDramaticOscilloscope();
            return;
        }
        for (let i = 0; i < BANDS; i++) {
            const sampleIdx = Math.floor(Math.pow(i / BANDS, 1.4) * (dataArray.length * 0.7));
            let val = dataArray[sampleIdx];
            let targetH = (val / 255) ** 1.4 * 420 * 2.8 * (1 + (i / BANDS) * 0.5);
            if (targetH > 420) targetH = 420;
            let lerp = (targetH > currentHeights[i]) ? LERP_UP : LERP_DOWN;
            currentHeights[i] += (targetH - currentHeights[i]) * lerp;
            if (currentHeights[i] > peaks[i]) {
                peaks[i] = currentHeights[i];
                peakTimes[i] = Date.now();
            } else if (Date.now() - peakTimes[i] > PEAK_HOLD_MS) {
                peaks[i] -= 4;
            }
            const x = i * (BAR_WIDTH + BAR_GAP);
            const centerY = 240;
            switch(modes[mode]) {
                case 'SPEANA': renderVFD(x, 400, currentHeights[i], peaks[i], true); break;
                case 'MAGNET': renderVFD(x, 60, currentHeights[i]/2, -1, false); renderVFD(x, 400, currentHeights[i]/2, -1, true); break;
                case 'STADIUM': renderVFD(x, centerY, currentHeights[i]/2, -1, false); renderVFD(x, centerY, currentHeights[i]/2, -1, true); break;
                case 'LASER': 
                    if (val > 195) { ctx.fillStyle = vfdColors[1]; ctx.shadowBlur = 25; ctx.fillRect(0, 400 - (i*12), 800, 2); }
                    renderVFD(x, 400, currentHeights[i], peaks[i], true); 
                    break;
                case 'SEASHORE': renderVFD(x, 400 + Math.sin(Date.now()/400 + i/4) * 45, currentHeights[i], peaks[i], true); break;
                case 'RAIN DROP':
                    if (val > 210) { ctx.fillStyle = vfdColors[1]; ctx.fillRect(x, (1 - (val/255)) * 400, BAR_WIDTH, 5); }
                    renderVFD(x, 400, currentHeights[i]*0.3, -1, true);
                    break;
            }
        }
    }
    function renderDramaticOscilloscope() {
        ctx.strokeStyle = "#00F0FF";
        ctx.lineWidth = 4;
        ctx.shadowBlur = 25;
        ctx.shadowColor = "#00F0FF";
        ctx.beginPath();
        const sliceWidth = canvas.width / timeDataArray.length;
        let x = 0;
        for (let i = 0; i < timeDataArray.length; i++) {
            waveSmooth[i] += (timeDataArray[i] - waveSmooth[i]) * 0.25;
            let deviation = (waveSmooth[i] - 128) * AMP_BOOST;
            const y = (canvas.height / 2) + deviation;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
            x += sliceWidth;
        }
        ctx.stroke();
    }
    function renderVFD(x, baselineY, height, peak, up = true) {
        const numSegments = Math.floor(height / (SEG_H + SEG_GAP));
        const peakSegment = Math.floor(peak / (SEG_H + SEG_GAP));
        ctx.shadowBlur = 12;
        ctx.shadowColor = "#00F0FF";
        for (let s = 0; s < numSegments; s++) {
            const xOff = s * SLANT;
            let y = up ? baselineY - (s * (SEG_H + SEG_GAP)) : baselineY + (s * (SEG_H + SEG_GAP));
            ctx.fillStyle = getVFDColor(s);
            ctx.fillRect(x + xOff, y, BAR_WIDTH, SEG_H);
        }
        if (peak > 0) {
            const pxOff = peakSegment * SLANT;
            let py = up ? baselineY - (peakSegment * (SEG_H + SEG_GAP)) : baselineY + (peakSegment * (SEG_H + SEG_GAP));
            ctx.fillStyle = vfdColors[1];
            ctx.fillRect(x + pxOff, py, BAR_WIDTH, 2);
        }
    }
</script>
</body>
</html>
```

### 6B. `kenwood_ultimate_web.html`: how it differs from 6A

It's the same as 6A apart from these parts.

Start overlay (CSS + HTML), hidden on the first click with `overlay.style.display = 'none'`:
```html
<style>
#overlay {
    position: absolute;
    color: #00F0FF;
    font-size: 24px;
    text-align: center;
    pointer-events: none;
    text-shadow: 0 0 10px #00F0FF;
}
</style>
<div id="overlay">TAP TO INITIALIZE AUDIO<br><span style="font-size:14px; opacity:0.7">KENWOOD DPX-6200M EMULATION</span></div>
```

Gentler oscilloscope, used in place of `renderDramaticOscilloscope()`:
```js
function renderSmoothOscilloscope() {
    ctx.strokeStyle = "#00F0FF";
    ctx.lineWidth = 3;
    ctx.shadowBlur = 15;
    ctx.shadowColor = "#00F0FF";
    ctx.beginPath();

    const sliceWidth = canvas.width / timeDataArray.length;
    let x = 0;

    for (let i = 0; i < timeDataArray.length; i++) {
        // Smooth wave LERP to prevent motion sickness
        waveSmooth[i] += (timeDataArray[i] - waveSmooth[i]) * 0.2;
        const v = waveSmooth[i] / 128.0;
        const y = v * canvas.height / 2;

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);

        x += sliceWidth;
    }
    ctx.stroke();
}
```

### 6C. `visualizer.py`: Python/pygame original for the Raspberry Pi (2026-04-14 01:08)

Dependencies: `pygame`, `numpy`, `sounddevice`. It needs the ALSA loopback device for Bluetooth audio, and `bluetoothctl` for the status header.

```python
#!/usr/bin/env python3
"""
Kenwood-Style Music Visualizer — Full Multi-Mode Edition
=========================================================
Raspberry Pi 3B+ + 4.3" 800×480 HDMI+USB Touch Display

Modes (tap screen to cycle):
  1. Spectrum Analyzer  — 16-band segmented bars, green→amber→red
  2. Level Meter        — L/R VU bars with dB scale, peak hold
  3. Oscilloscope       — Waveform trace with phosphor glow trail
  4. Spectrum + Level   — Split screen combo
  5. Peak Hold          — Spectrum with slow-falling peak blocks

Touch:
  Short tap   → next mode (with name overlay animation)
  Hold 1.5s   → brightness slider (tap to set, tap again to dismiss)
  Keyboard    → SPACE cycles modes, ESC quits (for dev)
"""

import pygame
import numpy as np
import sounddevice as sd
import threading
import queue
import time
import subprocess
import os
from enum import Enum
from collections import deque

# ── DISPLAY ───────────────────────────────────────────────────────
SCREEN_W = 800
SCREEN_H = 480
FPS      = 30

# ── AUDIO ─────────────────────────────────────────────────────────
SAMPLE_RATE     = 44100
BLOCK_SIZE      = 2048
LOOPBACK_DEVICE = "hw:Loopback,1,0"

# ── SPECTRUM ──────────────────────────────────────────────────────
NUM_BANDS  = 16
NUM_SEGS   = 22
SMOOTHING  = 0.74
PEAK_HOLD  = 52          # frames
PEAK_FALL  = 0.022

BAND_EDGES  = [20,40,63,100,160,250,400,630,1000,1600,2500,4000,6300,10000,14000,18000,22000]
FREQ_LABELS = ["20","40","63","100","160","250","400","630",
               "1k","1.6k","2.5k","4k","6.3k","10k","14k","18k"]

# ── VU METER ──────────────────────────────────────────────────────
VU_SEGS      = 28
VU_ATK       = 0.18      # fast attack
VU_DCY       = 0.91      # slow decay
VU_PEAK_HOLD = 65

# ── OSCILLOSCOPE ──────────────────────────────────────────────────
OSC_HISTORY = 6           # phosphor trail frames
OSC_SAMPLES = 600

# ── PEAK HOLD MODE ────────────────────────────────────────────────
PH_HOLD  = 130            # frames (~4.3s)
PH_FALL  = 0.006

# ── COLORS ────────────────────────────────────────────────────────
C_BG       = (3,   8,   4)
C_OFF      = (6,   20,  10)
C_DIM      = (0,   45,  18)
C_GREEN    = (0,   210, 75)
C_GREEN_D  = (0,   140, 50)
C_GREEN_DD = (0,   60,  25)
C_AMBER    = (255, 125, 0)
C_RED      = (240, 25,  10)
C_PEAK_COL = (255, 55,  0)
C_LABEL    = (0,   120, 45)
C_HEADER   = (10,  10,  10)
C_GRID     = (0,   28,  12)


# ─────────────────────────────────────────────────────────────────
class Mode(Enum):
    SPECTRUM  = 0
    LEVEL     = 1
    SCOPE     = 2
    COMBO     = 3
    PEAKHOLD  = 4

MODE_NAMES = {
    Mode.SPECTRUM: "SPECTRUM ANALYZER",
    Mode.LEVEL:    "LEVEL METER",
    Mode.SCOPE:    "OSCILLOSCOPE",
    Mode.COMBO:    "SPECTRUM + LEVEL",
    Mode.PEAKHOLD: "PEAK HOLD",
}

MODES = list(Mode)


# ── HELPERS ───────────────────────────────────────────────────────
def seg_color(idx, total):
    """Vertical segment color — idx=0 bottom, idx=total-1 top."""
    p = idx / max(total - 1, 1)
    if p >= 0.86: return C_RED
    if p >= 0.68: return C_AMBER
    return C_GREEN

def vu_color(idx, total):
    """Horizontal VU segment color — idx=0 left/quiet."""
    p = idx / max(total - 1, 1)
    if p >= 0.87: return C_RED
    if p >= 0.70: return C_AMBER
    return C_GREEN

def hi(color, amt=55):
    return tuple(min(255, c + amt) for c in color)

def dim(color, f=0.15):
    return tuple(int(c * f) for c in color)


# ── AUDIO ENGINE ──────────────────────────────────────────────────
class AudioEngine:
    def __init__(self):
        self.levels   = np.zeros(NUM_BANDS)
        self.vu       = np.zeros(2)
        self.waveform = np.zeros(OSC_SAMPLES)

        self._raw_lv   = np.zeros(NUM_BANDS)
        self._raw_vu   = np.zeros(2)
        self._raw_wave = np.zeros(OSC_SAMPLES)
        self._lock     = threading.Lock()
        self._q        = queue.Queue(maxsize=4)
        self._running  = False
        self._stream   = None

        self._freqs  = np.fft.rfftfreq(BLOCK_SIZE, 1.0 / SAMPLE_RATE)
        self._window = np.hanning(BLOCK_SIZE)
        self._masks  = [
            (self._freqs >= BAND_EDGES[i]) & (self._freqs < BAND_EDGES[i + 1])
            for i in range(NUM_BANDS)
        ]

    def _cb(self, indata, frames, t, status):
        if self._q.full():
            try: self._q.get_nowait()
            except: pass
        self._q.put(indata.copy())

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        for dev, ch in [(LOOPBACK_DEVICE, 2), (None, 2), (None, 1)]:
            try:
                self._stream = sd.InputStream(
                    device=dev, samplerate=SAMPLE_RATE, channels=ch,
                    blocksize=BLOCK_SIZE, callback=self._cb, dtype='float32'
                )
                self._stream.start()
                print(f"[Audio] device={dev or 'default'}  ch={ch}")
                return
            except Exception as e:
                print(f"[Audio] skip {dev} ch={ch}: {e}")
        print("[Audio] WARNING: no audio device found")

    def _loop(self):
        while self._running:
            try:
                data = self._q.get(timeout=0.1)
            except queue.Empty:
                continue

            if data.ndim == 1 or data.shape[1] == 1:
                left = right = data.flatten()
            else:
                left, right = data[:, 0], data[:, 1]
            mono = (left + right) * 0.5

            # Waveform
            n    = min(len(mono), OSC_SAMPLES)
            wave = mono[:n]
            if n < OSC_SAMPLES:
                wave = np.pad(wave, (0, OSC_SAMPLES - n))

            # FFT
            m = mono[:BLOCK_SIZE] if len(mono) >= BLOCK_SIZE \
                else np.pad(mono, (0, BLOCK_SIZE - len(mono)))
            mag = np.abs(np.fft.rfft(m * self._window)) / BLOCK_SIZE

            raw = np.zeros(NUM_BANDS)
            for i, mask in enumerate(self._masks):
                if np.any(mask):
                    rms     = np.sqrt(np.mean(mag[mask] ** 2))
                    raw[i]  = float(np.clip(rms / 0.25, 0, 1) ** 0.65)

            vu_l = float(np.clip(np.sqrt(np.mean(left  ** 2)) / 0.3, 0, 1) ** 0.5)
            vu_r = float(np.clip(np.sqrt(np.mean(right ** 2)) / 0.3, 0, 1) ** 0.5)

            with self._lock:
                self._raw_lv   = raw
                self._raw_vu   = np.array([vu_l, vu_r])
                self._raw_wave = wave

    def update(self):
        with self._lock:
            raw, vu_raw, wave = self._raw_lv.copy(), self._raw_vu.copy(), self._raw_wave.copy()
        self.levels   = self.levels * SMOOTHING + raw * (1 - SMOOTHING)
        self.waveform = wave
        for i in range(2):
            if vu_raw[i] > self.vu[i]:
                self.vu[i] = self.vu[i] * (1 - VU_ATK) + vu_raw[i] * VU_ATK
            else:
                self.vu[i] = self.vu[i] * VU_DCY + vu_raw[i] * (1 - VU_DCY)

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()


# ── BLUETOOTH ─────────────────────────────────────────────────────
class BTStatus:
    def __init__(self):
        self.connected   = False
        self.device_name = ""
        self._last       = 0

    def update(self):
        if time.time() - self._last < 3:
            return
        self._last = time.time()
        try:
            out = subprocess.check_output(
                ["bluetoothctl", "info"], stderr=subprocess.DEVNULL, timeout=1
            ).decode()
            self.connected = "Connected: yes" in out
            for line in out.splitlines():
                if "Name:" in line:
                    self.device_name = line.split("Name:")[-1].strip()[:18]
                    break
            if not self.connected:
                self.device_name = ""
        except:
            self.connected = False


# ── VISUALIZER ────────────────────────────────────────────────────
class Visualizer:
    HEADER_H = 28
    FOOTER_H = 24

    def __init__(self, screen):
        self.scr        = screen
        self.W, self.H  = SCREEN_W, SCREEN_H
        self.brightness = 1.0

        self.viz_y = self.HEADER_H + 2
        self.viz_h = self.H - self.HEADER_H - self.FOOTER_H - 4

        # Spectrum / Peak Hold state
        self.sp_peaks  = np.zeros(NUM_BANDS)
        self.sp_timers = np.zeros(NUM_BANDS, dtype=int)
        self.ph_peaks  = np.zeros(NUM_BANDS)
        self.ph_timers = np.zeros(NUM_BANDS, dtype=int)

        # VU state
        self.vu_peaks  = np.zeros(2)
        self.vu_timers = np.zeros(2, dtype=int)

        # Oscilloscope
        self.osc_hist = deque(maxlen=OSC_HISTORY)

        # Fonts
        pygame.font.init()
        self.f_xs  = pygame.font.SysFont("monospace", 10, bold=True)
        self.f_sm  = pygame.font.SysFont("monospace", 12, bold=True)
        self.f_md  = pygame.font.SysFont("monospace", 15, bold=True)
        self.f_lg  = pygame.font.SysFont("monospace", 20, bold=True)
        self.f_xl  = pygame.font.SysFont("monospace", 30, bold=True)

        # Pre-baked scanlines
        self._scanlines = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        for y in range(0, self.H, 3):
            pygame.draw.rect(self._scanlines, (0, 0, 0, 42), (0, y, self.W, 1))

    # ── Peak state updates ─────────────────────────────────────────
    def tick_sp_peaks(self, lv):
        for i in range(NUM_BANDS):
            if lv[i] >= self.sp_peaks[i]:
                self.sp_peaks[i], self.sp_timers[i] = lv[i], PEAK_HOLD
            else:
                if self.sp_timers[i] > 0: self.sp_timers[i] -= 1
                else: self.sp_peaks[i] = max(0, self.sp_peaks[i] - PEAK_FALL)

    def tick_ph_peaks(self, lv):
        for i in range(NUM_BANDS):
            if lv[i] >= self.ph_peaks[i]:
                self.ph_peaks[i], self.ph_timers[i] = lv[i], PH_HOLD
            else:
                if self.ph_timers[i] > 0: self.ph_timers[i] -= 1
                else: self.ph_peaks[i] = max(0, self.ph_peaks[i] - PH_FALL)

    def tick_vu_peaks(self, vu):
        for i in range(2):
            if vu[i] >= self.vu_peaks[i]:
                self.vu_peaks[i], self.vu_timers[i] = vu[i], VU_PEAK_HOLD
            else:
                if self.vu_timers[i] > 0: self.vu_timers[i] -= 1
                else: self.vu_peaks[i] = max(0, self.vu_peaks[i] - 0.012)

    # ── Shared UI ──────────────────────────────────────────────────
    def draw_header(self, mode, bt):
        scr = self.scr
        pygame.draw.rect(scr, C_HEADER, (0, 0, self.W, self.HEADER_H))
        pygame.draw.line(scr, (22, 22, 22), (0, self.HEADER_H), (self.W, self.HEADER_H))

        b = self.f_lg.render("KENWOOD", True, C_GREEN)
        scr.blit(b, (14, (self.HEADER_H - b.get_height()) // 2))

        mn = self.f_sm.render(MODE_NAMES[mode], True, (48, 48, 48))
        scr.blit(mn, (110, (self.HEADER_H - mn.get_height()) // 2 + 1))

        # BT dot + name
        bx   = self.W - 185
        col  = C_GREEN if bt.connected else (42, 42, 42)
        pygame.draw.circle(scr, col, (bx, self.HEADER_H // 2), 5)
        if bt.connected:
            pygame.draw.circle(scr, dim(C_GREEN, 0.35),
                               (bx, self.HEADER_H // 2), 9, 1)
        name = bt.device_name if bt.connected else "WAITING"
        bt_t = self.f_sm.render(name, True, col)
        scr.blit(bt_t, (bx + 12, (self.HEADER_H - bt_t.get_height()) // 2 + 1))

    def draw_footer(self, mode):
        scr  = self.scr
        fy   = self.H - self.FOOTER_H
        pygame.draw.rect(scr, (7, 7, 7), (0, fy, self.W, self.FOOTER_H))
        pygame.draw.line(scr, (18, 18, 18), (0, fy), (self.W, fy))

        spacing = self.W // (len(MODES) + 1)
        for i, m in enumerate(MODES):
            cx = spacing * (i + 1)
            cy = fy + self.FOOTER_H // 2
            active = (m == mode)
            if active:
                pygame.draw.circle(scr, C_GREEN, (cx, cy), 5)
                t = self.f_xs.render(MODE_NAMES[m], True, C_LABEL)
                scr.blit(t, (cx - t.get_width() // 2,
                             cy - self.FOOTER_H // 2 + 1))
            else:
                pygame.draw.circle(scr, (28, 28, 28), (cx, cy), 3)

    def draw_scanlines(self):
        self.scr.blit(self._scanlines, (0, 0))

    def apply_brightness(self):
        if self.brightness < 1.0:
            s = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            s.fill((0, 0, 0, int((1.0 - self.brightness) * 255)))
            self.scr.blit(s, (0, 0))

    # ── Internal drawing helpers ───────────────────────────────────
    def _grid(self):
        for i in range(1, 4):
            y = self.viz_y + int(self.viz_h * i / 4)
            pygame.draw.line(self.scr, C_GRID, (50, y), (self.W - 8, y), 1)

    def _db_scale(self, rx, ry, rw, rh):
        for lbl, pos in [("+6",0.0),("0",0.25),("-6",0.5),("-12",0.70),("-20",0.88)]:
            y  = int(ry + pos * rh)
            t  = self.f_xs.render(lbl, True, (0, 65, 28))
            self.scr.blit(t, (rx - t.get_width() - 5,
                               y - t.get_height() // 2))

    def _spec_bars(self, levels, peaks, rx, ry, rw, rh, ns=None):
        scr = self.scr
        ns  = ns or NUM_SEGS
        bw  = rw / NUM_BANDS
        sh  = rh / ns
        sg  = sh * 0.20
        sf  = sh - sg
        bgp = bw * 0.18

        for b in range(NUM_BANDS):
            lv   = levels[b]
            pk   = peaks[b]
            lit  = int(round(lv * ns))
            pseg = min(int(round(pk * ns)), ns - 1)
            x    = rx + b * bw + bgp / 2
            bfw  = bw - bgp

            for s in range(ns):
                si  = ns - 1 - s
                y   = ry + s * sh + sg / 2
                r   = (int(x), int(y), int(bfw), int(sf))
                if si < lit:
                    col = seg_color(si, ns)
                    pygame.draw.rect(scr, col, r)
                    pygame.draw.rect(scr, hi(col, 50), (r[0], r[1], r[2], 2))
                elif si == pseg and pseg > 0:
                    pygame.draw.rect(scr, C_PEAK_COL, r)
                else:
                    pygame.draw.rect(scr, C_OFF, r)

        for b in range(NUM_BANDS):
            lx = rx + b * bw + bw / 2
            t  = self.f_xs.render(FREQ_LABELS[b], True, C_LABEL)
            scr.blit(t, (int(lx - t.get_width() // 2), int(ry + rh + 3)))

    # ── Mode renderers ─────────────────────────────────────────────
    def draw_spectrum(self, lv):
        scr = self.scr
        scr.fill(C_BG)
        self._grid()
        pad_b = 18
        rx, ry = 52, self.viz_y + 4
        rw, rh = self.W - 60, self.viz_h - pad_b - 6
        self._spec_bars(lv, self.sp_peaks, rx, ry, rw, rh)
        self._db_scale(rx, ry, rw, rh)

    def draw_peakhold(self, lv):
        """Like spectrum but bars are dimmed, peak blocks are bright + outlined."""
        scr = self.scr
        scr.fill(C_BG)
        self._grid()
        pad_b = 18
        rx, ry = 52, self.viz_y + 4
        rw, rh = self.W - 60, self.viz_h - pad_b - 6
        ns  = NUM_SEGS
        bw  = rw / NUM_BANDS
        sh  = rh / ns
        sg  = sh * 0.20
        sf  = sh - sg
        bgp = bw * 0.18

        for b in range(NUM_BANDS):
            lit  = int(round(lv[b] * ns))
            pseg = min(int(round(self.ph_peaks[b] * ns)), ns - 1)
            x    = rx + b * bw + bgp / 2
            bfw  = bw - bgp

            for s in range(ns):
                si  = ns - 1 - s
                y   = ry + s * sh + sg / 2
                r   = (int(x), int(y), int(bfw), int(sf))
                if si < lit:
                    col = seg_color(si, ns)
                    pygame.draw.rect(scr, dim(col, 0.45), r)  # dim active bars
                elif si == pseg and pseg > 0:
                    col = seg_color(si, ns)
                    pygame.draw.rect(scr, col, r)
                    # Bright outline top+bottom = "block" feel
                    pygame.draw.rect(scr, hi(col, 90), (r[0], r[1], r[2], 2))
                    pygame.draw.rect(scr, hi(col, 90), (r[0], r[1]+int(sf)-2, r[2], 2))
                else:
                    pygame.draw.rect(scr, C_OFF, r)

        for b in range(NUM_BANDS):
            lx = rx + b * bw + bw / 2
            t  = self.f_xs.render(FREQ_LABELS[b], True, C_LABEL)
            scr.blit(t, (int(lx - t.get_width() // 2), int(ry + rh + 3)))
        self._db_scale(rx, ry, rw, rh)

    def draw_level_meter(self, vu):
        scr = self.scr
        scr.fill(C_BG)

        bar_h   = int(self.viz_h * 0.28)
        bar_gap = int(self.viz_h * 0.09)
        total_h = bar_h * 2 + bar_gap
        start_y = self.viz_y + (self.viz_h - total_h) // 2
        pad_l   = 68
        pad_r   = 30
        bar_w   = self.W - pad_l - pad_r

        # dB reference marks
        db_marks = [
            (-30, 0.0), (-20, 0.17), (-10, 0.40), (-7, 0.52),
            (-5, 0.60), (-3, 0.68), (0, 0.77), (+3, 0.88), (+6, 1.0)
        ]

        for ch_idx, ch_name in enumerate(["L", "R"]):
            by    = start_y + ch_idx * (bar_h + bar_gap)
            level = vu[ch_idx]
            peak  = self.vu_peaks[ch_idx]

            # Channel label
            lbl = self.f_xl.render(ch_name, True, C_GREEN_D)
            scr.blit(lbl, (14, by + (bar_h - lbl.get_height()) // 2))

            sw  = bar_w / VU_SEGS
            sg  = sw * 0.12
            sf  = sw - sg
            lit = int(round(level * VU_SEGS))
            pks = min(int(round(peak * VU_SEGS)), VU_SEGS - 1)

            for s in range(VU_SEGS):
                sx  = pad_l + s * sw
                col = vu_color(s, VU_SEGS)
                r   = (int(sx), int(by), int(sf), int(bar_h))
                if s < lit:
                    pygame.draw.rect(scr, col, r)
                    pygame.draw.rect(scr, hi(col, 50), (r[0], r[1], r[2], 3))
                elif s == pks and pks > 0:
                    pygame.draw.rect(scr, C_PEAK_COL, r)
                else:
                    pygame.draw.rect(scr, C_OFF, r)

        # dB scale between the two bars
        scale_y = start_y + bar_h + bar_gap // 2
        for db, pos in db_marks:
            sx = pad_l + int(pos * bar_w)
            t  = self.f_xs.render(str(db), True, C_LABEL)
            scr.blit(t, (sx - t.get_width() // 2,
                         scale_y - t.get_height() // 2))
            pygame.draw.line(scr, C_GREEN_DD,
                             (sx, start_y + bar_h - 5),
                             (sx, start_y + bar_h), 1)
            pygame.draw.line(scr, C_GREEN_DD,
                             (sx, start_y + bar_h + bar_gap),
                             (sx, start_y + bar_h + bar_gap + 5), 1)

        # VU label top-right
        vu_t = self.f_md.render("VU", True, (28, 28, 28))
        scr.blit(vu_t, (self.W - 32 - vu_t.get_width(),
                        start_y + bar_h // 2 - vu_t.get_height() // 2))

    def draw_oscilloscope(self, wave):
        scr = self.scr
        scr.fill((2, 5, 3))

        self.osc_hist.append(wave.copy())

        mid_y = self.viz_y + self.viz_h // 2
        scale = self.viz_h * 0.40
        x0, x1 = 44, self.W - 10
        viz_w  = x1 - x0

        # Grid
        for i in range(1, 4):
            gy = self.viz_y + int(self.viz_h * i / 4)
            pygame.draw.line(scr, (0, 22, 9), (x0, gy), (x1, gy), 1)
        for i in range(1, 9):
            gx = x0 + int(viz_w * i / 8)
            pygame.draw.line(scr, (0, 22, 9), (gx, self.viz_y),
                             (gx, self.viz_y + self.viz_h), 1)
        # Centre line (brighter)
        pygame.draw.line(scr, (0, 42, 18), (x0, mid_y), (x1, mid_y), 1)

        # Axis labels
        scr.blit(self.f_xs.render("AMPL", True, C_LABEL),
                 (2, mid_y - 6))
        scr.blit(self.f_xs.render("TIME →", True, C_LABEL),
                 (x1 - 56, self.viz_y + self.viz_h - 14))

        # Phosphor traces (oldest → dimmest)
        hist    = list(self.osc_hist)
        n_hist  = len(hist)
        for hi_idx, w in enumerate(hist):
            if len(w) < 2:
                continue
            is_current = (hi_idx == n_hist - 1)
            pts = []
            for i in range(min(len(w), OSC_SAMPLES)):
                px = x0 + int(i / (OSC_SAMPLES - 1) * viz_w)
                py = int(mid_y - w[i] * scale)
                py = max(self.viz_y, min(self.viz_y + self.viz_h, py))
                pts.append((px, py))
            if len(pts) < 2:
                continue
            if is_current:
                pygame.draw.lines(scr, C_GREEN, False, pts, 2)
                # Glow: draw again thicker at lower alpha via extra surface
                gsurf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
                pygame.draw.lines(gsurf, (*C_GREEN, 35), False, pts, 5)
                scr.blit(gsurf, (0, 0))
            else:
                decay = ((hi_idx + 1) / n_hist) ** 2.2
                col   = (0, int(90 * decay), int(38 * decay))
                pygame.draw.lines(scr, col, False, pts, 1)

    def draw_combo(self, lv, vu):
        """Top 58%: spectrum. Bottom 42%: dual VU."""
        scr = self.scr
        scr.fill(C_BG)

        # ── Spectrum (top) ──
        spec_h  = int(self.viz_h * 0.56)
        rx, ry  = 52, self.viz_y + 2
        rw, rh  = self.W - 60, spec_h - 16
        self._grid()
        self._spec_bars(lv, self.sp_peaks, rx, ry, rw, rh, ns=14)
        self._db_scale(rx, ry, rw, rh)

        # Divider
        div_y = self.viz_y + spec_h
        pygame.draw.line(scr, (18, 48, 22), (0, div_y), (self.W, div_y), 1)

        # ── VU (bottom) ──
        vu_y    = div_y + 4
        vu_h    = self.H - self.FOOTER_H - vu_y - 4
        bh      = max(12, int(vu_h * 0.34))
        bg      = int(vu_h * 0.14)
        pad_l   = 46
        bw      = self.W - pad_l - 14
        sc      = 22    # segment count in combo mode

        for ch_idx, ch_name in enumerate(["L", "R"]):
            by    = vu_y + ch_idx * (bh + bg) + 2
            level = vu[ch_idx]
            peak  = self.vu_peaks[ch_idx]

            lbl = self.f_md.render(ch_name, True, C_GREEN_D)
            scr.blit(lbl, (10, by + (bh - lbl.get_height()) // 2))

            sw  = bw / sc
            sf  = sw - sw * 0.12
            lit = int(round(level * sc))
            pks = min(int(round(peak * sc)), sc - 1)

            for s in range(sc):
                sx  = pad_l + s * sw
                col = vu_color(s, sc)
                r   = (int(sx), int(by), int(sf), int(bh))
                if s < lit:
                    pygame.draw.rect(scr, col, r)
                elif s == pks and pks > 0:
                    pygame.draw.rect(scr, C_PEAK_COL, r)
                else:
                    pygame.draw.rect(scr, C_OFF, r)

    # ── Overlay: mode label ────────────────────────────────────────
    def draw_mode_label(self, name, alpha):
        surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        t    = self.f_xl.render(name, True, (0, 0, 0))
        tw   = t.get_width() + 70
        th   = t.get_height() + 26
        bx   = (self.W - tw) // 2
        by   = (self.H - th) // 2
        a8   = int(alpha)
        pygame.draw.rect(surf, (0, 185, 72, int(a8 * 0.88)), (bx, by, tw, th), border_radius=7)
        pygame.draw.rect(surf, (0, 255, 100, int(a8 * 0.55)), (bx, by, tw, th), 2, border_radius=7)
        t2 = self.f_xl.render(name, True, (0, 0, 0))
        surf.blit(t2, (bx + 35, by + 13))
        self.scr.blit(surf, (0, 0))

    # ── Overlay: brightness ────────────────────────────────────────
    def draw_brightness_overlay(self, val):
        scr = self.scr
        bg  = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 145))
        scr.blit(bg, (0, 0))

        bw, bh = 420, 42
        bx = (self.W - bw) // 2
        by = self.H // 2

        title = self.f_lg.render("BRIGHTNESS", True, C_GREEN)
        scr.blit(title, ((self.W - title.get_width()) // 2, by - 52))

        pygame.draw.rect(scr, (18, 38, 22), (bx, by, bw, bh), border_radius=5)
        fill_w = max(6, int(bw * val))
        pygame.draw.rect(scr, C_GREEN, (bx, by, fill_w, bh), border_radius=5)
        pygame.draw.rect(scr, C_GREEN_D, (bx, by, bw, bh), 2, border_radius=5)

        pct = self.f_md.render(f"{int(val * 100)}%", True, C_GREEN)
        scr.blit(pct, ((self.W - pct.get_width()) // 2, by + bh + 14))

        hint = self.f_xs.render("TAP TO SET LEVEL  ·  TAP AGAIN TO CLOSE", True, (40, 40, 40))
        scr.blit(hint, ((self.W - hint.get_width()) // 2, by + bh + 38))


# ── APPLICATION ───────────────────────────────────────────────────
class App:
    LONG_PRESS_S = 1.5
    LABEL_HOLD_F = FPS * 2
    LABEL_FADE_F = int(FPS * 0.28)

    def __init__(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "fbcon")
        os.environ.setdefault("SDL_FBDEV",       "/dev/fb0")
        pygame.init()
        pygame.mouse.set_visible(False)
        try:
            self.screen = pygame.display.set_mode(
                (SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.NOFRAME
            )
        except:
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Kenwood Visualizer")

        self.audio = AudioEngine()
        self.bt    = BTStatus()
        self.viz   = Visualizer(self.screen)
        self.clock = pygame.time.Clock()

        self.mode_idx   = 0
        self.mode       = MODES[0]

        # Label anim
        self.lbl_timer  = 0
        self.lbl_alpha  = 0

        # Touch
        self.press_t        = None
        self.show_bright    = False
        self.brightness     = 1.0
        self.viz.brightness = 1.0

    @property
    def _lbl_total(self):
        return self.LABEL_HOLD_F + self.LABEL_FADE_F * 2

    def _next_mode(self):
        self.mode_idx  = (self.mode_idx + 1) % len(MODES)
        self.mode      = MODES[self.mode_idx]
        self.lbl_timer = self._lbl_total
        self.lbl_alpha = 255
        self.viz.osc_hist.clear()
        print(f"Mode → {MODE_NAMES[self.mode]}")

    def _set_brightness(self, mx):
        bw = 420
        bx = (SCREEN_W - bw) // 2
        val = (mx - bx) / bw
        self.brightness     = max(0.08, min(1.0, val))
        self.viz.brightness = self.brightness

    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE: return False
                if ev.key == pygame.K_SPACE:  self._next_mode()
                if ev.key == pygame.K_b:
                    self.show_bright = not self.show_bright

            if ev.type == pygame.MOUSEBUTTONDOWN:
                self.press_t = time.time()
                if self.show_bright:
                    self._set_brightness(ev.pos[0])

            if ev.type == pygame.MOUSEBUTTONUP:
                if self.press_t is not None:
                    held = time.time() - self.press_t
                    if held < self.LONG_PRESS_S:
                        if self.show_bright:
                            self.show_bright = False
                        else:
                            self._next_mode()
                self.press_t = None

        if self.press_t and (time.time() - self.press_t >= self.LONG_PRESS_S):
            self.show_bright = True
            self.press_t     = None

        return True

    def _tick_label(self):
        if self.lbl_timer <= 0:
            self.lbl_alpha = 0
            return
        self.lbl_timer -= 1
        t = self.lbl_timer
        total = self._lbl_total
        fade  = self.LABEL_FADE_F
        if t > total - fade:
            self.lbl_alpha = int(255 * (total - t) / fade)
        elif t > fade:
            self.lbl_alpha = 255
        else:
            self.lbl_alpha = int(255 * t / fade)

    def run(self):
        self.audio.start()
        print("Kenwood Visualizer — tap to cycle modes, hold for brightness")

        try:
            while True:
                if not self.handle_events():
                    break

                self.audio.update()
                self.bt.update()

                self.viz.tick_sp_peaks(self.audio.levels)
                self.viz.tick_ph_peaks(self.audio.levels)
                self.viz.tick_vu_peaks(self.audio.vu)
                self._tick_label()

                # ── Render current mode ──
                m = self.mode
                if m == Mode.SPECTRUM:
                    self.viz.draw_spectrum(self.audio.levels)
                elif m == Mode.LEVEL:
                    self.viz.draw_level_meter(self.audio.vu)
                elif m == Mode.SCOPE:
                    self.viz.draw_oscilloscope(self.audio.waveform)
                elif m == Mode.COMBO:
                    self.viz.draw_combo(self.audio.levels, self.audio.vu)
                elif m == Mode.PEAKHOLD:
                    self.viz.draw_peakhold(self.audio.levels)

                # ── Chrome ──
                self.viz.draw_header(self.mode, self.bt)
                self.viz.draw_footer(self.mode)
                self.viz.draw_scanlines()

                # ── Overlays ──
                if self.lbl_alpha > 0:
                    self.viz.draw_mode_label(MODE_NAMES[self.mode], self.lbl_alpha)
                if self.show_bright:
                    self.viz.draw_brightness_overlay(self.brightness)

                self.viz.apply_brightness()
                pygame.display.flip()
                self.clock.tick(FPS)

        except KeyboardInterrupt:
            pass
        finally:
            self.audio.stop()
            pygame.quit()
            print("Stopped.")


if __name__ == "__main__":
    App().run()
```

### 6D. `kenwood_visualizer-12.html`: most complete version of the first browser design (2026-04-14 02:13)

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kenwood Visualizer</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#060806;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:monospace;padding:12px}
#kw{width:100%;max-width:900px;display:block;border-radius:10px;cursor:pointer;background:#020502;border:2px solid #0d1a0d;box-shadow:0 0 40px rgba(0,200,60,0.08)}
#controls{display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap;max-width:900px;width:100%}
button{font-family:monospace;font-size:11px;letter-spacing:2px;padding:7px 14px;background:#050a06;border:1px solid #1a3a1a;color:#00e855;border-radius:3px;cursor:pointer}
button:hover{background:#0a1a0c}
#micStatus{font-family:monospace;font-size:10px;color:#1a3a1a;letter-spacing:1px;flex:1}
#themeBtn{color:#ffaa00;border-color:#3a2a00}
</style>
</head>
<body>
<canvas id="kw"></canvas>
<div id="controls">
  <button id="micBtn">● MIC IN</button>
  <button id="modeBtn">NEXT MODE ▶</button>
  <button id="themeBtn">VFD AMBER</button>
  <span id="micStatus">CLICK DISPLAY TO CYCLE MODES · DEMO ACTIVE</span>
</div>
<script>
const canvas=document.getElementById('kw');
const C=canvas.getContext('2d');
const MODES=['SPECTRUM','LEVEL METER','OSCILLOSCOPE','COMBO','PEAK HOLD','BASS REACTOR','DPX 3D'];
let modeIdx=0;
const NB=16, NS=22, VUS=28, OSC_N=600, OSC_HIST=6, BR=8;
const BEDGES=[60,100,150,220,320,450,650,950,1300,1800,2600,3700,5200,7400,10000,12500,14500];
const FLBLS=['60','100','150','220','320','450','650','950','1.3k','1.8k','2.6k','3.7k','5.2k','7.4k','10k','12.5k'];
const BR_LBLS=['SUB','BASS','LO-MID','MID','UP-MID','PRES','BRILL','AIR'];
const BR_EDGES=[20,60,120,250,500,1200,3000,7000,16000];
const BR_FREQ=['20','60','120','250','500','1.2k','3k','7k'];

// Demo patterns — all hit 1.0 on multiple bands
const PATS=[
  [1.0,1.0,.98,.96,.93,.90,.87,.84,.82,.80,.79,.82,.86,.90,.94,.98],
  [.7,.75,.82,.88,.95,1.0,1.0,.98,.96,.94,.91,.94,.96,.98,1.0,1.0],
  [.88,.90,.92,.95,.98,1.0,1.0,.98,.95,.92,.90,.92,.95,.98,1.0,.98],
  [1.0,.98,.95,.92,.88,.85,.88,.92,.95,.98,1.0,.98,.95,.92,.90,.88],
  [.92,.94,.96,.98,1.0,1.0,.98,.96,.94,.92,.94,.96,.98,1.0,1.0,.98]
];

let theme='green';
const T={
  green:{seg:'#00ff55',seg2:'#00cc44',amber:'#ffaa00',red:'#ff2200',off:'#041208',offb:'#082010',bg:'#020502',lbl:'#00882a',dim:'#001808',hdr:'#080d08',glowC:'#00ff55'},
  amber:{seg:'#ffcc00',seg2:'#ff9900',amber:'#ff6600',red:'#ff2200',off:'#120c00',offb:'#1e1400',bg:'#060400',lbl:'#886600',dim:'#0e0800',hdr:'#0a0800',glowC:'#ffcc00'}
};
function th(){return T[theme];}

// Audio state — single source of truth
let bands   = new Float32Array(NB);   // smoothed spectrum bands 0-1
let vuL     = 0;                       // VU left  0-1  (raw, no smoothing — instant)
let vuR     = 0;                       // VU right 0-1
let vuLpk   = 0, vuRpk   = 0;         // VU peaks
let vuLpkT  = 0, vuRpkT  = 0;
let spPk    = new Float32Array(NB);
let spT     = new Int32Array(NB);
let phPk    = new Float32Array(NB);
let phT     = new Int32Array(NB);
let brPos   = new Float32Array(BR);
let brVel   = new Float32Array(BR);
let waveform= new Float32Array(OSC_N);
let oscHist = [];
let beatFlash=0, beatPrev=0, lastBeat=0;

let dF=0, dPI=0, dPF=0;
let dpxFrame=0;
let analyser=null, audioCtx=null, micOn=false;
let lblA=0, lblT=0;
const LH=90, LF=9;
let W=900, H=540, HH=30, FH=26, VY=0, VH=0;

function resize(){
  const dpr=window.devicePixelRatio||1;
  const mw=Math.min(window.innerWidth-24,900);
  W=Math.round(mw*dpr); H=Math.round(W*0.6);
  canvas.width=W; canvas.height=H;
  canvas.style.width=mw+'px';
  canvas.style.height=Math.round(mw*0.6)+'px';
  VY=HH+2; VH=H-HH-FH-4;
}
resize(); window.addEventListener('resize',resize);

function sC(i,t){const p=i/Math.max(t-1,1),q=th();return p>=.86?q.red:p>=.68?q.amber:q.seg;}
function vC(i,t){const p=i/Math.max(t-1,1),q=th();return p>=.87?q.red:p>=.70?q.amber:q.seg;}
function glow(c,r){C.shadowBlur=r;C.shadowColor=c;}
function ng(){C.shadowBlur=0;}

// ── AUDIO ──────────────────────────────────────────────────────
function getDemo(){
  dF++; dPF++;
  if(dPF>220){dPI=(dPI+1)%PATS.length; dPF=0;}
  const p=PATS[dPI], n=PATS[(dPI+1)%PATS.length];
  const t=Math.min(dPF/60,1);
  const raw=new Float32Array(NB);
  for(let i=0;i<NB;i++){
    raw[i]=p[i]*(1-t)+n[i]*t + Math.sin(dF*.07+i*.8)*.08 + (Math.random()-.5)*.04;
    raw[i]=Math.max(0,Math.min(1.35,raw[i]));
  }
  // VU = peak of bands (NOT average — this is what hits 1.0)
  const peak=Math.max(...raw);
  vuL=Math.min(1,peak*1.15);
  vuR=Math.min(1,peak*1.15*(0.88+Math.sin(dF*.09)*.12));
  // Waveform from mix of bands
  const rms=raw.reduce((a,v)=>a+v,0)/NB;
  for(let i=0;i<OSC_N;i++)
    waveform[i]=rms*(Math.sin(i*.04+dF*.03)+Math.sin(i*.11+dF*.02)*.5)*(0.7+Math.sin(i*.25)*.3);
  return raw;
}

function getMic(){
  const d=new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(d);
  const raw=new Float32Array(NB);
  // PROPER logarithmic band mapping using actual Hz per bin
  const binHz=44100/analyser.fftSize;
  // Normalization per band — high freq bins are weaker in real audio
  const norm=[148,140,132,125,116,108,100,90,80,70,60,50,40,30,22,16];
  for(let i=0;i<NB;i++){
    const loBin=Math.max(0,Math.floor(BEDGES[i]/binHz));
    const hiBin=Math.min(d.length-1,Math.ceil(BEDGES[i+1]/binHz));
    let sum=0,cnt=0;
    for(let b=loBin;b<=hiBin;b++){sum+=d[b];cnt++;}
    raw[i]=cnt>0?Math.min(1,(sum/cnt)/norm[i]):0;
  }
  // Waveform
  const td=new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(td);
  for(let i=0;i<OSC_N;i++) waveform[i]=td[Math.floor(i*td.length/OSC_N)];
  // VU = instantaneous peak of time domain (much higher than RMS)
  let peakVal=0;
  for(let i=0;i<td.length;i++) peakVal=Math.max(peakVal,Math.abs(td[i]));
  // Typical music peak: 0.3-0.9. Scale so 0.4 = full bar.
  vuL=Math.min(1,peakVal/0.25);
  vuR=Math.min(1,(peakVal/0.25)*(0.88+Math.random()*.24));
  return raw;
}

function tickAudio(){
  const raw=analyser?getMic():getDemo();
  // Spectrum: fast smoothing
  for(let i=0;i<NB;i++){
    bands[i]=bands[i]*.62+raw[i]*.38;
    // Spec peaks
    if(raw[i]>=spPk[i]){spPk[i]=raw[i];spT[i]=50;}
    else if(spT[i]>0) spT[i]--;
    else spPk[i]=Math.max(0,spPk[i]-.02);
    // Peak hold peaks (slow fall)
    if(raw[i]>=phPk[i]){phPk[i]=raw[i];phT[i]=130;}
    else if(phT[i]>0) phT[i]--;
    else phPk[i]=Math.max(0,phPk[i]-.005);
  }
  // VU peaks
  if(vuL>=vuLpk){vuLpk=vuL;vuLpkT=55;} else if(vuLpkT>0)vuLpkT--; else vuLpk=Math.max(0,vuLpk-.01);
  if(vuR>=vuRpk){vuRpk=vuR;vuRpkT=55;} else if(vuRpkT>0)vuRpkT--; else vuRpk=Math.max(0,vuRpk-.01);
  // Bass reactor (spring physics on band averages)
  for(let i=0;i<BR;i++){
    let sum=0,cnt=0;
    for(let b=0;b<NB;b++) if(BEDGES[b]>=BR_EDGES[i]&&BEDGES[b]<BR_EDGES[i+1]){sum+=raw[b];cnt++;}
    const target=cnt>0?sum/cnt:0;
    const spring=0.35,damp=0.6,grav=0.014;
    brVel[i]+=(target-brPos[i])*spring;
    brVel[i]-=grav;
    brVel[i]*=damp;
    brPos[i]=Math.max(0,Math.min(1.1,brPos[i]+brVel[i]));
  }
  // Beat
  const sub=(bands[0]+bands[1])*.5;
  if(sub>0.5&&beatPrev<=0.5&&Date.now()-lastBeat>220){beatFlash=1;lastBeat=Date.now();}
  beatPrev=sub;
  if(beatFlash>0)beatFlash=Math.max(0,beatFlash-.055);
}


// ── DPX-5021M STYLE MODE ───────────────────────────────────────
function mDPX3D(){
  const sc=W/800;
  // Black background
  C.fillStyle='#000'; C.fillRect(0,VY,W,VH);
  dpxFrame++;

  // Colors
  const CYAN='#00d8ff', CYAN2='#00aacc', CYANG='rgba(0,216,255,0.18)';
  const CPEAK='#ffffff', CSUB='#0099bb', CDIM='rgba(0,180,220,0.12)';

  // ── MAIN SPECTRUM (top 60%) ──────────────────────────────────
  const mainH = Math.round(VH*0.60);
  const mainY = VY+Math.round(VH*0.02);
  const padL  = Math.round(28*sc);
  const padR  = Math.round(12*sc);
  const mainW = W-padL-padR;
  const bw    = mainW/NB;
  const LEAN  = Math.round(5*sc);  // 3D lean amount per segment height
  const NS3   = 26;                 // more segments for taller display
  const sh    = mainH/NS3;
  const sg    = sh*0.14;
  const sf    = sh-sg;
  const bgp   = bw*0.14;
  const fw    = bw-bgp;

  for(let b=0;b<NB;b++){
    const lit  = Math.min(NS3,Math.ceil(bands[b]*NS3));
    const pseg = Math.min(NS3-1,Math.ceil(spPk[b]*NS3)-1);
    const x    = padL+b*bw+bgp/2;

    for(let s=0;s<NS3;s++){
      const si = NS3-1-s;
      const y  = mainY+s*sh+sg/2;
      // 3D lean: top of segment shifts right relative to bottom
      const topShift = LEAN;

      if(si<lit){
        // Brightness: top segments brighter
        const bright = 0.55+0.45*(si/NS3);
        // Front face (parallelogram)
        C.beginPath();
        C.moveTo(x,      y+sf);
        C.lineTo(x+fw,   y+sf);
        C.lineTo(x+fw+topShift, y);
        C.lineTo(x+topShift,    y);
        C.closePath();
        // Color: top = amber/red, mid = cyan
        const pct=si/NS3;
        if(pct>=0.86) C.fillStyle=`rgba(255,60,0,${bright})`;
        else if(pct>=0.68) C.fillStyle=`rgba(255,160,0,${bright})`;
        else C.fillStyle=`rgba(0,${Math.round(180+40*bright)},255,${bright})`;
        C.fill();

        // Top face (3D depth) — lighter
        C.beginPath();
        C.moveTo(x+topShift,    y);
        C.lineTo(x+fw+topShift, y);
        C.lineTo(x+fw+topShift+2, y-sg*0.7);
        C.lineTo(x+topShift+2,    y-sg*0.7);
        C.closePath();
        C.fillStyle=`rgba(180,240,255,${bright*0.45})`;
        C.fill();

        // Bright bottom edge
        C.fillStyle=`rgba(0,220,255,${bright*0.3})`;
        C.fillRect(x,y+sf-1,fw,1);
      } else if(si===pseg&&spPk[b]>0.02){
        // Peak: white bright dot
        C.beginPath();
        C.moveTo(x,       y+sf);
        C.lineTo(x+fw,    y+sf);
        C.lineTo(x+fw+topShift, y);
        C.lineTo(x+topShift,    y);
        C.closePath();
        C.shadowBlur=8; C.shadowColor='#fff';
        C.fillStyle='rgba(255,255,255,0.9)'; C.fill();
        C.shadowBlur=0;
      } else {
        // Off: very dim grid
        C.strokeStyle=CDIM; C.lineWidth=0.5;
        C.strokeRect(x+topShift,y,fw,sf);
      }
    }
  }

  // Horizontal separator line with glow
  const divY=VY+Math.round(VH*0.63);
  C.shadowBlur=6; C.shadowColor=CYAN;
  C.strokeStyle=CYAN2; C.lineWidth=1;
  C.beginPath(); C.moveTo(padL,divY); C.lineTo(W-padR,divY); C.stroke();
  C.shadowBlur=0;

  // ── SUB SPECTRUMS (bottom) ────────────────────────────────────
  const subY    = divY+Math.round(VH*0.04);
  const subH    = H-FH-subY-Math.round(VH*0.04);
  const subW    = Math.round(W*0.30);
  const subNS   = 8;
  const subNB   = 8;
  const subBW   = subW/subNB;
  const subSH   = subH/subNS;
  const subSF   = subSH-subSH*0.2;
  const subLEAN = Math.round(3*sc);

  // Left sub-spectrum (first 8 bands)
  for(let b=0;b<subNB;b++){
    const bandIdx = Math.floor(b*NB/subNB);
    const lit = Math.min(subNS,Math.ceil(bands[bandIdx]*subNS));
    const pk  = Math.min(subNS-1,Math.ceil(spPk[bandIdx]*subNS)-1);
    const x   = padL+b*subBW+subBW*0.1;
    const fw2 = subBW*0.80;
    for(let s=0;s<subNS;s++){
      const si=subNS-1-s, y=subY+s*subSH+subSH*0.1;
      const ts=subLEAN;
      if(si<lit){
        C.beginPath();
        C.moveTo(x,y+subSF); C.lineTo(x+fw2,y+subSF);
        C.lineTo(x+fw2+ts,y); C.lineTo(x+ts,y); C.closePath();
        C.fillStyle=si>=subNS*.7?'rgba(255,100,0,0.9)':CSUB; C.fill();
      } else if(si===pk&&spPk[bandIdx]>0.02){
        C.beginPath();
        C.moveTo(x,y+subSF); C.lineTo(x+fw2,y+subSF);
        C.lineTo(x+fw2+ts,y); C.lineTo(x+ts,y); C.closePath();
        C.fillStyle='rgba(255,255,255,0.85)'; C.fill();
      } else {
        C.strokeStyle=CDIM; C.lineWidth=0.5;
        C.strokeRect(x+ts,y,fw2,subSF);
      }
    }
  }

  // Right sub-spectrum (last 8 bands)
  const rightX=W-padR-subW;
  for(let b=0;b<subNB;b++){
    const bandIdx=Math.floor((b+subNB)*NB/(subNB*2));
    const lit=Math.min(subNS,Math.ceil(bands[Math.min(bandIdx,NB-1)]*subNS));
    const pk=Math.min(subNS-1,Math.ceil(spPk[Math.min(bandIdx,NB-1)]*subNS)-1);
    const x=rightX+b*subBW+subBW*0.1;
    const fw2=subBW*0.80;
    for(let s=0;s<subNS;s++){
      const si=subNS-1-s, y=subY+s*subSH+subSH*0.1;
      const ts=subLEAN;
      if(si<lit){
        C.beginPath();
        C.moveTo(x,y+subSF); C.lineTo(x+fw2,y+subSF);
        C.lineTo(x+fw2+ts,y); C.lineTo(x+ts,y); C.closePath();
        C.fillStyle=si>=subNS*.7?'rgba(255,100,0,0.9)':CSUB; C.fill();
      } else if(si===pk&&spPk[Math.min(bandIdx,NB-1)]>0.02){
        C.beginPath();
        C.moveTo(x,y+subSF); C.lineTo(x+fw2,y+subSF);
        C.lineTo(x+fw2+ts,y); C.lineTo(x+ts,y); C.closePath();
        C.fillStyle='rgba(255,255,255,0.85)'; C.fill();
      } else {
        C.strokeStyle=CDIM; C.lineWidth=0.5;
        C.strokeRect(x+ts,y,fw2,subSF);
      }
    }
  }

  // ── CENTER INFO ───────────────────────────────────────────────
  const cx=W/2, cy=subY+subH/2;
  // Pulsing ring (beats with bass)
  const pulse=beatFlash>0?1+beatFlash*.15:1;
  const ringR=Math.round(22*sc)*pulse;
  C.beginPath(); C.arc(cx,cy,ringR,0,Math.PI*2);
  C.strokeStyle=beatFlash>0.3?'rgba(255,80,0,0.9)':'rgba(0,180,220,0.4)';
  C.lineWidth=2; C.stroke();
  C.beginPath(); C.arc(cx,cy,ringR*0.65,0,Math.PI*2);
  C.strokeStyle=beatFlash>0.3?'rgba(255,120,0,0.7)':'rgba(0,140,180,0.3)';
  C.lineWidth=1.5; C.stroke();

  // BT device name or "BLUETOOTH"
  const name = micOn?'MIC IN':'BLUETOOTH';
  C.font=`bold ${Math.round(9*sc)}px monospace`;
  C.fillStyle='rgba(0,200,240,0.7)';
  C.textAlign='center';
  C.fillText(name,cx,cy-Math.round(6*sc));

  // Scrolling frequency labels across bottom of main spectrum
  C.font=`bold ${Math.round(8*sc)}px monospace`;
  C.fillStyle='rgba(0,150,190,0.5)';
  for(let b=0;b<NB;b++){
    const lx=padL+b*bw+bw/2;
    C.fillText(FLBLS[b],lx,mainY+mainH+Math.round(10*sc));
  }

  // DSP label bottom left (like the real unit)
  C.font=`bold ${Math.round(7*sc)}px monospace`;
  C.fillStyle='rgba(0,160,200,0.4)';
  C.textAlign='left';
  C.fillText('DIGITAL SIGNAL PROCESSOR',padL,H-FH-Math.round(3*sc));
}

// ── UI CHROME ──────────────────────────────────────────────────
function drawHdr(){
  const sc=W/800,q=th();
  C.fillStyle=q.hdr; C.fillRect(0,0,W,HH);
  C.fillStyle='#181818'; C.fillRect(0,HH-1,W,1);
  glow(q.glowC,10);
  C.font=`bold ${Math.round(15*sc)}px monospace`;
  C.fillStyle=q.seg; C.textAlign='left';
  C.fillText('KENWOOD',Math.round(14*sc),HH-8);
  ng();
  C.font=`bold ${Math.round(10*sc)}px monospace`;
  C.fillStyle='#2a2a2a';
  C.fillText(MODES[modeIdx],Math.round(110*sc),HH-8);
  const bx=W-Math.round(160*sc);
  C.beginPath();C.arc(bx,HH/2,Math.round(4*sc),0,Math.PI*2);
  C.fillStyle=micOn?q.seg:'#222'; C.fill();
  C.font=`bold ${Math.round(10*sc)}px monospace`;
  C.fillStyle=micOn?q.seg:'#222'; C.textAlign='left';
  C.fillText(micOn?'MIC LIVE':'WAITING',bx+Math.round(11*sc),HH-8);
}

function drawFtr(){
  const sc=W/800,q=th();
  C.fillStyle='#060806'; C.fillRect(0,H-FH,W,FH);
  C.fillStyle='#0f120f'; C.fillRect(0,H-FH,W,1);
  const sp=W/(MODES.length+1),cy=H-FH/2,r=Math.max(3,W/300);
  C.font=`bold ${Math.round(8*sc)}px monospace`;
  for(let i=0;i<MODES.length;i++){
    const cx=sp*(i+1),act=i===modeIdx;
    if(act)glow(q.glowC,10);
    C.beginPath();C.arc(cx,cy,act?r+2:r,0,Math.PI*2);
    C.fillStyle=act?q.seg:'#1a1a1a'; C.fill(); ng();
    if(act){C.fillStyle=q.lbl;C.textAlign='center';C.fillText(MODES[i],cx,cy-r-3);}
  }
}

function drawGrid(){
  C.strokeStyle=th().dim; C.lineWidth=1;
  for(let i=1;i<4;i++){
    const gy=VY+VH*i/4;
    C.beginPath();C.moveTo(52,gy);C.lineTo(W-8,gy);C.stroke();
  }
}

function drawDB(rx,ry,rh){
  const sc=W/800;
  C.font=`bold ${Math.round(9*sc)}px monospace`;
  C.textAlign='right'; C.fillStyle=th().lbl;
  for(const[l,p]of[['+6',0],['0',.25],['-6',.5],['-12',.7],['-20',.88]])
    C.fillText(l,rx-4,ry+p*rh+4);
}

// ── BAR DRAWING — core function ─────────────────────────────────
function drawBars(lv,pks,rx,ry,rw,rh,ns){
  ns=ns||NS;
  const q=th(),bw=rw/NB,sh=rh/ns,sg=sh*.18,sf=sh-sg,gap=bw*.16;
  const sc=W/800;
  for(let b=0;b<NB;b++){
    const lit=Math.min(ns,Math.ceil(lv[b]*ns));
    const pseg=Math.min(ns-1,Math.ceil(pks[b]*ns)-1);
    const x=rx+b*bw+gap/2, fw=bw-gap;
    for(let s=0;s<ns;s++){
      const si=ns-1-s, y=ry+s*sh+sg/2;
      if(si<lit){
        const col=sC(si,ns);
        if(si>=ns*.6){glow(col,7);}
        C.fillStyle=col; C.fillRect(x,y,fw,sf); ng();
        C.fillStyle='rgba(255,255,255,.22)'; C.fillRect(x,y,fw,2);
      } else if(si===pseg&&pseg>=0&&pks[b]>0.02){
        glow('#ff3300',10); C.fillStyle='#ff3300'; C.fillRect(x,y,fw,sf); ng();
      } else {
        C.fillStyle=q.off; C.fillRect(x,y,fw,sf);
      }
    }
  }
  // Freq labels
  C.font=`bold ${Math.round(9*sc)}px monospace`;
  C.textAlign='center'; C.fillStyle=q.lbl;
  for(let b=0;b<NB;b++) C.fillText(FLBLS[b],rx+b*bw+bw/2,ry+rh+Math.round(13*sc));
}

// ── VU BAR — core function ──────────────────────────────────────
function drawVUBar(lv,pk,x,y,bw,bh,segCount){
  const q=th();
  const sw=bw/segCount, sf=sw-sw*.1;
  const lit=Math.min(segCount,Math.ceil(lv*segCount));
  const pks=Math.min(segCount-1,Math.ceil(pk*segCount)-1);
  for(let s=0;s<segCount;s++){
    const sx=x+s*sw, col=vC(s,segCount);
    if(s<lit){
      if(s>=segCount*.65){glow(col,8);}
      C.fillStyle=col; C.fillRect(sx,y,sf,bh); ng();
      C.fillStyle='rgba(255,255,255,.18)'; C.fillRect(sx,y,sf,3);
    } else if(s===pks&&pk>0.02){
      glow('#ff3300',12); C.fillStyle='#ff3300'; C.fillRect(sx,y,sf,bh); ng();
    } else {
      C.fillStyle=q.off; C.fillRect(sx,y,sf,bh);
    }
  }
}

// ── MODE RENDERERS ─────────────────────────────────────────────
function mSpectrum(){
  const q=th(); C.fillStyle=q.bg; C.fillRect(0,VY,W,VH);
  drawGrid();
  const sc=W/800,rx=52,ry=VY+4,rw=W-62,rh=VH-22;
  drawBars(bands,spPk,rx,ry,rw,rh); drawDB(rx,ry,rh);
}

function mLevel(){
  const q=th(),sc=W/800;
  C.fillStyle=q.bg; C.fillRect(0,VY,W,VH);
  // Layout
  const bh=Math.round(VH*.3);
  const gap=Math.round(VH*.1);
  const totalH=bh*2+gap;
  const sy=VY+Math.round((VH-totalH)/2);
  const pl=Math.round(52*sc);   // left pad (channel label)
  const pr=Math.round(4*sc);    // right pad
  const barW=W-pl-pr;
  const dbs=[[-30,0],[-20,.17],[-10,.4],[-7,.52],[-5,.6],[-3,.68],[0,.77],[3,.88],[6,1]];

  // L bar
  C.font=`bold ${Math.round(22*sc)}px monospace`;
  C.textAlign='center'; C.fillStyle=q.seg2;
  glow(q.glowC,8); C.fillText('L',Math.round(26*sc),sy+bh*.68); ng();
  drawVUBar(vuL,vuLpk,pl,sy,barW,bh,VUS);

  // R bar
  glow(q.glowC,8); C.fillText('R',Math.round(26*sc),sy+bh+gap+bh*.68); ng();
  drawVUBar(vuR,vuRpk,pl,sy+bh+gap,barW,bh,VUS);

  // dB scale between bars
  const scaleY=sy+bh+gap/2;
  C.font=`bold ${Math.round(9*sc)}px monospace`;
  C.textAlign='center'; C.fillStyle=q.lbl;
  for(const[db,pos]of dbs){
    const sx=pl+pos*barW;
    C.fillText(db,sx,scaleY+4);
    C.strokeStyle=q.dim; C.lineWidth=1;
    C.beginPath();C.moveTo(sx,sy+bh-5);C.lineTo(sx,sy+bh);C.stroke();
    C.beginPath();C.moveTo(sx,sy+bh+gap);C.lineTo(sx,sy+bh+gap+5);C.stroke();
  }
}

function mScope(){
  const q=th();
  C.fillStyle='#010302'; C.fillRect(0,VY,W,VH);
  const x0=46,x1=W-10,vw=x1-x0,mid=VY+VH/2,amp=VH*.44;
  C.strokeStyle=q.dim; C.lineWidth=1;
  for(let i=1;i<4;i++){const gy=VY+VH*i/4;C.beginPath();C.moveTo(x0,gy);C.lineTo(x1,gy);C.stroke();}
  for(let i=1;i<9;i++){const gx=x0+vw*i/8;C.beginPath();C.moveTo(gx,VY);C.lineTo(gx,VY+VH);C.stroke();}
  C.strokeStyle=q.off; C.beginPath();C.moveTo(x0,mid);C.lineTo(x1,mid);C.stroke();
  oscHist.push(waveform.slice());
  if(oscHist.length>OSC_HIST) oscHist.shift();
  for(let hi=0;hi<oscHist.length;hi++){
    const w=oscHist[hi],cur=hi===oscHist.length-1;
    const dec=Math.pow((hi+1)/oscHist.length,2.2);
    if(cur){C.strokeStyle=q.seg;C.lineWidth=2;glow(q.glowC,8);}
    else{const g=theme==='amber'?`rgb(${Math.round(200*dec)},${Math.round(100*dec)},0)`:`rgb(0,${Math.round(210*dec)},${Math.round(60*dec)})`;C.strokeStyle=g;C.lineWidth=1;}
    C.beginPath();
    for(let i=0;i<Math.min(w.length,OSC_N);i++){
      const px=x0+i/(OSC_N-1)*vw, py=Math.max(VY,Math.min(VY+VH,mid-w[i]*amp));
      i===0?C.moveTo(px,py):C.lineTo(px,py);
    }
    C.stroke(); ng();
  }
  const sc=W/800;
  C.font=`bold ${Math.round(9*sc)}px monospace`;
  C.fillStyle=q.lbl; C.textAlign='left'; C.fillText('AMPL',4,mid+4);
  C.textAlign='right'; C.fillText('TIME →',x1,VY+VH-4);
}

function mCombo(){
  const q=th(),sc=W/800;
  C.fillStyle=q.bg; C.fillRect(0,VY,W,VH);
  drawGrid();
  const sh=Math.round(VH*.54);
  drawBars(bands,spPk,52,VY+2,W-62,sh-16,14);
  drawDB(52,VY+2,sh-16);
  const dy=VY+sh;
  C.strokeStyle=q.off; C.lineWidth=1; C.beginPath();C.moveTo(0,dy);C.lineTo(W,dy);C.stroke();
  const uy=dy+4, uh=H-FH-uy-4;
  const cbh=Math.max(10,Math.round(uh*.38));
  const cgap=Math.round(uh*.15);
  const cpl=Math.round(46*sc), cpw=W-cpl-Math.round(4*sc);
  C.font=`bold ${Math.round(13*sc)}px monospace`;
  C.textAlign='center'; C.fillStyle=q.seg2;
  C.fillText('L',Math.round(20*sc),uy+cbh*.72);
  C.fillText('R',Math.round(20*sc),uy+cbh+cgap+cbh*.72);
  drawVUBar(vuL,vuLpk,cpl,uy,cpw,cbh,22);
  drawVUBar(vuR,vuRpk,cpl,uy+cbh+cgap,cpw,cbh,22);
}

function mPeakHold(){
  const q=th(),sc=W/800;
  C.fillStyle=q.bg; C.fillRect(0,VY,W,VH);
  drawGrid();
  const rx=52,ry=VY+4,rw=W-62,rh=VH-22;
  const bw=rw/NB,sh=rh/NS,sg=sh*.18,sf=sh-sg,gap=bw*.16;
  for(let b=0;b<NB;b++){
    const lit=Math.min(NS,Math.ceil(bands[b]*NS));
    const pseg=Math.min(NS-1,Math.ceil(phPk[b]*NS)-1);
    const x=rx+b*bw+gap/2, fw=bw-gap;
    for(let s=0;s<NS;s++){
      const si=NS-1-s, y=ry+s*sh+sg/2;
      if(si<lit){
        C.globalAlpha=.3; C.fillStyle=sC(si,NS); C.fillRect(x,y,fw,sf); C.globalAlpha=1;
      } else if(si===pseg&&phPk[b]>0.02){
        const col=sC(si,NS); glow(col,12);
        C.fillStyle=col; C.fillRect(x,y,fw,sf); ng();
        C.fillStyle='rgba(255,255,255,.55)'; C.fillRect(x,y,fw,2); C.fillRect(x,y+sf-2,fw,2);
      } else {
        C.fillStyle=q.off; C.fillRect(x,y,fw,sf);
      }
    }
  }
  C.font=`bold ${Math.round(9*sc)}px monospace`;
  C.textAlign='center'; C.fillStyle=q.lbl;
  for(let b=0;b<NB;b++) C.fillText(FLBLS[b],rx+b*bw+bw/2,ry+rh+Math.round(13*sc));
  drawDB(rx,ry,rh);
}

function mBassReactor(){
  const q=th(),sc=W/800;
  C.fillStyle=q.bg; C.fillRect(0,VY,W,VH);
  if(beatFlash>0){
    const cx=W/2,cy=VY+VH/2,maxR=Math.min(W,VH)*.6;
    const g=C.createRadialGradient(cx,cy,0,cx,cy,maxR);
    const gc=theme==='amber'?`rgba(255,160,0,${beatFlash*.2})`:`rgba(0,255,80,${beatFlash*.18})`;
    g.addColorStop(0,gc); g.addColorStop(1,'transparent');
    C.fillStyle=g; C.fillRect(0,VY,W,VH);
  }
  const PL=Math.round(52*sc),PR=Math.round(14*sc),PB=Math.round(32*sc),PT=Math.round(12*sc);
  const tw=W-PL-PR, barH=VH-PT-PB;
  const bw=tw/BR, BNS=14;
  const sh=barH/BNS, sg=sh*.15, sf=sh-sg, gap=bw*.12;
  for(let b=0;b<BR;b++){
    const pos=Math.min(1,brPos[b]);
    const lit=Math.min(BNS,Math.ceil(pos*BNS));
    const x=PL+b*bw+gap/2, fw=bw-gap, ry=VY+PT;
    for(let s=0;s<BNS;s++){
      const si=BNS-1-s, y=ry+s*sh+sg/2;
      if(si<lit){
        const col=sC(si,BNS);
        glow(col,b<2?14:8);
        C.fillStyle=col; C.fillRect(x,y,fw,sf); ng();
        C.fillStyle='rgba(255,255,255,.25)'; C.fillRect(x,y,fw,2);
      } else {
        C.fillStyle=q.off; C.fillRect(x,y,fw,sf);
      }
    }
    const lx=PL+b*bw+bw/2;
    C.font=`bold ${Math.round(9*sc)}px monospace`;
    C.textAlign='center'; C.fillStyle=b<2?q.seg2:q.lbl;
    C.fillText(BR_LBLS[b],lx,VY+VH-Math.round(8*sc));
    C.font=`bold ${Math.round(7*sc)}px monospace`;
    C.fillStyle=q.dim; C.fillText(BR_FREQ[b],lx,VY+VH-Math.round(18*sc));
  }
  // dB scale
  const ry2=VY+PT, rh2=barH;
  C.font=`bold ${Math.round(9*sc)}px monospace`;
  C.textAlign='right'; C.fillStyle=q.lbl;
  for(const[l,p]of[['+6',0],['0',.25],['-6',.5],['-12',.7],['-20',.88]]){
    const y=ry2+p*rh2; C.fillText(l,PL-4,y+4);
    C.strokeStyle=q.dim; C.lineWidth=1;
    C.beginPath();C.moveTo(PL,y);C.lineTo(W-PR,y);C.stroke();
  }
  // Beat indicator
  const bix=W-Math.round(55*sc), biy=VY+Math.round(18*sc);
  if(beatFlash>0.3){glow(q.glowC,14);}
  C.beginPath();C.arc(bix,biy,Math.round(6*sc),0,Math.PI*2);
  C.fillStyle=beatFlash>0.3?q.seg:q.off; C.fill(); ng();
  C.font=`bold ${Math.round(9*sc)}px monospace`;
  C.fillStyle=beatFlash>0.3?q.seg:q.dim; C.textAlign='right';
  C.fillText('BEAT',bix-Math.round(9*sc),biy+4);
}

// ── OVERLAYS ──────────────────────────────────────────────────
function drawLabel(){
  if(lblA<=0)return;
  const q=th(),sc=W/800,fs=Math.round(24*sc);
  C.font=`bold ${fs}px monospace`;
  const lbl=MODES[modeIdx],tw=C.measureText(lbl).width+Math.round(70*sc),tht=fs+24;
  const bx=(W-tw)/2,by=(H-tht)/2,a=lblA/255;
  glow(q.glowC,18); C.globalAlpha=a*.9; C.fillStyle=q.seg2;
  C.beginPath();C.roundRect(bx,by,tw,tht,6);C.fill(); ng();
  C.globalAlpha=a; C.fillStyle='#000'; C.textAlign='center'; C.textBaseline='middle';
  C.fillText(lbl,W/2,H/2); C.globalAlpha=1; C.textBaseline='alphabetic';
}

function drawScanlines(){
  C.globalAlpha=.04;
  for(let y=0;y<H;y+=3){C.fillStyle='#000';C.fillRect(0,y,W,1);}
  C.globalAlpha=.22;
  const v=C.createRadialGradient(W/2,H/2,H*.2,W/2,H/2,H*.75);
  v.addColorStop(0,'transparent');v.addColorStop(1,'#000');
  C.fillStyle=v; C.fillRect(0,0,W,H); C.globalAlpha=1;
}

function tickLbl(){
  if(lblT<=0){lblA=0;return;} lblT--;
  const tot=LH+LF*2;
  if(lblT>LH+LF) lblA=((tot-lblT)/LF)*255;
  else if(lblT>LF) lblA=255;
  else lblA=(lblT/LF)*255;
}

function nextMode(){
  modeIdx=(modeIdx+1)%MODES.length;
  lblT=LH+LF*2; oscHist=[];
}

function loop(){
  requestAnimationFrame(loop);
  tickAudio(); tickLbl();
  const m=modeIdx;
  if(m===0)mSpectrum();
  else if(m===1)mLevel();
  else if(m===2)mScope();
  else if(m===3)mCombo();
  else if(m===4)mPeakHold();
  else if(m===5)mBassReactor();
  else mDPX3D();
  drawHdr(); drawFtr(); drawScanlines(); drawLabel();
}

canvas.addEventListener('click',nextMode);
document.getElementById('modeBtn').addEventListener('click',nextMode);
document.getElementById('themeBtn').addEventListener('click',()=>{
  theme=theme==='green'?'amber':'green';
  document.getElementById('themeBtn').textContent=theme==='green'?'VFD AMBER':'VFD GREEN';
  document.getElementById('themeBtn').style.color=theme==='green'?'#ffaa00':'#00e855';
});
document.getElementById('micBtn').addEventListener('click',async()=>{
  if(micOn){
    if(audioCtx)audioCtx.close(); audioCtx=analyser=null; micOn=false;
    document.getElementById('micBtn').textContent='● MIC IN';
    document.getElementById('micBtn').style.color='#00e855';
    document.getElementById('micStatus').textContent='CLICK DISPLAY TO CYCLE MODES · DEMO ACTIVE';
    return;
  }
  try{
    const s=await navigator.mediaDevices.getUserMedia({audio:true,video:false});
    audioCtx=new AudioContext(); analyser=audioCtx.createAnalyser();
    analyser.fftSize=4096; analyser.smoothingTimeConstant=.75;
    audioCtx.createMediaStreamSource(s).connect(analyser);
    micOn=true;
    document.getElementById('micBtn').textContent='■ STOP MIC';
    document.getElementById('micBtn').style.color='#ff4400';
    document.getElementById('micStatus').textContent='MIC LIVE — PLAY MUSIC OR TALK';
  }catch(e){
    document.getElementById('micStatus').textContent='ERROR: '+e.message;
  }
});
loop();
</script>
</body>
</html>
```

### 6E. Track-info code from `automotive_custom_vfd.html` (2026-04-14 02:42)

```js
function updateMetadata(title) {
    if (title && title.trim() !== "") {
        songTitle = title.toUpperCase();
    }
}

function setupMetadataListeners() {
    // 1. Browser Media Session Listener
    if ('mediaSession' in navigator) {
        navigator.mediaSession.playbackState = 'playing';
        const updateFromSession = () => {
            const meta = navigator.mediaSession.metadata;
            if (meta) updateMetadata(`${meta.artist} - ${meta.title}`);
        };
        // Check periodically as session metadata can change
        setInterval(updateFromSession, 1000);
    }

    // 2. WebSocket Listener for Python Bridge (port 8765)
    const socket = new WebSocket('ws://localhost:8765');
    socket.onmessage = (event) => updateMetadata(event.data);
    socket.onerror = () => console.log("Bluetooth bridge not found. Using local metadata.");
}
```
