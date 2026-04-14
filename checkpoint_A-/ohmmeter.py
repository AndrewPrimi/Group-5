"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

Uses step-based calibration based on measured hardware behavior.
Display range is limited to 500 to 10000 ohms.
Special cases:
- Open circuit
- Short circuit
- Not in range
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
R_REF_TOLERANCE_PCT   = 0.001

R_MIN_OHMS = 500
R_MAX_OHMS = 10000

_SETTLE_S = 0.03

# -------------------------------------------------------------------
# Step-based calibration points from your measured data
# Format: (step, actual_ohms)
# -------------------------------------------------------------------
STEP_CAL_POINTS = [
    (18, 10000.0),
    (22, 5000.0),
    (25, 3000.0),
    (31, 1000.0),
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
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def calibrate_step_to_resistance(step):
    """
    Convert SAR step directly to resistance using measured data.

    Special handling:
    - very low steps behave like open circuit
    - very high steps behave like short circuit / very low resistance
    """
    pts = sorted(STEP_CAL_POINTS)

    # Open circuit region
    if step < pts[0][0]:
        return float('inf')

    # Short circuit / very low resistance region
    if step > pts[-1][0]:
        return 0.0

    # Exact top endpoint
    if step == pts[-1][0]:
        return pts[-1][1]

    for i in range(len(pts) - 1):
        s0, r0 = pts[i]
        s1, r1 = pts[i + 1]
        if s0 <= step <= s1:
            return _interp(step, s0, r0, s1, r1)

    return float('inf')


def step_to_resistance(step, r_ref=R_REF_OHMS):
    """
    Main resistance conversion.
    Returns:
    - float('inf') for open circuit
    - 0.0 for short circuit / near-short
    - calibrated resistance otherwise
    """
    return calibrate_step_to_resistance(step)


def tolerance(step, r_ref=R_REF_OHMS):
    resistance = step_to_resistance(step, r_ref)

    if math.isinf(resistance) or resistance <= 0:
        return 0.0

    return resistance * R_REF_TOLERANCE_PCT
