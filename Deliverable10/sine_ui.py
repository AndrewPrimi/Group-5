"""
sine_ui.py  –  Standalone test UI for the sine wave generator.

Controls:
  Rotate encoder  →  adjust frequency or amplitude
  Short press     →  confirm value / select menu item
  Long press      →  cancel / go back

Menu:
  Frequency  →  100–10000 Hz in 10 Hz steps
  Amplitude  →  0.00–1.00 in 0.05 steps
  Output     →  On / Off
  Quit
"""

import sys
import os
import time
import pigpio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Deliverable9'))

import i2c_lcd
import rotary_encoder
from Sinewave import SineWaveGenerator, MIN_FREQ, MAX_FREQ, FREQ_STEP, MAX_AMP, AMP_STEP

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


# ── Display helpers ───────────────────────────────────────────────────────────

def _draw_menu(lcd, options, idx):
    n = len(options)
    window = max(0, min(idx - 1, n - 3))
    lcd.put_line(0, "Sine Wave Test")
    for row in range(3):
        i = window + row
        if i < n:
            lcd.put_line(row + 1, (">" if i == idx else " ") + options[i])
        else:
            lcd.put_line(row + 1, "")


def _pick(pi, lcd, options):
    """Scrollable menu. Returns selected string."""
    idx = 0
    _reset()
    _attach(pi)
    _draw_menu(lcd, options, idx)
    try:
        while True:
            d = _state['encoder_delta']
            if d:
                idx = (idx + d) % len(options)
                _state['encoder_delta'] = 0
                _draw_menu(lcd, options, idx)
            if _state['button_pressed']:
                _state['button_pressed'] = False
                return options[idx]
            time.sleep(0.02)
    finally:
        _clear_callbacks()


def _adjust(pi, lcd, title, value, lo, hi, step, fmt):
    """Encoder value adjustment. Short press = confirm, long press = cancel."""
    _reset()
    _attach(pi)
    lcd.put_line(0, title)
    lcd.put_line(1, fmt(value))
    lcd.put_line(2, "Turn: adjust")
    lcd.put_line(3, "Btn:set  Hold:back")
    try:
        while True:
            d = _state['encoder_delta']
            if d:
                value = max(lo, min(hi, value + step * d))
                value = round(round(value / step) * step, 10)
                _state['encoder_delta'] = 0
                lcd.put_line(1, fmt(value))
            if _state['button_pressed']:
                _state['button_pressed'] = False
                return value
            if _state['long_press']:
                _state['long_press'] = False
                return None
            time.sleep(0.02)
    finally:
        _clear_callbacks()


# ── Main UI ───────────────────────────────────────────────────────────────────

def main():
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod not running — run 'sudo pigpiod' first.")

    lcd = i2c_lcd.lcd(pi, width=20)

    pi.set_mode(PIN_A,   pigpio.INPUT); pi.set_pull_up_down(PIN_A,   pigpio.PUD_UP)
    pi.set_mode(PIN_B,   pigpio.INPUT); pi.set_pull_up_down(PIN_B,   pigpio.PUD_UP)
    pi.set_mode(BTN_PIN, pigpio.INPUT); pi.set_pull_up_down(BTN_PIN, pigpio.PUD_UP)
    pi.set_glitch_filter(BTN_PIN, 10_000)

    freq   = 1000
    amp    = 0.5
    output = False
    gen    = SineWaveGenerator(pi, debug=True)

    try:
        while True:
            status = "ON" if output else "OFF"
            choice = _pick(pi, lcd, [
                f"Freq: {freq} Hz",
                f"Amp:  {amp:.2f}",
                f"Output: {status}",
                "Quit",
            ])

            if choice.startswith("Freq"):
                val = _adjust(pi, lcd, "Frequency", freq,
                              MIN_FREQ, MAX_FREQ, FREQ_STEP,
                              lambda v: f"{int(v)} Hz")
                if val is not None:
                    freq = int(val)
                    gen.set_frequency(freq)

            elif choice.startswith("Amp"):
                val = _adjust(pi, lcd, "Amplitude", amp,
                              0.0, MAX_AMP, AMP_STEP,
                              lambda v: f"{v:.2f}")
                if val is not None:
                    amp = val
                    gen.set_amplitude(amp)

            elif choice.startswith("Output"):
                if output:
                    gen.stop()
                    output = False
                else:
                    gen.set_frequency(freq)
                    gen.set_amplitude(amp)
                    gen.start()
                    output = True

            elif choice == "Quit":
                break

    finally:
        gen.cleanup()
        _clear_callbacks()
        lcd.clear()
        lcd.close()
        pi.stop()


if __name__ == "__main__":
    main()
