import time

PWM_GPIO = 13
DUTY = 500_000   # 50% duty cycle

MIN_FREQ = 100
MAX_FREQ = 10_000
FREQ_STEP = 10

MAX_AMP = 10.0

# MCP42X1 command bytes
CMD_W0 = 0x00
CMD_W1 = 0x10

MAX_WIPER = 127

# Choose one mapping style for testing.
# "same"     -> both wipers move together
# "opposite" -> one rises while the other falls
# "fixed_w1" -> W1 held at max, W0 varies
# "fixed_w0" -> W0 held at max, W1 varies
AMP_MODE = "opposite"

SETTLE_TIME = 0.01


def _clamp(value, low, high):
    return max(low, min(high, value))


def _lerp(a, b, t):
    return a + (b - a) * t


def _amp_to_wipers(display_amp):
    """
    Convert user amplitude (0..10 V) into digipot wiper steps.

    This does not drive PB terminals from GPIO.
    GPIO 13 only generates PWM.
    The digipot only sets resistance / control points.
    """
    display_amp = _clamp(float(display_amp), 0.0, MAX_AMP)
    t = display_amp / MAX_AMP

    if AMP_MODE == "same":
        w = int(round(_lerp(0, 127, t)))
        return w, w

    if AMP_MODE == "opposite":
        w0 = int(round(_lerp(0, 127, t)))
        w1 = int(round(_lerp(127, 0, t)))
        return w0, w1

    if AMP_MODE == "fixed_w1":
        w0 = int(round(_lerp(0, 127, t)))
        w1 = 127
        return w0, w1

    if AMP_MODE == "fixed_w0":
        w0 = 127
        w1 = int(round(_lerp(0, 127, t)))
        return w0, w1

    # safe fallback
    return 0, 0


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=SETTLE_TIME, debug=True):
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time
        self._debug = debug

        self._frequency = MIN_FREQ
        self._amplitude = 0.0
        self._running = False

        self._last_w0 = None
        self._last_w1 = None

    def _write_wipers(self, w0, w1):
        w0 = int(_clamp(w0, 0, MAX_WIPER))
        w1 = int(_clamp(w1, 0, MAX_WIPER))

        self._pi.spi_write(self._spi, [CMD_W0, w0])
        time.sleep(self._settle)

        self._pi.spi_write(self._spi, [CMD_W1, w1])
        time.sleep(self._settle)

        self._last_w0 = w0
        self._last_w1 = w1

        if self._debug:
            print(f"[SquareWave] wrote W0={w0}, W1={w1}")

    def _write_amplitude(self, display_amp):
        w0, w1 = _amp_to_wipers(display_amp)
        if self._debug:
            print(
                f"[SquareWave] amplitude={display_amp:.2f} V  "
                f"mode={AMP_MODE}  W0={w0}  W1={w1}"
            )
        self._write_wipers(w0, w1)

    def set_frequency(self, frequency: int):
        self._frequency = int(_clamp(int(frequency), MIN_FREQ, MAX_FREQ))
        if self._running:
            self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        if self._debug:
            print(f"[SquareWave] frequency={self._frequency} Hz")

    def set_amplitude(self, amplitude: float):
        self._amplitude = _clamp(float(amplitude), 0.0, MAX_AMP)
        self._write_amplitude(self._amplitude)

    def set_raw_wipers(self, w0: int, w1: int):
        if self._debug:
            print(f"[SquareWave] manual raw write W0={w0}, W1={w1}")
        self._write_wipers(w0, w1)

    def start(self):
        self._running = True
        self._write_amplitude(self._amplitude)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        if self._debug:
            print("[SquareWave] started")

    def stop(self):
        self._running = False
        self._pi.hardware_PWM(PWM_GPIO, 0, 0)
        self._write_wipers(0, 0)
        if self._debug:
            print("[SquareWave] stopped")

    def cleanup(self):
        self.stop()

    @property
    def frequency(self):
        return self._frequency

    @property
    def amplitude(self):
        return self._amplitude

    @property
    def last_w0(self):
        return self._last_w0

    @property
    def last_w1(self):
        return self._last_w1

    def test_amplitude_ramp(self, frequency=1000, wait_seconds=4):
        if self._debug:
            print(f"\n[TEST] Starting amplitude ramp at {frequency} Hz")

        self.set_frequency(frequency)
        self.start()

        try:
            for amp in [0, 2, 4, 6, 8, 10, 0]:
                print(f"[TEST] amplitude -> {amp} V")
                self.set_amplitude(amp)
                time.sleep(wait_seconds)
        finally:
            self.stop()

    def test_raw_wiper_sweep(self, frequency=1000, wait_seconds=4):
        if self._debug:
            print(f"\n[TEST] Starting raw wiper sweep at {frequency} Hz")

        self.set_frequency(frequency)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        self._running = True

        try:
            tests = [
                (0, 0),
                (32, 32),
                (64, 64),
                (96, 96),
                (127, 127),
                (0, 127),
                (127, 0),
            ]

            for w0, w1 in tests:
                print(f"[TEST] raw -> W0={w0}, W1={w1}")
                self._write_wipers(w0, w1)
                time.sleep(wait_seconds)
        finally:
            self.stop()


if __name__ == "__main__":
    import pigpio

    print("Running square_wave.py standalone test...")

    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    spi = pi.spi_open(0, 50_000, 0)
    gen = SquareWaveGenerator(pi, spi, debug=True)

    try:
        gen.test_raw_wiper_sweep(frequency=1000, wait_seconds=5)
        gen.test_amplitude_ramp(frequency=1000, wait_seconds=5)

    except KeyboardInterrupt:
        print("\nTest interrupted.")

    finally:
        print("Cleaning up...")
        gen.cleanup()
        pi.spi_close(spi)
        pi.stop()
