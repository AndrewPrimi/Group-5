# Constants; 7-bit digital potentiometer (0-128 steps)
MINIMUM_OHMS = 40
MAXIMUM_OHMS = 11000
MAX_STEPS = 128
DEFAULT_OHMS = 5000
SPEED_LIMIT = 100

# Debounce constants (microseconds)
ENCODER_DEBOUNCE_US = 10000    # 10ms encoder debounce
MENU_DEBOUNCE_US = 15000       # 15ms menu encoder debounce
BUTTON_DEBOUNCE_US = 200000    # 200ms button debounce

# SPI settings
SPI_CHANNEL_0 = 0
SPI_CHANNEL_1 = 1
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
