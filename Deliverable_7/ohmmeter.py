"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

Updated version:
- Uses full 7-bit SAR on the MCP4131 wiper (0..127)
- Uses divider equation for node measured across R_unknown
- Calibration disabled for now
"""

import time
import pigpio

ADC_SPI_CHANNEL = 1
ADC_SPI_SPEED   = 50_000
ADC_SPI_FLAGS   = 0

COMPARATOR2_PIN = 24

MCP4131_MAX_CODE = 127

R_REF_OHMS = 2000
R_REF_TOLERANCE_PCT = 0.01

R_MIN_OHMS = 100
R_MAX_OHMS = 10000

_SETTLE_S = 0.02

USE_CALIBRATION = False

CAL_POINTS = [
    (1000.0, 1000.0),
    (5000.0, 5000.0),
    (10000.0, 10000.0),
]


def open_adc(pi):
    pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)
    print(f"GPIO {COMPARATOR2_PIN} configured for ohmmeter comparator")
    return pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)


def close_adc(pi, spi_handle):
    pi.spi_close(spi_handle)


def _write_dac(pi, spi_handle, code):
    code = max(0, min(code, MCP4131_MAX_CODE))
    pi.spi_write(spi_handle, [0x00, code])


def sar_measure(pi, spi_handle, comp_pin):
    """
    Full 7-bit SAR using actual MCP4131 code values.

    Current comparator behavior:
      comp == 0 -> KEEP bit
      comp == 1 -> DISCARD bit
    """
    code = 0

    for bit_pos in range(6, -1, -1):
        trial = min(code | (1 << bit_pos), MCP4131_MAX_CODE)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        comp = pi.read(comp_pin)
        decision = "KEEP" if comp == 0 else "DISCARD"
        print(f"  bit {bit_pos}: trial={trial:3d}  comp={comp}  -> {decision}")

        if comp == 0:
            code = trial

    _write_dac(pi, spi_handle, code)
    print(f"Final SAR code = {code}")
    return code


def averaged_measure(pi, spi_handle, comp_pin, n=11):
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    median_code = readings[n // 2]
    print(f"Median SAR code = {median_code}")
    return median_code


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


def code_to_raw_resistance(code, r_ref=R_REF_OHMS):
    """
    Divider equation for node measured across R_unknown:

        Vnode / Vcc = R_unknown / (R_ref + R_unknown)

    If DAC threshold is proportional to code/127, then:

        R_unknown = R_ref * code / (127 - code)
    """
    if code <= 0:
        return 0.0

    if code >= MCP4131_MAX_CODE:
        return float('inf')

    return r_ref * code / (MCP4131_MAX_CODE - code)


def step_to_raw_resistance(step, r_ref=R_REF_OHMS):
    """
    Backward-compatible wrapper in case other files still call this name.
    """
    return code_to_raw_resistance(step, r_ref)


def step_to_resistance(step, r_ref=R_REF_OHMS):
    raw_r = code_to_raw_resistance(step, r_ref)
    print(f"step_to_resistance: code={step}, raw_r={raw_r}")

    if raw_r == float('inf'):
        return float('inf')

    if USE_CALIBRATION:
        calibrated = calibrate_resistance(raw_r)
        print(f"calibrated_r={calibrated}")
        return calibrated

    return raw_r


def tolerance(step, r_ref=R_REF_OHMS):
    if step <= 0:
        return 50.0

    if step >= MCP4131_MAX_CODE:
        return float('inf')

    r_here = code_to_raw_resistance(step, r_ref)
    r_next = code_to_raw_resistance(min(step + 1, MCP4131_MAX_CODE - 1), r_ref)

    quant_tol = abs(r_next - r_here)
    practical_tol = max(50.0, 0.02 * r_here)

    return max(quant_tol, practical_tol)
