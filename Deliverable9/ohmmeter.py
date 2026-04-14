"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

This version keeps the current SAR logic and uses the divider
relationship that matches the measured behavior:
higher resistance -> lower SAR step.

It also uses a more realistic R_REF_OHMS value based on your tests.
"""

import time
import math
import pigpio

ADC_SPI_CHANNEL   = 1
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR2_PIN   = 24
MCP4131_MAX_STEPS = 31

# Based on your measured steps, 2000 is not matching the real hardware.
# This value is a much better fit for your current results.
R_REF_OHMS            = 13000
R_REF_TOLERANCE_PCT   = 0.01

R_MIN_OHMS = 100
R_MAX_OHMS = 10000

_SETTLE_S = 0.02

# You can leave calibration off for now while getting the math right.
# Once the raw readings are close, then add calibration back in.
USE_CALIBRATION = False

CAL_POINTS = [
    (1000.0, 1000.0),
    (5000.0, 5000.0),
    (10000.0, 10000.0),
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
    """Linear interpolation."""
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
    """
    Convert SAR step to raw resistance.

    This matches the behavior you measured:
    - low resistance -> high step
    - high resistance -> low step
    """
    if step <= 0:
        return float('inf')

    if step >= MCP4131_MAX_STEPS:
        return 0.0

    return r_ref * (MCP4131_MAX_STEPS - step) / step


def step_to_resistance(step, r_ref=R_REF_OHMS):
    raw_ohms = step_to_raw_resistance(step, r_ref)

    # Open circuit is still floating in hardware, so treat very low steps as open.
    # You can tighten this later once the hardware is cleaned up.
    if step <= 13:
        return float('inf')

    if not USE_CALIBRATION:
        return raw_ohms

    return calibrate_resistance(raw_ohms)


def tolerance(step, r_ref=R_REF_OHMS):
    resistance = step_to_resistance(step, r_ref)

    if math.isinf(resistance):
        return float('inf')

    return resistance * R_REF_TOLERANCE_PCT
