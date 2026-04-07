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
        self.min_dt_us = min_dt_us  # This will act as the current largest dt seen so far

        pi.set_mode(self.gpio_pin, pigpio.INPUT)

        # Register callback on rising edge
        self.cb = pi.callback(self.gpio_pin, pigpio.RISING_EDGE, self._cb)

    def _cb(self, gpio, level, tick):
        if self.last_tick is not None:
            dt = pigpio.tickDiff(self.last_tick, tick)  # microseconds

            # Only update if this dt is greater than the current stored value
            if dt > self.min_dt_us:
                self.min_dt_us = dt
                self.frequency = 1_000_000 / dt  # Hz

                if self.debug:
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

    meter = FrequencyMeter(pi, debug=True, min_dt_us=100)

    try:
        while True:
            print(f"Max dt: {meter.get_max_dt()} us | Frequency: {meter.get_frequency():.2f} Hz")
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    meter.cleanup()
    pi.stop()
