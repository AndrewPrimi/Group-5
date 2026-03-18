"""
dc_reference.py – Bipolar DC voltage reference via MCP4231 dual digital pot.

Both wipers (W0 and W1) must move together to produce the correct output.
Calibration endpoints supplied by hardware team:

  Voltage  |  W0 step  |  W1 step
  ---------+-----------+---------
   +5.0 V  |    127    |    49
   -5.0 V  |     59    |   127

Linear interpolation gives:
  t  = (voltage + 5.0) / 10.0        # 0.0 at -5 V, 1.0 at +5 V
  W0 = round(59  + 68 * t)
  W1 = round(127 - 78 * t)

SPI command bytes (MCP4231):
  W0 write: 0x00  <step>
  W1 write: 0x10  <step>
"""

import time

MAX_VOLT =  5.0
MIN_VOLT = -5.0


def _volt_to_steps(voltage):
    """Return (w0_step, w1_step) for a voltage in [-5.0, +5.0] V."""
    voltage = max(MIN_VOLT, min(MAX_VOLT, voltage))
    t  = (voltage + 5.0) / 10.0
    w0 = round(59  + 68 * t)
    w1 = round(127 - 78 * t)
    return w0, w1


class DCReferenceGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.001):
        """
        pi          : shared pigpio instance
        spi_handle  : pigpio SPI handle opened for the DC-ref MCP4231
        settle_time : seconds to wait after each SPI write
        """
        self._pi      = pi
        self._spi     = spi_handle
        self._settle  = settle_time
        self._voltage = 0.0
        self._running = False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _write_wipers(self, voltage):
        """Write both W0 and W1 for the given voltage."""
        w0, w1 = _volt_to_steps(voltage)
        self._pi.spi_write(self._spi, [0x00, w0])
        time.sleep(self._settle)
        self._pi.spi_write(self._spi, [0x10, w1])
        time.sleep(self._settle)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_voltage(self, voltage):
        """Set target voltage (-5.0 to +5.0 V) and apply immediately if running."""
        self._voltage = max(MIN_VOLT, min(MAX_VOLT, voltage))
        if self._running:
            self._write_wipers(self._voltage)

    def start(self):
        """Enable output at the stored voltage."""
        self._running = True
        self._write_wipers(self._voltage)

    def stop(self):
        """Move both wipers to the 0 V position and disable output."""
        self._running = False
        self._write_wipers(0.0)

    def cleanup(self):
        self.stop()
