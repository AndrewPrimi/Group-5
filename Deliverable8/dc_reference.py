"""
dc_reference.py – Dual-channel DC voltage reference via MCP4231 digital pot.

The MCP4231 has two independent wiper channels (Pot 0 and Pot 1).
Each is set to produce 0–5 V.  Wired additively on the PCB, the two
channels together span 0–10 V.

Crucially, writing to one wiper register NEVER touches the other —
each channel's voltage is stored and applied independently.

SPI command bytes (MCP4231):
  Pot 0 write: 0x00  <step>
  Pot 1 write: 0x10  <step>
"""

import time

MAX_STEPS = 128     # MCP4231 is 7-bit (0–128)
MAX_VOLT  = 5.0     # each pot spans 0–5 V
MIN_VOLT  = 0.0

_CMD = [0x00, 0x10]  # SPI command byte per pot


def _volt_to_step(voltage):
    fraction = max(0.0, min(1.0, voltage / MAX_VOLT))
    return int(fraction * MAX_STEPS)


class DCReferenceGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.001):
        """
        pi          : shared pigpio instance
        spi_handle  : pigpio SPI handle opened for the DC-ref MCP4231
        settle_time : seconds to wait after each SPI write
        """
        self._pi          = pi
        self._spi         = spi_handle
        self._settle      = settle_time
        self._voltages    = [0.0, 0.0]   # one entry per pot
        self._running     = [False, False]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _write_pot(self, pot, step):
        """Write a single wiper — only pot 0 or pot 1 is affected."""
        step = max(0, min(MAX_STEPS, step))
        self._pi.spi_write(self._spi, [_CMD[pot], step])
        time.sleep(self._settle)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_voltage(self, voltage, pot):
        """
        Store and apply a voltage to one pot channel.
        The other pot's wiper is not written.
        """
        self._voltages[pot] = max(MIN_VOLT, min(MAX_VOLT, voltage))
        if self._running[pot]:
            self._write_pot(pot, _volt_to_step(self._voltages[pot]))

    def start(self, pot):
        """Enable output on one pot channel at its stored voltage."""
        self._running[pot] = True
        self._write_pot(pot, _volt_to_step(self._voltages[pot]))

    def stop(self, pot):
        """Zero one pot channel's wiper — the other is untouched."""
        self._running[pot] = False
        self._write_pot(pot, 0)

    def start_all(self):
        for pot in (0, 1):
            self.start(pot)

    def stop_all(self):
        for pot in (0, 1):
            self.stop(pot)

    def cleanup(self):
        self.stop_all()
