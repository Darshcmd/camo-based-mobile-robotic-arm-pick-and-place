"""Serial link to ArmServoDebug.ino. Sends "!0=90,1=120,5=70\\n" frames."""
import time

import serial
from serial.tools import list_ports

ARDUINO_VIDS = {0x1A86, 0x2341, 0x2A03, 0x10C4, 0x0403}  # CH340, Arduino, CP210x, FTDI
ARDUINO_HINTS = ("ch340", "arduino", "usb-serial", "cp210", "ftdi")


def find_port():
    for p in list_ports.comports():
        desc = f"{p.description} {p.manufacturer or ''}".lower()
        if p.vid in ARDUINO_VIDS or any(h in desc for h in ARDUINO_HINTS):
            return p.device
    return None


class ArmLink:
    def __init__(self, port, baud, send_hz, keepalive_s, dry_run=False):
        self.ser = None
        self.label = "DRY RUN"
        self.min_gap = 1.0 / send_hz
        self.keepalive_s = keepalive_s
        self.last_line = ""
        self._last = None
        self._t = 0.0
        self.port = None
        self.baud = baud
        self._retry_t = 0.0
        if dry_run:
            return
        if port == "auto":
            port = find_port()
            if port is None:
                print("No Arduino serial port found - running DRY RUN.")
                return
        self.port = port
        if not self._open():
            print(f"{port} is busy (Arduino IDE still holding it?). "
                  "Close the IDE - I'll keep retrying and connect automatically.")

    RETRY_S = 2.0

    def _open(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0, write_timeout=0.1)
        except serial.SerialException:
            self.ser = None
            self.label = f"{self.port} BUSY - RETRYING"
            self._retry_t = time.monotonic()
            return False
        self.label = self.port
        print(f"serial: {self.port} @ {self.baud}, waiting for Arduino reset...")
        time.sleep(2.5)  # opening the port resets the Uno; poll() then shows its boot message
        self._last = None  # force a fresh frame
        print(f"serial: connected to {self.port}")
        return True

    def send(self, angles, now):
        if now - self._t < self.min_gap:
            return
        if angles == self._last and now - self._t < self.keepalive_s:
            return
        line = "!" + ",".join(f"{k}={v}" for k, v in angles.items())
        if self.ser:
            try:
                self.ser.write((line + "\n").encode())
            except serial.SerialTimeoutException:
                return
        self._last = dict(angles)
        self._t = now
        self.last_line = line

    def poll(self):
        """Echo anything the Arduino prints; retry a busy port."""
        if self.ser is None:
            if self.port and time.monotonic() - self._retry_t > self.RETRY_S:
                self._open()
            return
        if self.ser.in_waiting:
            text = self.ser.read(self.ser.in_waiting).decode(errors="replace").strip()
            if text:
                print(f"[arduino] {text}")

    def close(self):
        if self.ser:
            self.ser.close()
