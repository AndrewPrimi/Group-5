"""
All rotary-encoder and button callback functions.

This file defines every interrupt-driven callback used by the menu system.
Callbacks are grouped by the page they belong to (main, var/const, constant,
pot control).  A single shared-state dictionary (_s) plus references to the
pigpio instance (_pi) and LCD driver (_lcd) are injected once at startup via
setup_callbacks().
"""

import pigpio
import time
from ohms_steps import (
    ohms_to_step, step_to_ohms, fix_ohms,
    MINIMUM_OHMS, MAXIMUM_OHMS,
    BUTTON_DEBOUNCE_US, DEFAULT_OHMS,
    CONSTANT_OHMS, CONSTANT_LABELS,
)

# Module-level references injected by setup_callbacks().
# _s  = shared state dict (ohms, selections, flags, etc.)
# _pi = pigpio.pi() instance for GPIO / SPI access
# _lcd = i2c_lcd.lcd instance for writing to the 2004A display
_s = None
_pi = None
_lcd = None

# Rotary encoder GPIO pin assignments (active-low with pull-ups)
PIN_A = 22   # CLK
PIN_B = 27   # DT


def setup_callbacks(state, pi, lcd):
    """Inject shared state, pigpio instance, and LCD into this module.

    Must be called once from main.py before any callback fires.
    """
    global _s, _pi, _lcd
    _s = state
    _pi = pi
    _lcd = lcd


def menu_direction_callback(direction):
    """Toggle the highlighted pot on each encoder detent.

    Flips menu_selection between 0 (Pot 1) and 1 (Pot 2) and
    redraws the cursor arrow on the LCD.
    """
    _s['menu_selection'] = 1 - _s['menu_selection']

    # Redraw menu with the arrow on the newly selected item
    if _s['menu_selection'] == 0:
        _lcd.put_line(1, '> Pot 1')
        _lcd.put_line(2, '  Pot 2')
    else:
        _lcd.put_line(1, '  Pot 1')
        _lcd.put_line(2, '> Pot 2')


def menu_button_callback(gpio, level, tick):
    """Confirm pot selection when the encoder button is pressed.

    Uses tick-based debouncing (BUTTON_DEBOUNCE_US) to ignore bounce.
    On a clean press (level == 0), records the chosen pot and exits
    the main-page loop by clearing isMainPage.
    """
    if level == 0:
        # Software debounce: ignore presses that arrive too quickly
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick
        _s['selected_pot'] = _s['menu_selection']   # 0 or 1
        # break out of main-page loop
        _s['isMainPage'] = False


def varconst_direction_callback(direction):
    """Toggle between Variable and Constant on each encoder detent.

    Works identically to menu_direction_callback but for the
    resistance-type selection screen.
    """
    _s['var_const_selection'] = 1 - _s['var_const_selection']

    if _s['var_const_selection'] == 0:
        _lcd.put_line(1, '> Variable')
        _lcd.put_line(2, '  Constant')
    else:
        _lcd.put_line(1, '  Variable')
        _lcd.put_line(2, '> Constant')


def varconst_button_callback(gpio, level, tick):
    """Confirm variable/constant choice on button press.

    Debounces identically to menu_button_callback, then exits the
    var/const page loop by clearing isVarConstPage.
    """
    if level == 0:
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick
        _s['isVarConstPage'] = False


def constant_direction_callback(direction):
    """Cycle through the four constant resistance presets (100, 1k, 5k, 10k).

    Wraps around using modulo so the user can keep spinning.
    """
    _s['constant_selection'] = (_s['constant_selection'] + 1) % 4
    label = CONSTANT_LABELS[_s['constant_selection']]
    _lcd.put_line(1, f'Value: {label} Ohms')
    _lcd.put_line(2, '')
    _lcd.put_line(3, '')


