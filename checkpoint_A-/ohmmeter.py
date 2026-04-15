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

# Used only for displayed tolerance
R_REF_OHMS            = 2000
R_REF_TOLERANCE_PCT   = 0.02

R_MIN_OHMS = 500
R_MAX_OHMS = 10000

_SETTLE_S = 0.02

# -------------------------------------------------------------------
# Step-based calibration points from measured hardware data
# Format: (step, actual_ohms)
#
# Lower step = higher resistance
# Higher step = lower resistance
# -------------------------------------------------------------------
STEP_CAL_POINTS = [
    (5,  9830.0),
    (6,  6690.0),
    (7,  6148.0),
    (8,  5109.0),
    (11, 3551.8),
    (12, 2947.7),
    (13, 2644.2),
    (16, 1793.3),
    (17, 1584.5),
    (20,  991.3),
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


def calibrate_step_to_resistance(step):
    """
    Convert SAR step directly to resistance using measured data.

    Behavior:
    - steps lower than the first calibration point act like open circuit
    - steps higher than the last calibration point act like short circuit
    - values in between are linearly interpolated
    """
    pts = sorted(STEP_CAL_POINTS)

    # Lower than smallest calibrated step means resistance above top range
    if step < pts[0][0]:
        return float('inf')

    # Higher than largest calibrated step means resistance below bottom range
    if step > pts[-1][0]:
        return 0.0

    # Exact point
    for s, r in pts:
        if step == s:
            return r

    # Interpolate between neighboring points
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
    """
    Simple display tolerance.
    """
    resistance = step_to_resistance(step, r_ref)

    if math.isinf(resistance) or resistance <= 0:
        return 0.0

    return resistance * R_REF_TOLERANCE_PCT
