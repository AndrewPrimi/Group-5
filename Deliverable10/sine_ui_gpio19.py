"""
sine_ui.py  –  Standalone UI for the new sine wave generator design.

Controls:
  Rotate encoder  ->  adjust frequency or amplitude
  Short press     ->  confirm value / select menu item
  Long press      ->  cancel / go back

Menu:
  Frequency  ->  1000–10000 Hz in 500 Hz steps
  Amplitude  ->  0.000–10.000 V in 0.625 V steps
  Output     ->  On / Off
  Quit
"""

import sys
import os
import time
import math
import pigpio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Deliverable9'))

import i2c_lcd
import rotary_encoder

# ── GPIO ──────────────────────────────────────────────────────────────────────
PWM_GPIO      = 19
PIN_A         = 22
PIN_B         = 27
BTN_PIN       = 17
DEBOUNCE_US   = 200_000
HOLD_US       = 2_000_000

# ── Sine generator specs ─────────────────────────────────────────────────────
MIN_FREQ = 1000
MAX_FREQ = 10000
FREQ_STEP = 500

MAX_AMP = 10.0
AMP_STEP = 0.625

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
    _state['button_press_tick'] = None


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


# ── Utility helpers ───────────────────────────────────────────────────────────

def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _snap_frequency(freq):
    freq = _clamp(int(freq), MIN_FREQ, MAX_FREQ)
    return int(round(freq / FREQ_STEP) * FREQ_STEP)


def _snap_amplitude(amp):
    amp = _clamp(float(amp), 0.0, MAX_AMP)
    return round(amp / AMP_STEP) * AMP_STEP


# ── Sine wave generator ───────────────────────────────────────────────────────

class SineWaveGenerator:
    def __init__(self, pi, debug=False):
        self._pi        = pi
        self._frequency = MIN_FREQ
        self._amp_v     = 0.0
        self._amplitude = 0.0   # normalized 0..1
        self._running   = False
        self._wave_id   = None
        self._debug     = debug

        pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        pi.write(PWM_GPIO, 0)

    def _get_samples(self):
        if self._frequency <= 2000:
            return 64
        elif self._frequency <= 5000:
            return 32
        else:
            return 16

    def _build_wave(self):
        N = self._get_samples()

        # One-cycle sine LUT
        lut = [math.sin(2 * math.pi * i / N) for i in range(N)]

        # Time per sample slot
        slot_us = max(2, round(1_000_000 / (self._frequency * N)))

        on_mask  = 1 << PWM_GPIO
        off_mask = 1 << PWM_GPIO

        pulses = []

        for sample in lut:
            # Positive-only PWM-centered sine
            duty = _clamp(0.5 + self._amplitude * 0.5 * sample, 0.0, 1.0)

            high_us = max(1, round(duty * slot_us))
            low_us  = max(1, slot_us - high_us)

            pulses.append(pigpio.pulse(on_mask, 0, high_us))
            pulses.append(pigpio.pulse(0, off_mask, low_us))

        self._pi.wave_tx_stop()
        self._pi.wave_clear()
        self._pi.wave_add_generic(pulses)
        wave_id = self._pi.wave_create()

        if self._debug:
            print(
                f"[SineWave] freq={self._frequency}Hz "
                f"N={N} slot={slot_us}us pulses={len(pulses)} wave_id={wave_id}"
            )

        return wave_id

    def _apply(self):
        wave_id = self._build_wave()
        if wave_id < 0:
            print(f"[SineWave] wave_create failed (error {wave_id})")
            return

        self._pi.wave_send_repeat(wave_id)
        self._wave_id = wave_id

    def set_frequency(self, frequency):
        self._frequency = _snap_frequency(frequency)
        if self._running:
            self._apply()

        if self._debug:
            print(f"[SineWave] frequency -> {self._frequency} Hz")

    def set_amplitude(self, amplitude_v):
        self._amp_v = _snap_amplitude(amplitude_v)
        self._amplitude = self._amp_v / MAX_AMP

        if self._running:
            self._apply()

        if self._debug:
            print(
                f"[SineWave] amplitude -> {self._amp_v:.3f} V "
                f"(fraction={self._amplitude:.3f})"
            )

    def start(self):
        self._running = True
        self._apply()

        if self._debug:
            print("[SineWave] started")

    def stop(self):
        self._pi.wave_tx_stop()
        self._pi.write(PWM_GPIO, 0)
        self._pi.wave_clear()

        self._running = False
        self._wave_id = None

        if self._debug:
            print("[SineWave] stopped")

    def cleanup(self):
        self.stop()


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

    pi.set_mode(PIN_A,   pigpio.INPUT)
    pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)

    pi.set_mode(PIN_B,   pigpio.INPUT)
    pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)

    pi.set_mode(BTN_PIN, pigpio.INPUT)
    pi.set_pull_up_down(BTN_PIN, pigpio.PUD_UP)

    pi.set_glitch_filter(BTN_PIN, 10_000)

    freq   = 1000
    amp    = 0.0
    output = False
    gen    = SineWaveGenerator(pi, debug=True)

    try:
        while True:
            status = "ON" if output else "OFF"
            choice = _pick(pi, lcd, [
                f"Freq: {freq} Hz",
                f"Amp:  {amp:.3f} V",
                f"Output: {status}",
                "Quit",
            ])

            if choice.startswith("Freq"):
                val = _adjust(
                    pi, lcd, "Frequency", freq,
                    MIN_FREQ, MAX_FREQ, FREQ_STEP,
                    lambda v: f"{int(v)} Hz"
                )
                if val is not None:
                    freq = int(val)
                    gen.set_frequency(freq)

            elif choice.startswith("Amp"):
                val = _adjust(
                    pi, lcd, "Amplitude", amp,
                    0.0, MAX_AMP, AMP_STEP,
                    lambda v: f"{v:.3f} V"
                )
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
