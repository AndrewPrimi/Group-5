import pigpio
import time
from ohms_steps import (
    ohms_to_step, step_to_ohms,
    MINIMUM_OHMS, MAXIMUM_OHMS,
    BUTTON_DEBOUNCE_US, DEFAULT_OHMS,
    CONSTANT_OHMS, CONSTANT_LABELS,
)

# Shared state dict - set by setup_callbacks() from main.py
_s = None
_pi = None
_lcd = None

# Pin assignments
PIN_A = 22
PIN_B = 27


def setup_callbacks(state, pi, lcd):
    """Give callbacks access to shared state and LCD."""
    global _s, _pi, _lcd
    _s = state
    _pi = pi
    _lcd = lcd


# --- Main page callbacks ---

def menu_direction_callback(direction):
    """Toggle between Pot 1 and Pot 2 on each encoder detent."""
    _s['menu_selection'] = 1 - _s['menu_selection']

    if _s['menu_selection'] == 0:
        _lcd.put_line(1, '> Pot 1')
        _lcd.put_line(2, '  Pot 2')
    else:
        _lcd.put_line(1, '  Pot 1')
        _lcd.put_line(2, '> Pot 2')


def menu_button_callback(gpio, level, tick):
    """Select a pot from the main page when button is pressed."""
    if level == 0:
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick
        _s['selected_pot'] = _s['menu_selection']
        _s['isMainPage'] = False


# --- Var/Const page callbacks ---

def varconst_direction_callback(direction):
    """Toggle between Variable and Constant on each encoder detent."""
    _s['var_const_selection'] = 1 - _s['var_const_selection']

    if _s['var_const_selection'] == 0:
        _lcd.put_line(1, '> Variable')
        _lcd.put_line(2, '  Constant')
    else:
        _lcd.put_line(1, '  Variable')
        _lcd.put_line(2, '> Constant')


def varconst_button_callback(gpio, level, tick):
    """Select variable or constant mode."""
    if level == 0:
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick
        _s['isVarConstPage'] = False


# --- Constant selection page callbacks ---

def constant_direction_callback(direction):
    """Cycle through constant resistance values (100, 1k, 5k, 10k)."""
    _s['constant_selection'] = (_s['constant_selection'] + 1) % 4
    label = CONSTANT_LABELS[_s['constant_selection']]
    _lcd.put_line(1, f'Value: {label} Ohms')
    _lcd.put_line(2, '')
    _lcd.put_line(3, '')


def constant_button_callback(gpio, level, tick):
    """Set constant resistance on press, return to main on 3s hold."""
    if level == 0:
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick
        _s['button_press_tick'] = tick

        ohms_value = CONSTANT_OHMS[_s['constant_selection']]
        step = ohms_to_step(ohms_value)
        _set_digipot_step(step)
        label = CONSTANT_LABELS[_s['constant_selection']]
        _lcd.put_line(2, 'Value set!')
        _lcd.put_line(3, f'{label} Ohms -> Pot {_s["selected_pot"] + 1}')
        print(f'Constant value set: {label} Ohms')
    elif level == 1 and _s['button_press_tick'] is not None:
        hold_time = pigpio.tickDiff(_s['button_press_tick'], tick)
        _s['button_press_tick'] = None
        if hold_time >= 3_000_000:
            _set_digipot_step(ohms_to_step(DEFAULT_OHMS))
            _s['isMainPage'] = True


# --- Pot control callbacks ---

def callback_set_digi(gpio, level, tick):
    """When button is pressed, set the digi pot. Track press time for long hold."""
    if level == 0:
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick

        _s['button_press_tick'] = tick
        step = ohms_to_step(_s['ohms'])
        _set_digipot_step(step)
        _lcd.put_line(2, 'Value set!')
        _lcd.put_line(3, f'Pot {_s["selected_pot"] + 1} updated')
        print('Button pressed! Value sent to digi pot.')
    elif level == 1 and _s['button_press_tick'] is not None:
        hold_time = pigpio.tickDiff(_s['button_press_tick'], tick)
        _s['button_press_tick'] = None
        if hold_time >= 2_000_000:  # 3 seconds
            _s['ohms'] = DEFAULT_OHMS
            _set_digipot_step(ohms_to_step(DEFAULT_OHMS))
            _s['isMainPage'] = True


def pot_direction_callback(direction):
    """Handle rotary encoder rotation on the pot control page.
    CW increases ohms, CCW decreases ohms.
    """
    direction = -direction  # flip to match encoder wiring
    now = time.time()
    if _s['last_time'] is not None:
        dt = now - _s['last_time']
        speed = min(1.0 / dt, 1000)  # detents per second
        _change_steps(direction, speed)
    _s['last_time'] = now


def _change_steps(direction, speed):
    """Change ohms value based on encoder direction and speed."""
    if speed < 10:
        change = 10
    else:
        change = 100

    resulting_ohms = _s['ohms'] + change * direction
    if MINIMUM_OHMS <= resulting_ohms <= MAXIMUM_OHMS:
        _s['ohms'] = resulting_ohms
        step = ohms_to_step(_s['ohms'])
        _lcd.put_line(1, f'Ohms: {resulting_ohms}')
        print(f"Current Ohms: {_s['ohms']}")
    else:
        print("ohm value is out of range...")


# --- Helper functions ---

def _set_digipot_step(step_value):
    """Write data bytes to the selected wiper on the MCP4231."""
    from ohms_steps import MAX_STEPS
    if 0 <= step_value <= MAX_STEPS:
        # MCP4231: 0x00 = Wiper 0 (Pot 1), 0x10 = Wiper 1 (Pot 2)
        cmd = 0x00 if _s['selected_pot'] == 0 else 0x10
        _pi.spi_write(_s['spi_handle'], [cmd, step_value])
        approx_ohms = step_to_ohms(step_value)
        print(
            f"Pot {_s['selected_pot'] + 1} | Step: {step_value:3d} | Approx: {approx_ohms:7.1f} Ohms")
    else:
        print(f"Invalid step: {step_value} (must be 0-{MAX_STEPS})")


def clear_callbacks(state):
    """Cancel all active callbacks."""
    for c in state['active_callbacks']:
        c.cancel()
    state['active_callbacks'] = []
