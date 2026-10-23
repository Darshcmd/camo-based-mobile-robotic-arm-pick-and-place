"""Every tunable lives here. Normal tuning never needs another file.

Adding a servo later = add one Channel(...) to CHANNELS and, if it needs a
new hand measurement, add that signal in tracker.py (see SIGNALS there).
"""
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Hardware
# --------------------------------------------------------------------------
SERIAL_PORT = "auto"     # "auto" picks the CH340/Arduino port, or e.g. "COM9"
BAUD = 115200
SEND_HZ = 30             # max frames/s sent to the Arduino
KEEPALIVE_S = 0.5        # resend unchanged angles this often

CAMERA = "Camo"          # device name (substring match) or index like 0
CAM_WIDTH = 1280
CAM_HEIGHT = 720
# Windows capture backend. Camo runs ~30 fps on "msmf" but only ~1 fps on
# "dshow". Try "dshow" only if a camera won't open with msmf.
CAM_BACKEND = "msmf"

# Orientation fix for the overhead camera. Goal: in the window, moving your
# hand RIGHT moves the reticle right, and moving it FARTHER from you moves the
# reticle UP. Toggle live with keys f / v / o, then copy the values here.
ROTATE = 90              # 0, 90, 180 or 270 (clockwise). Camo comes in sideways.
FLIP_H = False
FLIP_V = False

# --------------------------------------------------------------------------
# Hand tracking
# --------------------------------------------------------------------------
MODEL_COMPLEXITY = 1     # 0 = faster, 1 = more accurate
TRACK_WIDTH = 640        # frame is downscaled to this width for tracking only
DETECT_CONF = 0.6
TRACK_CONF = 0.5

# Working zone in normalised frame coords (x0, y0, x1, y1). The hand's
# position inside this box becomes the 0..1 "lr" and "far" signals; outside
# it is clamped. Shrink it if you can't comfortably reach the edges.
ZONE = (0.15, 0.10, 0.85, 0.90)

# Grip (fist) detection: a finger counts as extended when its tip is this
# much farther from the wrist than its middle knuckle.
FINGER_EXTENDED_RATIO = 1.15
OPEN_MIN_FINGERS = 3     # >= this many extended  -> open
CLOSED_MAX_FINGERS = 1   # <= this many extended  -> fist
GRIP_DEBOUNCE_FRAMES = 3 # frames a new grip state must hold before it counts

TRAIL_LEN = 24           # HUD trail length (frames)

# --------------------------------------------------------------------------
# Real-world scale: hand centimetres -> claw centimetres
# --------------------------------------------------------------------------
# Your hand is the ruler: the wrist-to-middle-knuckle length is measured every
# frame to convert pixels to cm, so the scale stays right whatever height the
# camera or your hand is at. Measure yours (adults are usually 8.5-10 cm).
PALM_CM = 9.0
SCALE_SMOOTH_S = 1.5     # time constant for the ruler; higher = steadier scale

# Arm geometry - measure these with a ruler on your arm at the start pose.
ARM_REACH_CM = 20.0       # base rotation axis -> claw tip, horizontally
SHOULDER_TO_TIP_CM = 25.0 # shoulder pivot -> claw tip

# 1.0 = the claw tip moves the same distance as your hand (true 1:1).
# 2.0 = claw moves twice as far as your hand. Live slider in Tuning window.
MOTION_SCALE = 1.0

# Hand position (normalised, after orientation) that maps to the start pose.
# Press c with your hand in view to make its current spot the new home.
HOME = (0.5, 0.6)


# --------------------------------------------------------------------------
# Servo channels
# --------------------------------------------------------------------------
@dataclass
class Channel:
    servo: int            # servo index on the Arduino (0-5)
    name: str
    signal: str           # hand signal driving it - see SIGNALS in tracker.py
    out_range: tuple      # servo angle limits (or angle at in_range start, end)
    start: float          # angle at startup; keep equal to the sketch's start angle
    # Mapping, pick one:
    #   gain set   -> angle = start + gain * signal   (for yaw/pitch, in degrees)
    #   gain None  -> signal in_range is stretched onto out_range (for grip etc.)
    gain: float = None
    in_range: tuple = (0.0, 1.0)
    # Smoothing (One Euro filter, in degrees). Tunable live in the Tuning window.
    min_cutoff: float = 1.0   # Hz. Lower = steadier when still, more lag
    beta: float = 0.02        # Higher = less lag on fast moves
    max_speed: float = 180.0  # deg/s slew limit, protects gears and wiring
    deadband: float = 1.0     # deg; ignore smaller changes (kills buzz)


CHANNELS = [
    # yaw = how far the claw must swing for your sideways move (degrees).
    # hand right -> angle drops toward 0 (clockwise), left -> toward 180.
    Channel(0, "base", "yaw", (0, 180), start=90, gain=-1.0,
            min_cutoff=0.8, beta=0.02, max_speed=150),
    # pitch = shoulder swing for your forward/back move (degrees).
    # hand farther -> angle rises toward 180 (down), nearer -> toward 30 (up).
    Channel(1, "shoulder", "pitch", (30, 180), start=90, gain=1.0,
            min_cutoff=0.8, beta=0.02, max_speed=120),
    # open hand -> 70, fist -> 25
    Channel(5, "claw", "grip", (70, 25), start=70,
            min_cutoff=20.0, beta=0.0, max_speed=300, deadband=0.0),
]

SHOW_TUNING_WINDOW = True
