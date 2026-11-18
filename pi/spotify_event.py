#!/usr/bin/env python3
"""librespot/raspotify --onevent hook.

librespot runs this on every player event with the details in environment
variables (PLAYER_EVENT, NAME, ARTISTS, ...). We forward them to the
visualizer as one small JSON packet on 127.0.0.1:5555 so it can show the
track name. Never blocks and never fails loudly: playback must not care.
"""
import json
import os
import socket

msg = {"source": "spotify", "event": os.environ.get("PLAYER_EVENT", "")}
for key in ("NAME", "ARTISTS", "ALBUM", "TRACK_ID", "DURATION_MS", "POSITION_MS"):
    if os.environ.get(key):
        msg[key.lower()] = os.environ[key]
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(json.dumps(msg).encode("utf-8"), ("127.0.0.1", 5555))
except OSError:
    pass
