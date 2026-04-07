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
        Adaptive sample count based on FREQUENCY, not dt.

        Desired behavior:
        - 1 kHz  -> 20 samples
        - 5 kHz  -> 14 samples
        - 10 kHz -> 8 samples
        """

        freq = 1_000_000 / dt  # Hz

        freq_low = 1000    # 1 kHz
        freq_high = 10000  # 10 kHz

        samples_low_freq = 20   # at 1 kHz
        samples_high_freq = 8   # at 10 kHz

        if freq <= freq_low:
            return samples_low_freq

        if freq >= freq_high:
            return samples_high_freq

        # Linear interpolation in frequency
        ratio = (freq - freq_low) / (freq_high - freq_low)
        samples = samples_low_freq - ratio * (samples_low_freq - samples_high_freq)

        # floor instead of round so 5 kHz becomes 14 instead of 15
        return int(samples)

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
