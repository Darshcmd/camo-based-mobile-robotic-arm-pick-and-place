"""Sci-fi overlay: hand net, reticle, trail, servo gauges, status."""
import math
import time

import cv2
import numpy as np

from tracker import CONNECTIONS, TIPS

# BGR
CYAN = (255, 220, 40)
MAGENTA = (220, 70, 255)
AMBER = (0, 190, 255)
GREEN = (120, 255, 140)
RED = (70, 70, 255)
WHITE = (240, 240, 240)
DIM = (110, 110, 110)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _p(pt):
    return int(pt[0]), int(pt[1])


def _text(img, s, org, color=WHITE, scale=0.5, thick=1):
    cv2.putText(img, s, org, FONT, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


_grid_cache = {}


def _grid(shape, step=48):
    """Black image with faint grid lines, cached per frame size."""
    if shape not in _grid_cache:
        layer = np.zeros(shape, np.uint8)
        h, w = shape[:2]
        for x in range(0, w, step):
            cv2.line(layer, (x, 0), (x, h), (50, 40, 10), 1)
        for y in range(0, h, step):
            cv2.line(layer, (0, y), (w, y), (50, 40, 10), 1)
        _grid_cache[shape] = layer
    return _grid_cache[shape]


def _brackets(img, zone, color, arm=28, thick=2):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = int(zone[0] * w), int(zone[1] * h), int(zone[2] * w), int(zone[3] * h)
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        cv2.line(img, (cx, cy), (cx + dx * arm, cy), color, thick, cv2.LINE_AA)
        cv2.line(img, (cx, cy), (cx, cy + dy * arm), color, thick, cv2.LINE_AA)
    _text(img, "FAR", ((x0 + x1) // 2 - 14, y0 - 8), DIM, 0.45)
    _text(img, "NEAR", ((x0 + x1) // 2 - 18, y1 + 18), DIM, 0.45)


def _hand_glow(glow, hand, color):
    pts = [_p(p) for p in hand.pts]
    for a, b in CONNECTIONS:
        cv2.line(glow, pts[a], pts[b], color, 9, cv2.LINE_AA)
    for i in TIPS + (4,):
        cv2.circle(glow, pts[i], 14, color, -1, cv2.LINE_AA)
    cv2.circle(glow, _p(hand.palm), 26, color, 6, cv2.LINE_AA)


def _hand_net(img, hand, color):
    pts = [_p(p) for p in hand.pts]
    for a, b in CONNECTIONS:
        cv2.line(img, pts[a], pts[b], color, 2, cv2.LINE_AA)
    for pt in pts:
        cv2.circle(img, pt, 4, WHITE, -1, cv2.LINE_AA)
        cv2.circle(img, pt, 6, color, 1, cv2.LINE_AA)
    for i in TIPS + (4,):
        cv2.circle(img, pts[i], 10, color, 1, cv2.LINE_AA)


def _reticle(img, center, color, t):
    c = _p(center)
    cv2.circle(img, c, 26, color, 1, cv2.LINE_AA)
    spin = int(t * 180) % 360
    cv2.ellipse(img, c, (36, 36), spin, 0, 70, color, 2, cv2.LINE_AA)
    cv2.ellipse(img, c, (36, 36), spin + 180, 0, 70, color, 2, cv2.LINE_AA)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cv2.line(img, (c[0] + dx * 8, c[1] + dy * 8), (c[0] + dx * 18, c[1] + dy * 18), WHITE, 1, cv2.LINE_AA)


def _trail(img, trail, color):
    n = len(trail)
    for i in range(1, n):
        k = i / n
        col = tuple(int(c * k) for c in color)
        cv2.line(img, _p(trail[i - 1]), _p(trail[i]), col, max(1, int(4 * k)), cv2.LINE_AA)


def _gauges(img, states, hand):
    h, w = img.shape[:2]
    pw, row = 300, 54
    x0, y0 = w - pw - 16, 16
    panel = img[y0:y0 + row * len(states) + 12, x0:x0 + pw]
    panel[:] = (panel * 0.35).astype(panel.dtype)
    for i, st in enumerate(states):
        ch = st.ch
        y = y0 + 22 + i * row
        sig = hand.signals.get(ch.signal) if hand else None
        sig_s = "--" if sig is None else f"{sig:.2f}"
        _text(img, f"S{ch.servo} {ch.name.upper()}", (x0 + 10, y), CYAN, 0.5)
        _text(img, f"{ch.signal}={sig_s}", (x0 + 150, y), DIM, 0.45)
        _text(img, f"{st.angle:3d}", (x0 + pw - 44, y), WHITE, 0.55, 1)
        bx0, bx1, by = x0 + 10, x0 + pw - 10, y + 12
        cv2.rectangle(img, (bx0, by), (bx1, by + 10), DIM, 1)
        span = (st.hi - st.lo) or 1
        fx = lambda a: int(bx0 + (a - st.lo) / span * (bx1 - bx0))
        cv2.rectangle(img, (bx0, by), (fx(st.current), by + 10), CYAN, -1)
        tx = fx(st.target)
        cv2.line(img, (tx, by - 4), (tx, by + 14), AMBER, 2)
        _text(img, f"{st.lo}", (bx0, by + 24), DIM, 0.35)
        _text(img, f"{st.hi}", (bx1 - 22, by + 24), DIM, 0.35)


def _home_and_ruler(img, hand, ui):
    """Home crosshair, hand->home offset in cm, and a 5 cm scale bar."""
    h, w = img.shape[:2]
    home = (int(ui["home"][0] * w), int(ui["home"][1] * h))
    cv2.drawMarker(img, home, AMBER, cv2.MARKER_CROSS, 30, 1, cv2.LINE_AA)
    cv2.circle(img, home, 6, AMBER, 1, cv2.LINE_AA)
    _text(img, "HOME", (home[0] + 10, home[1] - 10), AMBER, 0.45)
    cpp = ui["cm_per_px"]
    if not cpp:
        return
    if hand:
        p = _p(hand.palm)
        cv2.line(img, home, p, AMBER, 1, cv2.LINE_AA)
        dx, dy = hand.signals["dx_cm"], hand.signals["dy_cm"]
        _text(img, f"{dx:+.1f} / {dy:+.1f} cm", (p[0] + 40, p[1] + 50), AMBER, 0.5)
    bar = int(5 / cpp)  # 5 cm in pixels at hand height
    x0, y0 = 16, h - 60
    cv2.line(img, (x0, y0), (x0 + bar, y0), WHITE, 2)
    for x in (x0, x0 + bar):
        cv2.line(img, (x, y0 - 6), (x, y0 + 6), WHITE, 2)
    _text(img, f"5 cm   view {w * cpp:.0f} x {h * cpp:.0f} cm   scale x{ui['motion_scale']:.2f}",
          (x0, y0 - 12), WHITE, 0.45)


def draw(frame, hand, states, ui):
    """ui: dict with armed, fps, link, trail, last_line, orient, home,
    cm_per_px, motion_scale"""
    t = time.monotonic()
    color = MAGENTA if (hand and hand.closed) else CYAN
    if hand:
        glow = _grid(frame.shape).copy()
        _hand_glow(glow, hand, color)
        cv2.addWeighted(frame, 1.0, glow, 0.5, 0, frame)  # additive glow
    else:
        cv2.add(frame, _grid(frame.shape), frame)
    _trail(frame, ui["trail"], color)
    if hand:  # crisp layer on top of the blend
        _hand_net(frame, hand, color)
        _reticle(frame, hand.palm, color, t)
    _home_and_ruler(frame, hand, ui)
    _gauges(frame, states, hand)

    # status block
    armed = ui["armed"]
    pulse = 0.5 + 0.5 * math.sin(t * 6)
    st_col = tuple(int(c * (0.6 + 0.4 * pulse)) for c in RED) if armed else GREEN
    _text(frame, "ARMED - SENDING" if armed else "SAFE - NOT SENDING", (16, 32), st_col, 0.75, 2)
    _text(frame, f"LINK {ui['link']}   {ui['fps']:4.1f} FPS   {ui['orient']}", (16, 58), WHITE, 0.5)
    if hand:
        grip = "FIST" if hand.closed else "OPEN"
        _text(frame, f"HAND LOCK  grip={grip}  fingers={hand.fingers}", (16, 82), color, 0.5)
    else:
        _text(frame, "NO HAND - HOLDING", (16, 82), AMBER, 0.5)
    if ui["last_line"]:
        _text(frame, f"TX {ui['last_line']}", (16, 106), DIM, 0.45)

    h = frame.shape[0]
    _text(frame, "SPACE arm   c set home   p print tuning   q quit", (16, h - 32), DIM, 0.45)
    _text(frame, "f flipH   v flipV   o rotate", (16, h - 12), DIM, 0.45)
    return frame
