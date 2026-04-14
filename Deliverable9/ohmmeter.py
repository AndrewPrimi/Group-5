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

CAL_POINTS = [
    (214.0,   220.0),
    (5750.0,  5000.0),
    (10400.0, 10000.0),
]


def open_adc(pi):
    pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)
    return pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)


def close_adc(pi, spi_handle):
    pi.spi_close(spi_handle)


def _write_dac(pi, spi_handle, step):
    """Scale 5-bit step (0..31) to MCP4131 7-bit register DAC (0..127)."""
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])


def sar_measure(pi, spi_handle, comp_pin):
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
    """Return the median step from n SAR conversions."""
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


def _interp(x, x0, y0, x1, y1):
    """Linear interpolation for predicting the correct resistance."""
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def calibrate_resistance(raw_ohms):
    if math.isinf(raw_ohms):
        return raw_ohms

    pts = sorted(CAL_POINTS)

    if raw_ohms <= pts[0][0]:
        return _interp(raw_ohms, *pts[0], *pts[1])

    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= raw_ohms <= x1:
            return _interp(raw_ohms, x0, y0, x1, y1)

    return _interp(raw_ohms, *pts[-2], *pts[-1])


def step_to_raw_resistance(step, r_ref=R_REF_OHMS):
    """Return the raw resistance from the step value."""
    if step <= 0:
        return 0.0

    if step >= MCP4131_MAX_STEPS:
        return float('inf')

    return r_ref * step / (MCP4131_MAX_STEPS - step)


def step_to_resistance(step, r_ref=R_REF_OHMS):
    """Return calibrated resistance from the SAR step."""
    raw_ohms = step_to_raw_resistance(step, r_ref)

    if math.isinf(raw_ohms):
        return raw_ohms

    corrected = calibrate_resistance(raw_ohms)
    return max(R_MIN_OHMS, min(corrected, R_MAX_OHMS))


def tolerance(step, r_ref=R_REF_OHMS):
    """Simple tolerance estimate based on reference resistor tolerance."""
    resistance = step_to_resistance(step, r_ref)

    if math.isinf(resistance):
        return float('inf')

    return resistance * R_REF_TOLERANCE_PCT
