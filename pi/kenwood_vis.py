#!/usr/bin/env python3
"""
Kenwood DPX-6200M style VFD music visualizer
for a Raspberry Pi 3B+ driving a 2.8" 320x240 ILI9341 SPI screen (MSP2807).

Audio comes ONLY from the Pi's own playback (an ALSA loopback copy of what
Spotify Connect / Bluetooth is playing). It never opens a microphone, so room
noise can't move the bars.

Run modes
  kenwood_vis.py                 normal (framebuffer + touchscreen), used by systemd
  kenwood_vis.py --calibrate     touch calibration (tap 3 targets)
  kenwood_vis.py --window --demo desktop preview with fake music
  kenwood_vis.py --snapshot DIR  headless: save a PNG of every mode (demo audio)
"""
import argparse
import collections
import glob
import json
import math
import mmap
import os
import signal
import socket
import subprocess
import sys
import threading
import time

import numpy as np

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vfd_font import GLYPHS, GLYPH_H, GLYPH_W, normalize, text_width  # noqa: E402

W, H = 320, 240
CONFIG_PATH = "/etc/kenwood-vis.json"

DEFAULTS = {
    "audio_device": "plughw:Loopback,1,0",   # capture side of the loopback
    "sample_rate": 44100,
    "bands": 16,
    "fmin": 40,
    "fmax": 16000,
    "treble_tilt_db_per_octave": 3.0,        # lifts the high bands (music is bass heavy)
    "range_db": 42,                          # dB from top of bar to bottom of bar
    "silence_dbfs": -72,                     # below this the bars drop to zero
    "fps": 30,
    "framebuffer": "auto",                   # auto = the fb whose name contains ili9341
    "swap_red_blue": False,
    "rotate_180": False,
    "touch": {"device": "auto", "swap_xy": True,
              "x0": 3900, "x1": 200, "y0": 3900, "y1": 200},
    "backlight_gpio": 23,                    # null if LED is wired straight to 3.3V
    "bt_name": "KENWOOD-VIS",
    "spotify_name": "KENWOOD-VIS",
    "nowplaying_port": 5555,
    "show_clock": True,
    "clock_24h": True,
    "idle_dim_minutes": 10,                  # 0 = never dim when nothing is playing
    "idle_dim_brightness": 15,
}

# ── DPX-6200M palette (from kenwood_dramatic.html) ───────────────────
BLUE = (0, 51, 255)
CYAN = (0, 240, 255)
GREEN = (0, 255, 102)
YELLOW = (255, 255, 0)
ORANGE = (255, 153, 0)
RED = (255, 0, 51)
AMBER = (255, 170, 0)


def vfd_color(frac):
    """Colour of a segment by how far up the bar it is (0..1)."""
    if frac < 0.24:
        return BLUE
    if frac < 0.48:
        return CYAN
    if frac < 0.72:
        return GREEN
    if frac < 0.86:
        return YELLOW
    if frac < 0.96:
        return ORANGE
    return RED


MODES = ["SPEANA", "MAGNET", "STADIUM", "LASER", "SEASHORE", "RAIN DROP", "VIBROSCOPE"]

# ── Layout (320x240) ──────────────────────────────────────────────────
HUD_TOP = 18          # mode name + clock live above this
BASE = 220            # bottom of the bar area
SEG_H, SEG_GAP = 6, 2
PITCH = SEG_H + SEG_GAP
NSEG = 25             # 25 * 8 = 200 px of bars
SLANT = 1.0           # px shift per segment (the DPX's ~12° lean)
GLOW_PAD = 4


def load_config(path):
    cfg = json.loads(json.dumps(DEFAULTS))
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                user = json.load(f)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception as e:  # bad JSON shouldn't brick the display
            print(f"[config] ignoring {path}: {e}", file=sys.stderr)
    return cfg


