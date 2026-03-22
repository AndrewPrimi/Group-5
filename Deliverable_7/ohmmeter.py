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
    Node A  → comparator/op-amp V+
    P0W     → comparator/op-amp V−
    Output  → GPIO 23

SAR logic used here:
  comparator HIGH (1) -> V_node > V_wiper -> DAC too small -> KEEP bit
  comparator LOW  (0) -> V_node < V_wiper -> DAC too large -> DISCARD bit
"""

import time
import math
import pigpio

# ── Hardware constants ────────────────────────────────────────────────────────
ADC_SPI_CHANNEL   = 1          # SPI CE1 (GPIO 7)
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR_PIN    = 23         # BCM GPIO 23

MCP4131_MAX_STEPS = 31         # 5-bit SAR: 0..31

# ── Circuit constants ────────────────────────────────────────────────────────
R_REF_OHMS          = 15700    # Use the value that matches your actual circuit
R_REF_TOLERANCE_PCT = 0.043
V_SUPPLY            = 3.3

# ── Measurement range for display ────────────────────────────────────────────
R_MIN_OHMS = 500
R_MAX_OHMS = 10000

# DAC settle time after each SPI write before reading comparator
_SETTLE_S = 0.02

# IMPORTANT:
# Your digipot was proven to run backward before.
# So we invert the DAC code here.
INVERT_DAC = True


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
    Write a 5-bit SAR step (0..31) to the MCP4131 7-bit register (0..127).

    Because your hardware DAC direction is reversed, we invert the 5-bit step
    before scaling to the 7-bit digipot code.
    """
    step = max(0, min(step, MCP4131_MAX_STEPS))

    if INVERT_DAC:
        step_for_dac = MCP4131_MAX_STEPS - step
    else:
        step_for_dac = step

    dac_code = round(step_for_dac * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])


# ── SAR algorithm ─────────────────────────────────────────────────────────────

def sar_measure(pi, spi_handle, comp_pin):
    """
    Perform a 5-bit SAR conversion and return the best step (0..31).

    Logic used here:
      comp = 1  -> V_node > V_wiper -> DAC too small -> KEEP bit
      comp = 0  -> V_node < V_wiper -> DAC too large -> DISCARD bit
    """
    step = 0

    for bit_pos in range(4, -1, -1):
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        comp = pi.read(comp_pin)
        action = "KEEP" if comp == 1 else "DISCARD"
        print(f"  bit {bit_pos}: trial={trial:2d}  comp={comp}  -> {action}")

        if comp == 1:
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
    Convert a SAR step to external resistance.

    Divider equation:
        V_node / V_supply = R_ext / (R_ref + R_ext)

    SAR converges when:
        step / MAX = V_node / V_supply

    Therefore:
        step / MAX = R_ext / (R_ref + R_ext)

    Solve for R_ext:
        R_ext = R_ref * step / (MAX - step)
    """
    if step <= 0:
        return 0.0

    if step >= MCP4131_MAX_STEPS:
        return float('inf')

    return r_ref * step / (MCP4131_MAX_STEPS - step)


def tolerance(step, r_ref=R_REF_OHMS):
    """Return ±tolerance (Ω) at the given DAC step."""
    if step <= 0 or step >= MCP4131_MAX_STEPS:
        return float('inf')

    r_ext = step_to_resistance(step, r_ref)
    denom = (MCP4131_MAX_STEPS - step) ** 2
    quant_tol = 0.5 * r_ref * MCP4131_MAX_STEPS / denom
    ref_tol   = r_ext * R_REF_TOLERANCE_PCT
    return math.sqrt(quant_tol ** 2 + ref_tol ** 2)
