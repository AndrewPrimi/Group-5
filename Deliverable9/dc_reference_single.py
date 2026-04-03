"""
dc_reference_single.py

Single-wiper DC voltage reference for Deliverable 8.

This version is for a design where ONLY ONE digipot wiper is used
to control the DC reference output.

Voltage range:
    -5.000 V to +5.000 V

The Driver already limits the UI to 0.625 V steps, so this module
just needs to clamp and map the chosen voltage to one digipot wiper.

Default behavior:
- Uses W0 on the MCP4231
- Uses linear interpolation based on measured endpoints

IMPORTANT:
If your hardware is wired to W1 instead of W0, change:
    WIPER = 1

If your measured calibration endpoints are different, change:
    STEP_AT_NEG5
    STEP_AT_POS5
"""

import time

MAX_VOLT = 5.0
MIN_VOLT = -5.0

# ------------------------------------------------------------
# HARDWARE CONFIGURATION
# ------------------------------------------------------------

# Which single wiper are you using?
#   0 -> W0 -> command 0x00
#   1 -> W1 -> command 0x10
WIPER = 0

# Calibrated endpoint steps for the ONE wiper you are using.
#
# If using W0 only and your old calibration was:
#   -5 V -> W0 = 59
#   +5 V -> W0 = 127
# then keep:
STEP_AT_NEG5 = 59
STEP_AT_POS5 = 127
#
# If instead you are using W1 only from your old dual-wiper file, use:
# STEP_AT_NEG5 = 127
# STEP_AT_POS5 = 49

SETTLE_TIME_DEFAULT = 0.001


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _wiper_cmd():
    return 0x00 if WIPER == 0 else 0x10


def _volt_to_step(voltage):
    """
    Map voltage in [-5, +5] to a single digipot step using linear interpolation.
    """
    voltage = _clamp(voltage, MIN_VOLT, MAX_VOLT)

    # t = 0 at -5 V, 1 at +5 V
    t = (voltage - MIN_VOLT) / (MAX_VOLT - MIN_VOLT)

    step = round(STEP_AT_NEG5 + (STEP_AT_POS5 - STEP_AT_NEG5) * t)
    return _clamp(step, 0, 127)


class DCReferenceSingleGenerator:
    def __init__(self, pi, spi_handle, settle_time=SETTLE_TIME_DEFAULT):
        """
        pi          : shared pigpio instance
        spi_handle  : pigpio SPI handle opened for the DC reference digipot
        settle_time : seconds to wait after each SPI write
        """
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time
        self._voltage = 0.0
        self._running = False

    def _write_step(self, step):
        self._pi.spi_write(self._spi, [_wiper_cmd(), int(step)])
        time.sleep(self._settle)

    def _write_voltage(self, voltage):
        step = _volt_to_step(voltage)
        self._write_step(step)

    def set_voltage(self, voltage):
        """
        Save the target voltage. If output is active, update the hardware immediately.
        """
        self._voltage = _clamp(voltage, MIN_VOLT, MAX_VOLT)
        if self._running:
            self._write_voltage(self._voltage)

    def get_voltage(self):
        return self._voltage

    def start(self):
        """
        Enable/update the output at the current target voltage.
        """
        self._running = True
        self._write_voltage(self._voltage)

    def stop(self):
        """
        Turn the DC reference 'off' by driving it back to 0 V equivalent.
        """
        self._running = False
        self._write_voltage(0.0)

    def cleanup(self):
        self.stop()
