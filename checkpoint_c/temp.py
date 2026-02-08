import pigpio
import time
import i2c_lcd

# Constants; 7-bit digital potentiometer (0-128 steps)
MINIMUM_OHMS = 50
MAXIMUM_OHMS = 110000
MAX_STEPS = 128
DEFAULT_OHMS = 5000

# Set up SPI
SPI_CHANNEL = 0
SPI_SPEED = 50000
SPI_FLAGS = 0

pi = pigpio.pi()
lcd = i2c_lcd.lcd(pi, width=20)

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
    ohms = (step / MAX_STEPS) * MAXIMUM_OHMS
    lcd.put_line(0, ohms)  # added for lcd display
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
PIN_A = 22
PIN_B = 27
rotaryEncoder_pin = 17

# Define output pins (LCD)

last_tick = None
ohms = DEFAULT_OHMS

pi.set_mode(PIN_A, pigpio.INPUT)
pi.set_mode(PIN_B, pigpio.INPUT)
pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)
pi.set_mode(rotaryEncoder_pin, pigpio.INPUT)
pi.set_pull_up_down(rotaryEncoder_pin, pigpio.PUD_UP)

# when rotar encoder is set, i.e changes state (pulled down) this function is called to set the digi pot


def callback_set_digi(gpio, level, tick):
    print('This method is being called!')
    global ohms
    # Button press is falling edge (0) because of pull-up resistor
    if level == 0:
        step = ohms_to_step(ohms)
        set_digipot_step(step)
        print('Button pressed!')


def encoder_callback(gpio, level, tick):
    global last_tick, ohms
    print("CALLBACK FIRED", gpio, level)

    # print(f"last tick: {last_tick}")
    # print(f"current tick: {tick}")

    """Determine speed and direction of the rotation of the KY-040."""
    if last_tick is not None:
        dt = pigpio.tickDiff(last_tick, tick)  # microseconds

        # Debounce
        if dt < 1500:
            last_tick = tick
            return

        # Set dt to 1000 to clamp the speed
        speed = min(1_000_000 / dt, 1000)  # pulses per second

        # -1 = CCW, 1 = CW
        print(f"level is currently: {level}")
        if pi.read(PIN_B) == 0:
            direction = 1
            print("CW")
        else:
            direction = -1
            print("CCW")

        change_steps(direction, speed)

    last_tick = tick


def change_steps(direction, speed):
    global ohms

    if speed < 10:
        change = 10
    else:
        change = 100

    print(f"calculated speed: {speed}")

    resulting_ohms = ohms + change * direction
    if resulting_ohms >= MINIMUM_OHMS and resulting_ohms <= MAXIMUM_OHMS:
        ohms = ohms + change * direction
        step = ohms_to_step(ohms)
        set_digipot_step(step)
        print(f"Current Ohms: {ohms}")
        # print(f"Current Step: {step}")
        # Write to LCD Pins
    else:
        print("ohm value is out of range...")


print("Entering try block.")
try:
    ohms = DEFAULT_OHMS
    cb = pi.callback(PIN_A, pigpio.RISING_EDGE, encoder_callback)
    st = pi.callback(rotaryEncoder_pin, pigpio.FALLING_EDGE, callback_set_digi)
    lcd.put_line(0, 'test')  # added for lcd display

    while True:
        print(pi.read(PIN_A), pi.read(PIN_B))
        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopping...")
    cb.cancel()
    st.cancel()
    pi.spi_close(handle)
    pi.stop()
