import time

PWM_GPIO = 13
DUTY = 500_000   # 50% duty cycle

MIN_FREQ = 100
MAX_FREQ = 10_000
FREQ_STEP = 10
MAX_AMP = 10.0

CMD_W0 = 0x00
CMD_W1 = 0x10

MAX_WIPER = 127
ANALOG_FULL_SCALE_VOLTS = 10.0

# ── Amplitude mapping calibration ────────────────────────────────────────────
# At 0 V amplitude, both wipers go to the center point.
# As amplitude increases:
#   W0 moves downward
#   W1 moves upward
#
# You can tune these if hardware testing shows slightly different endpoints.
CENTER_W0 = 64
CENTER_W1 = 64

MIN_W0_AT_MAX_AMP = 0
MAX_W1_AT_MAX_AMP = 127


def _clamp(value, low, high):
    return max(low, min(high, value))


def _display_amp_to_actual_amp(display_amp):
    """
    Convert the LCD/UI amplitude to the actual target amplitude.
    """
    display_amp = _clamp(float(display_amp), 0.0, MAX_AMP)
    return _clamp(display_amp, 0.0, ANALOG_FULL_SCALE_VOLTS)


def _lerp(a, b, t):
    return a + (b - a) * t


def _actual_amp_to_steps(actual_amp):
    """
    Convert target amplitude into wiper positions.

    Behavior:
      amplitude = 0 V    -> both pots at center
      amplitude = 10 V   -> W0 near minimum, W1 near maximum

    This makes the positive and negative sides move apart as amplitude rises,
    instead of both wipers moving together.
    """
    actual_amp = _clamp(float(actual_amp), 0.0, ANALOG_FULL_SCALE_VOLTS)
    t = actual_amp / ANALOG_FULL_SCALE_VOLTS

    w0 = round(_lerp(CENTER_W0, MIN_W0_AT_MAX_AMP, t))
    w1 = round(_lerp(CENTER_W1, MAX_W1_AT_MAX_AMP, t))

    w0 = int(_clamp(w0, 0, MAX_WIPER))
    w1 = int(_clamp(w1, 0, MAX_WIPER))
    return w0, w1


def _display_amp_to_steps(display_amp):
    actual_amp = _display_amp_to_actual_amp(display_amp)
    return _actual_amp_to_steps(actual_amp)


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.01, debug=True):
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
        actual_amp = _display_amp_to_actual_amp(display_amp)
        w0, w1 = _actual_amp_to_steps(actual_amp)

        if self._debug:
            print(
                f"[SquareWave] display_amp={display_amp:.2f} V  "
                f"actual_target={actual_amp:.2f} V  "
                f"W0={w0}  W1={w1}"
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

        # Return to 0 V amplitude center when stopped
        self._write_wipers(CENTER_W0, CENTER_W1)

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

    def test_square_wave_swap(self, frequency=1000, wait_seconds=10):
        """
        Basic square-wave hardware test using raw wiper values.
        """
        w50 = round(MAX_WIPER * 0.5)
        w100 = MAX_WIPER

        if self._debug:
            print(f"\n[TEST] Starting square wave at {frequency} Hz")

        self.set_frequency(frequency)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        self._running = True

        if self._debug:
            print("[TEST] Step 1: W0=50%, W1=100%")
        self._write_wipers(w50, w100)
        time.sleep(wait_seconds)

        if self._debug:
            print("[TEST] Step 2: W0=100%, W1=50%")
        self._write_wipers(w100, w50)
        time.sleep(wait_seconds)

        if self._debug:
            print("[TEST] Step 3: center")
        self._write_wipers(CENTER_W0, CENTER_W1)
        time.sleep(1)

        if self._debug:
            print("[TEST] Step 4: stopping PWM")
        self.stop()

    def test_amplitude_ramp(self, frequency=1000, wait_seconds=3):
        """
        Better amplitude test:
          0 V -> 2 V -> 4 V -> 6 V -> 8 V -> 10 V -> 0 V
        This is usually more useful on the oscilloscope than the raw swap test.
        """
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


if __name__ == "__main__":
    import pigpio

    print("Running square_wave.py standalone square-wave test...")

    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    spi = pi.spi_open(0, 50_000, 0)
    gen = SquareWaveGenerator(pi, spi, debug=True)

    try:
        gen.test_amplitude_ramp(frequency=1000, wait_seconds=5)

    except KeyboardInterrupt:
        print("\nTest interrupted.")

    finally:
        print("Cleaning up...")
        gen.cleanup()
        pi.spi_close(spi)
        pi.stop()
