"""Open a camera by name (e.g. "Camo") or index, and list what's available."""
import sys

import cv2

WINDOWS = sys.platform.startswith("win")


def device_names():
    """DirectShow device names in OpenCV index order (Windows + pygrabber)."""
    if not WINDOWS:
        return None
    try:
        from pygrabber.dshow_graph import FilterGraph
        return FilterGraph().get_input_devices()
    except Exception:
        return None


def list_cameras(max_probe=6):
    names = device_names()
    if names:
        for i, n in enumerate(names):
            print(f"  [{i}] {n}")
        return
    print("(pygrabber not installed - probing indices, names unknown)")
    for i in range(max_probe):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) if WINDOWS else cv2.VideoCapture(i)
        if cap.isOpened():
            ok, frame = cap.read()
            shape = frame.shape[1::-1] if ok else "no frames"
            print(f"  [{i}] opens, {shape}")
        cap.release()


def _resolve(source):
    if isinstance(source, int):
        return source
    s = str(source)
    if s.isdigit():
        return int(s)
    if "://" in s:
        return s  # URL stream
    names = device_names()
    if names is None:
        sys.exit(f"Can't look up camera {s!r} by name (pip install pygrabber), "
                 "or set CAMERA to an index - see: python main.py --list-cameras")
    for i, n in enumerate(names):
        if s.lower() in n.lower():
            return i
    sys.exit(f"No camera matching {s!r}. Found: {names}. Is the Camo app running?")


BACKENDS = {"msmf": cv2.CAP_MSMF, "dshow": cv2.CAP_DSHOW, "any": cv2.CAP_ANY}


def open_camera(source, width, height, backend="msmf"):
    src = _resolve(source)
    if isinstance(src, int) and WINDOWS:
        cap = cv2.VideoCapture(src, BACKENDS[backend])
    else:
        cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        sys.exit(f"Could not open camera {source!r} ({src}).")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always process the newest frame
    print(f"camera: {source!r} -> {src}, "
          f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
    return cap


def orient(frame, rotate, flip_h, flip_v):
    rot = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
           270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(rotate)
    if rot is not None:
        frame = cv2.rotate(frame, rot)
    if flip_h and flip_v:
        return cv2.flip(frame, -1)
    if flip_h:
        return cv2.flip(frame, 1)
    if flip_v:
        return cv2.flip(frame, 0)
    return frame
