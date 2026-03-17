"""
ohmmeter.py
SAR (Successive Approximation Register) ADC ohmmeter functions.

Hardware:
  MCP4131 wiring (SPI CE1):
    Pin 1 (CS)  → GPIO 7  (CE1)
    Pin 2 (SCK) → GPIO 11 (SCLK)
    Pin 3 (SDI) → GPIO 10 (MOSI)
    Pin 4 (VSS) → GND
    Pin 5 (P0A) → 3.3V         ← sets wiper max voltage to 3.3V
    Pin 6 (P0W) → Op-Amp V−    ← wiper voltage swept by SAR algorithm
    Pin 7 (P0B) → GND          ← sets wiper min voltage to 0V
    Pin 8 (VDD) → 3.3V

  Circuit:
    3.3V → R_REF (10kΩ) → Node A → R_ext (unknown) → GND
    Node A  → Op-Amp V+  (non-inverting input)
    P0W     → Op-Amp V−  (inverting input)
    Op-Amp output → GPIO 23

  SAR logic:
    Op-Amp output HIGH (GPIO=1) when V_midpoint > V_wiper  → keep bit (step too small)
    Op-Amp output LOW  (GPIO=0) when V_midpoint < V_wiper  → discard bit (step too large)

Measurement range: 500 Ω – 10 kΩ

Tolerance sources:
  1. ADC quantisation  : ±½ LSB →  ΔR = R_REF * MAX_STEPS / (2*(MAX_STEPS - step)²)
  2. R_REF component   : ±R_REF_TOLERANCE_PCT  (e.g. 1 % for a precision resistor)
  Combined (RSS)       : sqrt(quant² + ref²)
"""

import time
import math
import pigpio

# ── Hardware constants ────────────────────────────────────────────────────────
ADC_SPI_CHANNEL   = 1          # SPI CE1 (GPIO 7) for the MCP4131 DAC
ADC_SPI_SPEED     = 50_000     # 50 kHz SPI clock
ADC_SPI_FLAGS     = 0          # Mode 0,0; CE active-low

COMPARATOR_PIN    = 23         # BCM GPIO 23 ← LM339 open-collector output

MCP4131_MAX_STEPS = 31         # 5-bit SAR: positions 0–31 (32 levels)

# ── Circuit constants (update to match your actual PCB values) ────────────────
R_REF_OHMS            = 10000   # Reference resistor in voltage divider (Ω)
R_REF_TOLERANCE_PCT   = 0.01     # 1 % tolerance (typical metal-film resistor)
V_SUPPLY              = 3.3      # Pi GPIO logic voltage (V)

# ── Measurement range for display ────────────────────────────────────────────
R_MIN_OHMS = 500
R_MAX_OHMS = 10000

# DAC settle time after each SPI write before reading comparator
_SETTLE_S = 0.020   # 20 ms


def open_adc(pi):
    """Open SPI handle for the MCP4131 DAC.  Call once at startup."""
    pi.set_pull_up_down(COMPARATOR_PIN, pigpio.PUD_UP)
    return pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)


def close_adc(pi, spi_handle):
    """Release the SPI handle."""
    pi.spi_close(spi_handle)


# ── Low-level DAC control ─────────────────────────────────────────────────────

def _write_dac(pi, spi_handle, step):
    # Scale the 5-bit SAR step (0-31) to the MCP4131's 7-bit register (0-127)
    step = max(0, min(step, MCP4131_MAX_STEPS))
    pi.spi_write(spi_handle, [0x00, round(step * 127 / MCP4131_MAX_STEPS)])

# ── SAR algorithm ─────────────────────────────────────────────────────────────

def sar_measure(pi, spi_handle, comp_pin):
    """Perform a 5-bit successive-approximation conversion.

    Returns the best-match DAC step (0–31) where the comparator transitions
    from HIGH to LOW as the DAC voltage sweeps past V_midpoint.

    Assumes:
      LM339 V+ = V_midpoint (from R_ext divider)
      LM339 V- = V_wiper    (from MCP4131)
      GPIO LOW  (0) → V_wiper < V_midpoint → keep bit (step too small)
      GPIO HIGH (1) → V_wiper > V_midpoint → discard bit (step too large)
    """
    step = 0
    for bit_pos in range(4, -1, -1):   # bits 4 down to 0  (2^4=16 … 2^0=1)
        #trial = step | (1 << bit_pos)
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)
        comp = pi.read(comp_pin)
        
        #if comp == 1:                  # V_midpoint > V_wiper: keep this bit
        #    step = trial

        if comp == 1:
            step = trial
        
    # Final write to leave DAC at the converged value
    _write_dac(pi, spi_handle, step)
    return step


def averaged_measure(pi, spi_handle, comp_pin, n=5):
    """Return the median step from n SAR conversions (reduces noise)."""
    readings = sorted(sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


# ── Conversion maths ──────────────────────────────────────────────────────────

def step_to_resistance(step):
    """Convert a DAC step to external resistance in ohms.

    From voltage divider (SAR converges when V_wiper = V_mid):
        step / MAX_STEPS  =  R_ext / (R_REF + R_ext)

    Solving for R_ext:
        R_ext  =  R_REF * step / (MAX_STEPS - step)
    """
    if step <= 0:
        return float('inf')
    if step >= MCP4131_MAX_STEPS:
        return 0.0
    
    return R_REF_OHMS * (MCP4131_MAX_STEPS - step) / step


def tolerance(step):
    """Return ±tolerance (Ω) at the given DAC step.

    Quantisation contribution (±½ LSB):
        dR/d(step) = R_REF * MAX_STEPS / (MAX_STEPS - step)²
        quant_tol  = 0.5 * dR/d(step)

    Reference resistor contribution:
        ref_tol = R_ext * R_REF_TOLERANCE_PCT

    Combined (RSS):
        total = sqrt(quant_tol² + ref_tol²)
    """
    if step <= 0 or step >= MCP4131_MAX_STEPS:
        return float('inf')
        #return 0.0

    r_ext = step_to_resistance(step)
    denom = step ** 2
    quant_tol = 0.5 * R_REF_OHMS * MCP4131_MAX_STEPS / denom
    ref_tol   = r_ext * R_REF_TOLERANCE_PCT
    return math.sqrt(quant_tol ** 2 + ref_tol ** 2)


# Check DAC Steps changes voltage
"""import pigpio

p = pigpio.pi()
spi = open_adc(p)

def write_dac(pi, spi_handle, step):
    step = max(0, min(step, MCP4131_MAX_STEPS))
    pi.spi_write(spi_handle, [0x00, round(step * 127 / MCP4131_MAX_STEPS)])
    
print("Sweeping DAC...")

for step in range(32):
    write_dac(p, ADC_SPI_CHANNEL, step)
    print("step:", step)
    time.sleep(0.2)

p.spi_close(spi)
p.stop()"""
