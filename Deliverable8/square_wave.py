"""
square_wave.py – Square wave generator using hardware PWM.

GPIO 13 is the hardware PWM output (alt-function 0, PWM channel 1).
Frequency is set directly via pigpio hardware_PWM.
Amplitude is stored and applied to an external analog stage (op-amp / digital
pot on a separate SPI channel) — adjust set_amplitude() to match your hardware.
"""

import pigpio

PWM_GPIO  = 13
DUTY      = 500_000   # 50 % duty cycle (pigpio range 0–1_000_000)

MIN_FREQ  = 100       # Hz
MAX_FREQ  = 10_000    # Hz
FREQ_STEP = 10        # Hz per encoder click
MAX_AMP   = 10.0      # V peak-to-peak max


class SquareWaveGenerator:
    def __init__(self):
        self._pi        = pigpio.pi()
        self._frequency = MIN_FREQ
        self._amplitude = 0.0
        self._running   = False

        if not self._pi.connected:
            raise SystemExit("SquareWaveGenerator: cannot connect to pigpio.")

        self._pi.set_mode(PWM_GPIO, pigpio.OUTPUT)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_frequency(self, frequency: int):
        self._frequency = max(MIN_FREQ, min(MAX_FREQ, int(frequency)))
        if self._running:
            self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)

    def set_amplitude(self, amplitude: float):
        """Store amplitude; wire your analog stage here if needed."""
        self._amplitude = max(0.0, min(MAX_AMP, amplitude))

    def start(self):
        self._running = True
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)

    def stop(self):
        self._running = False
        self._pi.hardware_PWM(PWM_GPIO, 0, 0)

    def cleanup(self):
        self.stop()
        self._pi.stop()
