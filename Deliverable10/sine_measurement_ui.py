"""
sine_measurement_ui.py

UI for live sine wave frequency measurement using LCD + rotary encoder.

Controls:
  Rotate encoder  →  (unused for now)
  Short press     →  exit
  Long press      →  exit

Displays:
  - Locking progress
  - Live frequency
  - Locked frequency + dt
"""

import time
import pigpio
import sys
import os

from Sinewave_measurement import FrequencyMeter

# ── GPIO ──────────────────────────────────────────────────────────────────────
PIN_A       = 22
PIN_B       = 27
BTN_PIN     = 17
GPIO_PIN    = 5   # comparator input

DEBOUNCE_US = 200_000
HOLD_US     = 2_000_000

# ── Import LCD + encoder (same pattern as sine_ui) ────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Deliverable9'))

import i2c_lcd
import rotary_encoder

# ── State ─────────────────────────────────────────────────────────────────────
_state = {
    'encoder_delta':     0,
    'button_pressed':    False,
    'long_press':        False,
    'button_last_tick':  None,
    'button_press_tick': None,
    'active_callbacks':  [],
}

# ── Callback helpers ──────────────────────────────────────────────────────────

def _clear_callbacks():
    for c in _state['active_callbacks']:
        c.cancel()
    _state['active_callbacks'] = []


def _reset():
    _state['encoder_delta']     = 0
    _state['button_pressed']    = False
    _state['long_press']        = False
    _state['button_last_tick']  = None
    _state['button_press_tick'] = None


def _on_rotate(direction):
    _state['encoder_delta'] -= direction   # not used but kept for consistency


def _on_button_edge(gpio, level, tick):
    if level == 0:
        last = _state['button_last_tick']
        if last is not None and pigpio.tickDiff(last, tick) < DEBOUNCE_US:
            return
        _state['button_last_tick']  = tick
        _state['button_press_tick'] = tick

    elif level == 1:
        press_tick = _state['button_press_tick']
        if press_tick is not None:
            hold = pigpio.tickDiff(press_tick, tick)
            _state['button_press_tick'] = None
            if hold >= HOLD_US:
                _state['long_press'] = True
            else:
                _state['button_pressed'] = True


def _attach(pi):
    _clear_callbacks()
    dec = rotary_encoder.decoder(pi, PIN_A, PIN_B, _on_rotate)
    cb  = pi.callback(BTN_PIN, pigpio.EITHER_EDGE, _on_button_edge)
    _state['active_callbacks'] = [dec, cb]


# ── UI ────────────────────────────────────────────────────────────────────────

def run_sine_measurement_ui(state):
    """
    Runs the sine measurement UI page.

    state: shared dict (must include 'pi')
    """

    pi  = state["pi"]
    lcd = i2c_lcd.lcd(pi, width=20)

    # GPIO setup (same style as sine_ui)
    pi.set_mode(PIN_A,   pigpio.INPUT); pi.set_pull_up_down(PIN_A,   pigpio.PUD_UP)
    pi.set_mode(PIN_B,   pigpio.INPUT); pi.set_pull_up_down(PIN_B,   pigpio.PUD_UP)
    pi.set_mode(BTN_PIN, pigpio.INPUT); pi.set_pull_up_down(BTN_PIN, pigpio.PUD_UP)
    pi.set_glitch_filter(BTN_PIN, 10_000)

    meter = FrequencyMeter(pi, gpio_pin=GPIO_PIN, min_dt_us=100)

    _reset()
    _attach(pi)

    try:
        while True:
            # ── Exit conditions ──
            if _state['button_pressed'] or _state['long_press']:
                break

            freq = meter.get_frequency()

            if not meter.locked:
                # ── Locking screen ──
                req = meter.required_samples or "?"
                lcd.put_line(0, "Measuring...")
                lcd.put_line(1, f"{meter.update_count}/{req} samples")
                lcd.put_line(2, f"{freq:8.2f} Hz")
                lcd.put_line(3, "Btn: exit")

            else:
                # ── Locked screen ──
                lcd.put_line(0, "Frequency Locked")
                lcd.put_line(1, f"{freq:8.2f} Hz")
                lcd.put_line(2, f"dt: {meter.get_max_dt()} us")
                lcd.put_line(3, "Btn: exit")

            time.sleep(0.2)

    finally:
        meter.cleanup()
        _clear_callbacks()
        lcd.clear()
        lcd.close()
