"""
square_wave.py – Square wave generator using hardware PWM + MCP4231 amplitude.

Frequency: hardware PWM on GPIO 13 (PWM channel 1).
Amplitude: MCP4231 dual digital pot via SPI CE0 (shared with DC reference).

Amplitude calibration endpoints:
   Amplitude  |  W0 step  |  W1 step
  ------------+-----------+---------
    0 V (-10) |    127    |     0
   10 V (+10) |      0    |   127

Linear interpolation:
  t  = amplitude / 10.0        # 0.0 at 0 V, 1.0 at 10 V
  W0 = round(127 - 127 * t)
  W1 = round(127 * t)

SPI command bytes (MCP4231):
  W0 write: 0x00  <step>
  W1 write: 0x10  <step>
"""

import pigpio
import time

PWM_GPIO  = 13
DUTY      = 500_000   # 50 % duty cycle (pigpio range 0–1_000_000)

MIN_FREQ  = 100       # Hz
MAX_FREQ  = 10_000    # Hz
FREQ_STEP = 10        # Hz per encoder click
MAX_AMP   = 10.0      # V peak amplitude max


def _amp_to_steps(amplitude):
    """Return (w0_step, w1_step) for the given amplitude (0–10 V)."""
    amplitude = max(0.0, min(MAX_AMP, amplitude))
    t  = amplitude / MAX_AMP
    w0 = round(127 - 127 * t)
    w1 = round(127 * t)
    return w0, w1


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.001):
        """
        pi          : shared pigpio instance
        spi_handle  : pigpio SPI handle for the amplitude MCP4231 (CE0)
        settle_time : seconds to wait after each SPI write
        """
        self._pi        = pi
        self._spi       = spi_handle
        self._settle    = settle_time
        self._frequency = MIN_FREQ
        self._amplitude = 0.0
        self._running   = False

        self._pi.set_mode(PWM_GPIO, pigpio.OUTPUT)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _write_amplitude(self, amplitude):
        w0, w1 = _amp_to_steps(amplitude)
        self._pi.spi_write(self._spi, [0x00, w0])
        time.sleep(self._settle)
        self._pi.spi_write(self._spi, [0x10, w1])
        time.sleep(self._settle)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_frequency(self, frequency: int):
        self._frequency = max(MIN_FREQ, min(MAX_FREQ, int(frequency)))
        if self._running:
            self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)

    def set_amplitude(self, amplitude: float):
        self._amplitude = max(0.0, min(MAX_AMP, amplitude))
        if self._running:
            self._write_amplitude(self._amplitude)

    def start(self):
        self._running = True
        self._write_amplitude(self._amplitude)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)

    def stop(self):
        self._running = False
        self._pi.hardware_PWM(PWM_GPIO, 0, 0)
        self._write_amplitude(0.0)

    def cleanup(self):
        self.stop()
