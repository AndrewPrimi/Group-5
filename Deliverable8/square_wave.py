import time

PWM_GPIO = 13
DUTY = 500_000   # 50% duty cycle

MIN_FREQ = 100
MAX_FREQ = 10_000
FREQ_STEP = 10

# User-facing amplitude is Vpp
# Example:
#   10.0 Vpp means the user wants a 10-volt peak-to-peak waveform
MAX_AMP = 10.0

CMD_W0 = 0x00
CMD_W1 = 0x10

#CMD_W0 = 0x10
#CMD_W1 = 0x00
MAX_WIPER = 127

# These are intentionally broad so amplitude clearly changes again.
# You can tune them later once the scope confirms motion.
W0_MIN = 0
W0_MAX = 127
W1_MIN = 0
W1_MAX = 127


def _clamp(value, low, high):
    return max(low, min(high, value))


def _lerp(a, b, t):
    return a + (b - a) * t


def _display_amp_to_steps(display_amp):
    """
    Convert amplitude in Vpp to wiper positions.

    W0 and W1 sweep in opposite directions so their differential changes the
    output amplitude. If both wipers move together, the circuit effect cancels
    and amplitude stays flat — the opposite sweep is required by the hardware.

    0.0 Vpp  -> W0=127, W1=0   (one extreme)
    10.0 Vpp -> W0=0,   W1=127 (opposite extreme)
    """
    display_amp = _clamp(float(display_amp), 0.0, MAX_AMP)
    t = display_amp / MAX_AMP

    w0 = int(_clamp(round(_lerp(127, 0, t)), 0, MAX_WIPER))
    w1 = int(_clamp(round(_lerp(0, 127, t)), 0, MAX_WIPER))
    return w0, w1


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.01, debug=True):
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time
        self._debug = debug

        self._frequency = MIN_FREQ
        self._amplitude = 0.0   # Vpp
        self._running = False

        self._last_w0 = None
        self._last_w1 = None

    def _write_wipers(self, w0, w1):
        w1 = int(_clamp(w0, 0, MAX_WIPER))
        w0 = int(_clamp(w1, 0, MAX_WIPER))

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
            print(
                f"[SquareWave] requested={display_amp:.2f} Vpp  "
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
        """
        Ramp amplitude in Vpp so you can verify movement on the scope.
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

    def test_raw_wiper_sweep(self, frequency=1000, wait_seconds=4):
        """
        Raw hardware test to prove the digipot is still changing.
        """
        if self._debug:
            print(f"\n[TEST] Starting raw wiper sweep at {frequency} Hz")

        self.set_frequency(frequency)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        self._running = True

        try:
            tests = [
                (127, 0),
                (96, 32),
                (64, 64),
                (32, 96),
                (0, 127),
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
        # First prove the pots move:
        gen.test_raw_wiper_sweep(frequency=1000, wait_seconds=5)

        # Then test amplitude mapping:
        gen.test_amplitude_ramp(frequency=1000, wait_seconds=5)

    except KeyboardInterrupt:
        print("\nTest interrupted.")

    finally:
        print("Cleaning up...")
        gen.cleanup()
        pi.spi_close(spi)
        pi.stop()
