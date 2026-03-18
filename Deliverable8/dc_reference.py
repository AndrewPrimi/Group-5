"""
dc_reference.py – Bipolar DC voltage reference via MCP4231 digital pot.

The MCP4231 Pot 0 wiper is used as a voltage divider:
  PA0  →  +5 V rail
  PB0  →  -5 V rail
  PW0  →  output (-5 V to +5 V)

The wiper position (0–128) maps linearly across the -5 V to +5 V span:
  step =  0  →  PB0 = -5.0 V
  step = 64  →  midpoint =  0.0 V
  step = 128 →  PA0 = +5.0 V

Pot 1 of the MCP4231 is not used for the voltage reference.

SPI command bytes (MCP4231):
  Pot 0 write: 0x00  <step>
"""

import time

MAX_STEPS = 128     # MCP4231 is 7-bit (0–128 positions)
MAX_VOLT  =  5.0    # +5 V upper rail
MIN_VOLT  = -5.0    # -5 V lower rail


def _volt_to_step(voltage):
    """
    Map -5 V..+5 V linearly onto wiper steps 0..128.

    Formula:  step = (voltage - MIN_VOLT) / (MAX_VOLT - MIN_VOLT) * MAX_STEPS
              step = (voltage + 5.0)      / 10.0                  * 128
    """
    fraction = (voltage - MIN_VOLT) / (MAX_VOLT - MIN_VOLT)
    fraction = max(0.0, min(1.0, fraction))
    return int(fraction * MAX_STEPS)


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

    def _write_pot(self, step):
        step = max(0, min(MAX_STEPS, step))
        self._pi.spi_write(self._spi, [0x00, step])
        time.sleep(self._settle)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_voltage(self, voltage):
        """Set target voltage (-5.0 to +5.0 V) and apply immediately if running."""
        self._voltage = max(MIN_VOLT, min(MAX_VOLT, voltage))
        if self._running:
            self._write_pot(_volt_to_step(self._voltage))

    def start(self):
        """Enable output at the stored voltage."""
        self._running = True
        self._write_pot(_volt_to_step(self._voltage))

    def stop(self):
        """Move wiper to midpoint (0 V) and disable output."""
        self._running = False
        self._write_pot(_volt_to_step(0.0))

    def cleanup(self):
        self.stop()
