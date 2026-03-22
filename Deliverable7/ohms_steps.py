"""
ohms_steps.py – Constants and conversion helpers for the MCP4231 digital pot.
"""

MINIMUM_OHMS = 100
MAXIMUM_OHMS = 10000

MAX_STEPS = 128          # total number of positions
MAX_CODE = 127           # actual highest valid code
DEFAULT_OHMS = 5000

BUTTON_DEBOUNCE_US = 200000

CONSTANT_OHMS = [100, 1000, 5000, 10000]
CONSTANT_LABELS = ['100', '1k', '5k', '10k']

SPI_CHANNEL = 1
SPI_SPEED = 50000
SPI_FLAGS = 0


def ohms_to_step(ohms):
    """
    Convert desired ohms to digipot code (0..127).
    """
    ohms = max(0, min(ohms, MAXIMUM_OHMS))
    step = int((ohms / MAXIMUM_OHMS) * MAX_CODE)
    return max(0, min(MAX_CODE, step))


def step_to_ohms(step):
    """
    Convert digipot code (0..127) back to approximate ohms.
    """
    step = max(0, min(MAX_CODE, step))
    return (step / MAX_CODE) * MAXIMUM_OHMS


def fix_ohms(approx_ohms):
    """
    Optional calibration curve.
    """
    return (-8.05e-7 * approx_ohms * approx_ohms) + (0.9306 * approx_ohms) + 86.9