class State:
    """Mode + brightness, remembered across reboots."""

    def __init__(self):
        d = os.environ.get("STATE_DIRECTORY") or os.path.expanduser("~/.config/kenwood-vis")
        self.path = os.path.join(d, "state.json")
        self.mode = 0
        self.brightness = 100
        try:
            with open(self.path) as f:
                s = json.load(f)
            self.mode = int(s.get("mode", 0)) % len(MODES)
            self.brightness = max(5, min(100, int(s.get("brightness", 100))))
        except Exception:
            pass

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"mode": self.mode, "brightness": self.brightness}, f)
            os.replace(tmp, self.path)
        except Exception as e:
            print(f"[state] {e}", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════
#  AUDIO  (loopback capture only, never a microphone)
# ══════════════════════════════════════════════════════════════════════
class AudioSource:
    RING = 8192

    def __init__(self, cfg, demo=False):
        self.cfg = cfg
        self.demo = demo
        self.sr = int(cfg["sample_rate"])
        self.ring = np.zeros(self.RING, np.float32)
        self.pos = 0
        self.lock = threading.Lock()
        self.status = "starting"
        self._stop = False

    def start(self):
        target = self._run_demo if self.demo else self._run_alsa
        threading.Thread(target=target, daemon=True).start()

    def stop(self):
        self._stop = True

    def _push(self, mono):
        n = len(mono)
        with self.lock:
            if n >= self.RING:
                self.ring[:] = mono[-self.RING:]
                self.pos = 0
                return
            end = self.pos + n
            if end <= self.RING:
                self.ring[self.pos:end] = mono
            else:
                k = self.RING - self.pos
                self.ring[self.pos:] = mono[:k]
                self.ring[:n - k] = mono[k:]
            self.pos = end % self.RING

    def latest(self, n):
        with self.lock:
            return np.roll(self.ring, -self.pos)[-n:].copy()

    def _open_pcm(self, alsaaudio):
        dev = self.cfg["audio_device"]
        try:
            return alsaaudio.PCM(type=alsaaudio.PCM_CAPTURE, mode=alsaaudio.PCM_NORMAL,
                                 device=dev, rate=self.sr, channels=2,
                                 format=alsaaudio.PCM_FORMAT_S16_LE, periodsize=512)
        except TypeError:  # very old pyalsaaudio
            pcm = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL, device=dev)
            pcm.setchannels(2)
            pcm.setrate(self.sr)
            pcm.setformat(alsaaudio.PCM_FORMAT_S16_LE)
            pcm.setperiodsize(512)
            return pcm

    def _run_alsa(self):
        try:
            import alsaaudio
        except ImportError:
            self.status = "no pyalsaaudio"
            print("[audio] python3-alsaaudio missing; bars will stay flat", file=sys.stderr)
            return
        while not self._stop:
            try:
                pcm = self._open_pcm(alsaaudio)
                self.status = "ok"
                print(f"[audio] capturing from {self.cfg['audio_device']}")
                while not self._stop:
                    length, data = pcm.read()
                    if length <= 0 or not data:
                        continue  # overrun: just keep going
                    s = np.frombuffer(data, dtype="<i2").astype(np.float32)
                    s = s[: (len(s) // 2) * 2].reshape(-1, 2).mean(axis=1) / 32768.0
                    self._push(s)
            except Exception as e:
                self.status = "no loopback"
                print(f"[audio] {e}; retrying in 3s", file=sys.stderr)
                time.sleep(3)

    def _run_demo(self):
        """Fake 120 BPM track so the screen can be tested without any audio set up."""
        self.status = "demo"
        sr, block = self.sr, 1024
        n0 = 0
        rng = np.random.default_rng(1)
        bass_notes = [55.0, 55.0, 65.4, 49.0]
        chords = [(220.0, 277.2, 329.6), (246.9, 311.1, 370.0),
                  (196.0, 246.9, 293.7), (220.0, 261.6, 329.6)]
        t_start = time.time()
        while not self._stop:
            t = (n0 + np.arange(block)) / sr
            beat = t * 2.0                     # 120 BPM
            bt = (beat % 1.0) / 2.0            # seconds since beat
            bar = (beat // 4).astype(int) % 4
            kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-bt * 30)) * bt) * np.exp(-bt * 9)
            off = ((beat + 0.5) % 1.0) / 2.0
            hat = rng.standard_normal(block) * np.exp(-off * 60) * 0.25
            hat = np.diff(np.concatenate(([0.0], hat)))
            sn_t = ((beat - 1) % 2.0) / 2.0
            snare = rng.standard_normal(block) * np.exp(-sn_t * 22) * 0.35
            bass = np.sin(2 * np.pi * np.take(bass_notes, bar) * t) * 0.35
            pad = np.zeros(block)
            for k in range(3):
                f = np.take([c[k] for c in chords], bar)
                pad += np.sign(np.sin(2 * np.pi * f * t)) * 0.04
            swell = 0.6 + 0.4 * np.sin(2 * np.pi * t / 16)
            lead = np.sin(2 * np.pi * (880 + 440 * (bar % 2)) * t) * 0.06 * (np.sin(2 * np.pi * t) > 0.3)
            sig = (kick * 0.8 + hat + snare + bass + pad * swell + lead) * 0.5
            self._push(sig.astype(np.float32))
            n0 += block
            ahead = n0 / sr - (time.time() - t_start)
            if ahead > 0:
                time.sleep(ahead)


class Analyzer:
    """FFT -> log-spaced bands -> 0..1 levels with automatic gain."""

    N = 2048

    def __init__(self, cfg):
        sr = int(cfg["sample_rate"])
        nb = int(cfg["bands"])
        self.nb = nb
        self.win = np.hanning(self.N).astype(np.float32)
        freqs = np.fft.rfftfreq(self.N, 1.0 / sr)
        edges = np.geomspace(cfg["fmin"], cfg["fmax"], nb + 1)
        lo = np.searchsorted(freqs, edges[:-1])
        hi = np.maximum(np.searchsorted(freqs, edges[1:]), lo + 1)
        self.lo, self.hi = lo, hi
        centers = np.sqrt(edges[:-1] * edges[1:])
        self.tilt = cfg["treble_tilt_db_per_octave"] * np.log2(centers / 1000.0)
        self.range = float(cfg["range_db"])
        self.silence = float(cfg["silence_dbfs"])
        self.ref = -10.0          # fast AGC reference (top of the bars)
        self.long_ref = -10.0     # slow reference so quiet intros don't look like noise
        self.rms_db = -120.0

    def process(self, x, dt):
        rms = float(np.sqrt(np.mean(x * x)) + 1e-12)
        self.rms_db = 20 * math.log10(rms)
        if self.rms_db < self.silence:
            return np.zeros(self.nb, np.float32)
        spec = np.abs(np.fft.rfft(x * self.win)) ** 2
        cs = np.concatenate(([0.0], np.cumsum(spec)))
        db = 10 * np.log10(cs[self.hi] - cs[self.lo] + 1e-12) + self.tilt
        top = float(db.max())
        if top > self.ref:
            self.ref += (top - self.ref) * 0.6
        else:
            self.ref -= 6.0 * dt                     # release ~6 dB/s
        if top > self.long_ref:
            self.long_ref += (top - self.long_ref) * 0.05
        else:
            self.long_ref -= 0.4 * dt
        self.ref = max(self.ref, self.long_ref - 14.0)
        lvl = (db - (self.ref - self.range)) / self.range
        return np.clip(lvl, 0.0, 1.0).astype(np.float32)


