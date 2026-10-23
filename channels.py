"""Signal -> angle mapping, smoothing and slew limiting for one servo."""
import math

from config import Channel


class OneEuro:
    """One Euro filter (Casiez et al. 2012): steady when the input is slow,
    low-lag when it moves fast. Units here are degrees and seconds."""

    def __init__(self, min_cutoff, beta, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self):
        self.x = None
        self.dx = 0.0
        self.t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self.x is None:
            self.x, self.t = x, t
            return x
        dt = t - self.t
        if dt <= 0:
            return self.x
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx = a_d * (x - self.x) / dt + (1 - a_d) * self.dx
        a = self._alpha(self.min_cutoff + self.beta * abs(self.dx), dt)
        self.x = a * x + (1 - a) * self.x
        self.t = t
        return self.x


def remap(v, in_range, out_range):
    a, b = in_range
    t = 0.0 if b == a else (v - a) / (b - a)
    t = min(max(t, 0.0), 1.0)
    return out_range[0] + t * (out_range[1] - out_range[0])


class ChannelState:
    """raw signal -> remap -> One Euro -> deadband -> slew limit -> angle"""

    def __init__(self, ch: Channel):
        self.ch = ch
        self.filter = OneEuro(ch.min_cutoff, ch.beta)
        self.target = float(ch.start)   # filtered goal
        self.current = float(ch.start)  # what is actually sent
        self.lo = min(ch.out_range)
        self.hi = max(ch.out_range)
        self._t = None

    def update(self, signals, now, armed):
        ch = self.ch
        self.filter.min_cutoff = max(ch.min_cutoff, 0.01)
        self.filter.beta = ch.beta

        if signals is not None and ch.signal in signals:
            sig = signals[ch.signal]
            if ch.gain is not None:
                raw = min(max(ch.start + ch.gain * sig, self.lo), self.hi)
            else:
                raw = remap(sig, ch.in_range, ch.out_range)
            goal = self.filter(raw, now)
            if abs(goal - self.target) >= ch.deadband:
                self.target = goal

        dt = 0.0 if self._t is None else now - self._t
        self._t = now
        # While disarmed the arm holds still, so freeze `current` too; on
        # re-arm it slews from where the arm really is.
        if armed:
            step = ch.max_speed * dt
            self.current += max(-step, min(step, self.target - self.current))

    @property
    def angle(self):
        return int(round(self.current))
