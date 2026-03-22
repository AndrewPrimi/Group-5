"""
square_wave.py – Square wave generator via hardware PWM + MCP4231 amplitude.

Frequency
---------
Driven entirely by pigpio hardware_PWM on GPIO 13 at a fixed 50% duty cycle.
Changing frequency just changes the FREQ argument — no manual signal toggling.

  pi.hardware_PWM(GPIO=13, FREQ=<user frequency>, DUTY=500000)

Amplitude
---------
The MCP4231 dual digital pot (SPI CE0) feeds a summing amplifier:
  W1 (command 0x10) → positive op-amp circuit  → sets +swing
  W0 (command 0x00) → negative op-amp circuit  → sets -swing

IMPORTANT:
  The actual hardware output is intentionally scaled to 1/3 of the value
  shown on the LCD / selected by the user.

  Example:
    LCD says 9.0 V  -> actual output target is 3.0 V
    LCD says 6.0 V  -> actual output target is 2.0 V
    LCD says 3.0 V  -> actual output target is 1.0 V

Calibration endpoints (for actual hardware output):
  Amplitude  |  W0 step  |  W1 step
  -----------+-----------+---------
    0.0 V    |    127    |     0
   10.0 V    |      0    |   127

So the code first scales:
  actual_amp = displayed_amp / 3

Then maps actual_amp into digipot steps.
"""

import time

# ── Hardware constants ────────────────────────────────────────────────────────
PWM_GPIO  = 13
DUTY      = 500_000     # 50 % duty cycle (pigpio: 0 – 1_000_000)

# ── User-facing range constants (imported by Driver.py) ──────────────────────
MIN_FREQ  = 100         # Hz
MAX_FREQ  = 10_000      # Hz
FREQ_STEP = 10          # Hz per encoder click
MAX_AMP   = 10.0        # V shown on LCD / user-facing max


def _amp_to_steps(amplitude):
    """
    Map displayed amplitude (0 – 10 V) to (W0_step, W1_step).

    The actual hardware output is intentionally 1/3 of the displayed value.
    W0 → negative op-amp, W1 → positive op-amp.
    """
    # Clamp user-selected/displayed amplitude
    amplitude = max(0.0, min(MAX_AMP, amplitude))

    # Scale actual output to 1/3 of displayed value
    actual_amp = amplitude / 3.0

    # Clamp actual amplitude to valid calibration range
    actual_amp = max(0.0, min(MAX_AMP, actual_amp))

    t  = actual_amp / MAX_AMP
    w0 = round(127 - 127 * t)   # negative circuit decreases as amplitude rises
    w1 = round(127 * t)         # positive circuit increases as amplitude rises

    return w0, w1


class SquareWaveGenerator:
    def __init__(self, pi, spi_handle, settle_time=0.001):
        """
        pi          : shared pigpio instance
        spi_handle  : SPI handle for amplitude MCP4231 (CE0, shared with DC ref)
        settle_time : delay after each SPI write for wiper to settle
        """
        self._pi        = pi
        self._spi       = spi_handle
        self._settle    = settle_time
        self._frequency = MIN_FREQ
        self._amplitude = 0.0
        self._running   = False

        # hardware_PWM sets GPIO 13 to ALT0 automatically — no set_mode needed

    # ── Internal ──────────────────────────────────────────────────────────────

    def _write_amplitude(self, amplitude):
        """Write W0 (negative) and W1 (positive) wipers for the given amplitude."""
        w0, w1 = _amp_to_steps(amplitude)
        self._pi.spi_write(self._spi, [0x00, w0])  # W0 – negative op-amp
        time.sleep(self._settle)
        self._pi.spi_write(self._spi, [0x10, w1])  # W1 – positive op-amp
        time.sleep(self._settle)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_frequency(self, frequency: int):
        """Update frequency. Applied immediately via hardware_PWM if running."""
        self._frequency = max(MIN_FREQ, min(MAX_FREQ, int(frequency)))
        if self._running:
            self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)

    def set_amplitude(self, amplitude: float):
        """Update displayed amplitude. Actual hardware output is 1/3 of this value."""
        self._amplitude = max(0.0, min(MAX_AMP, amplitude))
        if self._running:
            self._write_amplitude(self._amplitude)

    def start(self):
        """Set amplitude wipers then start hardware PWM at the stored frequency."""
        self._running = True
        self._write_amplitude(self._amplitude)
        self._pi.hardware_PWM(PWM_GPIO, self._frequency, DUTY)

    def stop(self):
        """Stop hardware PWM and zero amplitude wipers."""
        self._running = False
        self._pi.hardware_PWM(PWM_GPIO, 0, 0)
        self._write_amplitude(0.0)

    def cleanup(self):
        self.stop()
