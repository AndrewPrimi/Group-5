"""
sine_ui.py

GPIO19 sine-wave generator with LCD + rotary encoder UI.

Requirements implemented:
- Frequency: 1 kHz to 10 kHz in 500 Hz steps
- Amplitude: 0 to 10 V in 0.625 V steps
- Positive-only sine output
- Output On / Off from UI
- Output turns off when leaving the page

Hardware assumptions:
- PWM output: GPIO19
- Rotary A: GPIO22
- Rotary B: GPIO27
- Rotary push button: GPIO17
- LCD uses a common i2c_lcd driver with clear(), move_to(), putstr()

IMPORTANT:
1. Run pigpio daemon first:
   sudo pigpiod

2. This code generates a repeated digital waveform on GPIO19.
   Your RC filter + TL081 stage turn that into the analog 0-10 V sine.

3. If your LCD driver uses different method names, only edit lcd_show().
"""

import math
import time
import pigpio

# Change this import to match your LCD file if needed
from i2c_lcd import I2cLcd


# ----------------------------
# Pin configuration
# ----------------------------
PWM_GPIO = 19
ENC_A = 22
ENC_B = 27
ENC_SW = 17

# ----------------------------
# LCD configuration
# ----------------------------
LCD_I2C_BUS = 1
LCD_ADDR = 0x27
LCD_COLS = 20
LCD_ROWS = 4

# ----------------------------
# Sine settings
# ----------------------------
FREQ_MIN = 1000
FREQ_MAX = 10000
FREQ_STEP = 500

AMP_MIN = 0.0
AMP_MAX = 10.0
AMP_STEP = 0.625

# More samples = smoother, but high frequency needs larger time slots.
def choose_samples(freq: int) -> int:
    if freq <= 2000:
        return 80
    elif freq <= 5000:
        return 40
    else:
        return 20


class SineWaveGenerator:
    def __init__(self, pi: pigpio.pi, gpio: int = PWM_GPIO):
        self.pi = pi
        self.gpio = gpio
        self.current_wave_id = None
        self.is_on = False
        self.freq = 1000
        self.amplitude = 10.0

        self.pi.set_mode(self.gpio, pigpio.OUTPUT)
        self.pi.write(self.gpio, 0)

    def _clamp_frequency(self, freq: int) -> int:
        freq = max(FREQ_MIN, min(FREQ_MAX, freq))
        return int(round(freq / FREQ_STEP) * FREQ_STEP)

    def _clamp_amplitude(self, amp: float) -> float:
        amp = max(AMP_MIN, min(AMP_MAX, amp))
        return round(amp / AMP_STEP) * AMP_STEP

    def _build_wave(self, freq: int, amplitude: float):
        samples = choose_samples(freq)

        period_us = 1_000_000.0 / freq
        sample_period_us = period_us / samples

        amp_scale = amplitude / 10.0
        pulses = []
        mask = 1 << self.gpio

        for i in range(samples):
            angle = 2.0 * math.pi * i / samples

            # Positive-only normalized sine: 0..1
            sine_norm = 0.5 + 0.5 * math.sin(angle)

            # Scale amplitude in software
            duty_fraction = sine_norm * amp_scale

            high_us = int(round(sample_period_us * duty_fraction))
            low_us = int(round(sample_period_us - high_us))

            if high_us > 0:
                pulses.append(pigpio.pulse(mask, 0, high_us))
            if low_us > 0:
                pulses.append(pigpio.pulse(0, mask, low_us))

        return pulses

    def apply_settings(self, freq: int, amplitude: float):
        self.freq = self._clamp_frequency(freq)
        self.amplitude = self._clamp_amplitude(amplitude)

        if self.is_on:
            self.start()

    def start(self):
        self.stop()

        pulses = self._build_wave(self.freq, self.amplitude)
        self.pi.wave_clear()
        self.pi.wave_add_generic(pulses)
        wave_id = self.pi.wave_create()

        if wave_id < 0:
            raise RuntimeError("pigpio wave_create failed")

        self.current_wave_id = wave_id
        self.pi.wave_send_repeat(wave_id)
        self.is_on = True

    def stop(self):
        self.pi.wave_tx_stop()

        if self.current_wave_id is not None:
            try:
                self.pi.wave_delete(self.current_wave_id)
            except pigpio.error:
                pass
            self.current_wave_id = None

        self.pi.write(self.gpio, 0)
        self.is_on = False

    def shutdown(self):
        self.stop()


