"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

Hardware:
  MCP4131 DAC output -> comparator reference path
  Ohmmeter comparator output -> transistor buffer -> GPIO 24

Observed buffered GPIO behavior:
  low DAC step  -> GPIO reads HIGH
  high DAC step -> GPIO reads LOW

So SAR logic here uses:
  comp == 1 -> KEEP bit
  comp == 0 -> DISCARD bit
"""

import time
import math
import pigpio

ADC_SPI_CHANNEL   = 1
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR2_PIN   = 24
MCP4131_MAX_STEPS = 31

R_REF_OHMS            = 2000
R_REF_TOLERANCE_PCT   = 0.01
OHMS_CAL_FACTOR       = 1.00

R_MIN_OHMS = 500
R_MAX_OHMS = 10000

_SETTLE_S = 0.02


def open_adc(pi):
    """Open SPI handle for the MCP4131 DAC."""
    pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)
    print(f"GPIO {COMPARATOR2_PIN} configured for ohmmeter comparator")
    return pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)


def close_adc(pi, spi_handle):
    pi.spi_close(spi_handle)


def _write_dac(pi, spi_handle, step):
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])


def sar_measure(pi, spi_handle, comp_pin):
    """
    5-bit SAR conversion for ohmmeter.

    Buffered comparator/GPIO behavior:
      comp == 1 -> KEEP bit
      comp == 0 -> DISCARD bit
    """
    step = 0

    for bit_pos in range(4, -1, -1):
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        comp = pi.read(comp_pin)
        print(f"  bit {bit_pos}: trial={trial:2d}  comp={comp}  -> {'KEEP' if comp == 1 else 'DISCARD'}")

        if comp == 1:
            step = trial

    _write_dac(pi, spi_handle, step)
    return step


def averaged_measure(pi, spi_handle, comp_pin, n=11):
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


def step_to_resistance(step, r_ref=R_REF_OHMS):
    if step <= 0:
        return 0.0

    if step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = r_ref * step / (MCP4131_MAX_STEPS - step)
    return r_ext * OHMS_CAL_FACTOR


def tolerance(step, r_ref=R_REF_OHMS):
    if step <= 0 or step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = step_to_resistance(step, r_ref)
    denom = (MCP4131_MAX_STEPS - step) ** 2
    quant_tol = 0.5 * r_ref * MCP4131_MAX_STEPS / denom
    quant_tol *= OHMS_CAL_FACTOR
    ref_tol = r_ext * R_REF_TOLERANCE_PCT
    return math.sqrt(quant_tol ** 2 + ref_tol ** 2)
