"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

Final debug version:
- Full 7-bit SAR (0–127)
- Correct divider equation (measuring across R_unknown)
- Compatible with Driver.py (MCP4131_MAX_STEPS included)
- Calibration disabled
"""

import time
import pigpio

ADC_SPI_CHANNEL = 1
ADC_SPI_SPEED   = 50_000
ADC_SPI_FLAGS   = 0

COMPARATOR2_PIN = 24

# --- DIGIPOT RESOLUTION ---
MCP4131_MAX_CODE  = 127
MCP4131_MAX_STEPS = MCP4131_MAX_CODE   # <-- keeps Driver.py working

# --- OHMMETER PARAMETERS ---
R_REF_OHMS = 2000
R_REF_TOLERANCE_PCT = 0.01

R_MIN_OHMS = 100
R_MAX_OHMS = 10000

_SETTLE_S = 0.02

USE_CALIBRATION = False

# -------------------------------------------------------------------
# SPI + GPIO
# -------------------------------------------------------------------

def open_adc(pi):
    pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)
    print(f"GPIO {COMPARATOR2_PIN} configured for ohmmeter comparator")
    return pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)


def close_adc(pi, spi_handle):
    pi.spi_close(spi_handle)


def _write_dac(pi, spi_handle, code):
    code = max(0, min(code, MCP4131_MAX_CODE))
    pi.spi_write(spi_handle, [0x00, code])


# -------------------------------------------------------------------
# SAR LOGIC (FULL 7-BIT)
# -------------------------------------------------------------------

def sar_measure(pi, spi_handle, comp_pin):
    """
    Comparator logic (confirmed working):
      comp == 0 -> KEEP
      comp == 1 -> DISCARD
    """
    code = 0

    for bit_pos in range(6, -1, -1):
        trial = min(code | (1 << bit_pos), MCP4131_MAX_CODE)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        comp = pi.read(comp_pin)
        decision = "KEEP" if comp == 0 else "DISCARD"

        print(f"bit {bit_pos}: trial={trial:3d}  comp={comp} -> {decision}")

        if comp == 0:
            code = trial

    _write_dac(pi, spi_handle, code)
    print(f"Final SAR code = {code}")

    return code


def averaged_measure(pi, spi_handle, comp_pin, n=11):
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    median = readings[n // 2]
    print(f"Median SAR code = {median}")
    return median


# -------------------------------------------------------------------
# RESISTANCE CALCULATION
# -------------------------------------------------------------------

def code_to_raw_resistance(code, r_ref=R_REF_OHMS):
    """
    Based on your measured node:
    (we confirmed you're measuring across R_unknown)

    Formula:
        R_unknown = R_ref * code / (127 - code)
    """

    if code <= 0:
        return 0.0

    if code >= MCP4131_MAX_CODE:
        return float('inf')

    return r_ref * code / (MCP4131_MAX_CODE - code)


def step_to_resistance(step, r_ref=R_REF_OHMS):
    r = code_to_raw_resistance(step, r_ref)
    print(f"step={step} -> R={r:.2f} ohms")
    return r


# -------------------------------------------------------------------
# TOLERANCE
# -------------------------------------------------------------------

def tolerance(step, r_ref=R_REF_OHMS):
    if step <= 0:
        return 50.0

    if step >= MCP4131_MAX_CODE:
        return float('inf')

    r1 = code_to_raw_resistance(step, r_ref)
    r2 = code_to_raw_resistance(min(step + 1, MCP4131_MAX_CODE - 1), r_ref)

    quant = abs(r2 - r1)
    practical = max(50.0, 0.02 * r1)

    return max(quant, practical)
