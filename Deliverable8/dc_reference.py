"""
dc_reference.py – Bipolar DC voltage reference via MCP4231 dual digital pot.
"""

import time

MAX_VOLT = 5.0
MIN_VOLT = -5.0


def _volt_to_steps(voltage):
    """
    Return (w0_step, w1_step) for a voltage in [-5.0, +5.0] V.
    """
    voltage = max(MIN_VOLT, min(MAX_VOLT, voltage))
    t = (voltage + 5.0) / 10.0
    w0 = round(59 + 68 * t)
    w1 = round(127 - 78 * t)
    return w0, w1


class DCReferenceGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.001, debug=True):
        self._pi = pi
        self._spi = spi_handle
        self._settle = settle_time
        self._voltage = 0.0
        self._running = False
        self._debug = debug
        self._last_w0 = None
        self._last_w1 = None

    def _write_wipers(self, voltage):
        w0, w1 = _volt_to_steps(voltage)

        self._pi.spi_write(self._spi, [0x00, w0])
        time.sleep(self._settle)

        self._pi.spi_write(self._spi, [0x10, w1])
        time.sleep(self._settle)

        self._last_w0 = w0
        self._last_w1 = w1

        if self._debug:
            print(f"[DCRef] voltage={voltage:.3f} V -> W0={w0}, W1={w1}")

    def set_voltage(self, voltage):
        self._voltage = max(MIN_VOLT, min(MAX_VOLT, voltage))
        if self._running:
            self._write_wipers(self._voltage)

    def start(self):
        self._running = True
        self._write_wipers(self._voltage)

    def stop(self, clear_to_zero=True):
        self._running = False
        if clear_to_zero:
            self._write_wipers(0.0)

    def cleanup(self):
        self.stop(clear_to_zero=True)

    @property
    def voltage(self):
        return self._voltage

    @property
    def last_w0(self):
        return self._last_w0

    @property
    def last_w1(self):
        return self._last_w1
