"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

Behavior:
- Keeps the current SAR logic and step behavior
- Uses step-based coarse conversion
- Applies a second calibration layer using real measured data
- Supports open circuit / short circuit handling in Driver.py
- Intended display range: 500 to 10000 ohms
"""

import time
import math
import pigpio

ADC_SPI_CHANNEL   = 1
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR2_PIN   = 24
MCP4131_MAX_STEPS = 31

R_REF_OHMS            = 13000
R_REF_TOLERANCE_PCT   = 0.005
R_MIN_OHMS            = 500
R_MAX_OHMS            = 10000

_SETTLE_S = 0.02

# -------------------------------------------------------------------
# Coarse step-to-resistance points from measured hardware behavior
# Format: (step, coarse_resistance)
# -------------------------------------------------------------------
STEP_CAL_POINTS = [
    (18, 10000.0),
    (22, 5000.0),
    (25, 3000.0),
    (31, 1000.0),
]

# -------------------------------------------------------------------
# Fine calibration from coarse displayed value -> actual value
# Format: (coarse_displayed_ohms, actual_ohms)
# -------------------------------------------------------------------
DISPLAY_CAL_POINTS = [
    (1000.0,  520.0),
    (1333.0,  1578.0),
    (1667.0,  1790.0),
    (2333.0,  2360.0),
    (2667.0,  2630.0),
    (3000.0,  2950.0),
    (3667.0,  3570.0),
    (6250.0,  6140.0),
    (7500.0,  6710.0),
    (10000.0, 9730.0),
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
        print(
            f"  bit {bit_pos}: trial={trial:2d}  comp={comp}  "
            f"-> {'KEEP' if comp == 0 else 'DISCARD'}"
        )

        if comp == 0:
            step = trial

    _write_dac(pi, spi_handle, step)
    return step


def averaged_measure(pi, spi_handle, comp_pin, n=11):
    """Return the median step from n SAR conversions."""
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


def _interp(x, x0, y0, x1, y1):
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def _base_step_to_resistance(step):
    """
    Convert SAR step to the coarse resistance value using the step points
    that already matched your hardware reasonably well.
    """
    pts = sorted(STEP_CAL_POINTS)

    if step < pts[0][0]:
        return float('inf')

    if step >= pts[-1][0]:
        return pts[-1][1]

    for i in range(len(pts) - 1):
        s0, r0 = pts[i]
        s1, r1 = pts[i + 1]
        if s0 <= step <= s1:
            return _interp(step, s0, r0, s1, r1)

    return float('inf')


def _apply_display_calibration(coarse_ohms):
    """
    Convert the coarse/displayed resistance into the actual resistance
    using measured calibration data.
    """
    if math.isinf(coarse_ohms):
        return coarse_ohms

    pts = sorted(DISPLAY_CAL_POINTS)

    if coarse_ohms <= pts[0][0]:
        return _interp(coarse_ohms, *pts[0], *pts[1])

    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= coarse_ohms <= x1:
            return _interp(coarse_ohms, x0, y0, x1, y1)

    return _interp(coarse_ohms, *pts[-2], *pts[-1])


def step_to_resistance(step, r_ref=R_REF_OHMS):
    """
    Main conversion used by Driver.py.

    Returns:
    - float('inf') for open circuit
    - calibrated actual resistance otherwise
    """
    coarse = _base_step_to_resistance(step)
    actual = _apply_display_calibration(coarse)

    if math.isinf(actual):
        return actual

    return actual


def tolerance(step, r_ref=R_REF_OHMS):
    """
    Improved tolerance:
    - small percentage error
    - minimum floor
    - capped so it never explodes
    """
    resistance = step_to_resistance(step, r_ref)

    if math.isinf(resistance):
        return 0.0

    percent_error = resistance * 0.005
    min_error = 10.0
    max_error = 150.0

    tol = max(percent_error, min_error)
    tol = min(tol, max_error)

    return tol
