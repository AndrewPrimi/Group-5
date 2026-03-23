import time

PWM_GPIO = 13
DUTY = 500_000   # 50% duty cycle

MIN_FREQ = 100
MAX_FREQ = 10_000
FREQ_STEP = 10

# User amplitude is Vpp:
#   10.0 Vpp => +5 V to -5 V
#    6.0 Vpp => +3 V to -3 V
MAX_AMP = 10.0

CMD_W0 = 0x00
CMD_W1 = 0x10
MAX_WIPER = 127

# ── Calibrated square-wave rail points ───────────────────────────────────────
# These come from the DC-reference calibration trend and are used here as the
# best available calibration for the square-wave bias/span control.
#
# 0 V output center:
ZERO_W0 = 93
ZERO_W1 = 88

# +5 V positive rail target
POS5_W0 = 127

# -5 V negative rail target
NEG5_W1 = 127


def _clamp(value, low, high):
    return max(low, min(high, value))


def _lerp(a, b, t):
    return a + (b - a) * t


def _display_amp_to_steps(display_amp):
    """
    Convert desired Vpp amplitude into calibrated wiper positions.

    Amplitude meaning:
      0.0 Vpp  ->  0 V to 0 V
      2.0 Vpp  -> +1 V to -1 V
      10.0 Vpp -> +5 V to -5 V

    Mapping idea:
      - W0 controls the positive side from 0 V up to +5 V
      - W1 controls the negative side from 0 V down to -5 V
    """
    display_amp = _clamp(float(display_amp), 0.0, MAX_AMP)
    vpeak = display_amp / 2.0             # 10 Vpp -> 5 V peak
    t = vpeak / 5.0                       # normalize 0..1

    w0 = round(_lerp(ZERO_W0, POS5_W0, t))
    w1 = round(_lerp(ZERO_W1, NEG5_W1, t))

    w0 = int(_clamp(w0, 0, MAX_WIPER))
    w1 = int(_clamp(w1, 0, MAX_WIPER))
    return w0, w1


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.01, debug=True):
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time
        self._debug = debug

        self._frequency = MIN_FREQ
        self._amplitude = 0.0   # stored as Vpp
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
        w0, w1 = _display_amp_to_steps(display_amp)

        if self._debug:
            vpeak = display_amp / 2.0
            print(
                f"[SquareWave] requested={display_amp:.2f} Vpp  "
                f"(ideal +{vpeak:.2f} / -{vpeak:.2f} V)  "
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

        # Return to calibrated 0 V center
        self._write_wipers(ZERO_W0, ZERO_W1)

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

    def test_amplitude_ramp(self, frequency=1000, wait_seconds=5):
        """
        0 Vpp -> 2 -> 4 -> 6 -> 8 -> 10 -> 0
        """
        if self._debug:
            print(f"\n[TEST] Starting bipolar amplitude ramp at {frequency} Hz")

        self.set_frequency(frequency)
        self.start()

        try:
            for amp in [0, 2, 4, 6, 8, 10, 0]:
                print(f"[TEST] amplitude -> {amp} Vpp")
                self.set_amplitude(amp)
                time.sleep(wait_seconds)
        finally:
            self.stop()


if __name__ == "__main__":
    import pigpio

    print("Running square_wave.py standalone bipolar square-wave test...")

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
