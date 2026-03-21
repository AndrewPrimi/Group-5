"""
callbacks.py – rotary encoder and button callbacks for Deliverable 9.

Pages handled:
  Main menu  : menu_direction_callback, menu_button_callback
  Ohmmeter   : ohm_button_callback  (press to return to main menu)
"""

import pigpio

# Shared references set by setup_callbacks()
_s   = None   # state dict
_pi  = None   # pigpio.pi instance
_lcd = None   # i2c_lcd.lcd instance

# GPIO pin assignments
PIN_A               = 22     # Rotary encoder channel A
PIN_B               = 27     # Rotary encoder channel B
ROTARY_BTN_PIN      = 17     # Rotary encoder push-button

# Debounce threshold (microseconds)
BUTTON_DEBOUNCE_US  = 200_000    # 200 ms  – ignore repeat presses

# Number of selectable items on the main menu
MENU_ITEMS = 2   # Ohmmeter, Voltmeter


def setup_callbacks(state, pi, lcd):
    """Give callbacks access to shared state, pi, and lcd."""
    global _s, _pi, _lcd
    _s   = state
    _pi  = pi
    _lcd = lcd


def clear_callbacks(state):
    """Cancel and remove all active pigpio callbacks / decoder objects."""
    for cb in state['active_callbacks']:
        cb.cancel()
    state['active_callbacks'] = []


# ── Main-menu callbacks ───────────────────────────────────────────────────────

def menu_direction_callback(direction):
    """Rotate encoder on main menu → move the cursor between items."""
    old = _s['menu_selection']
    if old not in (1, 2):
        old = 1
    _s['menu_selection'] = 1 + ((old - 1 + direction) % MENU_ITEMS)
    _redraw_main_menu()


def menu_button_callback(gpio, level, tick):
    """Button press on main menu → enter the highlighted page."""
    if level != 0:          # only act on falling edge
        return
    if _debounce(tick):
        return
    if _s['menu_selection'] in (1, 2):
        _s['isMainPage'] = False


# ── Ohmmeter-page callbacks ───────────────────────────────────────────────────

def ohm_button_callback(gpio, level, tick):
    """Button press on the ohmmeter page → return to main menu."""
    if level != 0:
        return
    if _debounce(tick):
        return
    _s['isOhmPage'] = False


# ── Private helpers ───────────────────────────────────────────────────────────

def _debounce(tick):
    """Return True (and skip) if this tick is too close to the last one."""
    last = _s.get('button_last_tick')
    if last is not None and pigpio.tickDiff(last, tick) < BUTTON_DEBOUNCE_US:
        return True
    _s['button_last_tick'] = tick
    return False


def _redraw_main_menu():
    """Redraw only the item rows (rows 2-3) of the main menu."""
    sel = _s['menu_selection']
    _lcd.put_line(2, '> Ohmmeter'  if sel == 1 else '  Ohmmeter')
    _lcd.put_line(3, '> Voltmeter' if sel == 2 else '  Voltmeter')
