from pot_lcd import PotLCD
import pigpio
import time
import sys
from pigpio_encoder.rotary import Rotary

sys.path.insert(0, 'checkpoint_c')

# Constants
MINIMUM_OHMS = 40
MAXIMUM_OHMS = 11000
MAX_STEPS = 128
DEFAULT_OHMS = 5000

# SPI Setup
SPI_CHANNEL_0 = 0
SPI_CHANNEL_1 = 1
SPI_SPEED = 50000
SPI_FLAGS = 0

# Pin definitions
PIN_A = 22
PIN_B = 27
BUTTON_PIN = 17

pi = pigpio.pi()
if not pi.connected:
    exit()

pot_lcd = PotLCD(pi, width=20)
handle_pot1 = pi.spi_open(SPI_CHANNEL_0, SPI_SPEED, SPI_FLAGS)
handle_pot2 = pi.spi_open(SPI_CHANNEL_1, SPI_SPEED, SPI_FLAGS)

# Initialize the Encoder via the library
# We provide the pins here; callbacks will be assigned later
encoder = Rotary(pi, PIN_A, PIN_B, BUTTON_PIN)

# --- Logic Helpers ---


def ohms_to_step(ohms):
    ohms = max(0, min(ohms, MAXIMUM_OHMS))
    return int((ohms / MAXIMUM_OHMS) * MAX_STEPS)


def step_to_ohms(step):
    return (step / MAX_STEPS) * MAXIMUM_OHMS


def set_digipot_step(step_value):
    if 0 <= step_value <= MAX_STEPS:
        h = handle_pot1 if selected_pot == 0 else handle_pot2
        pi.spi_write(h, [0x00, step_value])
        approx_ohms = step_to_ohms(step_value)
        print(
            f"Pot {selected_pot + 1} | Step: {step_value} | Approx: {approx_ohms:.1f} Ohms")

# --- State Variables ---


ohms = DEFAULT_OHMS
selected_pot = 0
menu_selection = 0
isMainPage = True

# --- Callback Functions ---


def on_menu_rotate(direction):
    """Callback for Main Page: Switch between Pot 1 and Pot 2."""
    global menu_selection
    # direction is 1 (CW) or -1 (CCW)
    if direction == 1:
        menu_selection = 1
    else:
        menu_selection = 0
    pot_lcd.request_main_page_update(menu_selection)


def on_menu_press():
    """Callback for Main Page: Select the pot and switch states."""
    global isMainPage, selected_pot
    selected_pot = menu_selection
    isMainPage = False


def on_pot_rotate(direction):
    """Callback for Pot Page: Adjust Ohm value."""
    global ohms
    # Logic: small movements = 10, faster or consistent movements = 100
    # (Note: pigpio-encoder provides raw direction; you can add speed logic if needed)
    change = 100
    resulting_ohms = ohms + (change * direction)

    if MINIMUM_OHMS <= resulting_ohms <= MAXIMUM_OHMS:
        ohms = resulting_ohms
        step = ohms_to_step(ohms)
        pot_lcd.request_pot_page_update(step_to_ohms(step), selected_pot)


def on_pot_press():
    """Callback for Pot Page: Set value on click."""
    step = ohms_to_step(ohms)
    set_digipot_step(step)
    pot_lcd.request_confirmation(selected_pot)


def on_pot_long_press():
    """Callback for Pot Page: Return to main on 3s hold."""
    global isMainPage, ohms
    ohms = DEFAULT_OHMS
    isMainPage = True

# --- Main loop ---


print("Starting...")
try:
    while True:
        # --- State: Main Page ---
        isMainPage = True
        pot_lcd.draw_main_page()

        # Configure encoder for menu navigation
        encoder.setup(
            rotary_callback=on_menu_rotate,
            sw_callback=on_menu_press
        )

        while isMainPage:
            pot_lcd.process_updates()
            time.sleep(0.05)

        # --- State: Pot Control Page ---
        isMainPage = False
        ohms = DEFAULT_OHMS
        step = ohms_to_step(ohms)
        pot_lcd.request_pot_page_update(step_to_ohms(step), selected_pot)

        # Configure encoder for value adjustment
        # Setting long_press_duration to 3000ms (3 seconds)
        encoder.setup(
            rotary_callback=on_pot_rotate,
            sw_callback=on_pot_press,
            long_press_callback=on_pot_long_press,
            long_press_t=3000
        )

        while not isMainPage:
            pot_lcd.process_updates()
            time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping...")
    pot_lcd.close()
    pi.spi_close(handle_pot1)
    pi.spi_close(handle_pot2)
    pi.stop()
