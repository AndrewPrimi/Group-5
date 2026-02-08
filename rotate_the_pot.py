import pigpio
import time
import i2c_lcd

# Constants; 7-bit digital potentiometer (0-128 steps)
MINIMUM_OHMS = 40
MAXIMUM_OHMS = 11000
MAX_STEPS = 128
DEFAULT_OHMS = 5000
SPEED_LIMIT = 100

# Set up SPI
SPI_CHANNEL_0 = 0
SPI_CHANNEL_1 = 1
SPI_SPEED = 50000
SPI_FLAGS = 0

pi = pigpio.pi()

lcd = i2c_lcd.lcd(pi, width=20)

# Check if connection was successful
if not pi.connected:
    exit()

# Open SPI channel handles for both pots
handle_pot1 = pi.spi_open(SPI_CHANNEL_0, SPI_SPEED, SPI_FLAGS)
handle_pot2 = pi.spi_open(SPI_CHANNEL_1, SPI_SPEED, SPI_FLAGS)
print(f"Pot 1 handle: {handle_pot1}")
print(f"Pot 2 handle: {handle_pot2}")


def ohms_to_step(ohms):
    """Convert desired Ohms to a step value (0-128)."""
    ohms = max(0, min(ohms, MAXIMUM_OHMS))
    step = int((ohms / MAXIMUM_OHMS) * MAX_STEPS)
    return step


def step_to_ohms(step):
    """Convert step value to approximate Ohms."""
    return (step / MAX_STEPS) * MAXIMUM_OHMS


def set_digipot_step(step_value):
    """Write data bytes to the currently selected MCP4131's SPI device handle."""
    if 0 <= step_value <= MAX_STEPS:
        h = handle_pot1 if selected_pot == 0 else handle_pot2
        pi.spi_write(h, [0x00, step_value])  # this is for pot side one
        approx_ohms = step_to_ohms(step_value)
        print(
            f"Pot {selected_pot + 1} | Step: {step_value:3d} | Approx: {approx_ohms:7.1f} Ohms")
    else:
        print(f"Invalid step: {step_value} (must be 0-{MAX_STEPS})")


def set_lcd():
    """Update LCD with current ohms value for the active pot."""
    global ohms
    step = ohms_to_step(ohms)
    lcd.put_line(0, f'Pot {selected_pot + 1}')
    lcd.put_line(1, f'Ohms: {step_to_ohms(step):.1f}')
    lcd.put_line(2, '')
    lcd.put_line(3, '')


def draw_main_page():
    """Draw main page with < indicator on the selected pot."""
    lcd.put_line(0, 'Select a Pot:')
    if menu_selection == 0:
        lcd.put_line(1, '< Pot 1')
        lcd.put_line(2, '  Pot 2')
    else:
        lcd.put_line(1, '  Pot 1')
        lcd.put_line(2, '< Pot 2')
    lcd.put_line(3, '')


# Pin A connected to CLK, Pin B connected to DT
PIN_A = 22
PIN_B = 27
rotaryEncoder_pin = 17

last_tick = None

ohms = DEFAULT_OHMS
selected_pot = 0
menu_selection = 0
isMainPage = True
button_press_tick = None

pi.set_mode(PIN_A, pigpio.INPUT)
pi.set_mode(PIN_B, pigpio.INPUT)
pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)
pi.set_mode(rotaryEncoder_pin, pigpio.INPUT)
pi.set_pull_up_down(rotaryEncoder_pin, pigpio.PUD_UP)


# --- Main page callbacks ---

def menu_encoder_callback(gpio, level, tick):
    """Rotate between Pot 1 and Pot 2 on the main page."""
    global last_tick, menu_selection

    if last_tick is not None:
        dt = pigpio.tickDiff(last_tick, tick)
        if dt < 5000:
            last_tick = tick
            return

        if pi.read(PIN_B) == 0:
            menu_selection = 1
        else:
            menu_selection = 0

        draw_main_page()

    last_tick = tick


