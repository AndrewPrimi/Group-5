import pigpio
import time

GPIO_PIN = 5  # Comparator output

class FrequencyMeter:
    def __init__(self, pi, gpio_pin=GPIO_PIN, min_dt_us=100, max_updates=20):
        self.pi = pi
        self.gpio_pin = gpio_pin

        self.last_tick = None
        self.frequency = 0.0
        self.min_dt_us = min_dt_us  # running max dt

        self.update_count = 0
        self.max_updates = max_updates
        self.locked = False  # becomes True after 20 updates

        pi.set_mode(self.gpio_pin, pigpio.INPUT)

        # Register callback
        self.cb = pi.callback(self.gpio_pin, pigpio.RISING_EDGE, self._cb)

    def _cb(self, gpio, level, tick):
        # If locked, ignore further updates
        if self.locked:
            return

        if self.last_tick is not None:
            dt = pigpio.tickDiff(self.last_tick, tick)

            # Only accept larger (or equal) dt
            if dt >= self.min_dt_us:
                self.min_dt_us = dt
                self.frequency = 1_000_000 / dt

                self.update_count += 1

                print(f"[{self.update_count}/20] New max dt: {dt} us -> {self.frequency:.2f} Hz")

                # Lock after reaching 20 updates
                if self.update_count >= self.max_updates:
                    self.locked = True
                    print("Locked value. Now continuously reporting...")

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

    meter = FrequencyMeter(pi, min_dt_us=100, max_updates=20)

    try:
        while True:
            if meter.locked:
                print(f"Locked Frequency: {meter.get_frequency():.2f} Hz | dt: {meter.get_max_dt()} us")
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    meter.cleanup()
    pi.stop()
