import pigpio
import time
import i2c_lcd
from ohms_steps import (
    ohms_to_step, step_to_ohms,
    DEFAULT_OHMS, SPI_CHANNEL, SPI_SPEED, SPI_FLAGS,
)
from callbacks import (
    setup_callbacks, clear_callbacks,
    menu_direction_callback, menu_button_callback,
    pot_direction_callback, callback_set_digi,
    PIN_A, PIN_B,
)
import rotary_encoder

# Rotary encoder button pin
rotaryEncoder_pin = 17

pi = pigpio.pi()

# Check if connection was successful
if not pi.connected:
    exit()

# LCD
lcd = i2c_lcd.lcd(pi, width=20)

# Open SPI handle for MCP4231 (dual pot on one chip)
spi_handle = pi.spi_open(SPI_CHANNEL, SPI_SPEED, SPI_FLAGS)
print(f"SPI handle: {spi_handle}")

# Shared state
state = {
    'ohms': DEFAULT_OHMS,
    'selected_pot': 0,
    'menu_selection': 0,
    'isMainPage': True,
    'last_time': None,
    'button_press_tick': None,
    'button_last_tick': None,
    'spi_handle': spi_handle,
    'active_callbacks': [],
}

# Set up GPIO pins
pi.set_mode(PIN_A, pigpio.INPUT)
pi.set_mode(PIN_B, pigpio.INPUT)
pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)
pi.set_mode(rotaryEncoder_pin, pigpio.INPUT)
pi.set_pull_up_down(rotaryEncoder_pin, pigpio.PUD_UP)

# Hardware glitch filters
pi.set_glitch_filter(PIN_A, 10000)
pi.set_glitch_filter(PIN_B, 10000)
pi.set_glitch_filter(rotaryEncoder_pin, 10000)

# Give callbacks access to shared state and LCD
setup_callbacks(state, pi, lcd)

# --- Main loop ---

print("Starting...")
try:
    while True:
        # main page
        state['isMainPage'] = True
        state['button_last_tick'] = None
        clear_callbacks(state)

        lcd.put_line(0, 'Select a Pot:')
        lcd.put_line(1, '> Pot 1')
        lcd.put_line(2, '  Pot 2')
        lcd.put_line(3, '')

        decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, menu_direction_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.FALLING_EDGE, menu_button_callback)
        state['active_callbacks'] = [decoder, cb_btn]

        while state['isMainPage']:
            time.sleep(0.05)

        # pot control page
        state['isMainPage'] = False
        state['last_time'] = None
        state['button_last_tick'] = None
        clear_callbacks(state)

        state['ohms'] = DEFAULT_OHMS
        step = ohms_to_step(state['ohms'])
        lcd.put_line(0, f'Pot {state["selected_pot"] + 1}')
        lcd.put_line(1, f'Ohms: {step_to_ohms(step):.1f}')
        lcd.put_line(2, '')
        lcd.put_line(3, '')

        decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, pot_direction_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.EITHER_EDGE, callback_set_digi)
        state['active_callbacks'] = [decoder, cb_btn]

        while not state['isMainPage']:
            time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping...")
    clear_callbacks(state)
    lcd.close()
    pi.spi_close(spi_handle)
    pi.stop()
