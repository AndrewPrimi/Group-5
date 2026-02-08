import pigpio
import time
<<<<<<< HEAD
import i2c_lcd
import pigpio_encoder
=======
import sys
sys.path.insert(0, 'checkpoint_c')
from pot_lcd import PotLCD
>>>>>>> 3c7c3e904cc356deab32fe04918f0d06cc600394

# Constants; 7-bit digital potentiometer (0-128 steps)
MINIMUM_OHMS = 40
MAXIMUM_OHMS = 11000
MAX_STEPS = 128
DEFAULT_OHMS = 5000
# SPEED_LIMIT = 100

# Debounce constants (microseconds)
ENCODER_DEBOUNCE_US = 10000    # 10ms encoder debounce
MENU_DEBOUNCE_US = 15000       # 15ms menu encoder debounce
BUTTON_DEBOUNCE_US = 200000    # 200ms button debounce

# Set up SPI
SPI_CHANNEL_0 = 0
SPI_CHANNEL_1 = 1
SPI_SPEED = 50000
SPI_FLAGS = 0

pi = pigpio.pi()

# Check if connection was successful
if not pi.connected:
    exit()

# LCD display handler
pot_lcd = PotLCD(pi, width=20)

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
        pi.spi_write(h, [0x00, step_value])
        approx_ohms = step_to_ohms(step_value)
        print(
            f"Pot {selected_pot + 1} | Step: {step_value:3d} | Approx: {approx_ohms:7.1f} Ohms")
    else:
        print(f"Invalid step: {step_value} (must be 0-{MAX_STEPS})")


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
button_last_tick = None

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
        if dt < MENU_DEBOUNCE_US:
            last_tick = tick
            return

        if pi.read(PIN_B) == 0:
            menu_selection = 1
        else:
            menu_selection = 0

        # Set flag instead of writing LCD directly
        pot_lcd.request_main_page_update(menu_selection)

    last_tick = tick


def menu_button_callback(gpio, level, tick):
    """Select a pot from the main page when button is pressed."""
    global isMainPage, selected_pot, button_last_tick
    if level == 0:
        # Debounce button
        if button_last_tick is not None:
            if pigpio.tickDiff(button_last_tick, tick) < BUTTON_DEBOUNCE_US:
                return
        button_last_tick = tick
        selected_pot = menu_selection
        isMainPage = False


# --- Pot control callbacks ---

def callback_set_digi(gpio, level, tick):
    """When button is pressed, set the digi pot. Track press time for long hold."""
    global ohms, button_press_tick, button_last_tick
    if level == 0:
        # Debounce button
        if button_last_tick is not None:
            if pigpio.tickDiff(button_last_tick, tick) < BUTTON_DEBOUNCE_US:
                return
        button_last_tick = tick

        # Button pressed - record the tick for long-press detection
        button_press_tick = tick
        step = ohms_to_step(ohms)
        set_digipot_step(step)
        # Set flag instead of writing LCD directly
        pot_lcd.request_confirmation(selected_pot)
        print('Button pressed! Value sent to digi pot.')
    elif level == 1 and button_press_tick is not None:
        # Button released - check if held for 3 seconds
        hold_time = pigpio.tickDiff(button_press_tick, tick)
        button_press_tick = None
        if hold_time >= 3_000_000:  # 3 seconds in microseconds
            return_to_main()


<<<<<<< HEAD
=======
def encoder_callback(gpio, level, tick):
    global last_tick, ohms

    if last_tick is not None:
        dt = pigpio.tickDiff(last_tick, tick)

        # Debounce
        if dt < ENCODER_DEBOUNCE_US:
            last_tick = tick
            return

        speed = min(1_000_000 / dt, 1000)  # pulses per second

        if pi.read(PIN_B) == 0:
            direction = 1
        else:
            direction = -1

        if speed <= SPEED_LIMIT:
            change_steps(direction, speed)

    last_tick = tick


>>>>>>> 3c7c3e904cc356deab32fe04918f0d06cc600394
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
        # Set flag instead of writing LCD directly
        step = ohms_to_step(ohms)
        pot_lcd.request_pot_page_update(step_to_ohms(step), selected_pot)
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

<<<<<<< HEAD
    speed = 1_000_000 / dt  # detents/sec

    change = 10 if speed < 100 else 100

    new_ohms = ohms + direction * change
    if MINIMUM_OHMS <= new_ohms <= MAXIMUM_OHMS:
        ohms = new_ohms
        set_lcd()
=======
print("Starting...")
try:
    while True:
        # main page
        isMainPage = True
        last_tick = None
        button_last_tick = None
        clear_callbacks()

        pot_lcd.draw_main_page()

        cb_enc = pi.callback(PIN_A, pigpio.EITHER_EDGE, menu_encoder_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.FALLING_EDGE, menu_button_callback)
        active_callbacks = [cb_enc, cb_btn]

        while isMainPage:
            pot_lcd.process_updates()
            time.sleep(0.05)

        # pot control page
        isMainPage = False
        last_tick = None
        button_last_tick = None
        clear_callbacks()

        ohms = DEFAULT_OHMS
        step = ohms_to_step(ohms)
        pot_lcd.request_pot_page_update(step_to_ohms(step), selected_pot)
        pot_lcd.process_updates()
>>>>>>> 3c7c3e904cc356deab32fe04918f0d06cc600394


<<<<<<< HEAD
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
=======
        while not isMainPage:
            pot_lcd.process_updates()
            time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping...")
    clear_callbacks()
    pot_lcd.close()
    pi.spi_close(handle_pot1)
    pi.spi_close(handle_pot2)
    pi.stop()
>>>>>>> 3c7c3e904cc356deab32fe04918f0d06cc600394
