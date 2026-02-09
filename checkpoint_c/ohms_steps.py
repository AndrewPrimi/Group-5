# Constants; 7-bit digital potentiometer (0-128 steps)
MINIMUM_OHMS = 100
MAXIMUM_OHMS = 10000
MAX_STEPS = 128
DEFAULT_OHMS = 5000
BUTTON_DEBOUNCE_US = 200000    # 200ms button debounce

# Constant resistance presets
CONSTANT_OHMS = [100, 1000, 5000, 10000]
CONSTANT_LABELS = ['100', '1k', '5k', '10k']

# SPI settings
SPI_CHANNEL = 0
SPI_SPEED = 50000
SPI_FLAGS = 0


def ohms_to_step(ohms):
    """Convert desired Ohms to a step value (0-128)."""
    ohms = max(0, min(ohms, MAXIMUM_OHMS))
    step = int((ohms / MAXIMUM_OHMS) * MAX_STEPS)
    return step


def step_to_ohms(step):
    """Convert step value to approximate Ohms."""
    return (step / MAX_STEPS) * MAXIMUM_OHMS
