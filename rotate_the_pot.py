import pigpio
import time

# Constants; 7-bit digital potentiometer (0-128 steps)
MINIMUM_OHMS = 100
MAXIMUM_OHMS = 10000
MAX_STEPS = 128
DEFAULT_OHMS = 100

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


# wiper functions

# Pin A connected to CLK, Pin B connected to DT
PIN_A = 13
PIN_B = 15

# Define output pins (LCD)

last_tick = None
ohms = DEFAULT_OHMS

pi.set_mode(PIN_A, pigpio.INPUT)
pi.set_mode(PIN_B, pigpio.INPUT)
pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)
# set_mode pigpio.OUTPUT s


def encoder_callback(gpio, level, tick):
    global last_tick, ohms

    print(f"last tick: {last_tick}")
    print(f"current tick: {tick}")

    """Determine speed and direction of the rotation of the KY-040."""

    if last_tick is not None:
        dt = pigpio.tickDiff(last_tick, tick)  # microseconds

        # Debounce
        if dt < 2000:
            last_tick = tick
            return

        # Set dt to 1000 to clamp the speed
        speed = min(1_000_000 / dt, 1000)  # pulses per second

        # -1 = CCW, 1 = CW
        if pi.read(PIN_B) != level:
            print("CCW")
            direction = -1
        else:
            print("CW")
            direction = 1

        detector_and_change_steps(direction, speed)

    last_tick = tick

def detector_and_change_steps(direction, speed):
    global ohms

    if speed < 100:
        change = 10
    else:
        change = 100

    print(f"calculated speed: {speed}")

    ohms = ohms + change * direction
    step = ohms_to_step(ohms)
    set_digipot_step(step)
    print(f"Current Ohms: {ohms}")
    print(f"Current Step: {step}")
    # Write to LCD Pins

print("Entering try block.")
try:
    ohms = DEFAULT_OHMS
    cb = pi.callback(PIN_A, pigpio.RISING_EDGE, encoder_callback)

    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopping...")
    cb.cancel()
    pi.spi_close(handle)
    pi.stop()
