"""
square_wave.py – Square wave generator via hardware PWM + MCP4231 amplitude.

This version adds:
- explicit debug prints
- a simple linear mapping you can flip easily
- immediate amplitude writes even when PWM is already running
- a manual raw-wiper test helper

PWM output:
  GPIO 13 via pigpio hardware_PWM at 50% duty cycle

Amplitude:
  MCP4231 dual digipot on SPI CE0
"""

import time

# ── Hardware constants ────────────────────────────────────────────────────────
PWM_GPIO = 13
DUTY = 500_000   # 50% duty cycle

# ── User-facing constants ─────────────────────────────────────────────────────
MIN_FREQ = 100
MAX_FREQ = 10_000
FREQ_STEP = 10
MAX_AMP = 10.0

# Set to 1.0 if you want LCD value = actual target
# Set to 1/3 if you want actual target = LCD/3
DISPLAY_TO_ACTUAL_SCALE = 1.0 / 3.0

MAX_WIPER = 127
ANALOG_FULL_SCALE_VOLTS = 10.0

# ---------------------------------------------------------------------------
# IMPORTANT:
# If amplitude is not changing, one of these directions may be backward.
#
# Try these combinations:
#   POS_INCREASES_WITH_AMP = True / False
#   NEG_DECREASES_WITH_AMP = True / False
#
# Current assumption:
#   more amplitude -> W1 goes up, W0 goes down
# ---------------------------------------------------------------------------
POS_INCREASES_WITH_AMP = True
NEG_DECREASES_WITH_AMP = True

# If your command bytes are swapped in hardware, flip these:
CMD_W0 = 0x00
CMD_W1 = 0x10


def _clamp(value, low, high):
    return max(low, min(high, value))


def _display_amp_to_actual_amp(display_amp):
    display_amp = _clamp(float(display_amp), 0.0, MAX_AMP)
    actual_amp = display_amp * DISPLAY_TO_ACTUAL_SCALE
    return _clamp(actual_amp, 0.0, ANALOG_FULL_SCALE_VOLTS)


def _actual_amp_to_steps(actual_amp):
    """
    Convert actual target amplitude to digipot wiper values.
    """
    actual_amp = _clamp(float(actual_amp), 0.0, ANALOG_FULL_SCALE_VOLTS)
    t = actual_amp / ANALOG_FULL_SCALE_VOLTS

    # Positive side
    if POS_INCREASES_WITH_AMP:
        w1 = round(MAX_WIPER * t)
    else:
        w1 = round(MAX_WIPER * (1.0 - t))

    # Negative side
    if NEG_DECREASES_WITH_AMP:
        w0 = round(MAX_WIPER * (1.0 - t))
    else:
        w0 = round(MAX_WIPER * t)

    w0 = int(_clamp(w0, 0, MAX_WIPER))
    w1 = int(_clamp(w1, 0, MAX_WIPER))
    return w0, w1


def _display_amp_to_steps(display_amp):
    actual_amp = _display_amp_to_actual_amp(display_amp)
    return _actual_amp_to_steps(actual_amp)


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.005, debug=True):
        """
        pi          : shared pigpio instance
        spi_handle  : SPI handle for MCP4231 on CE0
        settle_time : delay after each SPI write
        debug       : print wiper values when changed
        """
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time
        self._debug = debug

        self._frequency = MIN_FREQ
        self._amplitude = 0.0
        self._running = False

        self._last_w0 = None
        self._last_w1 = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _write_wipers(self, w0, w1):
        """
        Write raw wiper values directly.
        """
        w0 = int(_clamp(w0, 0, MAX_WIPER))
        w1 = int(_clamp(w1, 0, MAX_WIPER))

        # Write W0
        self._pi.spi_write(self._spi, [CMD_W0, w0])
        time.sleep(self._settle)

        # Write W1
        self._pi.spi_write(self._spi, [CMD_W1, w1])
        time.sleep(self._settle)

        self._last_w0 = w0
        self._last_w1 = w1

        if self._debug:
            print(f"[SquareWave] wrote W0={w0}, W1={w1}")

    def _write_amplitude(self, display_amp):
        """
        Convert displayed amplitude to direct wiper values and write them.
        """
        actual_amp = _display_amp_to_actual_amp(display_amp)
        w0, w1 = _display_amp_to_steps(display_amp)

        if self._debug:
            print(
                f"[SquareWave] display_amp={display_amp:.2f} V  "
                f"actual_target={actual_amp:.2f} V  "
                f"W0={w0}  W1={w1}"
            )

        self._write_wipers(w0, w1)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_frequency(self, frequency: int):
        self._frequency = int(_clamp(int(frequency), MIN_FREQ, MAX_FREQ))
        if self._running:
            self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)
        if self._debug:
            print(f"[SquareWave] frequency={self._frequency} Hz")

    def set_amplitude(self, amplitude: float):
        """
        Update amplitude and immediately write both wipers.
        """
        self._amplitude = _clamp(float(amplitude), 0.0, MAX_AMP)
        self._write_amplitude(self._amplitude)

    def set_raw_wipers(self, w0: int, w1: int):
        """
        Manual debug helper. Use this to prove hardware responds.
        """
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
        self._write_amplitude(0.0)
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
