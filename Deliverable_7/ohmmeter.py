"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

Debug version:
- Restores original SAR logic
- Restores original divider formula
- Disables calibration so raw behavior can be checked first
"""

import time
import pigpio

ADC_SPI_CHANNEL   = 1
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR2_PIN   = 24
MCP4131_MAX_STEPS = 31

R_REF_OHMS          = 2000
R_REF_TOLERANCE_PCT = 0.01

R_MIN_OHMS = 100
R_MAX_OHMS = 10000

_SETTLE_S = 0.02

USE_CALIBRATION = False

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
    Original working SAR logic:
      comp == 0 -> KEEP bit
      comp == 1 -> DISCARD bit
    """
    step = 0

    for bit_pos in range(4, -1, -1):
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        comp = pi.read(comp_pin)
        decision = "KEEP" if comp == 0 else "DISCARD"
        print(f"  bit {bit_pos}: trial={trial:2d}  comp={comp}  -> {decision}")

        if comp == 0:
            step = trial

    _write_dac(pi, spi_handle, step)
    print(f"Final SAR step = {step}")
    return step


def averaged_measure(pi, spi_handle, comp_pin, n=11):
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    median_step = readings[n // 2]
    print(f"Median SAR step = {median_step}")
    return median_step


def _interp(x, x0, y0, x1, y1):
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def calibrate_resistance(raw_ohms):
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
    Divider formula for this wiring:
        R_unknown = R_ref * (MAX - step) / step
    """
    if step <= 0:
        return float('inf')

    if step >= MCP4131_MAX_STEPS:
        return 0.0

    return r_ref * (MCP4131_MAX_STEPS - step) / step


def step_to_resistance(step, r_ref=R_REF_OHMS):
    raw_r = step_to_raw_resistance(step, r_ref)
    print(f"step_to_resistance: step={step}, raw_r={raw_r}")

    if raw_r == float('inf'):
        return float('inf')

    if USE_CALIBRATION:
        calibrated = calibrate_resistance(raw_r)
        print(f"calibrated_r={calibrated}")
        return calibrated

    return raw_r


def tolerance(step, r_ref=R_REF_OHMS):
    if step <= 0:
        return float('inf')

    if step >= MCP4131_MAX_STEPS:
        return 50.0

    r_ext = step_to_resistance(step, r_ref)
    return max(50.0, 0.02 * r_ext)
