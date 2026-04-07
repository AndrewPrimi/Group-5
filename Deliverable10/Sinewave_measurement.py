import pigpio
import time
from collections import deque

GPIO_PIN = 5  # Comparator output
#MIN_DT_US = 100

class FrequencyMeter:
    def __init__(self, pi, debug=False):
        self.pi = pi
        self.debug = debug

        self.last_tick = None
        self.max_dt = 0 # this max dt
        self.frequency = 0.0

        #self.dt_buffer = deque(maxlen=5) # this
        
        pi.set_mode(GPIO_PIN, pigpio.INPUT)

        # Register callback on rising edge
        self.cb = pi.callback(GPIO_PIN, pigpio.RISING_EDGE, self._cb)

    def _cb(self, gpio, level, tick):
        if self.last_tick is not None:
            dt = pigpio.tickDiff(self.last_tick, tick)  # microseconds

            if dt > self.max_dt:
                self.max_dt = dt
                self.frequency = 1_000_000 / dt  # Hz

                if self.debug:
                    print(f"New max dt: {dt} µs → frequency: {self.frequency:.2f} Hz")
                    
        self.last_tick = tick

    def get_frequency(self):
        return self.frequency

    def cleanup(self):
        self.cb.cancel()


if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    meter = FrequencyMeter(pi, debug=True)

    try:
        while True:
            print(f"Frequency: {meter.get_frequency():.2f} Hz")
            import time
            time.sleep(0.5)

    except KeyboardInterrupt:
        pass

    meter.cleanup()
    pi.stop()
