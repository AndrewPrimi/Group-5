"""
callbacks.py – rotary encoder and button callbacks for Deliverable 9.

Pages handled:
  - Main menu
  - Ohmmeter page

This version is intentionally clean and minimal so it works with:
  - Driver.py
  - rotary_encoder.py
  - voltmeter.py
"""

import pigpio

# Module-level references injected by setup_callbacks()
_s = None
_pi = None
_lcd = None

# Rotary encoder GPIO pin assignments
PIN_A = 22
PIN_B = 27
ROTARY_BTN_PIN = 17

# Debounce threshold
BUTTON_DEBOUNCE_US = 200_000  # 200 ms

# Only two items on this menu
MENU_ITEMS = 2  # 1 = Ohmmeter, 2 = Voltmeter


def setup_callbacks(state, pi, lcd):
    """Give callbacks access to shared state, pigpio instance, and lcd."""
    global _s, _pi, _lcd
    _s = state
    _pi = pi
    _lcd = lcd


def clear_callbacks(state=None):
    """
    Cancel and remove all active callbacks / decoders.

    Compatible with:
      clear_callbacks()
      clear_callbacks(state)
    """
    target = state if state is not None else _s
    if target is None:
        return

    for cb in target.get('active_callbacks', []):
        try:
            cb.cancel()
        except Exception:
            pass

    target['active_callbacks'] = []


def _debounce(tick):
    """Return True if this button event is too close to the previous one."""
    last = _s.get('button_last_tick')
    if last is not None and pigpio.tickDiff(last, tick) < BUTTON_DEBOUNCE_US:
        return True

    _s['button_last_tick'] = tick
    return False


def _redraw_main_menu():
    """Redraw the two selectable rows of the main menu."""
    sel = _s.get('menu_selection', 1)

    _lcd.put_line(2, '> Ohmmeter' if sel == 1 else '  Ohmmeter')
    _lcd.put_line(3, '> Voltmeter' if sel == 2 else '  Voltmeter')


def menu_direction_callback(direction):
    """Rotate encoder on main menu -> move cursor between Ohmmeter and Voltmeter."""
    old = _s.get('menu_selection', 1)
    if old not in (1, 2):
        old = 1

    _s['menu_selection'] = 1 + ((old - 1 + direction) % MENU_ITEMS)
    _redraw_main_menu()


def menu_button_callback(gpio, level, tick):
    """Button press on main menu -> enter highlighted page."""
    if level != 0:
        return
    if _debounce(tick):
        return

    if _s.get('menu_selection') in (1, 2):
        _s['isMainPage'] = False


def ohm_button_callback(gpio, level, tick):
    """Button press on ohmmeter page -> return to main menu."""
    if level != 0:
        return
    if _debounce(tick):
        return

    _s['isOhmPage'] = False
