"""
main.py – Entry point for the digital potentiometer controller.

Initialises hardware (pigpio, I2C LCD, SPI for the MCP4231), then runs a
page-based menu loop driven by a rotary encoder and its push-button:

  1. Main page       – choose Pot 1 or Pot 2
  2. Var/Const page  – choose Variable or Constant resistance mode
  3a. Variable page  – dial in a resistance with the encoder, press to set
  3b. Constant page  – pick a preset (100, 1k, 5k, 10k), press to set

A long button hold (2-3 s) on pages 3a/3b returns to the main page.
"""

import pigpio
import time
import i2c_lcd
from ohms_steps import (
    ohms_to_step, step_to_ohms,
    DEFAULT_OHMS, SPI_CHANNEL, SPI_SPEED, SPI_FLAGS,
    CONSTANT_LABELS,
)
from callbacks import (
    setup_callbacks, clear_callbacks,
    menu_direction_callback, menu_button_callback,
    varconst_direction_callback, varconst_button_callback,
    pot_direction_callback, callback_set_digi,
    constant_direction_callback, constant_button_callback,
    PIN_A, PIN_B,
)
import rotary_encoder

# ── Hardware setup ──────────────────────────────────────

# GPIO pin for the rotary encoder's built-in push-button 
rotaryEncoder_pin = 17

# Connect to the pigpio daemon 
pi = pigpio.pi()
if not pi.connected:
    exit()

# Initialise the 20x4 I2C LCD (PCF8574T backpack, default address 0x27)
lcd = i2c_lcd.lcd(pi, width=20)

# Open SPI for the MCP4231 dual digital potentiometer
spi_handle = pi.spi_open(SPI_CHANNEL, SPI_SPEED, SPI_FLAGS)
print(f"SPI handle: {spi_handle}")

# Shared state dictionary
# Passed to callbacks.py so interrupt handlers can read/write program state.
state = {
    'ohms': DEFAULT_OHMS,            # current target resistance (variable mode)
    'selected_pot': 0,               # 0 = Pot 1, 1 = Pot 2
    'menu_selection': 0,             # highlighted item on the main page
    'isMainPage': True,              # flag: currently on main page?
    'isVarConstPage': False,         # flag: currently on var/const page?
    'var_const_selection': 0,        # 0 = Variable, 1 = Constant
    'constant_selection': 0,         # index into CONSTANT_OHMS presets
    'last_time': None,               # timestamp of last encoder detent (speed calc)
    'button_press_tick': None,       # tick when button was pressed (hold detection)
    'button_last_tick': None,        # tick of last accepted press (debounce)
    'spi_handle': spi_handle,        # pigpio SPI handle for MCP4231
    'active_callbacks': [],          # list of pigpio callbacks to cancel on page change
}


# Encoder A/B channels
pi.set_mode(PIN_A, pigpio.INPUT)
pi.set_mode(PIN_B, pigpio.INPUT)
pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)

# Encoder button 
pi.set_mode(rotaryEncoder_pin, pigpio.INPUT)
pi.set_pull_up_down(rotaryEncoder_pin, pigpio.PUD_UP)

# 10 ms glitch filter on the button pin only.
# The encoder channels are debounced by the Gray-code state machine in
# rotary_encoder.decoder, so they don't need a glitch filter.
pi.set_glitch_filter(rotaryEncoder_pin, 10000)

# Inject hardware references into the callbacks module
setup_callbacks(state, pi, lcd)

print("Starting...")
try:
    while True:

        # main page
        state['isMainPage'] = True
        state['menu_selection'] = 0
        state['button_last_tick'] = None
        clear_callbacks(state)

        # Draw the initial menu screen
        lcd.put_line(0, 'Select a Pot:')
        lcd.put_line(1, '> Pot 1')
        lcd.put_line(2, '  Pot 2')
        lcd.put_line(3, '')

        # Register encoder rotation + button press callbacks
        decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, menu_direction_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.FALLING_EDGE, menu_button_callback)
        state['active_callbacks'] = [decoder, cb_btn]

        # Spin until the button callback clears isMainPage
        while state['isMainPage']:
            time.sleep(0.05)

        # page 2
        state['isVarConstPage'] = True
        state['var_const_selection'] = 0
        state['button_last_tick'] = None
        clear_callbacks(state)

        lcd.put_line(0, 'Resistance Type:')
        lcd.put_line(1, '> Variable')
        lcd.put_line(2, '  Constant')
        lcd.put_line(3, '')

        decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, varconst_direction_callback)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.FALLING_EDGE, varconst_button_callback)
        state['active_callbacks'] = [decoder, cb_btn]

        while state['isVarConstPage']:
            time.sleep(0.05)

        if state['var_const_selection'] == 0:
            #page 3a
            state['isMainPage'] = False
            state['last_time'] = None
            state['button_last_tick'] = None
            clear_callbacks(state)

            # Reset to default and display starting value
            state['ohms'] = DEFAULT_OHMS
            step = ohms_to_step(state['ohms'])
            lcd.put_line(0, f'Pot {state["selected_pot"] + 1}')
            lcd.put_line(1, f'Ohms: {step_to_ohms(step):.1f}')
            lcd.put_line(2, '')
            lcd.put_line(3, '')

            # Encoder rotation adjusts ohms; button press writes to MCP4231.
            # EITHER_EDGE on button so we can detect long holds on release.
            decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, pot_direction_callback)
            cb_btn = pi.callback(
                rotaryEncoder_pin, pigpio.EITHER_EDGE, callback_set_digi)
            state['active_callbacks'] = [decoder, cb_btn]

            # Stay until a long hold sets isMainPage = True
            while not state['isMainPage']:
                press_tick = state['button_press_tick']
                if press_tick is not None:
                    now = pi.get_current_tick()
                    if pigpio.tickDiff(press_tick, now) >= 2_000_000:
                        # 3 seconds elapsed while held 
                        state['ohms'] = DEFAULT_OHMS
                        state['button_press_tick'] = None
                        state['isMainPage'] = True
                time.sleep(0.05)

        else:
            # page 3b
            state['isMainPage'] = False
            state['constant_selection'] = 0
            state['button_last_tick'] = None
            clear_callbacks(state)

            lcd.put_line(0, f'Pot {state["selected_pot"] + 1} - Constant')
            lcd.put_line(1, f'Value: {CONSTANT_LABELS[0]} Ohms')
            lcd.put_line(2, '')
            lcd.put_line(3, '')

            # Encoder cycles through presets; button writes chosen value.
            decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, constant_direction_callback)
            cb_btn = pi.callback(
                rotaryEncoder_pin, pigpio.EITHER_EDGE, constant_button_callback)
            state['active_callbacks'] = [decoder, cb_btn]

            while not state['isMainPage']:
                time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping...")
    clear_callbacks(state)
    lcd.close()
    pi.spi_close(spi_handle)
    pi.stop()
