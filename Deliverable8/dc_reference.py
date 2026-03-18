"""
dc_reference.py – DC voltage reference output using hardware PWM + RC filter.

The Raspberry Pi hardware PWM pin outputs a PWM signal whose duty cycle is
set proportional to the desired DC voltage.  An external RC low-pass filter
on the PCB smooths this into a steady DC level.

GPIO 18 is used (hardware PWM channel 0, alt-function 5).
"""

import pigpio

PWM_GPIO   = 18          # hardware PWM pin
PWM_FREQ   = 100_000     # 100 kHz carrier – well above RC filter corner
MAX_VOLT   = 5.0         # full-scale output voltage (V)
MIN_VOLT   = 0.0


class DCReferenceGenerator:
    def __init__(self):
        self._pi      = pigpio.pi()
        self._voltage = 0.0
        self._running = False

        if not self._pi.connected:
            raise SystemExit("DCReferenceGenerator: cannot connect to pigpio.")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _duty(self, voltage):
        """Convert voltage to pigpio duty cycle (0 – 1_000_000)."""
        fraction = max(0.0, min(1.0, voltage / MAX_VOLT))
        return int(fraction * 1_000_000)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_voltage(self, voltage: float):
        """Set the desired output voltage (0.0 – 5.0 V)."""
        self._voltage = max(MIN_VOLT, min(MAX_VOLT, voltage))
        if self._running:
            self._pi.hardware_PWM(PWM_GPIO, PWM_FREQ, self._duty(self._voltage))

    def start(self):
        """Enable the DC output at the last set voltage."""
        self._running = True
        self._pi.hardware_PWM(PWM_GPIO, PWM_FREQ, self._duty(self._voltage))

    def stop(self):
        """Disable the DC output (drive pin low)."""
        self._running = False
        self._pi.hardware_PWM(PWM_GPIO, 0, 0)

    def cleanup(self):
        """Release hardware resources."""
        self.stop()
        self._pi.stop()