# ══════════════════════════════════════════════════════════════════════
#  NOW PLAYING  (Spotify Connect events over UDP, Bluetooth AVRCP over D-Bus)
# ══════════════════════════════════════════════════════════════════════
class NowPlaying:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.sp = {"title": "", "artist": "", "state": "stopped", "t": 0.0}
        self.bt = {"title": "", "artist": "", "status": "", "device": "", "connected": False}

    def start(self, with_bt=True):
        threading.Thread(target=self._udp, daemon=True).start()
        if with_bt:
            threading.Thread(target=self._bluez, daemon=True).start()

    def _udp(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("127.0.0.1", int(self.cfg["nowplaying_port"])))
        except OSError as e:
            print(f"[nowplaying] udp: {e}", file=sys.stderr)
            return
        while True:
            try:
                msg = json.loads(s.recv(4096).decode("utf-8", "replace"))
            except Exception:
                continue
            ev = msg.get("event", "")
            with self.lock:
                if msg.get("name"):
                    self.sp["title"] = msg["name"]
                    self.sp["artist"] = msg.get("artists", "").replace("\n", ", ")
                if ev in ("playing", "track_changed", "started", "changed", "loading"):
                    self.sp["state"] = "playing"
                elif ev == "paused":
                    self.sp["state"] = "paused"
                elif ev in ("stopped", "session_disconnected"):
                    self.sp["state"] = "stopped"
                self.sp["t"] = time.time()

    def _bluez(self):
        try:
            import dbus
        except ImportError:
            return
        bus = None
        while True:
            try:
                if bus is None:
                    bus = dbus.SystemBus()
                om = dbus.Interface(bus.get_object("org.bluez", "/"),
                                    "org.freedesktop.DBus.ObjectManager")
                objs = om.GetManagedObjects()
                info = {"title": "", "artist": "", "status": "", "device": "", "connected": False}
                for path, ifs in objs.items():
                    dev = ifs.get("org.bluez.Device1")
                    if dev and bool(dev.get("Connected", False)):
                        info["connected"] = True
                        info["device"] = str(dev.get("Alias", ""))
                    mp = ifs.get("org.bluez.MediaPlayer1")
                    if mp:
                        tr = mp.get("Track", {})
                        info["title"] = str(tr.get("Title", ""))
                        info["artist"] = str(tr.get("Artist", ""))
                        info["status"] = str(mp.get("Status", ""))
                with self.lock:
                    self.bt = info
            except Exception:
                bus = None
            time.sleep(2)

    def describe(self, has_signal):
        """-> (source label, scrolling text, connected-to-bt flag)"""
        with self.lock:
            sp, bt = dict(self.sp), dict(self.bt)
        if sp["state"] == "playing" and sp["title"]:
            return "SPOTIFY", f"{sp['artist']} - {sp['title']}", bt["connected"]
        if bt["status"] == "playing" or (bt["connected"] and has_signal):
            txt = f"{bt['artist']} - {bt['title']}" if bt["title"] else bt["device"] or "BLUETOOTH AUDIO"
            return "BT", txt, True
        if sp["state"] == "playing":
            return "SPOTIFY", "SPOTIFY CONNECT", bt["connected"]
        if has_signal:
            return "AUDIO", "LINE IN", bt["connected"]
        if sp["state"] == "paused" and sp["title"]:
            return "PAUSED", f"{sp['artist']} - {sp['title']}", bt["connected"]
        if bt["connected"]:
            return "BT", f"{bt['device']} CONNECTED", True
        return "READY", (f"SPOTIFY: PICK '{self.cfg['spotify_name']}'  -  "
                         f"BLUETOOTH: HOLD SCREEN, TAP PAIR"), False


