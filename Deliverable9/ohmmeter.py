"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

This version keeps the current working SAR logic and adds
piecewise-linear calibration for the resistance display.
"""

import time
import math
import pigpio

ADC_SPI_CHANNEL = 1
ADC_SPI_SPEED = 50_000
ADC_SPI_FLAGS = 0

COMPARATOR2_PIN = 24
MCP4131_MAX_STEPS = 31

R_REF_OHMS = 2000
R_REF_TOLERANCE_PCT = 0.01

R_MIN_OHMS = 100
R_MAX_OHMS = 10000

_SETTLE_S = 0.02

# -------------------------------------------------------------------
# Calibration points
# Format: (raw_measured_ohms, actual_ohms)
# Add more points later if needed.
# -------------------------------------------------------------------
CAL_POINTS = [
    (214.0, 220.0),
    (5750.0, 5000.0),
    (10400.0, 10000.0),
]


def open_adc(pi):
    """Open the SPI channel and configure the comparator pin."""
    pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)
    spi_handle = pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)
    return spi_handle


def close_adc(pi, spi_handle):
    """Close the SPI handle."""
    pi.spi_close(spi_handle)


def _write_dac(pi, spi_handle, step):
    """Scale 5-bit step (0..31) to MCP4131 7-bit register DAC (0..127)."""
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])


def sar_measure(pi, spi_handle, comp_pin):
    """Perform one 5-bit SAR conversion. comp == 0 keeps the bit."""
    step = 0

    for bit_pos in range(4, -1, -1):
        # The trial is the step value plus the next significant bit.
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        # The comp_pin read determines keep (0) or discard (1).
        comp = pi.read(comp_pin)
        print(
            f"  bit {bit_pos}: trial={trial:2d}  comp={comp}  "
            f"-> {'KEEP' if comp == 0 else 'DISCARD'}"
        )

        if comp == 0:
            step = trial

    # Write the final step value to convert to analog.
    _write_dac(pi, spi_handle, step)
    return step


def averaged_measure(pi, spi_handle, comp_pin, n=11):
    """Return the median step from n SAR conversions."""
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


def _interp(x, x0, y0, x1, y1):
    """
    Linear interpolation for predicting the correct resistance y
    between y0 and y1. x is the uncalibrated resistance.
    """
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def calibrate_resistance(raw_ohms):
    """Apply piecewise-linear calibration from CAL_POINTS."""
    if math.isinf(raw_ohms):
        return raw_ohms

    points = sorted(CAL_POINTS)

    if not points:
        return raw_ohms

    if len(points) == 1:
        raw0, actual0 = points[0]
        if raw0 == 0:
            return raw_ohms
        return raw_ohms * (actual0 / raw0)

    if raw_ohms <= points[0][0]:
        x0, y0 = points[0]
        x1, y1 = points[1]
        return _interp(raw_ohms, x0, y0, x1, y1)

    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        if x0 <= raw_ohms <= x1:
            return _interp(raw_ohms, x0, y0, x1, y1)

    x0, y0 = points[-2]
    x1, y1 = points[-1]
    return _interp(raw_ohms, x0, y0, x1, y1)


def step_to_raw_resistance(step, r_ref=R_REF_OHMS):
    """
    Raw divider formula:
        R_unknown = R_ref * (MAX - step) / step
    """
    if step <= 0:
        # open
        return float("inf")

    if step >= MCP4131_MAX_STEPS:
        # short
        return 0.0

    return r_ref * (MCP4131_MAX_STEPS - step) / step


def step_to_resistance(step, r_ref=R_REF_OHMS):
    """Convert SAR step to calibrated resistance."""
    raw_ohms = step_to_raw_resistance(step, r_ref=r_ref)
    return calibrate_resistance(raw_ohms)


def measure_resistance(pi, spi_handle, comp_pin=COMPARATOR2_PIN, n=11, r_ref=R_REF_OHMS):
    """Take a median SAR measurement and return calibrated resistance."""
    step = averaged_measure(pi, spi_handle, comp_pin, n=n)
    ohms = step_to_resistance(step, r_ref=r_ref)
    return step, ohms


def resistance_tolerance(ohms, r_ref=R_REF_OHMS, r_ref_tol_pct=R_REF_TOLERANCE_PCT):
    """
    Rough tolerance estimate based on reference resistor tolerance only.
    You can expand this later to include SAR quantization error.
    """
    if math.isinf(ohms):
        return float("inf")
    return abs(ohms) * r_ref_tol_pct


def clamp_display_ohms(ohms):
    """Clamp only for display purposes."""
    if math.isinf(ohms):
        return ohms
    return max(R_MIN_OHMS, min(R_MAX_OHMS, ohms))


if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("Could not connect to pigpio daemon.")

    spi_handle = None
    try:
        spi_handle = open_adc(pi)

        while True:
            step, ohms = measure_resistance(pi, spi_handle)
            tol = resistance_tolerance(ohms)
            display_ohms = clamp_display_ohms(ohms)

            if math.isinf(display_ohms):
                print(f"step={step:2d}  R=OPEN")
            else:
                print(f"step={step:2d}  R={display_ohms:.1f} ohms  +/- {tol:.1f}")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        if spi_handle is not None:
            close_adc(pi, spi_handle)
        pi.stop()
