"""
dc_reference_single.py

Single-wiper DC voltage reference using MCP4231 WIPER 1.

Voltage range:
    -5.000 V to +5.000 V

This version ONLY uses W1 (command 0x10).
"""

import time

MAX_VOLT = 5.0
MIN_VOLT = -5.0

# -------------------------------
# WIPER 1 CONFIGURATION
# -------------------------------

WIPER_CMD = 0x10  # W1 ONLY

# Calibration from your original file:
# -5V → 127
# +5V → 49
STEP_AT_NEG5 = 127
STEP_AT_POS5 = 0

SETTLE_TIME_DEFAULT = 0.001


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _volt_to_step(voltage):
    """
    Convert voltage [-5, +5] → digipot step (W1 only)
    """
    voltage = _clamp(voltage, MIN_VOLT, MAX_VOLT)

    # Normalize to 0 → 1
    t = (voltage - MIN_VOLT) / (MAX_VOLT - MIN_VOLT)

    # Linear interpolation
    step = round(STEP_AT_NEG5 + (STEP_AT_POS5 - STEP_AT_NEG5) * t)

    return _clamp(step, 0, 127)


class DCReferenceSingleGenerator:
    def __init__(self, pi, spi_handle, settle_time=SETTLE_TIME_DEFAULT):
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time
        self._voltage = 0.0
        self._running = False

    def _write_step(self, step):
        self._pi.spi_write(self._spi, [WIPER_CMD, int(step)])
        time.sleep(self._settle)

    def _write_voltage(self, voltage):
        step = _volt_to_step(voltage)
        self._write_step(step)

    def set_voltage(self, voltage):
        self._voltage = _clamp(voltage, MIN_VOLT, MAX_VOLT)

        if self._running:
            self._write_voltage(self._voltage)

    def get_voltage(self):
        return self._voltage

    def start(self):
        self._running = True
        self._write_voltage(self._voltage)

    def stop(self):
        self._running = False
        self._write_voltage(0.0)

    def cleanup(self):
        self.stop()
