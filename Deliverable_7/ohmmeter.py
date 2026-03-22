"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

Hardware:
  MCP4131 wiring (SPI CE1):
    Pin 1 (CS)  → GPIO 7  (CE1)
    Pin 2 (SCK) → GPIO 11 (SCLK)
    Pin 3 (SDI) → GPIO 10 (MOSI)
    Pin 4 (VSS) → GND
    Pin 5 (P0A) → 3.3V
    Pin 6 (P0W) → TL081 buffer input
    Pin 7 (P0B) → GND
    Pin 8 (VDD) → 3.3V

  Comparator 2 on LM339:
    Pin 6 = inverting input      (DAC reference from TL081 output)
    Pin 7 = non-inverting input  (Node A from ohmmeter divider)
    Pin 1 = output               -> GPIO 24

  Ohmmeter divider:
    3.3V -> R_REF -> Node A -> R_unknown -> GND
"""

import time
import math
import pigpio

# ── Hardware constants ────────────────────────────────────────────────────────
ADC_SPI_CHANNEL   = 1          # SPI CE1 (GPIO 7) for MCP4131 DAC
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR2_PIN   = 24         # GPIO for LM339 comparator 2 output (pin 1)
MCP4131_MAX_STEPS = 31         # 5-bit SAR: positions 0–31

# ── Circuit constants ────────────────────────────────────────────────────────
R_REF_OHMS            = 2000       # your new reference resistor
R_REF_TOLERANCE_PCT   = 0.01       # adjust if needed
V_SUPPLY              = 3.3
OHMS_CAL_FACTOR       = 1.00

# ── Measurement range for display ────────────────────────────────────────────
R_MIN_OHMS = 500
R_MAX_OHMS = 10000

# DAC settle time after each SPI write before reading comparator
_SETTLE_S = 0.02


def open_adc(pi):
    """Open SPI handle for the MCP4131 DAC."""
    pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_UP)
    print(f"GPIO {COMPARATOR2_PIN} pull-up set")
    return pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)


def close_adc(pi, spi_handle):
    """Release the SPI handle."""
    pi.spi_close(spi_handle)


# ── Low-level DAC control ─────────────────────────────────────────────────────

def _write_dac(pi, spi_handle, step):
    """
    Scale 5-bit SAR step (0–31) to MCP4131 7-bit register (0–127).
    """
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])


# ── SAR algorithm ─────────────────────────────────────────────────────────────

def sar_measure(pi, spi_handle, comp_pin):
    """
    Perform a 5-bit SAR conversion for ohmmeter.

    Comparator behavior used here:
      GPIO LOW  (0) -> Node A < DAC -> DAC too high -> DISCARD bit
      GPIO HIGH (1) -> Node A > DAC -> DAC too low  -> KEEP bit
    """
    step = 0

    for bit_pos in range(4, -1, -1):
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        comp = pi.read(comp_pin)
        print(f"  bit {bit_pos}: trial={trial:2d}  comp={comp}  -> {'KEEP' if comp == 1 else 'DISCARD'}")

        if comp == 0:
            step = trial

    _write_dac(pi, spi_handle, step)
    return step


def averaged_measure(pi, spi_handle, comp_pin, n=5):
    """Return the median step from n SAR conversions."""
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


# ── Conversion maths ──────────────────────────────────────────────────────────

def step_to_resistance(step, r_ref=R_REF_OHMS):
    """
    Convert SAR step to external resistance.

    step / MAX = R_unknown / (R_ref + R_unknown)

    => R_unknown = R_ref * step / (MAX - step)
    """
    if step <= 0:
        return 0.0

    if step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = r_ref * step / (MCP4131_MAX_STEPS - step)
    return r_ext * OHMS_CAL_FACTOR


def tolerance(step, r_ref=R_REF_OHMS):
    """Return approximate ±tolerance (Ω) at the given DAC step."""
    if step <= 0 or step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = step_to_resistance(step, r_ref)
    denom = (MCP4131_MAX_STEPS - step) ** 2
    quant_tol = 0.5 * r_ref * MCP4131_MAX_STEPS / denom
    quant_tol *= OHMS_CAL_FACTOR
    ref_tol = r_ext * R_REF_TOLERANCE_PCT
    return math.sqrt(quant_tol ** 2 + ref_tol ** 2)
