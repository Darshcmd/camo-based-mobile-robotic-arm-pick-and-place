"""MediaPipe hand tracking -> named signals.

SIGNALS produced (use these names in config.Channel.signal):
    yaw    deg the base must turn so the claw tip follows your sideways move
           1:1 (x MOTION_SCALE). + = hand moved right of HOME
    pitch  deg the shoulder must swing so the claw tip follows your forward
           move 1:1 (x MOTION_SCALE). + = hand moved farther than HOME
    dx_cm, dy_cm  hand offset from HOME in real cm (+x right, +y farther)
    grip   0 = open hand, 1 = fist (debounced)
    roll   hand rotation in degrees, 0 = fingers pointing up the frame
    lr, far  0..1 position inside ZONE (old absolute mapping)
"""
import math
import time
from dataclasses import dataclass, field

import cv2
import mediapipe as mp

import config as cfg

PALM = (0, 5, 9, 13, 17)
TIPS = (8, 12, 16, 20)
PIPS = (6, 10, 14, 18)
CONNECTIONS = tuple(mp.solutions.hands.HAND_CONNECTIONS)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class Hand:
    pts: list                 # 21 landmarks in pixels
    palm: tuple               # palm centre in pixels
    fingers: int              # extended fingers (thumb ignored)
    closed: bool
    signals: dict = field(default_factory=dict)


class HandTracker:
    def __init__(self):
        self.hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=cfg.MODEL_COMPLEXITY,
            min_detection_confidence=cfg.DETECT_CONF,
            min_tracking_confidence=cfg.TRACK_CONF,
        )
        self.closed = False
        self._streak = 0
        self.home = list(cfg.HOME)   # normalised
        self.cm_per_px = None        # smoothed hand-ruler scale
        self._scale_t = None
        self._last_palm_norm = None

    def set_home(self):
        """Make the hand's current spot map to the start pose."""
        if self._last_palm_norm:
            self.home = list(self._last_palm_norm)

    def _update_scale(self, palm_px):
        if palm_px < 5:
            return
        now = time.monotonic()
        sample = cfg.PALM_CM / palm_px
        if self.cm_per_px is None:
            self.cm_per_px = sample
        else:
            a = 1 - math.exp(-(now - self._scale_t) / cfg.SCALE_SMOOTH_S)
            self.cm_per_px += a * (sample - self.cm_per_px)
        self._scale_t = now

    def _debounce_grip(self, fingers):
        if fingers <= cfg.CLOSED_MAX_FINGERS:
            want = True
        elif fingers >= cfg.OPEN_MIN_FINGERS:
            want = False
        else:
            want = self.closed  # in between: keep current state
        if want != self.closed:
            self._streak += 1
            if self._streak >= cfg.GRIP_DEBOUNCE_FRAMES:
                self.closed = want
                self._streak = 0
        else:
            self._streak = 0

    def process(self, frame_bgr):
        h, w = frame_bgr.shape[:2]
        small = frame_bgr
        if w > cfg.TRACK_WIDTH:  # landmarks are normalised, so this is free accuracy-wise
            small = cv2.resize(frame_bgr, (cfg.TRACK_WIDTH, int(h * cfg.TRACK_WIDTH / w)),
                               interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        res = self.hands.process(rgb)
        if not res.multi_hand_landmarks:
            return None

        pts = [(p.x * w, p.y * h) for p in res.multi_hand_landmarks[0].landmark]
        palm = (sum(pts[i][0] for i in PALM) / len(PALM),
                sum(pts[i][1] for i in PALM) / len(PALM))

        wrist = pts[0]
        fingers = sum(_dist(wrist, pts[t]) > _dist(wrist, pts[p]) * cfg.FINGER_EXTENDED_RATIO
                      for t, p in zip(TIPS, PIPS))
        self._debounce_grip(fingers)

        mid = pts[9]
        self._update_scale(_dist(wrist, mid))
        self._last_palm_norm = (palm[0] / w, palm[1] / h)

        # Real-world offset from HOME, then the joint angles that move the
        # claw tip by the same distance (scaled by MOTION_SCALE).
        dx_cm = (palm[0] - self.home[0] * w) * self.cm_per_px
        dy_cm = (self.home[1] * h - palm[1]) * self.cm_per_px
        k = cfg.MOTION_SCALE
        yaw = math.degrees(math.atan2(dx_cm * k, cfg.ARM_REACH_CM))
        pitch = math.degrees(dy_cm * k / cfg.SHOULDER_TO_TIP_CM)  # arc length -> angle

        x0, y0, x1, y1 = cfg.ZONE
        clamp01 = lambda v: min(max(v, 0.0), 1.0)
        signals = {
            "yaw": yaw,
            "pitch": pitch,
            "dx_cm": dx_cm,
            "dy_cm": dy_cm,
            "lr": clamp01((palm[0] / w - x0) / (x1 - x0)),
            "far": clamp01((y1 - palm[1] / h) / (y1 - y0)),
            "grip": 1.0 if self.closed else 0.0,
            "roll": math.degrees(math.atan2(mid[0] - wrist[0], wrist[1] - mid[1])),
        }
        return Hand(pts, palm, fingers, self.closed, signals)

    def close(self):
        self.hands.close()
