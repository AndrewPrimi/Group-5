from pot_lcd import PotLCD
import pigpio
import time
import sys
# Import the actual Rotary class and constants
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

PIN_A = 22
PIN_B = 27
BUTTON_PIN = 17

pi = pigpio.pi()
if not pi.connected:
    exit()

pot_lcd = PotLCD(pi, width=20)
handle_pot1 = pi.spi_open(SPI_CHANNEL_0, SPI_SPEED, SPI_FLAGS)
handle_pot2 = pi.spi_open(SPI_CHANNEL_1, SPI_SPEED, SPI_FLAGS)

# --- Logic Helpers ---


def ohms_to_step(ohms):
    ohms = max(0, min(ohms, MAXIMUM_OHMS))
    return int((ohms / MAXIMUM_OHMS) * MAX_STEPS)


def step_to_ohms(step):
    return (step / MAX_STEPS) * MAXIMUM_OHMS


def set_digipot_step(step_value, selected_pot):
    if 0 <= step_value <= MAX_STEPS:
        h = handle_pot1 if selected_pot == 0 else handle_pot2
        pi.spi_write(h, [0x00, step_value])
        approx_ohms = step_to_ohms(step_value)
        print(
            f"Pot {selected_pot + 1} | Step: {step_value} | Approx: {approx_ohms:.1f} Ohms")


# --- Global State ---
ohms = DEFAULT_OHMS
selected_pot = 0
menu_selection = 0
is_main_page = True

# --- Unified Callback ---


def encoder_event_callback(event):
    """
    The pigpio-encoder library calls this with an 'event' integer.
    We check this against the library's internal constants.
    """
    global menu_selection, is_main_page, selected_pot, ohms

    # --- Main Page Logic ---
    if is_main_page:
        if event == Rotary.ROT_CW:
            menu_selection = 1
            pot_lcd.request_main_page_update(menu_selection)
        elif event == Rotary.ROT_CCW:
            menu_selection = 0
            pot_lcd.request_main_page_update(menu_selection)
        elif event == Rotary.SW_PRESS:
            selected_pot = menu_selection
            is_main_page = False

    # --- Pot Control Page Logic ---
    else:
        if event == Rotary.ROT_CW:
            change_ohms(1)
        elif event == Rotary.ROT_CCW:
            change_ohms(-1)
        elif event == Rotary.SW_PRESS:
            step = ohms_to_step(ohms)
            set_digipot_step(step, selected_pot)
            pot_lcd.request_confirmation(selected_pot)
        elif event == Rotary.SW_LONG_PRESS:
            # Return to main
            ohms = DEFAULT_OHMS
            is_main_page = True


def change_ohms(direction):
    global ohms
    # Standard increment
    change = 100
    new_val = ohms + (change * direction)
    if MINIMUM_OHMS <= new_val <= MAXIMUM_OHMS:
        ohms = new_val
        step = ohms_to_step(ohms)
        pot_lcd.request_pot_page_update(step_to_ohms(step), selected_pot)

# --- Initialization ---


# Create the encoder object
my_encoder = Rotary(pi, PIN_A, PIN_B, BUTTON_PIN)

# The library uses a single callback function for all events
my_encoder.setup_rotary(callback=encoder_event_callback)
my_encoder.setup_switch(callback=encoder_event_callback,
                        long_press=True, long_press_t=3000)

# --- Main Loop ---

print("System Ready...")
try:
    # Initialize the first screen
    pot_lcd.draw_main_page()

    current_state_was_main = True

    while True:
        # Check if we just transitioned states to update the LCD base layer
        if is_main_page != current_state_was_main:
            if is_main_page:
                pot_lcd.draw_main_page()
            else:
                step = ohms_to_step(ohms)
                pot_lcd.request_pot_page_update(
                    step_to_ohms(step), selected_pot)
            current_state_was_main = is_main_page

        pot_lcd.process_updates()
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping...")
    pot_lcd.close()
    pi.spi_close(handle_pot1)
    pi.spi_close(handle_pot2)
    pi.stop()
