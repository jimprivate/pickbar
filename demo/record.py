#!/usr/bin/env python3
"""Record demo.gif by driving `python -m pickbar` under ConPTY (Windows).

Runs the real program, replays a key script, reconstructs every screen state
with pyte, and renders frames with Pillow using Maple Mono NF CN.
Requires: pip install pywinpty pyte pillow
"""
import os
import threading
import time
import unicodedata
from pathlib import Path

import pyte
import winpty
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
COLS, ROWS = 88, 22
FONT_SIZE = 22
BG, FG = (30, 31, 41), (222, 222, 215)
BAR_BG, BAR_FG = (222, 222, 215), (30, 31, 41)
PAD, TITLEBAR = 24, 36

# Neutral staging directory so the recording never shows a real local path.
STAGE = Path("C:/Users/Public/demo/project")

# (seconds to wait before sending, keys)
SCRIPT = [
    (1.2, "\x1b[B"), (0.55, "\x1b[B"), (0.55, "\x1b[A"), (0.6, "\r"),
    (1.1, " "), (0.5, " "), (0.5, "\x1b[B"), (0.45, " "), (0.8, "\r"),
    (1.2, "d"), (0.3, "o"), (0.9, "\r"), (0.9, "\r"),
]
TAIL = 2.2

FONT = ImageFont.truetype(
    str(Path.home() / "AppData/Local/Microsoft/Windows/Fonts/MapleMono-NF-CN-Regular.ttf"),
    FONT_SIZE)
CELL_W = int(FONT.getlength("M"))
CELL_H = FONT_SIZE + 8


def snapshot(screen):
    rows = []
    for y in range(ROWS):
        row = []
        for x in range(COLS):
            c = screen.buffer[y][x]
            row.append((c.data, c.reverse))
        rows.append(tuple(row))
    return tuple(rows)


def render(snap):
    w = COLS * CELL_W + PAD * 2
    h = ROWS * CELL_H + PAD * 2 + TITLEBAR
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    for i, col in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse((PAD + i * 26, 14, PAD + i * 26 + 14, 28), fill=col)
    for y, row in enumerate(snap):
        px, py = PAD, TITLEBAR + PAD + y * CELL_H
        for ch, rev in row:
            if ch == "":  # wide-char continuation cell
                continue
            cw = CELL_W * (2 if unicodedata.east_asian_width(ch) in "WF" else 1)
            if rev:
                d.rectangle((px, py, px + cw, py + CELL_H - 1), fill=BAR_BG)
                d.text((px, py + 3), ch, font=FONT, fill=BAR_FG)
            elif ch != " ":
                d.text((px, py + 3), ch, font=FONT, fill=FG)
            px += cw
    return img


def main():
    for sub in ("src", "docs", "assets"):
        (STAGE / sub).mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.Stream(screen)
    lock = threading.Lock()
    proc = winpty.PtyProcess.spawn("python -m pickbar",
                                   dimensions=(ROWS, COLS), cwd=str(STAGE),
                                   env=env)

    def reader():
        while True:
            try:
                data = proc.read(4096)
            except Exception:
                return
            if not data:
                return
            with lock:
                stream.feed(data)

    threading.Thread(target=reader, daemon=True).start()

    frames, durations = [], []
    last = None
    t_prev = time.time()

    def sample():
        nonlocal last, t_prev
        with lock:
            snap = snapshot(screen)
        now = time.time()
        if snap != last:
            if last is not None:
                durations.append(max(30, int((now - t_prev) * 1000)))
            frames.append(snap)
            last, t_prev = snap, now

    def watch(seconds):
        end = time.time() + seconds
        while time.time() < end:
            sample()
            time.sleep(0.05)

    for delay, keys in SCRIPT:
        watch(delay)
        proc.write(keys)
    watch(TAIL)
    durations.append(1800)  # hold the final frame
    try:
        proc.terminate()
    except Exception:
        pass

    # Drop leading frames captured before the first menu draw.
    while frames and all(ch == " " for row in frames[0] for ch, _ in row):
        frames.pop(0)
        durations.pop(0)

    imgs = [render(s) for s in frames]
    out = ROOT / "demo.gif"
    imgs[0].save(out, save_all=True, append_images=imgs[1:],
                 duration=durations, loop=0, optimize=True)
    print(f"{out}: {len(imgs)} frames, {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
