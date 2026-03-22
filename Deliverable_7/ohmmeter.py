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
    Pin 6 (P0W) → Op-Amp V−
    Pin 7 (P0B) → GND
    Pin 8 (VDD) → 3.3V

  Circuit:
    3.3V → R_REF → Node A → R_ext (unknown) → GND
    Node A  → comparator V+
    P0W     → comparator V−
    Output  → GPIO 23
"""

import time
import math
import pigpio

# ── Hardware constants ────────────────────────────────────────────────────────
ADC_SPI_CHANNEL   = 1
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR_PIN    = 23

# 5-bit SAR for the ohmmeter display/search
MCP4131_MAX_STEPS = 31

# ── Circuit constants ────────────────────────────────────────────────────────
R_REF_OHMS            = 15700
R_REF_TOLERANCE_PCT   = 0.043
V_SUPPLY              = 3.3

# This fixes the earlier "about half" reading behavior
OHMS_CAL_FACTOR       = 1.90

# ── Measurement range for display ────────────────────────────────────────────
R_MIN_OHMS = 500
R_MAX_OHMS = 10000

_SETTLE_S = 0.02


def open_adc(pi):
    """Open SPI handle for the MCP4131 DAC."""
    pi.set_pull_up_down(COMPARATOR_PIN, pigpio.PUD_UP)
    print(f"GPIO {COMPARATOR_PIN} pull-up set")
    return pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)


def close_adc(pi, spi_handle):
    """Release the SPI handle."""
    pi.spi_close(spi_handle)


# ── Low-level DAC control ─────────────────────────────────────────────────────

def _write_dac(pi, spi_handle, step):
    """
    Write 5-bit SAR step (0..31) to MCP4131 7-bit register (0..127).

    IMPORTANT:
    This is the original direction that was semi-working for your actual circuit.
    """
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])


# ── SAR algorithm ─────────────────────────────────────────────────────────────

def sar_measure(pi, spi_handle, comp_pin):
    """
    Perform a 5-bit SAR conversion.

    This uses the original keep/discard behavior that matched your real setup:
      comp == 0  -> keep bit
      comp == 1  -> discard bit
    """
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


def averaged_measure(pi, spi_handle, comp_pin, n=5):
    """Return median step from n SAR conversions."""
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


# ── Conversion maths ──────────────────────────────────────────────────────────

def step_to_resistance(step, r_ref=R_REF_OHMS):
    """
    Convert SAR step to external resistance.

    Divider relation:
        step / MAX = R_ext / (R_ref + R_ext)

    Solve:
        R_ext = R_ref * step / (MAX - step)

    Then apply calibration factor because your earlier readings were about half.
    """
    if step <= 0:
        return 0.0

    if step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = r_ref * step / (MCP4131_MAX_STEPS - step)
    r_ext *= OHMS_CAL_FACTOR
    return r_ext


def tolerance(step, r_ref=R_REF_OHMS):
    """Return ±tolerance (Ω) at the given DAC step."""
    if step <= 0 or step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = step_to_resistance(step, r_ref)
    denom = (MCP4131_MAX_STEPS - step) ** 2
    quant_tol = 0.5 * r_ref * MCP4131_MAX_STEPS / denom
    quant_tol *= OHMS_CAL_FACTOR
    ref_tol   = r_ext * R_REF_TOLERANCE_PCT
    return math.sqrt(quant_tol ** 2 + ref_tol ** 2)
