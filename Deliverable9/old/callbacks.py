"""
callbacks.py

Generic rotary encoder + button callback helpers for the LCD UI.

This file is intentionally generic so Driver.py can build:
- Main menu
- Function Generator menus
- Ohmmeter page
- Voltmeter menus
- DC Reference menus

Works with:
- pigpio
- rotary_encoder.py
- i2c_lcd.py
"""

import time
import pigpio
import rotary_encoder
import ohms_steps

PIN_A = 22
PIN_B = 27
ROTARY_BTN_PIN = 17

BUTTON_DEBOUNCE_US = 200_000
HOLD_US = 1_200_000  # optional hold support if you ever want it

_state = None
_pi = None
_lcd = None


def setup_callbacks(state, pi, lcd):
    """
    Store shared references so helpers in this file can access the
    application state, pigpio instance, and LCD object.
    """
    global _state, _pi, _lcd
    _state = state
    _pi = pi
    _lcd = lcd


def clear_callbacks(state=None):
    """
    Cancel all active callbacks / rotary decoders.

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


def _reset_input_flags():
    _state["encoder_delta"] = 0
    _state["button_pressed"] = False
    _state["button_held"] = False
    _state["button_press_tick"] = None


def _button_cb(_gpio, level, tick):
    """
    Generic pushbutton callback:
      falling edge -> start press timing
      rising edge  -> mark short press or hold
    """
    if level == 0:
        last = _state.get("button_last_tick")
        if last is not None and pigpio.tickDiff(last, tick) < BUTTON_DEBOUNCE_US:
            return
        _state["button_last_tick"] = tick
        _state["button_press_tick"] = tick

    elif level == 1:
        press_tick = _state.get("button_press_tick")
        if press_tick is None:
            return

        held_us = pigpio.tickDiff(press_tick, tick)
        if held_us >= HOLD_US:
            _state["button_held"] = True
        else:
            _state["button_pressed"] = True

        _state["button_press_tick"] = None


def _encoder_cb(direction):
    """
    Generic rotary movement callback from rotary_encoder.decoder.
    """
    _state["encoder_delta"] = _state.get("encoder_delta", 0) + direction


def attach_input_callbacks():
    """
    Attach generic rotary/button handlers and store them in state.
    """
    clear_callbacks()
    decoder = rotary_encoder.decoder(_pi, PIN_A, PIN_B, _encoder_cb)
    cb_btn = _pi.callback(ROTARY_BTN_PIN, pigpio.EITHER_EDGE, _button_cb)
    _state["active_callbacks"] = [decoder, cb_btn]


def draw_menu(title, options, selected_idx):
    """
    Draw a scrolling 3-option window under a 1-line title.

    LCD layout:
      row 0 = title
      row 1..3 = visible options
    """
    title = str(title)[:20]
    _lcd.put_line(0, title)

    if not options:
        for row in range(1, 4):
            _lcd.put_line(row, "")
        return

    # Keep selected item centered when possible
    if len(options) <= 3:
        start = 0
    else:
        start = max(0, min(selected_idx - 1, len(options) - 3))

    for row in range(3):
        i = start + row
        if i < len(options):
            prefix = ">" if i == selected_idx else " "
            _lcd.put_line(row + 1, f"{prefix} {options[i]}"[:20])
        else:
            _lcd.put_line(row + 1, "")


def pick_menu(title, options, start_idx=0):
    """
    Generic rotary menu.

    Returns:
      selected option string
    """
    idx = max(0, min(start_idx, len(options) - 1 if options else 0))
    _reset_input_flags()
    attach_input_callbacks()
    draw_menu(title, options, idx)

    try:
        while True:
            delta = _state.get("encoder_delta", 0)
            if delta != 0 and options:
                idx = (idx + delta) % len(options)
                _state["encoder_delta"] = 0
                draw_menu(title, options, idx)

            if _state.get("button_pressed"):
                _state["button_pressed"] = False
                return options[idx]

            time.sleep(0.02)
    finally:
        clear_callbacks()


def adjust_value(title, value, min_val, max_val, step, formatter=str):
    """
    Generic rotary numeric adjuster.

    Short press confirms.
    Hold cancels and returns None.
    """
    _reset_input_flags()
    attach_input_callbacks()

    def redraw():
        _lcd.put_line(0, str(title)[:20])
        _lcd.put_line(1, str(formatter(value))[:20])
        _lcd.put_line(2, "Rotate to adjust"[:20])
        _lcd.put_line(3, "Btn=OK Hold=Cancel"[:20])

    redraw()

    try:
        while True:
            delta = _state.get("encoder_delta", 0)
            if delta != 0:
                value += delta * step
                value = max(min_val, min(max_val, value))
                # snap to step cleanly
                value = round(round(value / step) * step, 10)
                _state["encoder_delta"] = 0
                redraw()

            if _state.get("button_pressed"):
                _state["button_pressed"] = False
                return value

            if _state.get("button_held"):
                _state["button_held"] = False
                return None

            time.sleep(0.02)
    finally:
        clear_callbacks()


def wait_for_back_page(lines_getter, refresh_s=0.25):
    """
    Show a live page until short press or hold.

    lines_getter must return a tuple/list of 4 strings.
    """
    _reset_input_flags()
    attach_input_callbacks()
    last = 0.0

    try:
        while True:
            now = time.time()
            if now - last >= refresh_s:
                last = now
                lines = lines_getter()
                for row in range(4):
                    text = lines[row] if row < len(lines) else ""
                    _lcd.put_line(row, str(text)[:20])

            if _state.get("button_pressed") or _state.get("button_held"):
                _state["button_pressed"] = False
                _state["button_held"] = False
                return

            time.sleep(0.02)
    finally:
        clear_callbacks()


def run_ohmmeter():
    """
    Entry point for ohmmeter control.

    Uses:
    - Variable resistance mode (adjust freely)
    - Constant presets (100, 1k, 5k, 10k)
    """
    while True:
        choice = pick_menu(
            "OHMMETER",
            ["Variable", "Constant", "Back"]
        )

        if choice == "Variable":
            run_variable_ohms()

        elif choice == "Constant":
            run_constant_ohms()

        elif choice == "Back":
            return

        
def run_variable_ohms():
    """
    Rotary adjustment of resistance using interpolation-backed conversion.
    """
    value = _state.get("ohms", ohms_steps.DEFAULT_OHMS)

    while True:
        new_val = adjust_value(
            "OHMS",
            value,
            ohms_steps.MINIMUM_OHMS,
            ohms_steps.MAXIMUM_OHMS,
            10,  # matches your 10-ohm resolution idea
            lambda v: f"{int(v)} ohm"
        )

        if new_val is None:
            return

        value = int(new_val)
        _state["ohms"] = value

        step = ohms_steps.ohms_to_step(value)

        # Store for other modules (SPI writer, etc.)
        _state["digipot_step"] = step

        # Optional live confirmation page
        wait_for_back_page(lambda: (
            "OHMMETER ACTIVE",
            f"Set: {value} ohm",
            f"Step: {step}",
            "Btn: Back"
        ))

        
def run_constant_ohms():
    """
    Select from predefined resistance values.
    """
    while True:
        choice = pick_menu(
            "CONST OHMS",
            ohms_steps.CONSTANT_LABELS + ["Back"]
        )

        if choice == "Back":
            return

        idx = ohms_steps.CONSTANT_LABELS.index(choice)
        value = ohms_steps.CONSTANT_OHMS[idx]

        _state["ohms"] = value
        step = ohms_steps.ohms_to_step(value)
        _state["digipot_step"] = step

        wait_for_back_page(lambda: (
            "CONST MODE",
            f"Set: {value} ohm",
            f"Step: {step}",
            "Btn: Back"
        ))
