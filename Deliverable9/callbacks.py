"""
callbacks.py

Generic rotary encoder + button callback helpers for the LCD UI.

Provides:
- pick_menu()     – scrollable menu, returns selected option string
- adjust_value()  – numeric adjustment with encoder, returns confirmed value
- wait_for_back() – display page and wait for button press

Works with:
- pigpio
- rotary_encoder.py
- i2c_lcd.py
"""

import time
import pigpio
import rotary_encoder

# Rotary encoder GPIO pin assignments (active-low with pull-ups)
PIN_A = 22   # CLK
PIN_B = 27   # DT
ROTARY_BTN_PIN = 17

BUTTON_DEBOUNCE_US = 200_000
HOLD_US = 2_000_000  # 2-second long-press threshold

_s = None
_pi = None
_lcd = None


def setup_callbacks(state, pi, lcd):
    """Inject shared state, pigpio instance, and LCD into this module."""
    global _s, _pi, _lcd
    _s = state
    _pi = pi
    _lcd = lcd


def clear_callbacks(state):
    """Cancel all active pigpio callbacks and clear the list."""
    for c in state.get('active_callbacks', []):
        c.cancel()
    state['active_callbacks'] = []


# ── Internal helpers ─────────────────────────────────────────────────────────

def _reset_input_flags():
    _s["encoder_delta"] = 0
    _s["button_pressed"] = False
    _s["button_last_tick"] = None


def _on_rotate(direction):
    _s["encoder_delta"] = _s.get("encoder_delta", 0) - direction


def _on_button(_gpio, level, tick):
    if level != 0:
        return
    last = _s.get("button_last_tick")
    if last is not None and pigpio.tickDiff(last, tick) < BUTTON_DEBOUNCE_US:
        return
    _s["button_last_tick"] = tick
    _s["button_pressed"] = True


def _attach_input_callbacks():
    clear_callbacks(_s)
    decoder = rotary_encoder.decoder(_pi, PIN_A, PIN_B, _on_rotate)
    cb_btn = _pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
    _s["active_callbacks"] = [decoder, cb_btn]


def _draw_menu(title, options, idx):
    """Render a scrollable menu on the 20×4 LCD.

    Line 0: title
    Lines 1-3: up to 3 visible options with '>' on the selected one.
    """
    _lcd.put_line(0, title)

    # Compute a 3-item window around idx
    n = len(options)
    if n <= 3:
        window_start = 0
    else:
        window_start = max(0, min(idx - 1, n - 3))

    for row in range(3):
        i = window_start + row
        if i < n:
            prefix = "> " if i == idx else "  "
            _lcd.put_line(row + 1, prefix + options[i])
        else:
            _lcd.put_line(row + 1, "")


# ── Public API ───────────────────────────────────────────────────────────────

def pick_menu(title, options, start_idx=0):
    """Generic rotary menu.  Returns the selected option string."""
    idx = max(0, min(start_idx, len(options) - 1))
    _reset_input_flags()
    _attach_input_callbacks()
    _draw_menu(title, options, idx)

    try:
        while True:
            delta = _s.get("encoder_delta", 0)
            if delta != 0 and options:
                idx = (idx + delta) % len(options)
                _s["encoder_delta"] = 0
                _draw_menu(title, options, idx)

            if _s.get("button_pressed"):
                _s["button_pressed"] = False
                return options[idx]

            time.sleep(0.02)
    finally:
        clear_callbacks(_s)


def adjust_value(title, value, min_val, max_val, step, fmt_fn):
    """Numeric adjustment with rotary encoder.

    Encoder rotation changes value by ±step.
    Short press confirms and returns the value.
    Long press (>= 2s) cancels and returns None.

    fmt_fn(value) -> string for LCD display.
    """
    _reset_input_flags()
    _s["button_press_tick"] = None

    def _adj_rotate(direction):
        _s["encoder_delta"] = _s.get("encoder_delta", 0) - direction

    def _adj_button(_gpio, level, tick):
        if level == 0:
            last = _s.get("button_last_tick")
            if last is not None and pigpio.tickDiff(last, tick) < BUTTON_DEBOUNCE_US:
                return
            _s["button_last_tick"] = tick
            _s["button_press_tick"] = tick
        elif level == 1:
            press_tick = _s.get("button_press_tick")
            if press_tick is not None:
                hold = pigpio.tickDiff(press_tick, tick)
                _s["button_press_tick"] = None
                if hold >= HOLD_US:
                    _s["long_press"] = True
                else:
                    _s["button_pressed"] = True

    _s["long_press"] = False
    clear_callbacks(_s)
    decoder = rotary_encoder.decoder(_pi, PIN_A, PIN_B, _adj_rotate)
    cb_btn = _pi.callback(ROTARY_BTN_PIN, pigpio.EITHER_EDGE, _adj_button)
    _s["active_callbacks"] = [decoder, cb_btn]

    _lcd.put_line(0, title)
    _lcd.put_line(1, fmt_fn(value))
    _lcd.put_line(2, "Turn: adjust")
    _lcd.put_line(3, "Btn: set  Hold: back")

    try:
        while True:
            delta = _s.get("encoder_delta", 0)
            if delta != 0:
                value += step * delta
                value = max(min_val, min(max_val, value))
                # Snap to step grid
                value = round(round(value / step) * step, 10)
                _s["encoder_delta"] = 0
                _lcd.put_line(1, fmt_fn(value))

            if _s.get("button_pressed"):
                _s["button_pressed"] = False
                return value

            if _s.get("long_press"):
                _s["long_press"] = False
                return None

            time.sleep(0.02)
    finally:
        clear_callbacks(_s)


def wait_for_back(line_fn):
    """Display 4 lines and wait for a button press to return.

    line_fn() should return a tuple/list of 4 strings.
    """
    _reset_input_flags()
    _attach_input_callbacks()

    lines = line_fn()
    for row, text in enumerate(lines[:4]):
        _lcd.put_line(row, text)

    try:
        while True:
            if _s.get("button_pressed"):
                _s["button_pressed"] = False
                return
            time.sleep(0.02)
    finally:
        clear_callbacks(_s)
