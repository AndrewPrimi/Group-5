import pigpio
import time
import i2c_lcd
import pigpio_encoder

# Constants; 7-bit digital potentiometer (0-128 steps)
MINIMUM_OHMS = 40
MAXIMUM_OHMS = 11000
MAX_STEPS = 128
DEFAULT_OHMS = 5000
# SPEED_LIMIT = 100

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


def on_rotate(direction, dt):
    global ohms

    speed = 1_000_000 / dt  # detents/sec

    change = 10 if speed < 100 else 100

    new_ohms = ohms + direction * change
    if MINIMUM_OHMS <= new_ohms <= MAXIMUM_OHMS:
        ohms = new_ohms
        set_lcd()


class RotaryEncoder:
    def __init__(self, pi, gpioA, gpioB, callback):
        self.pi = pi
        self.gpioA = gpioA
        self.gpioB = gpioB
        self.callback = callback

        self.last_state = 0
        self.last_tick = None

        self.pi.set_mode(gpioA, pigpio.INPUT)
        self.pi.set_mode(gpioB, pigpio.INPUT)
        self.pi.set_pull_up_down(gpioA, pigpio.PUD_UP)
        self.pi.set_pull_up_down(gpioB, pigpio.PUD_UP)

        self.cbA = self.pi.callback(gpioA, pigpio.EITHER_EDGE, self._pulse)
        self.cbB = self.pi.callback(gpioB, pigpio.EITHER_EDGE, self._pulse)

    def _pulse(self, gpio, level, tick):
        a = self.pi.read(self.gpioA)
        b = self.pi.read(self.gpioB)
        state = (a << 1) | b

        delta = {
            (0, 1):  1,
            (1, 3):  1,
            (3, 2):  1,
            (2, 0):  1,
            (0, 2): -1,
            (2, 3): -1,
            (3, 1): -1,
            (1, 0): -1,
        }.get((self.last_state, state), 0)

        self.last_state = state

        # Only trigger on full detent
        if delta == 0 or state != 0:
            return

        if self.last_tick is None:
            self.last_tick = tick
            return

        dt = pigpio.tickDiff(self.last_tick, tick)
        self.last_tick = tick

        self.callback(delta, dt)

    def cancel(self):
        self.cbA.cancel()
        self.cbB.cancel()

    def on_rotate(direction, dt):
        global ohms

        speed = 1_000_000 / dt  # detents per second

        change = 10 if speed < 100 else 100

        new_ohms = ohms + direction * change
        if MINIMUM_OHMS <= new_ohms <= MAXIMUM_OHMS:
            ohms = new_ohms
            set_lcd()


encoder = None
active_callbacks = []


def clear_callbacks():
    global encoder, active_callbacks
    if encoder:
        encoder.cancel()
        encoder = None
    for c in active_callbacks:
        c.cancel()
    active_callbacks = []


    # --- Pot control page ---
clear_callbacks()

encoder = RotaryEncoder(pi, PIN_A, PIN_B, on_rotate)
cb_btn = pi.callback(rotaryEncoder_pin, pigpio.EITHER_EDGE, callback_set_digi)
active_callbacks = [cb_btn]

while not isMainPage:
    time.sleep(0.1)
