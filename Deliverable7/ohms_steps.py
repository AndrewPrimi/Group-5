"""
ohms_steps.py

Constants and conversion helpers for the MCP4231 / MCP4131 family.

Important:
- 7-bit wiper codes go from 0 to 127
- There are 128 total positions
"""

# ===== Digital pot constants =====
MINIMUM_OHMS = 0
MAXIMUM_OHMS = 10000

NUM_POSITIONS = 128      # total positions
MAX_CODE = 127           # valid code range: 0..127
DEFAULT_CODE = 64

# ===== UI / presets =====
DEFAULT_OHMS = 5000
CONSTANT_OHMS = [100, 1000, 5000, 10000]
CONSTANT_LABELS = ["100", "1k", "5k", "10k"]

# ===== SPI config =====
# IMPORTANT:
# If CS is on GPIO8 (CE0), use SPI_CHANNEL = 0
# If CS is on GPIO7 (CE1), use SPI_CHANNEL = 1
SPI_CHANNEL = 1
SPI_SPEED = 100000
SPI_FLAGS = 0

# ===== Misc =====
BUTTON_DEBOUNCE_US = 200000


def clamp_code(code: int) -> int:
    """Clamp a digipot code to the valid 0..127 range."""
    return max(0, min(MAX_CODE, int(code)))


def ohms_to_code(ohms: float) -> int:
    """
    Convert desired ohms to digipot code.
    Assumes approximately linear mapping across 0..10k.
    """
    ohms = max(MINIMUM_OHMS, min(MAXIMUM_OHMS, float(ohms)))
    code = round((ohms / MAXIMUM_OHMS) * MAX_CODE)
    return clamp_code(code)


def code_to_ohms(code: int) -> float:
    """Convert digipot code back to approximate ohms."""
    code = clamp_code(code)
    return (code / MAX_CODE) * MAXIMUM_OHMS


def fix_ohms(approx_ohms: float) -> float:
    """
    Optional empirical calibration correction.
    Keep this only if it improves your measured results.
    """
    return (-8.05e-7 * approx_ohms * approx_ohms) + (0.9306 * approx_ohms) + 86.9
