import pigpio
import time
from pigpio_encoder import encoder

# =======================
# Constants
# =======================

MINIMUM_OHMS = 40
MAXIMUM_OHMS = 11000
MAX_STEPS = 128
DEFAULT_OHMS = 5000

# Speed thresholds (detents/sec)
SLOW_THRESHOLD = 40

# GPIO pins
PIN_A = 22   # CLK
PIN_B = 27   # DT
BUTTON_PIN = 17

# =======================
# Helpers
# =======================


def ohms_to_step(ohms):
    ohms = max(MINIMUM_OHMS, min(ohms, MAXIMUM_OHMS))
    return int((ohms - MINIMUM_OHMS) / (MAXIMUM_OHMS - MINIMUM_OHMS) * (MAX_STEPS - 1))


def step_to_ohms(step):
    return int(
        MINIMUM_OHMS +
        (step / (MAX_STEPS - 1)) * (MAXIMUM_OHMS - MINIMUM_OHMS)
    )


# =======================
# Rotary Encoder Controller
# =======================

class RotaryEncoder:
    def __init__(self, pi):
        self.pi = pi
        self.ohms = DEFAULT_OHMS
        self.last_tick = None

        self.encoder = encoder(
            pi,
            PIN_A,
            PIN_B,
            callback=self._on_rotate,
            pulses_per_rev=20
        )

    def _on_rotate(self, delta):
        """
        delta > 0  -> clockwise (by library definition)
        delta < 0  -> counterclockwise

        We INVERT delta so:
        - Clockwise   -> increase ohms
        - CCW         -> decrease ohms
        """

        delta = -delta  # 🔥 FIXES DIRECTION FOREVER 🔥

        now = self.pi.get_current_tick()

        if self.last_tick is None:
            self.last_tick = now
            return

        dt = pigpio.tickDiff(self.last_tick, now)
        self.last_tick = now

        if dt <= 0:
            return

        speed = 1_000_000 / dt  # detents/sec

        if speed < SLOW_THRESHOLD:
            step = 10
        else:
            step = 100

        self._apply_change(delta * step)

    def _apply_change(self, delta_ohms):
        new_val = self.ohms + delta_ohms

        if MINIMUM_OHMS <= new_val <= MAXIMUM_OHMS:
            self.ohms = new_val
            step = ohms_to_step(self.ohms)
            approx = step_to_ohms(step)

            print(
                f"Ohms: {self.ohms:5d} | "
                f"Step: {step:3d} | "
                f"Approx: {approx:6d}"
            )

    def cancel(self):
        self.encoder.cancel()


# =======================
# Main
# =======================

def main():
    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("pigpio not running")

    pi.set_mode(PIN_A, pigpio.INPUT)
    pi.set_mode(PIN_B, pigpio.INPUT)
    pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
    pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)

    rotary = RotaryEncoder(pi)

    print("Rotary encoder running (Ctrl+C to exit)")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        rotary.cancel()
        pi.stop()


if __name__ == "__main__":
    main()
