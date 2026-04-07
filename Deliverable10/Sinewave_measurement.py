import pigpio
import time

GPIO_PIN = 5  # Comparator output

class FrequencyMeter:
    def __init__(self, pi, gpio_pin=GPIO_PIN, min_dt_us=100):
        self.pi = pi
        self.gpio_pin = gpio_pin

        self.last_tick = None
        self.frequency = 0.0
        self.min_dt_us = min_dt_us  # running max dt

        self.update_count = 0
        self.locked = False
        self.required_samples = None

        pi.set_mode(self.gpio_pin, pigpio.INPUT)

        # Register callback
        self.cb = pi.callback(self.gpio_pin, pigpio.RISING_EDGE, self._cb)

    def get_required_samples(self, dt):
        """
        Adaptive sample count based on dt.

        Rules:
        - Around 1 kHz (dt about 1000 us): always use 20 samples
        - Around 10 kHz (dt about 100 us): always use 8 samples
        - Between them: scale gradually
        """

        # Force anything near 1 kHz to use 20
        if dt >= 900:
            return 20

        # Force anything near 10 kHz to use 8
        if dt <= 150:
            return 8

        # Linearly interpolate between 150 us and 900 us
        dt_low = 150
        dt_high = 900
        samples_low = 8
        samples_high = 20

        ratio = (dt - dt_low) / (dt_high - dt_low)
        samples = samples_low + ratio * (samples_high - samples_low)
        return round(samples)

    def _cb(self, gpio, level, tick):
        if self.locked:
            return

        if self.last_tick is not None:
            dt = pigpio.tickDiff(self.last_tick, tick)

            # Only accept larger (or equal) dt
            if dt >= self.min_dt_us:
                self.min_dt_us = dt
                self.frequency = 1_000_000 / dt
                self.update_count += 1

                # Determine required samples from the current accepted dt
                self.required_samples = self.get_required_samples(dt)

                print(
                    f"[{self.update_count}/{self.required_samples}] "
                    f"New max dt: {dt} us -> {self.frequency:.2f} Hz"
                )

                if self.update_count >= self.required_samples:
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

    meter = FrequencyMeter(pi, min_dt_us=100)

    try:
        while True:
            if meter.locked:
                print(
                    f"Locked Frequency: {meter.get_frequency():.2f} Hz | "
                    f"dt: {meter.get_max_dt()} us"
                )
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    meter.cleanup()
    pi.stop()
