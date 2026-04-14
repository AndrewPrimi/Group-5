import pigpio
import time
from collections import deque

GPIO_PIN   = 5    # Comparator output -> Pi GPIO 5
MIN_DT_US       = 50   # ignore pulses shorter than 50µs
BUFFER_LEN      = 32   # rolling average over last 32 periods
EDGE_DIVISOR    = 1   # comparator fires 2 edges per sine cycle — divide out


class FrequencyMeter:
    def __init__(self, pi, gpio_pin=GPIO_PIN):
        self.pi        = pi
        self.gpio_pin  = gpio_pin
        self.last_tick = None
        self.frequency = 0.0
        self._buf      = deque(maxlen=BUFFER_LEN)

        pi.set_mode(self.gpio_pin, pigpio.INPUT)
        self.cb = pi.callback(self.gpio_pin, pigpio.RISING_EDGE, self._cb)

    def _cb(self, gpio, level, tick):
        if self.last_tick is not None:
            dt = pigpio.tickDiff(self.last_tick, tick)
            if dt >= MIN_DT_US:
                self._buf.append(dt)
                avg_dt = sum(self._buf) / len(self._buf)
                self.frequency = (1_000_000.0 / avg_dt) / EDGE_DIVISOR

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

    meter = FrequencyMeter(pi)

    try:
        while True:
            freq = meter.get_frequency()
            if freq > 0:
                print(f"Frequency: {freq:.2f} Hz")
            else:
                print("No signal")
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    meter.cleanup()
    pi.stop()
