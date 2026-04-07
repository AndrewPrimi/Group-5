import pigpio
import time

GPIO_PIN = 5  # Comparator output

class FrequencyMeter:
    def __init__(self, pi, gpio_pin=GPIO_PIN, debug=False, min_dt_us=100):
        self.pi = pi
        self.gpio_pin = gpio_pin
        self.debug = debug

        self.last_tick = None
        self.frequency = 0.0
        self.min_dt_us = min_dt_us  # Acts as running max dt

        pi.set_mode(self.gpio_pin, pigpio.INPUT)

        # Register callback on rising edge
        self.cb = pi.callback(self.gpio_pin, pigpio.RISING_EDGE, self._cb)

    def _cb(self, gpio, level, tick):
        if self.last_tick is not None:
            dt = pigpio.tickDiff(self.last_tick, tick)  # microseconds

            # Only accept NEW largest dt
            if dt >= self.min_dt_us:
                self.min_dt_us = dt
                self.frequency = 1_000_000 / dt  # Hz

                # ✅ PRINT ONLY WHEN NEW MAX OCCURS
                print(f"New max dt: {dt} us -> frequency: {self.frequency:.2f} Hz")

        self.last_tick = tick

    def get_frequency(self):
        return self.frequency

    def get_max_dt(self):
        return self.min_dt_us

    def cleanup(self):
        if self.cb is not None:
            self.cb.cancel()
            self.cb = None


if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    meter = FrequencyMeter(pi, min_dt_us=100)

    try:
        # 🔇 No continuous printing here anymore
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        pass

    meter.cleanup()
    pi.stop()
