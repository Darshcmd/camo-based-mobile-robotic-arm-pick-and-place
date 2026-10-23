"""Camo based Mobile Robotic Arm Pick and Place.

Gesture-controlled 6-DOF robot arm: overhead camera -> hand signals -> servos.

    python main.py                  # Camo + auto-detected Arduino
    python main.py --dry-run        # no serial, just the HUD
    python main.py --list-cameras
    python main.py --camera 1 --port COM9
"""
import argparse
import time
from collections import deque

import cv2

import camera
import config as cfg
import hud
from channels import ChannelState
from link import ArmLink
from tracker import HandTracker

WIN = "Gesture Arm"
TUNE_WIN = "Tuning"


class TuningPanel:
    """One set of sliders per channel; edits the Channel objects live."""

    def __init__(self, states):
        self.states = states
        cv2.namedWindow(TUNE_WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(TUNE_WIN, 420, 100 + 140 * len(states))
        cv2.createTrackbar("motion scale x100", TUNE_WIN, int(cfg.MOTION_SCALE * 100), 400, lambda _: None)
        for st in states:
            n = st.ch.name
            cv2.createTrackbar(f"{n} cutoff x100", TUNE_WIN, int(st.ch.min_cutoff * 100), 2000, lambda _: None)
            cv2.createTrackbar(f"{n} beta x1000", TUNE_WIN, int(st.ch.beta * 1000), 200, lambda _: None)
            cv2.createTrackbar(f"{n} speed deg/s", TUNE_WIN, int(st.ch.max_speed), 600, lambda _: None)

    def read(self):
        cfg.MOTION_SCALE = max(cv2.getTrackbarPos("motion scale x100", TUNE_WIN), 5) / 100
        for st in self.states:
            n = st.ch.name
            st.ch.min_cutoff = cv2.getTrackbarPos(f"{n} cutoff x100", TUNE_WIN) / 100
            st.ch.beta = cv2.getTrackbarPos(f"{n} beta x1000", TUNE_WIN) / 1000
            st.ch.max_speed = max(cv2.getTrackbarPos(f"{n} speed deg/s", TUNE_WIN), 1)


def print_tuning(states, orient, tracker):
    print("\n# --- paste into config.py ---")
    print(f"ROTATE = {orient['rotate']}\nFLIP_H = {orient['flip_h']}\nFLIP_V = {orient['flip_v']}")
    print(f"MOTION_SCALE = {cfg.MOTION_SCALE:.2f}")
    print(f"HOME = ({tracker.home[0]:.2f}, {tracker.home[1]:.2f})")
    for st in states:
        c = st.ch
        print(f"#  {c.name}: min_cutoff={c.min_cutoff:.2f}, beta={c.beta:.3f}, max_speed={c.max_speed:.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", default=cfg.CAMERA)
    ap.add_argument("--port", default=cfg.SERIAL_PORT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-cameras", action="store_true")
    args = ap.parse_args()

    if args.list_cameras:
        camera.list_cameras()
        return

    cap = camera.open_camera(args.camera, cfg.CAM_WIDTH, cfg.CAM_HEIGHT, cfg.CAM_BACKEND)
    link = ArmLink(args.port, cfg.BAUD, cfg.SEND_HZ, cfg.KEEPALIVE_S, args.dry_run)
    tracker = HandTracker()
    states = [ChannelState(ch) for ch in cfg.CHANNELS]

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    tuning = TuningPanel(states) if cfg.SHOW_TUNING_WINDOW else None

    orient = {"rotate": cfg.ROTATE, "flip_h": cfg.FLIP_H, "flip_v": cfg.FLIP_V}
    trail = deque(maxlen=cfg.TRAIL_LEN)
    armed = False
    fps, t_prev, misses = 0.0, time.monotonic(), 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                misses += 1
                if misses > 60:
                    raise SystemExit("Camera stopped delivering frames.")
                cv2.waitKey(10)
                continue
            misses = 0
            frame = camera.orient(frame, orient["rotate"], orient["flip_h"], orient["flip_v"])

            now = time.monotonic()
            fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-3)
            t_prev = now

            if tuning:
                tuning.read()
            hand = tracker.process(frame)
            if hand:
                trail.append(hand.palm)
            elif trail:
                trail.popleft()

            for st in states:
                st.update(hand.signals if hand else None, now, armed)
            if armed:
                link.send({st.ch.servo: st.angle for st in states}, now)
            link.poll()

            orient_s = f"rot{orient['rotate']}{' fH' if orient['flip_h'] else ''}{' fV' if orient['flip_v'] else ''}"
            hud.draw(frame, hand, states, {
                "armed": armed, "fps": fps, "link": link.label, "zone": cfg.ZONE,
                "trail": trail, "last_line": link.last_line, "orient": orient_s,
                "home": tracker.home, "cm_per_px": tracker.cm_per_px,
                "motion_scale": cfg.MOTION_SCALE,
            })
            cv2.imshow(WIN, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord(" "):
                armed = not armed
                print("ARMED" if armed else "disarmed")
            elif key == ord("f"):
                orient["flip_h"] = not orient["flip_h"]
            elif key == ord("v"):
                orient["flip_v"] = not orient["flip_v"]
            elif key == ord("o"):
                orient["rotate"] = (orient["rotate"] + 90) % 360
            elif key == ord("c"):
                tracker.set_home()
                print(f"home set to ({tracker.home[0]:.2f}, {tracker.home[1]:.2f})")
            elif key == ord("p"):
                print_tuning(states, orient, tracker)
            if cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        # Servos keep holding their last angle - releasing here would drop the shoulder.
        cap.release()
        link.close()
        tracker.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
