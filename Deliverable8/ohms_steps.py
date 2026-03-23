"""
ohms_steps.py – Constants and conversion helpers for the MCP4231 digital pot.

The MCP4231 is a 7-bit (128-position) SPI-controlled dual potentiometer.
Raw wiper values go from 0 to 127 inclusive.
This module defines the resistance range, step count, SPI bus settings,
preset values, and helper functions that convert between ohms and wiper values.
"""

# ── Potentiometer range ───────────────────────────────────────────────────────
MINIMUM_OHMS = 100         # lowest practical resistance (ohms)
MAXIMUM_OHMS = 10000       # full-scale resistance (ohms)

MAX_STEPS = 128            # total positions: 0..127
MAX_STEP_INDEX = 127       # maximum raw wiper value
DEFAULT_OHMS = 5000        # starting resistance on page load

# ── Debounce ──────────────────────────────────────────────────────────────────
BUTTON_DEBOUNCE_US = 200000    # 200 ms – ignore button presses within this window

# ── Constant-resistance presets ───────────────────────────────────────────────
CONSTANT_OHMS = [100, 1000, 5000, 10000]
CONSTANT_LABELS = ['100', '1k', '5k', '10k']

# ── SPI bus configuration for the MCP4231 ────────────────────────────────────
SPI_CHANNEL = 0       # CE0 chip-select line
SPI_SPEED = 50000     # 50 kHz clock
SPI_FLAGS = 0         # SPI mode 0


def ohms_to_step(ohms):
    """
    Convert a desired resistance (ohms) to a raw wiper value (0-127).
    """
    ohms = max(0, min(ohms, MAXIMUM_OHMS))
    step = int(round((ohms / MAXIMUM_OHMS) * MAX_STEP_INDEX))
    return max(0, min(step, MAX_STEP_INDEX))


def step_to_ohms(step):
    """
    Convert a raw wiper value (0-127) back to approximate resistance (ohms).
    """
    step = max(0, min(step, MAX_STEP_INDEX))
    return (step / MAX_STEP_INDEX) * MAXIMUM_OHMS


def fix_ohms(approx_ohms):
    """
    Finetune the approximate ohms closer to the desired ohms.
    """
    return (-8.05e-7 * approx_ohms * approx_ohms) + (0.9306 * approx_ohms) + 86.9