def constant_button_callback(gpio, level, tick):
    """Handle button press/release on the constant-selection page.

    Press  (level 0): debounce, convert chosen preset to a step value,
                      write it to the MCP4231, and update the LCD.
    Release (level 1): if the button was held >= 3 seconds, reset the
                       digipot to DEFAULT_OHMS and return to the main page.
    """
    if level == 0:
        # Debounce
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick
        # record press time for hold detection
        _s['button_press_tick'] = tick

        # Convert the selected preset to a step and send over SPI
        ohms_value = CONSTANT_OHMS[_s['constant_selection']]
        step = ohms_to_step(ohms_value)
        _set_digipot_step(step)

        # Show confirmation on LCD
        label = CONSTANT_LABELS[_s['constant_selection']]
        _lcd.put_line(2, 'Value set!')
        _lcd.put_line(3, f'{label} Ohms -> Pot {_s["selected_pot"] + 1}')
        print(f'Constant value set: {label} Ohms')

    elif level == 1 and _s['button_press_tick'] is not None:
        # Button released – check for long hold (>= 3 s)
        hold_time = pigpio.tickDiff(_s['button_press_tick'], tick)
        _s['button_press_tick'] = None
        if hold_time >= 3_000_000:
            # Long hold: reset digipot and navigate back to main page
            _set_digipot_step(ohms_to_step(DEFAULT_OHMS))
            _s['isMainPage'] = True


def callback_set_digi(gpio, level, tick):
    """Handle button press/release on the variable pot control page.

    Press  (level 0): debounce, convert current ohms to a step, send to
                      MCP4231, and confirm on LCD.
    Release (level 1): if held >= 2 seconds, reset to DEFAULT_OHMS and
                       return to the main page.
    """
    if level == 0:
        # Debounce
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick

        _s['button_press_tick'] = tick   # start timing for long-press
        step = ohms_to_step(_s['ohms'])
        _set_digipot_step(step)
        _lcd.put_line(2, 'Value set!')
        _lcd.put_line(3, f'Pot {_s["selected_pot"] + 1} updated')
        print('Button pressed! Value sent to digi pot.')

    elif level == 1 and _s['button_press_tick'] is not None:
        # Button released – check for long hold (>= 2 s)
        hold_time = pigpio.tickDiff(_s['button_press_tick'], tick)
        _s['button_press_tick'] = None
        if hold_time >= 2_000_000:  # 2 seconds
            _s['ohms'] = DEFAULT_OHMS
            _set_digipot_step(ohms_to_step(DEFAULT_OHMS))
            _s['isMainPage'] = True


def pot_direction_callback(direction):
    """Handle rotary encoder rotation on the variable pot control page.

    Flips direction to match encoder wiring, calculates rotation speed
    (detents/sec) from the time since the last detent, and passes both
    to _change_steps() for acceleration-aware adjustment.
    """
    direction = -direction  # flip to match encoder wiring
    now = time.time()
    if _s['last_time'] is not None:
        dt = now - _s['last_time']          # seconds since last detent
        speed = min(1.0 / dt, 1000)         # cap at 1000 detents/sec
        _change_steps(direction, speed)
    _s['last_time'] = now


def _change_steps(direction, speed):
    """Adjust the target ohms value based on encoder direction and speed.

    Slow rotation (< 10 det/s)  -> fine adjustment   (+/- 10 ohms)
    Fast rotation (>= 10 det/s) -> coarse adjustment  (+/- 100 ohms)
    Clamps the result to [MINIMUM_OHMS, MAXIMUM_OHMS] and updates the LCD.
    """
    if speed < 10:
        change = 10      # fine
    else:
        change = 100     # coarse

    resulting_ohms = _s['ohms'] + change * direction
    if MINIMUM_OHMS <= resulting_ohms <= MAXIMUM_OHMS:
        _s['ohms'] = resulting_ohms
        step = ohms_to_step(_s['ohms'])
        _lcd.put_line(1, f'Ohms: {resulting_ohms}')
        print(f"Current Ohms: {_s['ohms']}")
    else:
        print("ohm value is out of range...")


def _set_digipot_step(step_value):
    """Write a wiper step to the MCP4231 digital potentiometer over SPI.

    The MCP4231 has two wipers addressed by different command bytes:
      0x00 = Wiper 0 (Pot 1)
      0x10 = Wiper 1 (Pot 2)
    The selected pot is determined by state['selected_pot'].
    """
    from ohms_steps import MAX_STEPS
    if 0 <= step_value <= MAX_STEPS:
        # choosing which digi pot to use
        cmd = 0x00 if _s['selected_pot'] == 0 else 0x10
        _pi.spi_write(_s['spi_handle'], [cmd, step_value])
        approx_ohms = step_to_ohms(step_value)
        print(
            f"Pot {_s['selected_pot'] + 1} | Step: {step_value:3d} | Approx: {approx_ohms:7.1f} Ohms")
    else:
        print(f"Invalid step: {step_value} (must be 0-{MAX_STEPS})")


def clear_callbacks(state):
    """Cancel all active pigpio callbacks and clear the list."""
    for c in state['active_callbacks']:
        c.cancel()
    state['active_callbacks'] = []
