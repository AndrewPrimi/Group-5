import math
import pigpio

PWM_GPIO = 12

MIN_FREQ = 1000
MAX_FREQ = 10_000
FREQ_STEP = 500

GAIN      = 3
VREF      = 3.3
MAX_AMP   = VREF * GAIN
AMP_STEP  = 0.5


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


class SineWaveGenerator:
    def __init__(self, pi, debug=False):
        self._pi        = pi
        self._frequency = MIN_FREQ
        self._amplitude = 0.0
        self._amp_v     = 0.0
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

        # Generate LUT dynamically
        lut = [math.sin(2 * math.pi * i / N) for i in range(N)]

        slot_us = max(2, round(1_000_000 / (self._frequency * N)))

        on_mask  = 1 << PWM_GPIO
        off_mask = 1 << PWM_GPIO

        pulses = []

        for sample in lut:
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
                f"N={N} slot={slot_us}µs pulses={len(pulses)} wave_id={wave_id}"
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
        self._frequency = int(_clamp(int(frequency), MIN_FREQ, MAX_FREQ))
        if self._running:
            self._apply()

        if self._debug:
            print(f"[SineWave] frequency → {self._frequency} Hz")

    def set_amplitude(self, amplitude_vpp):
        self._amp_v     = _clamp(float(amplitude_vpp), 0.0, MAX_AMP)
        self._amplitude = self._amp_v / MAX_AMP

        if self._running:
            self._apply()

        if self._debug:
            print(
                f"[SineWave] amplitude → {self._amp_v:.2f} Vpp "
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
    def frequency(self):
        return self._frequency

    @property
    def amplitude(self):
        return self._amp_v


if __name__ == "__main__":
    import time

    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    gen = SineWaveGenerator(pi, debug=True)

    gen.set_amplitude(5.0)
    gen.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    gen.cleanup()
    pi.stop()
