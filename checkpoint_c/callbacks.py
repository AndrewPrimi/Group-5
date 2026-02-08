import pigpio
from ohms_steps import (
    ohms_to_step, step_to_ohms,
    MINIMUM_OHMS, MAXIMUM_OHMS, SPEED_LIMIT,
    ENCODER_DEBOUNCE_US, MENU_DEBOUNCE_US, BUTTON_DEBOUNCE_US,
    DEFAULT_OHMS,
)

# Shared state dict - set by setup_callbacks() from main.py
_s = None
_pi = None
_pot_lcd = None

# Pin assignments
PIN_A = 22
PIN_B = 27


def setup_callbacks(state, pi, pot_lcd):
    """Initialize callbacks with shared state from main.py.

    state dict must contain:
        - ohms, selected_pot, menu_selection
        - isMainPage, last_tick, button_press_tick, button_last_tick
        - handle_pot1, handle_pot2
        - active_callbacks
    """
    global _s, _pi, _pot_lcd
    _s = state
    _pi = pi
    _pot_lcd = pot_lcd


# --- Main page callbacks ---

def menu_encoder_callback(gpio, level, tick):
    """Rotate between Pot 1 and Pot 2 on the main page."""
    if _s['last_tick'] is not None:
        dt = pigpio.tickDiff(_s['last_tick'], tick)
        if dt < MENU_DEBOUNCE_US:
            _s['last_tick'] = tick
            return

        if _pi.read(PIN_B) == 0:
            _s['menu_selection'] = 1
        else:
            _s['menu_selection'] = 0

        _pot_lcd.request_main_page_update(_s['menu_selection'])

    _s['last_tick'] = tick


def menu_button_callback(gpio, level, tick):
    """Select a pot from the main page when button is pressed."""
    if level == 0:
        if _s['button_last_tick'] is not None:
            if pigpio.tickDiff(_s['button_last_tick'], tick) < BUTTON_DEBOUNCE_US:
                return
        _s['button_last_tick'] = tick
        _s['selected_pot'] = _s['menu_selection']
        _s['isMainPage'] = False


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
        _pot_lcd.request_confirmation(_s['selected_pot'])
        print('Button pressed! Value sent to digi pot.')
    elif level == 1 and _s['button_press_tick'] is not None:
        hold_time = pigpio.tickDiff(_s['button_press_tick'], tick)
        _s['button_press_tick'] = None
        if hold_time >= 3_000_000:  # 3 seconds
            _s['ohms'] = DEFAULT_OHMS
            _s['isMainPage'] = True


def encoder_callback(gpio, level, tick):
    """Handle rotary encoder rotation on the pot control page."""
    if _s['last_tick'] is not None:
        dt = pigpio.tickDiff(_s['last_tick'], tick)

        if dt < ENCODER_DEBOUNCE_US:
            _s['last_tick'] = tick
            return

        speed = min(1_000_000 / dt, 1000)

        if _pi.read(PIN_B) == 0:
            direction = 1
        else:
            direction = -1

        if speed <= SPEED_LIMIT:
            _change_steps(direction, speed)

    _s['last_tick'] = tick


# --- Helper functions ---

def _set_digipot_step(step_value):
    """Write data bytes to the currently selected MCP4131."""
    from ohms_steps import MAX_STEPS
    if 0 <= step_value <= MAX_STEPS:
        h = _s['handle_pot1'] if _s['selected_pot'] == 0 else _s['handle_pot2']
        _pi.spi_write(h, [0x00, step_value])
        approx_ohms = step_to_ohms(step_value)
        print(
            f"Pot {_s['selected_pot'] + 1} | Step: {step_value:3d} | Approx: {approx_ohms:7.1f} Ohms")
    else:
        print(f"Invalid step: {step_value} (must be 0-{MAX_STEPS})")


def _change_steps(direction, speed):
    """Change ohms value based on encoder direction and speed."""
    if speed < 10:
        change = 10
    else:
        change = 100

    resulting_ohms = _s['ohms'] + change * direction
    if resulting_ohms >= MINIMUM_OHMS and resulting_ohms <= MAXIMUM_OHMS:
        _s['ohms'] = resulting_ohms
        print(f"Current Ohms: {_s['ohms']}")
        step = ohms_to_step(_s['ohms'])
        _pot_lcd.request_pot_page_update(step_to_ohms(step), _s['selected_pot'])
    else:
        print("ohm value is out of range...")


def clear_callbacks(state):
    """Cancel all active callbacks."""
    for c in state['active_callbacks']:
        c.cancel()
    state['active_callbacks'] = []
