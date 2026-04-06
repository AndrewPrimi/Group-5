"""
Sinewave.py
SPWM sine wave generator using pigpio waveforms.

How it works:
  One full sine cycle is divided into N_SAMPLES time slots.
  Each slot has a duty cycle proportional to sin(2π*i/N_SAMPLES):

      duty[i] = 0.5 + amplitude * 0.5 * sin(2π*i/N)

  The slot duration controls frequency:

      slot_us = 1_000_000 / (frequency * N_SAMPLES)

  The waveform is compiled once into the pigpiod daemon and plays in hardware
  — no Python timing loops required.

Hardware:
  GPIO 13 — SPWM output (same pin as square wave generator)
  A low-pass filter on the output is required to reconstruct the sine.
  RC suggestion: 1kΩ + 10nF  →  cutoff ≈ 16kHz (passes 100Hz–10kHz sine,
  attenuates the ~10kHz–500kHz carrier content).

Amplitude:
  Expressed as a fraction 0.0–1.0.
  1.0 = duty cycle swings from 0% to 100% (maximum AC content).
  0.0 = 50% constant duty cycle (no AC output).
  Actual output voltage depends on the analog gain stage and must be
  calibrated on the hardware if a specific Vpp is required.
"""

import math
import pigpio

PWM_GPIO  = 12
N_SAMPLES = 32        # LUT points per sine cycle

MIN_FREQ  = 100       # Hz
MAX_FREQ  = 10_000    # Hz
FREQ_STEP = 10        # Hz per encoder click
MAX_AMP   = 1.0       # amplitude fraction 0.0–1.0
AMP_STEP  = 0.05

# Pre-computed sine LUT: N_SAMPLES values in [-1.0, +1.0]
_LUT = [math.sin(2 * math.pi * i / N_SAMPLES) for i in range(N_SAMPLES)]


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


class SineWaveGenerator:
    """
    Generates a sine wave on GPIO 13 using Sinusoidal PWM (SPWM).

    Frequency is set by changing the time per LUT slot.
    Amplitude is set by scaling the duty cycle swing around 50%.
    Both changes rebuild and restart the waveform.

    Interface mirrors SquareWaveGenerator for easy integration into Driver.py.
    """

    def __init__(self, pi, debug=False):
        self._pi        = pi
        self._frequency = MIN_FREQ
        self._amplitude = 0.5
        self._running   = False
        self._wave_id   = None
        self._debug     = debug

        pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        pi.write(PWM_GPIO, 0)

    def _build_wave(self):
        """
        Compile one full SPWM cycle into the pigpiod wave buffer.

        For each of the N_SAMPLES LUT points:
            slot_us  = 1_000_000 / (frequency * N_SAMPLES)
            duty     = 0.5 + amplitude * 0.5 * sin(2π*i/N)
            high_us  = max(1, round(duty * slot_us))
            low_us   = max(1, slot_us - high_us)

        Minimum slot enforced at 2µs so high_us and low_us both stay ≥ 1µs.
        At 10kHz with N=32: slot = 3µs  (3.125 rounded)
        At 100Hz with N=32: slot = 312µs
        """
        slot_us = max(2, round(1_000_000 / (self._frequency * N_SAMPLES)))
        on_mask  = 1 << PWM_GPIO
        off_mask = 1 << PWM_GPIO

        pulses = []
        for sample in _LUT:
            duty    = _clamp(0.5 + self._amplitude * 0.5 * sample, 0.0, 1.0)
            high_us = max(1, round(duty * slot_us))
            low_us  = max(1, slot_us - high_us)
            pulses.append(pigpio.pulse(on_mask,  0,        high_us))
            pulses.append(pigpio.pulse(0,        off_mask, low_us))

        self._pi.wave_tx_stop()
        self._pi.wave_clear()
        self._pi.wave_add_generic(pulses)
        wave_id = self._pi.wave_create()

        if self._debug:
            print(f"[SineWave] freq={self._frequency}Hz  amp={self._amplitude:.2f}"
                  f"  slot={slot_us}µs  pulses={len(pulses)}  wave_id={wave_id}")
        return wave_id

    def _apply(self):
        """Rebuild wave and start looping it."""
        wave_id = self._build_wave()
        if wave_id < 0:
            print(f"[SineWave] wave_create failed (error {wave_id})")
            return
        self._pi.wave_send_repeat(wave_id)
        self._wave_id = wave_id

    def set_frequency(self, frequency):
        """Set output frequency in Hz (100–10000). Rebuilds wave if running."""
        self._frequency = int(_clamp(int(frequency), MIN_FREQ, MAX_FREQ))
        if self._running:
            self._apply()
        if self._debug:
            print(f"[SineWave] frequency → {self._frequency} Hz")

    def set_amplitude(self, amplitude):
        """Set amplitude fraction 0.0–1.0. Rebuilds wave if running."""
        self._amplitude = _clamp(float(amplitude), 0.0, MAX_AMP)
        if self._running:
            self._apply()
        if self._debug:
            print(f"[SineWave] amplitude → {self._amplitude:.2f}")

    def start(self):
        """Start the sine wave output."""
        self._running = True
        self._apply()
        if self._debug:
            print("[SineWave] started")

    def stop(self):
        """Stop output and set GPIO low."""
        self._pi.wave_tx_stop()
        self._pi.write(PWM_GPIO, 0)
        self._pi.wave_clear()
        self._running   = False
        self._wave_id   = None
        if self._debug:
            print("[SineWave] stopped")

    def cleanup(self):
        self.stop()

    @property
    def frequency(self):
        return self._frequency

    @property
    def amplitude(self):
        return self._amplitude


if __name__ == "__main__":
    import time

    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    gen = SineWaveGenerator(pi, debug=True)

    try:
        print("1kHz at 50% amplitude for 5s...")
        gen.set_frequency(1000)
        gen.set_amplitude(0.5)
        gen.start()
        time.sleep(5)

        print("Sweeping frequency: 100 → 500 → 1k → 2k → 5k → 10k Hz")
        for f in [100, 500, 1000, 2000, 5000, 10000]:
            gen.set_frequency(f)
            print(f"  {f} Hz")
            time.sleep(2)

        print("Sweeping amplitude 0.1 → 1.0 at 1kHz")
        gen.set_frequency(1000)
        for a in [0.1, 0.25, 0.5, 0.75, 1.0]:
            gen.set_amplitude(a)
            print(f"  amp={a:.2f}")
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        gen.cleanup()
        pi.stop()
