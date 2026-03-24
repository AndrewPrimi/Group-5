import time

PWM_GPIO = 13
DUTY = 500_000   # 50% duty cycle

MIN_FREQ = 100
MAX_FREQ = 10_000
FREQ_STEP = 10

# User-facing amplitude in V (peak). Output swings ±amplitude centered at 0V.
MAX_AMP = 10.0
AMP_STEP = 0.3125

# MCP4131 single digital potentiometer (10kΩ, 7-bit, 129 taps)
CMD_W0 = 0x00
MAX_WIPER = 128

# Empirical calibration from scope measurements:
#   Step 28 → 4.8 Vpp,  Step 55 → 8.8 Vpp,  Step 111 → 17.5 Vpp
# Linear regression: Vpp = CAL_SLOPE * step + CAL_OFFSET
# The 470µF DC-blocking cap and 100kΩ bias cause some voltage runaway
# at higher amplitudes, so the theoretical gain (7.0) doesn't hold —
# this empirical fit accounts for that.
CAL_SLOPE = 0.1534
CAL_OFFSET = 0.45

SETTLE_TIME = 0.01


def _clamp(value, low, high):
    return max(low, min(high, value))


def _amp_to_step(amplitude):
    """
    Convert peak amplitude (0–10 V) to MCP4131 wiper step (0–128).

    Uses empirical calibration: Vpp = CAL_SLOPE * step + CAL_OFFSET
    Desired Vpp = 2 * amplitude, so step = (2 * amplitude - CAL_OFFSET) / CAL_SLOPE
    """
    amplitude = _clamp(float(amplitude), 0.0, MAX_AMP)
    if amplitude <= 0.0:
        return 0
    step = round((2.0 * amplitude - CAL_OFFSET) / CAL_SLOPE)
    return int(_clamp(step, 0, MAX_WIPER))


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=SETTLE_TIME, debug=True):
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time
        self._debug = debug

        self._frequency = MIN_FREQ
        self._amplitude = 0.0   # V peak
        self._running = False

        self._last_step = None

    def _write_wiper(self, step):
        step = int(_clamp(step, 0, MAX_WIPER))
        r = self._pi.spi_write(self._spi, [CMD_W0, step])
        time.sleep(self._settle)
        self._last_step = step
        if self._debug:
            print(f"[SquareWave] spi_write r={r}  wiper={step}")

    def _write_amplitude(self, amplitude):
        step = _amp_to_step(amplitude)
        if self._debug:
            print(f"[SquareWave] amplitude={amplitude:.4f} V  wiper={step}")
        self._write_wiper(step)

    def set_frequency(self, frequency: int):
        self._frequency = int(_clamp(int(frequency), MIN_FREQ, MAX_FREQ))
        if self._running:
            self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        if self._debug:
            print(f"[SquareWave] frequency={self._frequency} Hz")

    def set_amplitude(self, amplitude: float):
        self._amplitude = _clamp(float(amplitude), 0.0, MAX_AMP)
        self._write_amplitude(self._amplitude)

    def set_raw_wiper(self, step: int):
        if self._debug:
            print(f"[SquareWave] manual raw write wiper={step}")
        self._write_wiper(step)

    def start(self):
        self._running = True
        self._write_amplitude(self._amplitude)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        if self._debug:
            print("[SquareWave] started")

    def stop(self, clear_wipers=True):
        self._running = False
        self._pi.hardware_PWM(PWM_GPIO, 0, 0)
        if clear_wipers:
            self._write_wiper(0)
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
    def last_step(self):
        return self._last_step

    def test_amplitude_ramp(self, frequency=1000, wait_seconds=4):
        if self._debug:
            print(f"\n[TEST] Starting amplitude ramp at {frequency} Hz")

        self.set_frequency(frequency)
        self.start()

        try:
            for amp in [0, 2.5, 5, 7.5, 10, 0]:
                print(f"[TEST] amplitude -> {amp} V peak")
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
            for step in [0, 32, 64, 96, 128]:
                print(f"[TEST] raw wiper -> {step}")
                self._write_wiper(step)
                time.sleep(wait_seconds)
        finally:
            self.stop()


if __name__ == "__main__":
    import pigpio

    print("Running square_wave.py standalone test (MCP4131)...")

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
