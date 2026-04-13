"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

This version keeps the current working SAR logic and adds
piecewise-linear calibration for the resistance display.
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

R_MIN_OHMS = 100
R_MAX_OHMS = 10000

_SETTLE_S = 0.02

# -------------------------------------------------------------------
# Calibration points
# Format: (raw_measured_ohms, actual_ohms)
# Add more points later if needed.
# -------------------------------------------------------------------
CAL_POINTS = [
    (214.0,   220.0),
    (5750.0,  5000.0),
    (10400.0, 10000.0),
]


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
    Current working SAR logic:
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


def _interp(x, x0, y0, x1, y1):
    """Linear interpolation."""
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def calibrate_resistance(raw_ohms):
    """
    Convert raw computed resistance to calibrated resistance using
    piecewise-linear interpolation through CAL_POINTS.
    """
    pts = CAL_POINTS

    if raw_ohms <= pts[0][0]:
        return _interp(raw_ohms, 0.0, 0.0, pts[0][0], pts[0][1])

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= raw_ohms <= x1:
            return _interp(raw_ohms, x0, y0, x1, y1)

    x0, y0 = pts[-2]
    x1, y1 = pts[-1]
    return _interp(raw_ohms, x0, y0, x1, y1)


def step_to_raw_resistance(step, r_ref=R_REF_OHMS):
    """
    Raw divider formula:
        R_unknown = R_ref * step / (MAX - step)
    """
    if step <= 0:
        return 0.0

    if step >= MCP4131_MAX_STEPS:
        return float('inf')

    return r_ref * step / (MCP4131_MAX_STEPS - step)


def step_to_resistance(step, r_ref=R_REF_OHMS):
    raw_r = step_to_raw_resistance(step, r_ref)

    if raw_r == float('inf'):
        return float('inf')

    return calibrate_resistance(raw_r)


def tolerance(step, r_ref=R_REF_OHMS):
    """
    Practical display tolerance.
    """
    if step <= 0 or step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = step_to_resistance(step, r_ref)

    return max(50.0, 0.02 * r_ext)
