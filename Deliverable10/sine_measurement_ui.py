"""
sine_measurement_ui.py – LCD UI for sine wave frequency measurement.

Displays:
  - Sampling progress while acquiring frequency
  - Locked frequency and dt once stable

Controls:
  Long press → exit
"""

import sys
import os
import time
import pigpio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Deliverable9'))

import i2c_lcd
import rotary_encoder
from Sinewave_measurement import FrequencyMeter

# ── GPIO ──────────────────────────────────────────────────────────────────────
PIN_A         = 22
PIN_B         = 27
BTN_PIN       = 17
DEBOUNCE_US   = 200_000
HOLD_US       = 2_000_000

# ── State ─────────────────────────────────────────────────────────────────────
_state = {
    'encoder_delta':    0,
    'button_pressed':   False,
    'long_press':       False,
    'button_last_tick': None,
    'button_press_tick': None,
    'active_callbacks': [],
}

# ── Callback helpers ──────────────────────────────────────────────────────────

def _clear_callbacks():
    for c in _state['active_callbacks']:
        c.cancel()
    _state['active_callbacks'] = []


def _reset():
    _state['encoder_delta']    = 0
    _state['button_pressed']   = False
    _state['long_press']       = False
    _state['button_last_tick'] = None


def _on_rotate(direction):
    _state['encoder_delta'] = _state['encoder_delta'] - direction


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


# ── Display logic ─────────────────────────────────────────────────────────────

def _draw_sampling(lcd, meter):
    """Display sampling progress."""
    lcd.put_line(0, "Measuring...")
    
    required = meter.required_samples or 0
    count = meter.update_count

    lcd.put_line(1, f"Samples: {count}/{required}")

    if meter.get_frequency() > 0:
        lcd.put_line(2, f"{meter.get_frequency():.1f} Hz")
        lcd.put_line(3, f"dt: {meter.get_max_dt()} us")
    else:
        lcd.put_line(2, "Waiting signal...")
        lcd.put_line(3, "")


def _draw_locked(lcd, meter):
    """Display locked frequency."""
    lcd.put_line(0, "Locked")
    lcd.put_line(1, f"{meter.get_frequency():.2f} Hz")
    lcd.put_line(2, f"dt: {meter.get_max_dt()} us")
    lcd.put_line(3, "Hold btn to exit")


# ── Main UI ───────────────────────────────────────────────────────────────────

def main():
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    lcd = i2c_lcd.lcd(pi, width=20)

    # GPIO setup
    pi.set_mode(PIN_A,   pigpio.INPUT); pi.set_pull_up_down(PIN_A,   pigpio.PUD_UP)
    pi.set_mode(PIN_B,   pigpio.INPUT); pi.set_pull_up_down(PIN_B,   pigpio.PUD_UP)
    pi.set_mode(BTN_PIN, pigpio.INPUT); pi.set_pull_up_down(BTN_PIN, pigpio.PUD_UP)
    pi.set_glitch_filter(BTN_PIN, 10_000)

    meter = FrequencyMeter(pi, min_dt_us=100)

    _reset()
    _attach(pi)

    try:
        while True:
            if meter.locked:
                _draw_locked(lcd, meter)
            else:
                _draw_sampling(lcd, meter)

            # Exit on long press
            if _state['long_press']:
                break

            time.sleep(0.1)

    finally:
        meter.cleanup()
        _clear_callbacks()
        lcd.clear()
        lcd.close()
        pi.stop()


if __name__ == "__main__":
    main()
