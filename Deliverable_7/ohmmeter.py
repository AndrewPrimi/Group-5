"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

This version uses the corrected resistance formula:
    R_unknown = R_ref * (MAX - step) / step
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

R_MIN_OHMS = 100
R_MAX_OHMS = 10000

_SETTLE_S = 0.02


def open_adc(pi):
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
    Current working rollback logic:
      comp == 0 -> KEEP bit
      comp == 1 -> DISCARD bit
    """
    step = 0

    for bit_pos in range(4, -1, -1):
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        comp = pi.read(comp_pin)
        print(f"  bit {bit_pos}: trial={trial:2d}  comp={comp}  -> {'KEEP' if comp == 0 else 'DISCARD'}")

        if comp == 0:
            step = trial

    _write_dac(pi, spi_handle, step)
    return step


def averaged_measure(pi, spi_handle, comp_pin, n=11):
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


def step_to_resistance(step, r_ref=R_REF_OHMS):
    """
    Corrected formula:
        step / MAX = R_ref / (R_ref + R_unknown)

    So:
        R_unknown = R_ref * (MAX - step) / step
    """
    if step <= 0:
        return float('inf')

    if step >= MCP4131_MAX_STEPS:
        return 0.0

    raw_r = r_ref * (MCP4131_MAX_STEPS - step) / step
    return raw_r * OHMS_CAL_FACTOR


def tolerance(step, r_ref=R_REF_OHMS):
    if step <= 0 or step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = step_to_resistance(step, r_ref)

    # Practical tolerance estimate
    return max(0.05 * r_ext, 10.0)
