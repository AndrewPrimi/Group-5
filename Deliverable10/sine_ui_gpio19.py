#!/usr/bin/env python3

import math
import time
import pigpio
import i2c_lcd

# ----------------------------
# GPIO pins
# ----------------------------
PWM_GPIO = 19

ENC_A = 22
ENC_B = 27
ENC_SW = 17

# ----------------------------
# Sine wave specs
# ----------------------------
MIN_FREQ = 1000
MAX_FREQ = 10000
FREQ_STEP = 500

MIN_AMP = 0.0
MAX_AMP = 10.0
AMP_STEP = 0.625

LCD_WIDTH = 20


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _snap_frequency(freq):
    freq = _clamp(int(freq), MIN_FREQ, MAX_FREQ)
    return int(round(freq / FREQ_STEP) * FREQ_STEP)


def _snap_amplitude(amp):
    amp = _clamp(float(amp), MIN_AMP, MAX_AMP)
    return round(amp / AMP_STEP) * AMP_STEP


class SineWaveGenerator:
    def __init__(self, pi, debug=False):
        self._pi = pi
        self._frequency = MIN_FREQ
        self._amp_v = 0.0
        self._amplitude = 0.0   # normalized 0 to 1
        self._running = False
        self._wave_id = None
        self._debug = debug

        self._pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        self._pi.write(PWM_GPIO, 0)

    def _get_samples(self):
        if self._frequency <= 2000:
            return 64
        elif self._frequency <= 5000:
            return 32
        else:
            return 16

    def _build_wave(self):
        N = self._get_samples()
        lut = [math.sin(2 * math.pi * i / N) for i in range(N)]

        slot_us = max(2, round(1_000_000 / (self._frequency * N)))

        on_mask = 1 << PWM_GPIO
        off_mask = 1 << PWM_GPIO
        pulses = []

        for sample in lut:
            # Positive-only PWM sine
            duty = _clamp(0.5 + self._amplitude * 0.5 * sample, 0.0, 1.0)

            high_us = max(1, round(duty * slot_us))
            low_us = max(1, slot_us - high_us)

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

    @property
    def is_on(self):
        return self._running

    @property
    def frequency(self):
        return self._frequency

    @property
    def amplitude(self):
        return self._amp_v


class RotaryInput:
    def __init__(self, pi):
        self.pi = pi

        self.pi.set_mode(ENC_A, pigpio.INPUT)
        self.pi.set_mode(ENC_B, pigpio.INPUT)
        self.pi.set_mode(ENC_SW, pigpio.INPUT)

        self.pi.set_pull_up_down(ENC_A, pigpio.PUD_UP)
        self.pi.set_pull_up_down(ENC_B, pigpio.PUD_UP)
        self.pi.set_pull_up_down(ENC_SW, pigpio.PUD_UP)

        self.pi.set_glitch_filter(ENC_SW, 10000)

        self.last_ab = (self.pi.read(ENC_A) << 1) | self.pi.read(ENC_B)
        self.delta = 0

        self.button_pressed = False
        self.button_down_tick = None
        self.short_press = False
        self.long_press = False

        self.cb_a = self.pi.callback(ENC_A, pigpio.EITHER_EDGE, self._enc_cb)
        self.cb_b = self.pi.callback(ENC_B, pigpio.EITHER_EDGE, self._enc_cb)
        self.cb_sw = self.pi.callback(ENC_SW, pigpio.EITHER_EDGE, self._button_cb)

        self.transitions = {
            (0b00, 0b01): +1,
            (0b01, 0b11): +1,
            (0b11, 0b10): +1,
            (0b10, 0b00): +1,
            (0b00, 0b10): -1,
            (0b10, 0b11): -1,
            (0b11, 0b01): -1,
            (0b01, 0b00): -1,
        }

    def _enc_cb(self, gpio, level, tick):
        a = self.pi.read(ENC_A)
        b = self.pi.read(ENC_B)
        current_ab = (a << 1) | b
        step = self.transitions.get((self.last_ab, current_ab), 0)
        self.delta += step
        self.last_ab = current_ab

    def _button_cb(self, gpio, level, tick):
        if level == 0:
            self.button_pressed = True
            self.button_down_tick = tick
        elif level == 1 and self.button_pressed:
            held_us = pigpio.tickDiff(self.button_down_tick, tick)
            self.button_pressed = False
            self.button_down_tick = None

            if held_us >= 1_500_000:
                self.long_press = True
            else:
                self.short_press = True

    def get_rotation(self):
        steps = int(self.delta / 4)
        self.delta -= steps * 4
        return steps

    def consume_short_press(self):
        if self.short_press:
            self.short_press = False
            return True
        return False

    def consume_long_press(self):
        if self.long_press:
            self.long_press = False
            return True
        return False

    def cleanup(self):
        self.cb_a.cancel()
        self.cb_b.cancel()
        self.cb_sw.cancel()


