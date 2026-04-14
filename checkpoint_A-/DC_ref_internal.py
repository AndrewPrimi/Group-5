"""
DC_ref_internal.py
SAR ADC measurement backend for the internal DC reference.

Hardware:
  LM339 comparator:
    pin 11 = input from MCP4131 DAC (ADC reference voltage)
    pin 10 = input from DC reference output (signal being measured)
    pin 12 = comparator output -> Pi GPIO 18

  SPI CE1 (same chip select as external voltmeter)

This module is measurement-only — no LCD or UI logic.
Call measure_dc_ref() and display the result in Driver.py.
"""

import time
import pigpio

from ohmmeter import MCP4131_MAX_STEPS, _SETTLE_S
from voltmeter import STEP_TO_VOLT, step_to_voltage, step_to_tolerance

COMPARATOR_PIN = 18   # LM339 pin 12 -> Pi GPIO 18


def _write_dac(pi, spi_handle, step):
    """Scale 5-bit step (0..31) to MCP4131 7-bit register (0..127)."""
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])


def _sar_measure(pi, spi_handle):
    """5-bit SAR binary search. Returns best step (0..31)."""
    step = 0
    for bit_pos in range(4, -1, -1):
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)
        if pi.read(COMPARATOR_PIN) == 0:
            step = trial
    _write_dac(pi, spi_handle, step)
    return step


def _averaged_measure(pi, spi_handle, n=11):
    """Return median step from n SAR conversions."""
    readings = sorted(_sar_measure(pi, spi_handle) for _ in range(n))
    return readings[n // 2]


def measure_dc_ref(pi, spi_handle, n=11):
    """
    Measure the DC reference output voltage.

    Returns (voltage, tolerance) in volts.
    Uses the same STEP_TO_VOLT calibration table as the external voltmeter
    since it is the same ADC circuit.
    """
    pi.set_pull_up_down(COMPARATOR_PIN, pigpio.PUD_OFF)
    step = _averaged_measure(pi, spi_handle, n)
    voltage = step_to_voltage(step)
    tolerance = step_to_tolerance(step)
    return voltage, tolerance
