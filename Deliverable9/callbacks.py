"""
callbacks.py

Shared callback logic for:
- Main menu navigation
- Ohmmeter page exit
- Voltmeter page exit
- DC reference page live rotary adjustment + exit
"""

import pigpio

PIN_A = 22
PIN_B = 27
ROTARY_BTN_PIN = 17

BUTTON_DEBOUNCE_US = 200_000  # 200 ms

_state = None
_pi = None
_lcd = None


def setup_callbacks(state, pi, lcd):
    """
    Store shared references for callbacks.
    """
    global _state, _pi, _lcd
    _state = state
    _pi = pi
    _lcd = lcd


def clear_callbacks(state=None):
    """
    Cancel all active callbacks / rotary decoders in the provided state.
    Compatible with:
        clear_callbacks()
        clear_callbacks(state)
    """
    target = state if state is not None else _state
    if target is None:
        return

    for cb in target.get("active_callbacks", []):
        try:
            cb.cancel()
        except Exception:
            pass

    target["active_callbacks"] = []


def _debounced_press(tick):
    """
    Returns True if this press is outside the debounce window.
    """
    last = _state.get("button_last_tick")
    if last is not None and pigpio.tickDiff(last, tick) < BUTTON_DEBOUNCE_US:
        return False

    _state["button_last_tick"] = tick
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Main menu
# ─────────────────────────────────────────────────────────────────────────────

MAIN_MENU_ITEMS = [
    "Ohmmeter",
    "Voltmeter",
    "DC Ref",
]


def _redraw_main_menu():
    sel = _state.get("menu_selection", 0)

    _lcd.put_line(0, "Main Menu")
    _lcd.put_line(1, "Select Mode")

    # 20x4 LCD, so show title + 3 options
    for i, label in enumerate(MAIN_MENU_ITEMS):
        prefix = ">" if i == sel else " "
        _lcd.put_line(i + 1, f"{prefix} {label}")


def show_main_menu():
    _redraw_main_menu()


def menu_direction_callback(direction):
    current = _state.get("menu_selection", 0)
    current = (current + direction) % len(MAIN_MENU_ITEMS)
    _state["menu_selection"] = current
    _redraw_main_menu()


def menu_button_callback(gpio, level, tick):
    if level != 0:
        return
    if not _debounced_press(tick):
        return

    _state["selected_mode"] = _state.get("menu_selection", 0)
    _state["isMainPage"] = False


# ─────────────────────────────────────────────────────────────────────────────
# Ohmmeter page
# ─────────────────────────────────────────────────────────────────────────────

def ohm_button_callback(gpio, level, tick):
    if level != 0:
        return
    if not _debounced_press(tick):
        return

    _state["isOhmPage"] = False


# ─────────────────────────────────────────────────────────────────────────────
# Voltmeter page
# ─────────────────────────────────────────────────────────────────────────────

def volt_button_callback(gpio, level, tick):
    if level != 0:
        return
    if not _debounced_press(tick):
        return

    _state["isVoltPage"] = False


# ─────────────────────────────────────────────────────────────────────────────
# DC reference page
# ─────────────────────────────────────────────────────────────────────────────

def dc_ref_direction_callback(direction):
    """
    Rotary adjustment for bipolar DC reference.
    """
    step_size = _state.get("dc_ref_step_size", 0.1)
    voltage = _state.get("dc_ref_voltage", 0.0)

    voltage += direction * step_size
    voltage = max(-5.0, min(5.0, round(voltage, 2)))

    _state["dc_ref_voltage"] = voltage

    dc_ref = _state.get("dc_ref_obj")
    if dc_ref is not None:
        dc_ref.set_voltage(voltage)

    _redraw_dc_reference_page()


def dc_ref_button_callback(gpio, level, tick):
    """
    Button exits DC reference page.
    """
    if level != 0:
        return
    if not _debounced_press(tick):
        return

    _state["isDCRefPage"] = False


def _redraw_dc_reference_page():
    voltage = _state.get("dc_ref_voltage", 0.0)
    enabled = _state.get("dc_ref_enabled", False)

    _lcd.put_line(0, "DC Reference")
    _lcd.put_line(1, f"Vout: {voltage:+.2f} V")
    _lcd.put_line(2, f"Output: {'ON ' if enabled else 'OFF'}")
    _lcd.put_line(3, "Rotate=adj Btn=back")


def show_dc_reference_page():
    _redraw_dc_reference_page()
