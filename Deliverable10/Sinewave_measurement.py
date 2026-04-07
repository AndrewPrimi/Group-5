import pigpio
import time
from collections import deque

GPIO_PIN = 5  # Comparator output

class FrequencyMeter:
    def __init__(self, pi, gpio_pin=GPIO_PIN, debug=False, min_dt_us=50, avg_samples=5):
        self.pi = pi
        self.gpio_pin = gpio_pin
        self.debug = debug

        self.last_tick = None
        self.frequency = 0.0

        # Fixed lower limit to reject glitches / false triggers
        self.min_dt_us = min_dt_us

        # Store recent valid periods for smoothing
        self.dt_buffer = deque(maxlen=avg_samples)

        pi.set_mode(self.gpio_pin, pigpio.INPUT)

        # Rising edge callback
        self.cb = pi.callback(self.gpio_pin, pigpio.RISING_EDGE, self._cb)

    def _cb(self, gpio, level, tick):
        if self.last_tick is not None:
            dt = pigpio.tickDiff(self.last_tick, tick)  # microseconds

            # Ignore impossible / glitchy readings
            if dt >= self.min_dt_us:
                self.dt_buffer.append(dt)

                avg_dt = sum(self.dt_buffer) / len(self.dt_buffer)
                self.frequency = 1_000_000 / avg_dt

                if self.debug:
                    print(
                        f"dt: {dt} us | avg_dt: {avg_dt:.2f} us | "
                        f"frequency: {self.frequency:.2f} Hz"
                    )

        self.last_tick = tick

    def get_frequency(self):
        return self.frequency

    def cleanup(self):
        if self.cb is not None:
            self.cb.cancel()
            self.cb = None


if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    meter = FrequencyMeter(pi, debug=True, min_dt_us=50, avg_samples=5)

    try:
        while True:
            print(f"Frequency: {meter.get_frequency():.2f} Hz")
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    meter.cleanup()
    pi.stop()