def menu_button_callback(gpio, level, tick):
    """Select a pot from the main page when button is pressed."""
    global isMainPage, selected_pot
    if level == 0:
        selected_pot = menu_selection
        isMainPage = False


# --- Pot control callbacks ---

def callback_set_digi(gpio, level, tick):
    """When button is pressed, set the digi pot. Track press time for long hold."""
    global ohms, button_press_tick
    if level == 0:
        # Button pressed - record the tick for long-press detection
        button_press_tick = tick
        step = ohms_to_step(ohms)
        set_digipot_step(step)
        lcd.put_line(2, 'Value set!')
        lcd.put_line(3, f'Pot {selected_pot + 1} updated')
        print('Button pressed! Value sent to digi pot.')
    elif level == 1 and button_press_tick is not None:
        # Button released - check if held for 3 seconds
        hold_time = pigpio.tickDiff(button_press_tick, tick)
        button_press_tick = None
        if hold_time >= 3_000_000:  # 3 seconds in microseconds
            return_to_main()


last_state = None
last_step_tick = None


def encoder_callback(gpio, level, tick):
    global last_state, last_step_tick, ohms

    a = pi.read(PIN_A)
    b = pi.read(PIN_B)
    state = (a << 1) | b

    if last_state is None:
        last_state = state
        return

    # Determine direction from state progression
    if (last_state, state) in ((0, 1), (1, 3), (3, 2), (2, 0)):
        direction = 1     # CW
    elif (last_state, state) in ((0, 2), (2, 3), (3, 1), (1, 0)):
        direction = -1    # CCW
    else:
        last_state = state
        return  # bounce or invalid transition

    last_state = state

    # Only act once per detent (state == 00)
    if state != 0:
        return

    if last_step_tick is None:
        last_step_tick = tick
        return

    dt = pigpio.tickDiff(last_step_tick, tick)
    last_step_tick = tick

    speed = 1_000_000 / dt

    change = 10 if speed < SPEED_LIMIT else 100

    new_ohms = ohms + direction * change
    if MINIMUM_OHMS <= new_ohms <= MAXIMUM_OHMS:
        ohms = new_ohms
        set_lcd()


def change_steps(direction, speed):
    global ohms

    if speed < 10:
        change = 10
    else:
        change = 100

    resulting_ohms = ohms + change * direction
    if resulting_ohms >= MINIMUM_OHMS and resulting_ohms <= MAXIMUM_OHMS:
        ohms = ohms + change * direction
        print(f"Current Ohms: {ohms}")
        set_lcd()
    else:
        print("ohm value is out of range...")


# --- State management ---

active_callbacks = []


def clear_callbacks():
    """Cancel all active callbacks."""
    global active_callbacks
    for c in active_callbacks:
        c.cancel()
    active_callbacks = []


def return_to_main():
    """Reset pot ohms to default and go back to main page."""
    global isMainPage, ohms
    ohms = DEFAULT_OHMS
    isMainPage = True


# --- Main loop ---

print("Starting...")
try:
    while True:
        # main page
        isMainPage = True
        last_tick = None
        clear_callbacks()

        draw_main_page()

        cb_enc_a = pi.callback(PIN_A, pigpio.EITHER_EDGE, encoder_callback)
        cb_enc_b = pi.callback(PIN_B, pigpio.EITHER_EDGE, encoder_callback)
        # cb_enc_b = pi.callback(PIN_B, pigpio.FALLING_EDGE,
        # menu_encoder_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.FALLING_EDGE, menu_button_callback)
        active_callbacks = [cb_enc, cb_btn]

        while isMainPage:
            time.sleep(0.1)

        # pot control page
        isMainPage = False
        last_tick = None
        clear_callbacks()

        ohms = DEFAULT_OHMS
        set_lcd()

        cb_enc = pi.callback(PIN_A, pigpio.EITHER_EDGE, encoder_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.EITHER_EDGE, callback_set_digi)
        active_callbacks = [cb_enc, cb_btn]

        while not isMainPage:
            time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopping...")
    clear_callbacks()
    lcd.close()
    pi.spi_close(handle_pot1)
    pi.spi_close(handle_pot2)
    pi.stop()
