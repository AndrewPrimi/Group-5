import time

PWM_GPIO = 13
DUTY = 500_000   # 50% duty cycle

MIN_FREQ = 100
MAX_FREQ = 10_000
FREQ_STEP = 10

# Amplitude is Vpp:
#   10.0 Vpp => ideally +5 V to -5 V
MAX_AMP = 10.0

CMD_W0 = 0x00
CMD_W1 = 0x10
MAX_WIPER = 127

# ── Calibrated points from your hardware trend ───────────────────────────────
# From dc_reference calibration:
#   +5 V  -> W0=127, W1=49
#    0 V  -> W0=93,  W1=88
#   -5 V  -> W0=59,  W1=127
#
# For square-wave amplitude centered at 0:
#   positive rail side should move from 0 V toward +5 V
#   negative rail side should move from 0 V toward -5 V
#
# Best working assumption:
#   W0 controls the positive side: 93 -> 127
#   W1 controls the negative side: 88 -> 49
#
# This restores amplitude motion while recentering around 0 V.
ZERO_W0 = 93
ZERO_W1 = 88

POS_FULL_W0 = 127   # toward +5 V side
NEG_FULL_W1 = 49    # toward -5 V side


def _clamp(value, low, high):
    return max(low, min(high, value))


def _lerp(a, b, t):
    return a + (b - a) * t


def _display_amp_to_steps(display_amp):
    """
    Convert desired Vpp amplitude into wiper positions.

    0.0 Vpp  -> 0 V centered output
    10.0 Vpp -> ideally +5 V / -5 V

    Mapping:
      W0 goes from ZERO_W0 toward POS_FULL_W0
      W1 goes from ZERO_W1 toward NEG_FULL_W1
    """
    display_amp = _clamp(float(display_amp), 0.0, MAX_AMP)
    t = display_amp / MAX_AMP

    w0 = round(_lerp(ZERO_W0, POS_FULL_W0, t))
    w1 = round(_lerp(ZERO_W1, NEG_FULL_W1, t))

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

        # Return to centered 0 V position
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

    def test_amplitude_ramp(self, frequency=1000, wait_seconds=4):
        """
        0 Vpp -> 2 -> 4 -> 6 -> 8 -> 10 -> 0
        """
        if self._debug:
            print(f"\n[TEST] Starting amplitude ramp at {frequency} Hz")

        self.set_frequency(frequency)
        self.start()

        try:
            for amp in [0, 2, 4, 6, 8, 10, 0]:
                print(f"[TEST] amplitude -> {amp} Vpp")
                self.set_amplitude(amp)
                time.sleep(wait_seconds)
        finally:
            self.stop()

    def test_each_wiper(self, frequency=1000, wait_seconds=5):
        """
        Hardware diagnosis:
          1) center
          2) move W0 only
          3) center
          4) move W1 only
          5) center
        """
        if self._debug:
            print(f"\n[TEST] Starting single-wiper diagnostic at {frequency} Hz")

        self.set_frequency(frequency)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        self._running = True

        try:
            print("[TEST] Center")
            self._write_wipers(ZERO_W0, ZERO_W1)
            time.sleep(wait_seconds)

            print("[TEST] Move W0 only to positive endpoint")
            self._write_wipers(POS_FULL_W0, ZERO_W1)
            time.sleep(wait_seconds)

            print("[TEST] Back to center")
            self._write_wipers(ZERO_W0, ZERO_W1)
            time.sleep(wait_seconds)

            print("[TEST] Move W1 only to negative endpoint")
            self._write_wipers(ZERO_W0, NEG_FULL_W1)
            time.sleep(wait_seconds)

            print("[TEST] Back to center")
            self._write_wipers(ZERO_W0, ZERO_W1)
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

        # For deeper diagnosis, comment the line above and use this instead:
        # gen.test_each_wiper(frequency=1000, wait_seconds=5)

    except KeyboardInterrupt:
        print("\nTest interrupted.")

    finally:
        print("Cleaning up...")
        gen.cleanup()
        pi.spi_close(spi)
        pi.stop()
