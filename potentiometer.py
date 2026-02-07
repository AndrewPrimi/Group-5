import pigpio
import time

# Constants; 7-bit digital potentiometer (0-128 steps)
MAXIMUM_OHMS = 10000
MAX_STEPS = 128

# Set up SPI
SPI_CHANNEL = 0
SPI_SPEED = 50000
SPI_FLAGS = 0

pi = pigpio.pi()

# Check if connection was successful
if not pi.connected:
    exit()

# Open SPI channel handle
handle = pi.spi_open(SPI_CHANNEL, SPI_SPEED, SPI_FLAGS)
print(f"Handle is: {handle}")


def ohms_to_step(ohms):
    """Convert desired Ohms to a step value (0-128)."""
    ohms = max(0, min(ohms, MAXIMUM_OHMS))
    step = int((ohms / MAXIMUM_OHMS) * MAX_STEPS)
    return step


def step_to_ohms(step):
    """Convert step value to approximate Ohms."""
    return (step / MAX_STEPS) * MAXIMUM_OHMS


def set_digipot_step(step_value):
    """Write data bytes to MCP4131's SPI device handle."""
    if 0 <= step_value <= MAX_STEPS:
        pi.spi_write(handle, [0x00, step_value])
        approx_ohms = step_to_ohms(step_value)
        print(f"Step: {step_value:3d} | Approx: {approx_ohms:7.1f} Ohms")
    else:
        print(f"Invalid step: {step_value} (must be 0-{MAX_STEPS})")

try:
    print("Starting the cycle.\nMeasure across Terminal A and Wiper.")
    print("Press Ctrl+C to stop.\n")

    # Mode 1: Step through specific Ohm values (100, 1000, 5000, 10000)
    print("=== Testing specific Ohm values: 100, 1000, 5000, 10000 ===")
    pot_values = [100, 1000, 5000, 10000]
    for ohms in pot_values:
        step = ohms_to_step(ohms)
        set_digipot_step(step)
        time.sleep(10)

    # Mode 2: Increment step by one (0 to 128)
    print("\n=== Stepping through all values (0 to 128) ===")
    for step in range(0, MAX_STEPS + 1):
        set_digipot_step(step)
        time.sleep(2)

except KeyboardInterrupt:
    print("\nStopping...")
    pi.spi_close(handle)
    pi.stop()