# ══════════════════════════════════════════════════════════════════════
#  OUTPUT: raw RGB565 straight into the ILI9341 framebuffer
# ══════════════════════════════════════════════════════════════════════
class FrameBuffer:
    def __init__(self, cfg):
        self.cfg = cfg
        path = cfg["framebuffer"]
        if path == "auto":
            path = self.find()
        if not path:
            raise RuntimeError("no ILI9341 framebuffer found (is the fbtft overlay in config.txt?)")
        name = os.path.basename(path)
        sysd = f"/sys/class/graphics/{name}"
        self.bpp = int(open(f"{sysd}/bits_per_pixel").read())
        self.w, self.h = [int(v) for v in open(f"{sysd}/virtual_size").read().split(",")]
        self.stride = int(open(f"{sysd}/stride").read())
        if self.bpp != 16:
            raise RuntimeError(f"{path} is {self.bpp} bpp, expected 16")
        self.portrait = (self.w, self.h) == (H, W)
        self.f = open(path, "r+b")
        self.mm = mmap.mmap(self.f.fileno(), self.stride * self.h)
        self.view = np.frombuffer(self.mm, dtype=np.uint16).reshape(self.h, self.stride // 2)
        print(f"[fb] {path} {self.w}x{self.h} stride {self.stride}"
              + (" (portrait, rotating in software)" if self.portrait else ""))

    @staticmethod
    def find():
        for d in sorted(glob.glob("/sys/class/graphics/fb*")):
            try:
                n = open(f"{d}/name").read().strip().lower()
            except OSError:
                continue
            if "ili9341" in n or "ili9340" in n:
                return "/dev/" + os.path.basename(d)
        return None

    def show(self, surf, dim=1.0):
        a = np.frombuffer(pygame.image.tobytes(surf, "RGB"), np.uint8).reshape(H, W, 3)
        if dim < 0.999:
            a = (a.astype(np.uint16) * int(dim * 256) >> 8).astype(np.uint8)
        r, g, b = a[..., 0].astype(np.uint16), a[..., 1].astype(np.uint16), a[..., 2].astype(np.uint16)
        if self.cfg["swap_red_blue"]:
            r, b = b, r
        px = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        if self.cfg["rotate_180"]:
            px = px[::-1, ::-1]
        if self.portrait:
            px = np.rot90(px, -1)
        self.view[: px.shape[0], : px.shape[1]] = px

    def clear(self):
        self.view[:] = 0


class Backlight:
    """PWM on the LED pin via lgpio. Falls back to dimming the image itself."""

    def __init__(self, gpio):
        self.h = None
        self.gpio = gpio
        if gpio is None:
            return
        try:
            import lgpio
            self.lg = lgpio
            self.h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(self.h, gpio, 1)
        except Exception as e:
            print(f"[backlight] no PWM ({e}); dimming in software", file=sys.stderr)
            self.h = None

    @property
    def hardware(self):
        return self.h is not None

    def set(self, pct):
        if self.h is None:
            return
        try:
            if pct >= 100:
                self.lg.tx_pwm(self.h, self.gpio, 0, 0)
                self.lg.gpio_write(self.h, self.gpio, 1)
            elif pct <= 0:
                self.lg.tx_pwm(self.h, self.gpio, 0, 0)
                self.lg.gpio_write(self.h, self.gpio, 0)
            else:
                self.lg.tx_pwm(self.h, self.gpio, 1000, float(pct))
        except Exception as e:
            print(f"[backlight] {e}", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════
#  TOUCH  (XPT2046 via the kernel ads7846 driver, read with evdev)
# ══════════════════════════════════════════════════════════════════════
class Pointer:
    """Turns press/release into 'tap' and 'long' gestures."""
    LONG = 0.8

    def __init__(self):
        self.lock = threading.Lock()
        self.events = collections.deque()
        self.down = False
        self.t_down = 0.0
        self.t_up = 0.0
        self.pos = (0, 0)
        self.long_fired = False

    def press(self, pos):
        with self.lock:
            now = time.time()
            if self.down or now - self.t_up < 0.12:  # resistive panels bounce
                self.pos = pos
                self.down = True
                return
            self.down, self.t_down, self.pos, self.long_fired = True, now, pos, False

    def move(self, pos):
        with self.lock:
            if self.down:
                self.pos = pos

    def release(self):
        with self.lock:
            if not self.down:
                return
            now = time.time()
            dur = now - self.t_down
            self.down, self.t_up = False, now
            if not self.long_fired and 0.02 < dur < self.LONG:
                self.events.append(("tap", self.pos))

    def poll(self):
        with self.lock:
            if self.down and not self.long_fired and time.time() - self.t_down >= self.LONG:
                self.long_fired = True
                self.events.append(("long", self.pos))
            out = list(self.events)
            self.events.clear()
            return out


class Touch:
    def __init__(self, cfg, pointer, raw_cb=None):
        self.cfg = cfg["touch"]
        self.pointer = pointer
        self.raw_cb = raw_cb
        self.dev = None
        try:
            import evdev
            self.evdev = evdev
        except ImportError:
            print("[touch] python3-evdev missing; touch disabled", file=sys.stderr)
            return
        want = self.cfg.get("device", "auto")
        for p in evdev.list_devices():
            d = evdev.InputDevice(p)
            if (want != "auto" and p == want) or (want == "auto" and (
                    "ads7846" in d.name.lower() or "xpt2046" in d.name.lower()
                    or "touch" in d.name.lower())):
                self.dev = d
                break
        if self.dev:
            print(f"[touch] {self.dev.path} ({self.dev.name})")
            threading.Thread(target=self._run, daemon=True).start()
        else:
            print("[touch] no touchscreen found", file=sys.stderr)

    def to_screen(self, rx, ry):
        c = self.cfg
        if c.get("swap_xy"):
            rx, ry = ry, rx
        nx = (rx - c["x0"]) / float(c["x1"] - c["x0"] or 1)
        ny = (ry - c["y0"]) / float(c["y1"] - c["y0"] or 1)
        return (int(max(0, min(W - 1, nx * W))), int(max(0, min(H - 1, ny * H))))

    def _run(self):
        e = self.evdev.ecodes
        rx = ry = 0
        touching = was = False
        while True:
            try:
                for ev in self.dev.read_loop():
                    if ev.type == e.EV_ABS:
                        if ev.code == e.ABS_X:
                            rx = ev.value
                        elif ev.code == e.ABS_Y:
                            ry = ev.value
                    elif ev.type == e.EV_KEY and ev.code == e.BTN_TOUCH:
                        touching = bool(ev.value)
                    elif ev.type == e.EV_SYN:
                        if touching:
                            if self.raw_cb:
                                self.raw_cb(rx, ry, True)
                            pos = self.to_screen(rx, ry)
                            (self.pointer.move if was else self.pointer.press)(pos)
                        elif was:
                            if self.raw_cb:
                                self.raw_cb(rx, ry, False)
                            self.pointer.release()
                        was = touching
            except OSError as ex:
                print(f"[touch] {ex}; retrying", file=sys.stderr)
                time.sleep(2)


# ══════════════════════════════════════════════════════════════════════
#  DRAWING HELPERS
# ══════════════════════════════════════════════════════════════════════
def surface(size):
    return pygame.Surface(size, 0, 32)


def add_glow(core, strength=0.55, pad=GLOW_PAD):
    """Return core plus a soft halo (cheap blur: down-scale then up-scale)."""
    w, h = core.get_size()
    big = surface((w + 2 * pad, h + 2 * pad))
    big.fill((0, 0, 0))
    big.blit(core, (pad, pad))
    bw, bh = big.get_size()
    small = pygame.transform.smoothscale(big, (max(1, bw // 3), max(1, bh // 3)))
    small = pygame.transform.smoothscale(small, (max(1, bw // 6), max(1, bh // 6)))
    blur = pygame.transform.smoothscale(small, (bw, bh))
    k = int(max(0, min(255, strength * 255)))
    blur.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
    blur.blit(big, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return blur


def scaled(color, k):
    return tuple(int(c * k) for c in color)


class Text:
    """Dot-matrix text with glow, cached."""

    def __init__(self):
        self.cache = {}

    def render(self, text, color=CYAN, scale=2, glow=0.5):
        text = normalize(text)
        key = (text, color, scale, glow)
        s = self.cache.get(key)
        if s is not None:
            return s
        w = max(1, text_width(text, scale))
        core = surface((w, GLYPH_H * scale))
        core.fill((0, 0, 0))
        x = 0
        for ch in text:
            rows = GLYPHS.get(ch, GLYPHS["?"])
            for ry, bits in enumerate(rows):
                for cx in range(GLYPH_W):
                    if bits & (0x10 >> cx):
                        core.fill(color, (x + cx * scale, ry * scale, scale, scale))
            x += (GLYPH_W + 1) * scale
        s = add_glow(core, glow, pad=3) if glow else core
        if len(self.cache) > 300:
            self.cache.clear()
        self.cache[key] = s
        return s

    def draw(self, dst, text, pos, color=CYAN, scale=2, align="left", glow=0.5):
        s = self.render(text, color, scale, glow)
        pad = 3 if glow else 0
        x, y = pos
        if align == "center":
            x -= (s.get_width() - 2 * pad) // 2
        elif align == "right":
            x -= s.get_width() - 2 * pad
        dst.blit(s, (x - pad, y - pad), special_flags=pygame.BLEND_RGB_ADD)
        return s.get_width() - 2 * pad


# ══════════════════════════════════════════════════════════════════════
#  THE VISUALIZER
# ══════════════════════════════════════════════════════════════════════
class Visualizer:
    def __init__(self, cfg, state, nbands):
        self.cfg = cfg
        self.state = state
        self.nb = nbands
        self.text = Text()
        self.bw = 13
        self.bpitch = 17
        total_w = nbands * self.bpitch - (self.bpitch - self.bw) + int(NSEG * SLANT)
        self.x0 = (W - total_w) // 2
        self.cols = {}
        self.cur = np.zeros(nbands, np.float32)
        self.prev_lvl = np.zeros(nbands, np.float32)
        self.peak = np.zeros(nbands, np.float32)
        self.peak_t = np.zeros(nbands)
        self.laser = np.zeros(nbands, np.float32)
        self.drops = []  # [x, y, vy, life]
        self.wave = np.zeros(W, np.float32)
        self.wave_gain = 4.0
        self.scroll_x = 0.0
        self.scroll_key = None
        self.peak_spr = add_glow(self._solid((self.bw, 2), CYAN), 0.6)
        self.drop_spr = add_glow(self._solid((self.bw, 4), CYAN), 0.7)
        self.laser_spr = [add_glow(self._solid((W, 2), scaled(CYAN, k)), 0.8)
                          for k in (0.25, 0.5, 0.75, 1.0)]
        self.scope_bg = self._scope_bg()

    @staticmethod
    def _solid(size, color):
        s = surface(size)
        s.fill(color)
        return s

    def bar_x(self, i):
        return self.x0 + i * self.bpitch

    # one pre-rendered sprite per (lit segments, length, direction) = 1 blit per bar
    def column(self, lit, total, up=True):
        key = (lit, total, up)
        s = self.cols.get(key)
        if s is not None:
            return s
        core = surface((self.bw + int(math.ceil(total * SLANT)), total * PITCH))
        core.fill((0, 0, 0))
        for seg in range(total):
            col = vfd_color(seg / max(1, total - 1) if total < NSEG else seg / NSEG)
            if seg >= lit:
                col = scaled(col, 0.07)   # unlit VFD segments still glow faintly
            x = int(round(seg * SLANT))
            y = (total - 1 - seg) * PITCH + SEG_GAP if up else seg * PITCH
            core.fill(col, (x, y, self.bw, SEG_H))
        s = add_glow(core, 0.5)
        self.cols[key] = s
        return s

    def draw_bar(self, dst, i, base, level, total, up=True, peak=None):
        lit = int(max(0.0, min(1.0, level)) * total + 0.001)
        spr = self.column(lit, total, up)
        x = self.bar_x(i)
        y = base - total * PITCH if up else base
        dst.blit(spr, (x - GLOW_PAD, y - GLOW_PAD), special_flags=pygame.BLEND_RGB_ADD)
        if peak is not None and peak > 0.02:
            p = min(total - 1, int(peak * total))
            px = x + int(round(p * SLANT))
            py = base - (p + 1) * PITCH + SEG_GAP
            dst.blit(self.peak_spr, (px - GLOW_PAD, py - GLOW_PAD),
                     special_flags=pygame.BLEND_RGB_ADD)

    def _scope_bg(self):
        s = surface((W, H))
        s.fill((0, 0, 0))
        dim = (0, 34, 40)
        top, bot = HUD_TOP + 2, BASE
        for k in range(9):
            x = int(4 + k * (W - 8) / 8)
            for y in range(top, bot, 4):
                s.set_at((x, y), dim)
        for k in range(7):
            y = int(top + k * (bot - top) / 6)
            for x in range(4, W - 4, 4):
                s.set_at((x, y), dim)
        return s

    # ── per-frame update ──
    def update(self, lvl, dt):
        rise = 1 - (1 - 0.6) ** (dt * 30)
        fall = 1 - (1 - 0.28) ** (dt * 30)
        k = np.where(lvl > self.cur, rise, fall)
        self.cur += (lvl - self.cur) * k
        now = time.time()
        up = self.cur > self.peak
        self.peak[up] = self.cur[up]
        self.peak_t[up] = now
        old = (~up) & (now - self.peak_t > 0.9)
        self.peak[old] = np.maximum(0.0, self.peak[old] - 0.6 * dt)
        onset = (lvl > 0.72) & (lvl - self.prev_lvl > 0.06)
        self.prev_lvl = lvl.copy()
        self.laser = np.maximum(self.laser - 3.0 * dt, 0)
        self.laser[onset] = 1.0
        mode = MODES[self.state.mode]
        if mode == "RAIN DROP":
            for i in np.nonzero(onset)[0]:
                y = HUD_TOP + 4 + (1 - lvl[i]) * 60
                self.drops.append([self.bar_x(i) + 4, y, 0.0, 1.0])
        for d in self.drops:
            d[2] += 260 * dt
            d[1] += d[2] * dt
        self.drops = [d for d in self.drops if d[1] < BASE - 8 * PITCH][-60:]

    def draw(self, dst, samples):
        mode = MODES[self.state.mode]
        dst.fill((0, 0, 0))
        nb = self.nb
        if mode == "SPEANA":
            for i in range(nb):
                self.draw_bar(dst, i, BASE, self.cur[i], NSEG, True, self.peak[i])
        elif mode == "MAGNET":
            half = NSEG // 2
            for i in range(nb):
                self.draw_bar(dst, i, HUD_TOP + 2, self.cur[i], half, False)
                self.draw_bar(dst, i, BASE, self.cur[i], half, True)
        elif mode == "STADIUM":
            half = NSEG // 2
            mid = (HUD_TOP + 2 + BASE) // 2
            for i in range(nb):
                self.draw_bar(dst, i, mid, self.cur[i], half, True)
                self.draw_bar(dst, i, mid + SEG_GAP, self.cur[i], half, False)
        elif mode == "LASER":
            for i in range(nb):
                if self.laser[i] > 0:
                    y = BASE - 6 - i * ((BASE - HUD_TOP - 10) / nb)
                    spr = self.laser_spr[min(3, int(self.laser[i] * 4))]
                    dst.blit(spr, (-GLOW_PAD, int(y) - GLOW_PAD), special_flags=pygame.BLEND_RGB_ADD)
            for i in range(nb):
                self.draw_bar(dst, i, BASE, self.cur[i], NSEG, True, self.peak[i])
        elif mode == "SEASHORE":
            t = time.time()
            dst.set_clip(pygame.Rect(0, HUD_TOP + 1, W, BASE - HUD_TOP + 2))
            for i in range(nb):
                base = int(BASE - 12 + math.sin(t / 0.4 + i / 4.0) * 12)
                self.draw_bar(dst, i, base, self.cur[i], NSEG - 3, True, self.peak[i])
            dst.set_clip(None)
        elif mode == "RAIN DROP":
            short = 8
            for d in self.drops:
                dst.blit(self.drop_spr, (int(d[0]) - 4 - GLOW_PAD, int(d[1]) - GLOW_PAD),
                         special_flags=pygame.BLEND_RGB_ADD)
            for i in range(nb):
                self.draw_bar(dst, i, BASE, self.cur[i], short, True)
        elif mode == "VIBROSCOPE":
            self.draw_scope(dst, samples)

    def draw_scope(self, dst, x):
        dst.blit(self.scope_bg, (0, 0))
        n = len(x)
        # trigger on a rising zero crossing so the wave stands still
        seg = x[: n // 2]
        idx = np.nonzero((seg[:-1] < 0) & (seg[1:] >= 0))[0]
        start = int(idx[0]) if len(idx) else 0
        win = x[start: start + 3 * W]
        if len(win) < 3 * W:
            win = x[-3 * W:]
        y = win[::3][:W]
        peak = float(np.max(np.abs(y))) + 1e-6
        target = min(40.0, max(1.0, 0.7 / peak)) if peak > 1e-4 else self.wave_gain
        self.wave_gain += (target - self.wave_gain) * 0.1
        self.wave += (y * self.wave_gain - self.wave) * 0.5
        mid = (HUD_TOP + 2 + BASE) / 2
        amp = (BASE - HUD_TOP - 6) / 2
        ys = np.clip(mid - self.wave * amp, HUD_TOP + 3, BASE - 1)
        pts = list(zip(range(W), ys.astype(int).tolist()))
        for width, col in ((7, (0, 40, 48)), (4, (0, 120, 140)), (2, CYAN)):
            pygame.draw.lines(dst, col, False, pts, width)

    def draw_hud(self, dst, src, text, bt, pairing_left, dt):
        t = self.text
        t.draw(dst, MODES[self.state.mode], (4, 2), CYAN, 2)
        if self.cfg["show_clock"]:
            fmt = "%H:%M" if self.cfg["clock_24h"] else "%I:%M"
            t.draw(dst, time.strftime(fmt).lstrip("0") if not self.cfg["clock_24h"] else time.strftime(fmt),
                   (W - 4, 2), CYAN, 2, "right")
        if pairing_left > 0:
            m, s = divmod(int(pairing_left), 60)
            col = AMBER if int(time.time() * 2) % 2 else scaled(AMBER, 0.5)
            t.draw(dst, f"PAIR {m}:{s:02d}", (W // 2 + 18, 4), col, 1, "center", glow=0.6)
        elif bt:
            t.draw(dst, "\x03BT", (W // 2 + 18, 4), BLUE, 1, "center", glow=0.6)
        # bottom line: source + scrolling title
        y = BASE + 4
        label = f"{src} \x01"
        lw = t.draw(dst, label, (4, y), AMBER, 2, glow=0.45)
        x0 = 4 + lw + 8
        avail = W - 4 - x0
        surf = t.render(text, CYAN, 2, 0.45)
        tw = surf.get_width() - 6
        clip = pygame.Rect(x0, y - 3, avail, 20)
        dst.set_clip(clip)
        if tw <= avail:
            dst.blit(surf, (x0 - 3, y - 3), special_flags=pygame.BLEND_RGB_ADD)
            self.scroll_x = 0
        else:
            if self.scroll_key != text:
                self.scroll_key, self.scroll_x = text, -40.0   # short pause before scrolling
            self.scroll_x += 28 * dt
            gap = 60
            off = int(max(0, self.scroll_x)) % (tw + gap)
            dst.blit(surf, (x0 - 3 - off, y - 3), special_flags=pygame.BLEND_RGB_ADD)
            dst.blit(surf, (x0 - 3 - off + tw + gap, y - 3), special_flags=pygame.BLEND_RGB_ADD)
        dst.set_clip(None)


class Settings:
    """Long-press overlay: brightness -/+, PAIR, CLOSE."""
    TIMEOUT = 8.0

    def __init__(self, text):
        self.text = text
        self.open = False
        self.t = 0.0
        self.minus = pygame.Rect(12, 66, 64, 48)
        self.plus = pygame.Rect(W - 76, 66, 64, 48)
        self.pair = pygame.Rect(12, 150, 140, 48)
        self.close = pygame.Rect(W - 152, 150, 140, 48)

    def show(self):
        self.open, self.t = True, time.time()

    def tap(self, pos, app):
        self.t = time.time()
        if self.minus.collidepoint(pos):
            app.set_brightness(app.state.brightness - 15)
        elif self.plus.collidepoint(pos):
            app.set_brightness(app.state.brightness + 15)
        elif self.pair.collidepoint(pos):
            app.start_pairing()
            self.open = False
        elif self.close.collidepoint(pos):
            self.open = False

    def draw(self, dst, brightness):
        if self.open and time.time() - self.t > self.TIMEOUT:
            self.open = False
        if not self.open:
            return
        dst.fill((40, 40, 40), special_flags=pygame.BLEND_RGB_MULT)
        t = self.text
        t.draw(dst, "SETUP", (W // 2, 26), AMBER, 2, "center")
        t.draw(dst, "BRIGHTNESS", (W // 2, 52), CYAN, 1, "center")
        for r, label in ((self.minus, "-"), (self.plus, "+"), (self.pair, "PAIR BT"), (self.close, "CLOSE")):
            pygame.draw.rect(dst, CYAN, r, 2, border_radius=6)
            t.draw(dst, label, (r.centerx, r.centery - 7), CYAN, 2, "center")
        # brightness meter in VFD segments
        n, x, w = 10, 88, (W - 176)
        lit = int(round(brightness / 100 * n))
        for k in range(n):
            col = vfd_color(k / (n - 1)) if k < lit else (14, 14, 22)
            pygame.draw.rect(dst, col, (x + k * w // n + 1, 76, w // n - 3, 28))
        t.draw(dst, f"{brightness}%", (W // 2, 110), CYAN, 1, "center")


# ══════════════════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════════════════
class App:
    def __init__(self, args):
        self.args = args
        self.cfg = load_config(args.config)
        self.state = State()
        self.running = True
        pygame.display.init()
        self.window = None
        self.fb = None
        if args.window:
            self.window = pygame.display.set_mode((W * 2, H * 2))
            pygame.display.set_caption("Kenwood VFD visualizer (320x240 preview)")
        elif not args.snapshot:
            self.fb = FrameBuffer(self.cfg)
        self.frame = surface((W, H))
        self.audio = AudioSource(self.cfg, demo=args.demo or bool(args.snapshot))
        self.analyzer = Analyzer(self.cfg)
        self.vis = Visualizer(self.cfg, self.state, int(self.cfg["bands"]))
        self.settings = Settings(self.vis.text)
        self.np = NowPlaying(self.cfg)
        self.pointer = Pointer()
        self.backlight = Backlight(None if (args.window or args.snapshot) else self.cfg["backlight_gpio"])
        self.touch = None
        self.pair_until = 0.0
        self.last_signal = time.time()
        self.applied_bl = None

    def set_brightness(self, v):
        self.state.brightness = int(max(5, min(100, v)))
        self.state.save()

    def start_pairing(self):
        self.pair_until = time.time() + 180
        name = self.cfg["bt_name"]
        cmd = (f"bluetoothctl system-alias '{name}' >/dev/null 2>&1; "
               "bluetoothctl pairable on >/dev/null 2>&1; "
               "bluetoothctl discoverable-timeout 180 >/dev/null 2>&1; "
               "bluetoothctl discoverable on >/dev/null 2>&1")
        subprocess.Popen(["sh", "-c", cmd])

    def effective_brightness(self):
        b = self.state.brightness
        idle_min = self.cfg["idle_dim_minutes"]
        if idle_min and time.time() - self.last_signal > idle_min * 60 and not self.settings.open:
            b = min(b, int(self.cfg["idle_dim_brightness"]))
        return b

    def handle_input(self):
        if self.window:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.running = False
                elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.running = False
                elif ev.type == pygame.MOUSEBUTTONDOWN:
                    self.pointer.press((ev.pos[0] // 2, ev.pos[1] // 2))
                elif ev.type == pygame.MOUSEBUTTONUP:
                    self.pointer.release()
        for kind, pos in self.pointer.poll():
            self.last_signal = max(self.last_signal, time.time() - 1)  # wake from idle dim
            if self.settings.open:
                if kind == "tap":
                    self.settings.tap(pos, self)
            elif kind == "tap":
                self.state.mode = (self.state.mode + 1) % len(MODES)
                self.state.save()
            elif kind == "long":
                self.settings.show()

    def render(self, dt):
        samples = self.audio.latest(Analyzer.N)
        lvl = self.analyzer.process(samples, dt)
        has_signal = self.analyzer.rms_db > self.analyzer.silence
        if has_signal:
            self.last_signal = time.time()
        if not has_signal:
            samples = samples * 0
        self.vis.update(lvl, dt)
        self.vis.draw(self.frame, samples)
        src, text, bt = self.np.describe(has_signal)
        self.vis.draw_hud(self.frame, src, text, bt, self.pair_until - time.time(), dt)
        self.settings.draw(self.frame, self.state.brightness)

    def present(self):
        b = self.effective_brightness()
        if self.window:
            self.window.blit(pygame.transform.scale(self.frame, (W * 2, H * 2)), (0, 0))
            pygame.display.flip()
            return
        if self.backlight.hardware:
            if b != self.applied_bl:
                self.backlight.set(b)
                self.applied_bl = b
            self.fb.show(self.frame)
        else:
            self.fb.show(self.frame, dim=b / 100.0)

    def run(self):
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
        self.audio.start()
        self.np.start(with_bt=not self.args.window)
        if self.fb:
            self.touch = Touch(self.cfg, self.pointer)
        clock = pygame.time.Clock()
        fps = int(self.cfg["fps"])
        while self.running:
            dt = min(0.1, clock.tick(fps) / 1000.0) or 1.0 / fps
            self.handle_input()
            self.render(dt)
            self.present()
        if self.fb:
            self.fb.clear()
            self.backlight.set(0)
        pygame.quit()

    def snapshot(self, outdir):
        """Render every mode with demo audio and save PNGs (used for previews/tests)."""
        os.makedirs(outdir, exist_ok=True)
        self.audio.start()
        time.sleep(0.3)
        dt = 1 / 30
        self.np.sp.update(title="Instant Crush (feat. Julian Casablancas)",
                          artist="Daft Punk", state="playing")
        for m in range(len(MODES)):
            self.state.mode = m
            for _ in range(45):
                self.render(dt)
                time.sleep(dt)
            path = os.path.join(outdir, f"{m}_{MODES[m].replace(' ', '_').lower()}.png")
            pygame.image.save(self.frame, path)
            print(path)
        self.state.mode = 0
        self.settings.show()
        self.render(dt)
        pygame.image.save(self.frame, os.path.join(outdir, "settings.png"))
        self.settings.open = False
        self.np.sp.update(state="stopped", title="")
        self.audio.stop()


# ══════════════════════════════════════════════════════════════════════
#  TOUCH CALIBRATION
# ══════════════════════════════════════════════════════════════════════
def calibrate(args):
    cfg = load_config(args.config)
    pygame.display.init()
    fb = FrameBuffer(cfg)
    text = Text()
    frame = surface((W, H))
    samples, done = [], threading.Event()
    result = {}

    def raw_cb(rx, ry, down):
        if down:
            samples.append((rx, ry))
        elif samples:
            pts = samples[len(samples) // 3:] or samples   # skip the first wobbly readings
            result["p"] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            samples.clear()
            done.set()

    Touch(cfg, Pointer(), raw_cb)
    targets = [(20, 30), (W - 20, 30), (20, H - 30)]
    raws = []
    for tx, ty in targets:
        frame.fill((0, 0, 0))
        text.draw(frame, "TOUCH CALIBRATION", (W // 2, 90), AMBER, 2, "center")
        text.draw(frame, f"TAP THE CROSS  ({len(raws) + 1}/3)", (W // 2, 120), CYAN, 1, "center")
        pygame.draw.line(frame, CYAN, (tx - 10, ty), (tx + 10, ty), 2)
        pygame.draw.line(frame, CYAN, (tx, ty - 10), (tx, ty + 10), 2)
        fb.show(frame)
        done.clear()
        done.wait()
        raws.append(result["p"])
        time.sleep(0.3)
    (ax, ay), (bx, by), (cx, cy) = raws
    swap = abs(by - ay) > abs(bx - ax)       # moving right changed raw Y -> axes swapped
    if swap:
        ax, ay, bx, by, cx, cy = ay, ax, by, bx, cy, cx
    rpp_x = (bx - ax) / (targets[1][0] - targets[0][0])
    rpp_y = (cy - ay) / (targets[2][1] - targets[0][1])
    tcfg = {"device": cfg["touch"].get("device", "auto"), "swap_xy": swap,
            "x0": round(ax - targets[0][0] * rpp_x), "x1": round(ax + (W - targets[0][0]) * rpp_x),
            "y0": round(ay - targets[0][1] * rpp_y), "y1": round(ay + (H - targets[0][1]) * rpp_y)}
    user = {}
    if os.path.exists(args.config):
        try:
            user = json.load(open(args.config))
        except Exception:
            pass
    user["touch"] = tcfg
    try:
        with open(args.config, "w") as f:
            json.dump(user, f, indent=2)
        msg = "SAVED"
    except PermissionError:
        msg = "RUN WITH SUDO TO SAVE"
    print(json.dumps(tcfg, indent=2))
    frame.fill((0, 0, 0))
    text.draw(frame, "CALIBRATION " + msg, (W // 2, 110), GREEN, 1, "center")
    fb.show(frame)
    time.sleep(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=CONFIG_PATH)
    ap.add_argument("--window", action="store_true", help="desktop preview window instead of /dev/fb")
    ap.add_argument("--demo", action="store_true", help="fake music instead of the loopback")
    ap.add_argument("--snapshot", metavar="DIR", help="save a PNG of each mode and exit")
    ap.add_argument("--calibrate", action="store_true", help="touchscreen calibration")
    args = ap.parse_args()
    if args.calibrate:
        return calibrate(args)
    if args.snapshot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        App(args).snapshot(args.snapshot)
        return
    if not args.window:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    App(args).run()


if __name__ == "__main__":
    main()
