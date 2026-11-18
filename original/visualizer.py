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