class RotaryUI:
    def __init__(self, pi: pigpio.pi):
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

        # Quadrature transition table
        self._transitions = {
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

        step = self._transitions.get((self.last_ab, current_ab), 0)
        self.delta += step
        self.last_ab = current_ab

    def _button_cb(self, gpio, level, tick):
        # Active low button
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

    def get_rotation(self) -> int:
        """
        Return detent-like step count.
        Divide by 4 because many encoders produce 4 transitions per click.
        """
        steps = int(self.delta / 4)
        self.delta -= steps * 4
        return steps

    def consume_short_press(self) -> bool:
        if self.short_press:
            self.short_press = False
            return True
        return False

    def consume_long_press(self) -> bool:
        if self.long_press:
            self.long_press = False
            return True
        return False

    def cancel(self):
        self.cb_a.cancel()
        self.cb_b.cancel()
        self.cb_sw.cancel()


class SineGeneratorUI:
    MENU_ITEMS = ["Frequency", "Amplitude", "Output", "Back"]

    def __init__(self):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Could not connect to pigpio. Start pigpio with: sudo pigpiod")

        self.lcd = I2cLcd(LCD_I2C_BUS, LCD_ADDR, LCD_ROWS, LCD_COLS)
        self.ui = RotaryUI(self.pi)
        self.gen = SineWaveGenerator(self.pi, PWM_GPIO)

        self.menu_index = 0
        self.mode = "menu"   # menu, adjust_freq, adjust_amp
        self.freq = 1000
        self.amp = 10.0
        self.running = True

    # -------------
    # LCD helpers
    # -------------
    def lcd_show(self, lines):
        """
        Update this only if your LCD driver is slightly different.
        Expects up to 4 strings.
        """
        self.lcd.clear()
        for row, text in enumerate(lines[:4]):
            self.lcd.move_to(0, row)
            self.lcd.putstr(text[:LCD_COLS].ljust(LCD_COLS))

    def draw(self):
        if self.mode == "menu":
            line0 = "Sine Generator"
            line1 = ("> " if self.menu_index == 0 else "  ") + f"Freq: {self.freq:5d}Hz"
            line2 = ("> " if self.menu_index == 1 else "  ") + f"Amp : {self.amp:5.3f}V"
            out_text = "ON" if self.gen.is_on else "OFF"
            if self.menu_index == 2:
                line3 = f"> Output: {out_text}"
            elif self.menu_index == 3:
                line3 = "> Back"
            else:
                line3 = f"  Output: {out_text}"
            self.lcd_show([line0, line1, line2, line3])

        elif self.mode == "adjust_freq":
            self.lcd_show([
                "Adjust Frequency",
                f"{self.freq:5d} Hz",
                "Rotate to change",
                "Press=Save Hold=Main"
            ])

        elif self.mode == "adjust_amp":
            self.lcd_show([
                "Adjust Amplitude",
                f"{self.amp:5.3f} V",
                "Rotate to change",
                "Press=Save Hold=Main"
            ])

    # -------------
    # Actions
    # -------------
    def toggle_output(self):
        if self.gen.is_on:
            self.gen.stop()
        else:
            self.gen.apply_settings(self.freq, self.amp)
            self.gen.start()

    def leave_page(self):
        # Requirement says output should turn off when you back out
        self.gen.stop()
        self.running = False

    def handle_menu_rotation(self, steps: int):
        if steps != 0:
            self.menu_index = max(0, min(len(self.MENU_ITEMS) - 1, self.menu_index + steps))

    def handle_freq_rotation(self, steps: int):
        if steps != 0:
            self.freq += steps * FREQ_STEP
            self.freq = max(FREQ_MIN, min(FREQ_MAX, self.freq))

    def handle_amp_rotation(self, steps: int):
        if steps != 0:
            self.amp += steps * AMP_STEP
            self.amp = max(AMP_MIN, min(AMP_MAX, self.amp))
            self.amp = round(self.amp / AMP_STEP) * AMP_STEP

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
            self.gen.apply_settings(self.freq, self.amp)
            self.mode = "menu"

        elif self.mode == "adjust_amp":
            self.gen.apply_settings(self.freq, self.amp)
            self.mode = "menu"

    def handle_long_press(self):
        # Hold returns to main / exits page
        self.leave_page()

    def run(self):
        self.draw()

        try:
            while self.running:
                steps = self.ui.get_rotation()

                if self.mode == "menu":
                    self.handle_menu_rotation(steps)
                elif self.mode == "adjust_freq":
                    self.handle_freq_rotation(steps)
                elif self.mode == "adjust_amp":
                    self.handle_amp_rotation(steps)

                if self.ui.consume_short_press():
                    self.handle_short_press()

                if self.ui.consume_long_press():
                    self.handle_long_press()

                self.draw()
                time.sleep(0.03)

        finally:
            self.gen.shutdown()
            self.ui.cancel()
            self.lcd_show([
                "Sine Generator Off",
                "",
                "",
                ""
            ])
            time.sleep(0.5)
            self.pi.stop()


if __name__ == "__main__":
    app = SineGeneratorUI()
    app.run()