class SineGeneratorUI:
    MENU_ITEMS = ["Frequency", "Amplitude", "Output", "Back"]

    def __init__(self, pi, lcd, debug=False):
        self.pi = pi
        self.lcd = lcd
        self.debug = debug

        self.encoder = RotaryInput(self.pi)
        self.gen = SineWaveGenerator(self.pi, debug=debug)

        self.menu_index = 0
        self.mode = "menu"
        self.freq = MIN_FREQ
        self.amp = 0.0
        self.running = False

    def lcd_show(self, lines):
        for row in range(4):
            if row < len(lines):
                self.lcd.put_line(row, lines[row])
            else:
                self.lcd.put_line(row, "")

    def draw(self):
        if self.mode == "menu":
            line0 = "Sine Generator"
            line1 = (">" if self.menu_index == 0 else " ") + f"Freq {self.freq:5d}Hz"
            line2 = (">" if self.menu_index == 1 else " ") + f"Amp  {self.amp:5.3f}V"

            if self.menu_index == 2:
                line3 = ">" + f"Output {'ON' if self.gen.is_on else 'OFF'}"
            elif self.menu_index == 3:
                line3 = ">Back"
            else:
                line3 = " " + f"Output {'ON' if self.gen.is_on else 'OFF'}"

            self.lcd_show([line0, line1, line2, line3])

        elif self.mode == "adjust_freq":
            self.lcd_show([
                "Adjust Frequency",
                f"{self.freq:5d} Hz",
                "Rotate to change",
                "Press=Save"
            ])

        elif self.mode == "adjust_amp":
            self.lcd_show([
                "Adjust Amplitude",
                f"{self.amp:5.3f} V",
                "Rotate to change",
                "Press=Save"
            ])

    def toggle_output(self):
        if self.gen.is_on:
            self.gen.stop()
        else:
            self.gen.set_frequency(self.freq)
            self.gen.set_amplitude(self.amp)
            self.gen.start()

    def leave_page(self):
        self.gen.stop()
        self.running = False

    def handle_menu_rotation(self, steps):
        if steps != 0:
            self.menu_index = max(0, min(len(self.MENU_ITEMS) - 1, self.menu_index + steps))

    def handle_freq_rotation(self, steps):
        if steps != 0:
            self.freq += steps * FREQ_STEP
            self.freq = _snap_frequency(self.freq)

    def handle_amp_rotation(self, steps):
        if steps != 0:
            self.amp += steps * AMP_STEP
            self.amp = _snap_amplitude(self.amp)

    def handle_short_press(self):
        if self.mode == "menu":
            item = self.MENU_ITEMS[self.menu_index]

            if item == "Frequency":
                self.mode = "adjust_freq"
            elif item == "Amplitude":
                self.mode = "adjust_amp"
            elif item == "Output":
                self.toggle_output()
            elif item == "Back":
                self.leave_page()

        elif self.mode == "adjust_freq":
            self.gen.set_frequency(self.freq)
            self.mode = "menu"

        elif self.mode == "adjust_amp":
            self.gen.set_amplitude(self.amp)
            self.mode = "menu"

    def handle_long_press(self):
        self.leave_page()

    def run(self):
        self.running = True
        self.draw()

        try:
            while self.running:
                steps = self.encoder.get_rotation()

                if self.mode == "menu":
                    self.handle_menu_rotation(steps)
                elif self.mode == "adjust_freq":
                    self.handle_freq_rotation(steps)
                elif self.mode == "adjust_amp":
                    self.handle_amp_rotation(steps)

                if self.encoder.consume_short_press():
                    self.handle_short_press()

                if self.encoder.consume_long_press():
                    self.handle_long_press()

                self.draw()
                time.sleep(0.03)

        finally:
            self.gen.stop()
            self.lcd_show([
                "Sine Generator Off",
                "",
                "",
                ""
            ])

    def cleanup(self):
        self.gen.cleanup()
        self.encoder.cleanup()


if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    lcd = i2c_lcd.lcd(pi, width=20)

    app = SineGeneratorUI(pi, lcd, debug=True)

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()
        lcd.close()
        pi.stop()
