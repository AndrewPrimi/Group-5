"""
Driver.py

Integrated LCD UI driver following this structure:

Mode Select
1. Function Generator
2. Ohmmeter
3. Voltmeter
4. DC Reference
5. Back
6. Main

Function Generator
- Type
- Frequency
- Amplitude
- Output
- Back
- Main

Voltmeter
- Source
- Back
- Main

DC Reference
- Voltage Value Input
- Output
- Back
- Main

This version integrates:
- i2c_lcd.py
- rotary_encoder.py (through callbacks.py)
- ohmmeter.py
- ohms_steps.py
- dc_reference.py
- sar_logic.py

It also keeps a placeholder function-generator branch so the UI tree
matches your required structure even if the waveform path is still being
finished.
"""

import time
import pigpio

import i2c_lcd
import rotary_encoder

from callbacks import (
    PIN_A,
    PIN_B,
    ROTARY_BTN_PIN,
    
    setup_callbacks,
    clear_callbacks,

    pot_menu_direction_callback,
    pot_menu_button_callback,

    varconst_direction_callback,
    varconst_button_callback,
    
    constant_direction_callback,
    constant_button_callback,
    
    callback_set_digi,
    pot_direction_callback,
    
    pick_menu,
    #adjust_value,
    #wait_for_back_page,

)

from ohmmeter import (
    open_adc,
    close_adc,
    averaged_measure as ohm_averaged_measure,
    step_to_resistance,
    tolerance as ohm_tolerance,
    COMPARATOR2_PIN as OHM_COMPARATOR_PIN,
    MCP4131_MAX_STEPS,
)

from ohms_steps import (
    #MINIMUM_OHMS,
    #MAXIMUM_OHMS,
    ohms_to_step, step_to_ohms,
    DEFAULT_OHMS, SPI_CHANNEL, SPI_SPEED, SPI_FLAGS,
    CONSTANT_LABELS,
)

from dc_reference import DCReferenceGenerator
from sar_logic import SAR_ADC

# square wave stuff

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
    'ohms': DEFAULT_OHMS,                        # current target resistance (variable mode)
    'selected_pot': 0,                           # 0 = Pot 1, 1 = Pot 2
    'pot_values': [DEFAULT_OHMS, DEFAULT_OHMS],  # [Pot 1 Value, Pot 2 Value]
    'menu_selection': 0,                         # highlighted item on the main page
    'isMainPage': True,                          # flag: currently on main page?
    'isVarConstPage': False,                     # flag: currently on var/const page?
    'var_const_selection': 0,                    # 0 = Variable, 1 = Constant
    'constant_selection': 0,                     # index into CONSTANT_OHMS presets
    'last_time': None,                           # timestamp of last encoder detent (speed calc)
    'button_press_tick': None,                   # tick when button was pressed (hold detection)
    'button_last_tick': None,                    # tick of last accepted press (debounce)
    'spi_handle': spi_handle,                    # pigpio SPI handle for MCP4231
    'active_callbacks': [],                      # list of pigpio callbacks to cancel on page change

    'pot_mode_on': False,
    'ohmmeter_mode_on': False,
    'voltmeter_mode_on': False,
    'function_generator_mode_on': False,
    'dc_reference_mode_on': False,
    
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


# Objects
sar_adc = SAR_ADC(
    pi=pi,
    spi_handle=adc_handle,
    comparator_pin=VOLT_COMPARATOR_PIN,
    selected_pot=0,
    settle_time=0.002,
    invert_comparator=False,
)

dc_ref = DCReferenceGenerator(
    pi=pi,
    spi_handle=dc_spi_handle,
    settle_time=0.001,
)


def pot_start(state):
    gen = state.get("pot_mode_on")
    if gen is None:
        return
    fg_apply_settings(state)
    try:
        gen.start()
        state["fg_output_on"] = True
    except Exception:
        state["fg_output_on"] = False



# Potentiometer Menu

def run_potentiometer_menu(state):
    while True:
        choice = pick_menu(
            "Potentiometer",
            ["Variable", "Constant", "Back", "Main"],
        )

        if choice == "Variable":
            run_pot_variable(state)

        elif choice == "Constant":
            run_pot_constant(state)

        elif choice == "Back":
            return "BACK"

        elif choice == "Main":
            return "MAIN"


def run_pot_variable(state):
    value = state.get("pot_ohms", 1000)

    new_val = adjust_value(
        "Set Resistance",
        value,
        MINIMUM_OHMS,
        MAXIMUM_OHMS,
        10,
        lambda v: f"{int(v)} ohm",
    )

    if new_val is None:
        return

    value = int(new_val)
    state["pot_ohms"] = value

    step = ohms_to_step(value)
    state["pot_step"] = step

    wait_for_back_page(lambda: (
        "Potentiometer",
        f"Set: {value} ohm",
        f"Step: {step}",
        "Btn: Back",
    ))


def run_pot_constant(state):
    presets = [100, 1000, 5000, 10000]

    labels = [f"{p} ohm" for p in presets]

    choice = pick_menu("Const Res", labels + ["Back", "Main"])

    if choice in ("Back", "Main"):
        return

    value = presets[labels.index(choice)]

    state["pot_ohms"] = value
    step = ohms_to_step(value)
    state["pot_step"] = step

    wait_for_back_page(lambda: (
        "Const Mode",
        f"Set: {value} ohm",
        f"Step: {step}",
        "Btn: Back",
    ))


# Main Loop
print("Starting...")
try:
    while True:

        # main page
        state['isMainPage'] = True
        state['menu_selection'] = 0
        state['button_last_tick'] = None
        clear_callbacks(state)

        choice = pick_menu(
            "Mode Select",
            ["Function Generator", "Ohmmeter", "Voltmeter", "DC Reference", "Potentiometer", "Back", "Main"],
        )

        if choice == "Function Generator":
            #result = run_function_generator_menu(state)
            if result == "MAIN":
                continue

        #elif choice == "Ohmmeter":
            # direct live reading matches your note that UI shows reading and threshold
            #run_ohmmeter_live(state, pi, adc_handle)

        elif choice == "Voltmeter":
            result = run_voltmeter_menu(state)
            if result == "MAIN":
                continue

        #elif choice == "DC Reference":
        #    result = run_dc_reference_menu(state)
        #    if result == "MAIN":
        #        continue

        elif choice == "Potentiometer":
            result = run_potentiometer_menu(state)
            if result == "MAIN":
                continue






        """
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
        #print("decoder", decoder)
        cb_btn = pi.callback(
            rotaryEncoder_pin, pigpio.FALLING_EDGE, menu_button_callback)
        #print("cb_btn", cb_btn)
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
            state['ohms'] = state['pot_values'][state['selected_pot']]
                
            step = ohms_to_step(state['ohms'])
            lcd.put_line(0, f'Pot {state["selected_pot"] + 1}')
            lcd.put_line(1, f'Ohms: {5000}')
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
        """
except KeyboardInterrupt:
    print("\nStopping...")
    clear_callbacks(state)
    lcd.close()
    pi.spi_close(spi_handle)
    pi.stop()
