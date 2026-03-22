"""
square_wave.py – Square wave generator via hardware PWM + MCP4231 amplitude.

PWM output
----------
hardware PWM comes from GPIO 13 at 50% duty cycle.

Amplitude control
-----------------
The MCP4231 dual digital pot is used by controlling the resistance
between terminal B and the wiper for each pot.

Assumed behavior:
  - W1 controls the positive side
  - W0 controls the negative side
  - higher displayed amplitude should increase W1 and decrease W0

If your hardware responds backward on one side, swap the mapping for that side.

IMPORTANT
---------
DISPLAY_TO_ACTUAL_SCALE controls the relationship between what the LCD shows
and what you want the hardware to target.

Examples:
  DISPLAY_TO_ACTUAL_SCALE = 1.0   -> LCD 9.0 means target 9.0
  DISPLAY_TO_ACTUAL_SCALE = 1/3   -> LCD 9.0 means target 3.0
"""

import time

# ── Hardware constants ────────────────────────────────────────────────────────
PWM_GPIO = 13
DUTY = 500_000   # 50% duty cycle (pigpio range: 0 to 1_000_000)

# ── User-facing constants ─────────────────────────────────────────────────────
MIN_FREQ = 100
MAX_FREQ = 10_000
FREQ_STEP = 10

# This is the value the UI / LCD shows
MAX_AMP = 10.0

# Change this if you want actual output to be some fraction of the LCD value
DISPLAY_TO_ACTUAL_SCALE = 1.0 / 3.0

# MCP4231 is a 7-bit dual pot
MAX_WIPER = 127

# If the hardware gives full desired swing when the actual target is 10 V,
# keep this at 10.0. If your analog stage is calibrated to some other full
# scale, change this.
ANALOG_FULL_SCALE_VOLTS = 10.0


def _clamp(value, low, high):
    return max(low, min(high, value))


def _display_amp_to_actual_amp(display_amp):
    """
    Convert the LCD/display amplitude to the actual target amplitude.
    """
    display_amp = _clamp(float(display_amp), 0.0, MAX_AMP)
    actual_amp = display_amp * DISPLAY_TO_ACTUAL_SCALE
    return _clamp(actual_amp, 0.0, ANALOG_FULL_SCALE_VOLTS)


def _actual_amp_to_steps(actual_amp):
    """
    Convert actual target amplitude into direct MCP4231 wiper codes,
    based on controlling B-to-wiper resistance.

    Assumed endpoint behavior:
      actual_amp = 0 V   -> W0 = 127, W1 = 0
      actual_amp = 10 V  -> W0 = 0,   W1 = 127

    That means:
      W1 rises with amplitude
      W0 falls with amplitude
    """
    actual_amp = _clamp(float(actual_amp), 0.0, ANALOG_FULL_SCALE_VOLTS)
    t = actual_amp / ANALOG_FULL_SCALE_VOLTS

    w1 = round(MAX_WIPER * t)
    w0 = round(MAX_WIPER * (1.0 - t))

    w0 = int(_clamp(w0, 0, MAX_WIPER))
    w1 = int(_clamp(w1, 0, MAX_WIPER))
    return w0, w1


def _display_amp_to_steps(display_amp):
    """
    Full conversion:
      displayed amplitude -> actual target amplitude -> direct wiper codes
    """
    actual_amp = _display_amp_to_actual_amp(display_amp)
    return _actual_amp_to_steps(actual_amp)


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.001):
        """
        pi          : shared pigpio instance
        spi_handle  : SPI handle for MCP4231 on CE0
        settle_time : delay after each SPI write
        """
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time

        self._frequency = MIN_FREQ
        self._amplitude = 0.0
        self._running = False

        self._last_w0 = None
        self._last_w1 = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _write_wipers(self, w0, w1):
        """
        Write raw wiper values directly.
        W0 command = 0x00
        W1 command = 0x10
        """
        w0 = int(_clamp(w0, 0, MAX_WIPER))
        w1 = int(_clamp(w1, 0, MAX_WIPER))

        self._pi.spi_write(self._spi, [0x00, w0])   # W0
        time.sleep(self._settle)
        self._pi.spi_write(self._spi, [0x10, w1])   # W1
        time.sleep(self._settle)

        self._last_w0 = w0
        self._last_w1 = w1

    def _write_amplitude(self, display_amp):
        """
        Convert displayed amplitude to direct wiper values and write them.
        """
        w0, w1 = _display_amp_to_steps(display_amp)
        self._write_wipers(w0, w1)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_frequency(self, frequency: int):
        """
        Update frequency. Applied immediately if running.
        """
        self._frequency = int(_clamp(int(frequency), MIN_FREQ, MAX_FREQ))
        if self._running:
            self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)

    def set_amplitude(self, amplitude: float):
        """
        Update displayed amplitude and immediately write the wipers.

        This writes even if PWM is not running, so you can verify the analog
        stage changes while debugging.
        """
        self._amplitude = _clamp(float(amplitude), 0.0, MAX_AMP)
        self._write_amplitude(self._amplitude)

    def set_raw_wipers(self, w0: int, w1: int):
        """
        Manual debug helper: directly set W0 and W1.
        """
        self._write_wipers(w0, w1)

    def start(self):
        """
        Apply amplitude then start hardware PWM.
        """
        self._running = True
        self._write_amplitude(self._amplitude)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)

    def stop(self):
        """
        Stop PWM and zero the amplitude.
        """
        self._running = False
        self._pi.hardware_PWM(PWM_GPIO, 0, 0)
        self._write_amplitude(0.0)

    def cleanup(self):
        self.stop()

    # ── Optional debug accessors ──────────────────────────────────────────────

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
