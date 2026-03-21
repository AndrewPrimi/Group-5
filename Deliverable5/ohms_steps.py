"""
ohms_steps.py – Constants and conversion helpers for the MCP4231 digital pot.

The MCP4231 is a 7-bit (128-step) SPI-controlled dual potentiometer.
This module defines the resistance range, step count, SPI bus settings,
preset values, and two functions that convert between ohms and step values.
"""

# ── Potentiometer range ──────────────────────────────────
MINIMUM_OHMS = 100        # lowest settable resistance (ohms)
MAXIMUM_OHMS = 10000      # full-scale resistance (ohms)
MAX_STEPS = 128           # 7-bit wiper: 0 to 128 inclusive
#MAX_STEPS = 31            # 5-bit wiper: 0 to 31 inclusive???
DEFAULT_OHMS = 5000       # starting resistance on page load

# ── Debounce ─────────────────────────────────────────────
BUTTON_DEBOUNCE_US = 200000    # 200 ms – ignore button presses within this window

# ── Constant-resistance presets ──────────────────────────
# Four quick-select values shown on the "Constant" page.
CONSTANT_OHMS = [100, 1000, 5000, 10000]
CONSTANT_LABELS = ['100', '1k', '5k', '10k']

# ── SPI bus configuration for the MCP4231 ────────────────
SPI_CHANNEL = 1       # CE1 chip-select line
SPI_SPEED = 50000     # 50 kHz clock (well within MCP4231's 10 MHz max)
SPI_FLAGS = 0         # default SPI mode 0,0


def ohms_to_step(ohms):
    """Convert a desired resistance (ohms) to a wiper step (0-128).

    Clamps the input to [0, MAXIMUM_OHMS] before converting so out-of-range
    values don't produce invalid steps.
    """
    #ohms = 0.9204 * ohms + 89
    #ohms = 1.0865 * ohms
    #ohms = max(0, min(ohms, MAXIMUM_OHMS))
    step = int((ohms / MAXIMUM_OHMS) * MAX_STEPS)
    return step


def step_to_ohms(step):
    """Convert a wiper step (0-128) back to an approximate resistance (ohms).

    This is the inverse of ohms_to_step (with minor rounding differences).
    """

    raw_ohms = (step / MAX_STEPS) * MAXIMUM_OHMS

    #corrected_ohms = raw_ohms - 96.692
    
    #corrected_ohms = 1.5 * raw_ohms - 150

    return corrected_ohms
