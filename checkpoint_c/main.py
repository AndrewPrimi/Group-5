import pigpio
import time
from pot_lcd import PotLCD
from ohms_steps import (
    ohms_to_step, step_to_ohms,
    DEFAULT_OHMS, SPI_CHANNEL_0, SPI_CHANNEL_1, SPI_SPEED, SPI_FLAGS,
)
from callbacks import (
    setup_callbacks, clear_callbacks,
    menu_encoder_callback, menu_button_callback,
    encoder_callback, callback_set_digi,
    PIN_A, PIN_B,
)

# Rotary encoder button pin
rotaryEncoder_pin = 17

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

# Shared state - all mutable state lives here
state = {
    'ohms': DEFAULT_OHMS,
    'selected_pot': 0,
    'menu_selection': 0,
    'isMainPage': True,
    'last_tick': None,
    'button_press_tick': None,
    'button_last_tick': None,
    'handle_pot1': handle_pot1,
    'handle_pot2': handle_pot2,
    'active_callbacks': [],
}

# Set up GPIO pins
pi.set_mode(PIN_A, pigpio.INPUT)
pi.set_mode(PIN_B, pigpio.INPUT)
pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)
pi.set_mode(rotaryEncoder_pin, pigpio.INPUT)
pi.set_pull_up_down(rotaryEncoder_pin, pigpio.PUD_UP)

# Give callbacks access to shared state
setup_callbacks(state, pi, pot_lcd)

# --- Main loop ---

print("Starting...")
try:
    while True:
        # main page
        state['isMainPage'] = True
        state['last_tick'] = None
        state['button_last_tick'] = None
        clear_callbacks(state)

        pot_lcd.draw_main_page()

        cb_enc = pi.callback(PIN_A, pigpio.EITHER_EDGE, menu_encoder_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.FALLING_EDGE, menu_button_callback)
        state['active_callbacks'] = [cb_enc, cb_btn]

        while state['isMainPage']:
            pot_lcd.process_updates()
            time.sleep(0.05)

        # pot control page
        state['isMainPage'] = False
        state['last_tick'] = None
        state['button_last_tick'] = None
        clear_callbacks(state)

        state['ohms'] = DEFAULT_OHMS
        step = ohms_to_step(state['ohms'])
        pot_lcd.request_pot_page_update(step_to_ohms(step), state['selected_pot'])
        pot_lcd.process_updates()

        cb_enc = pi.callback(PIN_A, pigpio.EITHER_EDGE, encoder_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.EITHER_EDGE, callback_set_digi)
        state['active_callbacks'] = [cb_enc, cb_btn]

        while not state['isMainPage']:
            pot_lcd.process_updates()
            time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping...")
    clear_callbacks(state)
    pot_lcd.close()
    pi.spi_close(handle_pot1)
    pi.spi_close(handle_pot2)
    pi.stop()
