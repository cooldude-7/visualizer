#!/usr/bin/env python3
"""Slow bit-banged ILI9341 test: talks to the screen by toggling the GPIO pins
by hand, without the SPI hardware or the fbtft driver. Speed doesn't matter here,
so this tells you whether the screen and its wires work at all.

Run (the visualizer + drivers must be out of the way first):
    sudo systemctl stop kenwood-vis
    sudo rmmod fb_ili9341 fbtft ads7846 spi_bcm2835
    sudo python3 screen_test.py
Afterwards:  sudo reboot

Expected: white -> random coloured noise -> red, green, blue squares -> the
screen flashes inverted 4 times. If it stays white the whole time, a wire
(CS / DC / RESET / SDI / SCK) or the board is the problem.
"""
import sys
import time

import lgpio

CS, DC, RST, MOSI, SCK = 8, 24, 25, 10, 11   # BCM numbers (pins 24, 18, 22, 19, 23)

h = lgpio.gpiochip_open(0)
for pin, level in ((CS, 1), (DC, 1), (RST, 1), (MOSI, 0), (SCK, 0)):
    err = lgpio.gpio_claim_output(h, pin, level)
    if err < 0:
        sys.exit(f"GPIO{pin} is busy ({lgpio.error_text(err)}). Run the rmmod line from the top of this file first.")

w = lgpio.gpio_write


def send(b):
    for i in range(7, -1, -1):
        w(h, MOSI, (b >> i) & 1)
        w(h, SCK, 1)
        w(h, SCK, 0)


def cmd(c, *data):
    w(h, CS, 0)
    w(h, DC, 0)
    send(c)
    w(h, DC, 1)
    for d in data:
        send(d)
    w(h, CS, 1)


def square(x, y, size, rgb565):
    x2, y2 = x + size - 1, y + size - 1
    cmd(0x2A, x >> 8, x & 255, x2 >> 8, x2 & 255)   # column range
    cmd(0x2B, y >> 8, y & 255, y2 >> 8, y2 & 255)   # row range
    w(h, CS, 0)
    w(h, DC, 0)
    send(0x2C)                                       # write pixels
    w(h, DC, 1)
    hi, lo = rgb565 >> 8, rgb565 & 255
    for _ in range(size * size):
        send(hi)
        send(lo)
    w(h, CS, 1)


print("1. hardware reset (RESET wire)")
w(h, RST, 0); time.sleep(0.05); w(h, RST, 1); time.sleep(0.15)
print("2. software reset + wake up")
cmd(0x01); time.sleep(0.15)
cmd(0x11); time.sleep(0.15)       # sleep out
cmd(0x3A, 0x55)                   # 16-bit colour
cmd(0x36, 0x48)                   # orientation
cmd(0x29); time.sleep(0.05)       # display on
print("   -> the screen should now show RANDOM COLOURED NOISE instead of white")
time.sleep(2)
print("3. drawing red, green, blue squares (takes a few seconds)")
square(20, 20, 50, 0xF800)
square(95, 20, 50, 0x07E0)
square(170, 20, 50, 0x001F)
print("4. flashing inverted 4 times")
for _ in range(4):
    cmd(0x21); time.sleep(0.4)
    cmd(0x20); time.sleep(0.4)
print("Done. Did the screen change at all? Reboot afterwards: sudo reboot")
lgpio.gpiochip_close(h)
