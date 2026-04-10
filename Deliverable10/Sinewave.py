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

SPI_CHANNEL = 0
SPI_BAUD    = 1_000_000

CMD_WRITE_WIPER0 = 0x00
CMD_WRITE_WIPER1 = 0x10

# Replace these with your measured calibration points.
# Format: requested Vpp -> digipot step
AMP_CAL_TABLE = {
    0.0: 0,
    0.5: 6,
    1.0: 13,
    1.5: 19,
    2.0: 26,
    2.5: 32,
    3.0: 39,
    3.5: 45,
    4.0: 52,
    4.5: 58,
    5.0: 65,
    5.5: 72,
    6.0: 79,
    6.5: 86,
    7.0: 93,
    7.5: 100,
    8.0: 107,
    8.5: 114,
    9.0: 121,
    9.5: 127,
}


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

        self._spi = pi.spi_open(SPI_CHANNEL, SPI_BAUD, 0)

        pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        pi.write(PWM_GPIO, 0)

    def _get_samples(self):
        if self._frequency <= 2000:
            return 64
        elif self._frequency <= 5000:
            return 32
        else:
            return 16

    def _write_wiper0(self, step):
        step = int(_clamp(step, 0, 127))
        self._pi.spi_write(self._spi, bytes([CMD_WRITE_WIPER0, step]))

        if self._debug:
            print(f"[Digipot] Wiper 0 -> step {step}")

    def _amp_to_step(self, amplitude_vpp):
        amplitude_vpp = _clamp(float(amplitude_vpp), 0.0, max(AMP_CAL_TABLE.keys()))

        keys = sorted(AMP_CAL_TABLE.keys())

        if amplitude_vpp <= keys[0]:
            return AMP_CAL_TABLE[keys[0]]
        if amplitude_vpp >= keys[-1]:
            return AMP_CAL_TABLE[keys[-1]]

        for i in range(len(keys) - 1):
            x0 = keys[i]
            x1 = keys[i + 1]

            if x0 <= amplitude_vpp <= x1:
                y0 = AMP_CAL_TABLE[x0]
                y1 = AMP_CAL_TABLE[x1]

                if x1 == x0:
                    return int(y0)

                frac = (amplitude_vpp - x0) / (x1 - x0)
                step = y0 + frac * (y1 - y0)
                return int(round(step))

        return 0

    def _build_wave(self):
        N = self._get_samples()
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
                f"N={N} slot={slot_us}us pulses={len(pulses)} wave_id={wave_id}"
            )

        return wave_id

    def _apply(self):
        step = self._amp_to_step(self._amp_v)

        step = 127 - step
        
        self._write_wiper0(step)

        wave_id = self._build_wave()
        if wave_id < 0:
            print(f"[SineWave] wave_create failed (error {wave_id})")
            return

        self._pi.wave_send_repeat(wave_id)
        self._wave_id = wave_id

        if self._debug:
            print(
                f"[SineWave] applied freq={self._frequency}Hz "
                f"amp={self._amp_v:.2f}Vpp step={step}"
            )

    def set_frequency(self, frequency):
        snapped = round(int(frequency) / FREQ_STEP) * FREQ_STEP
        self._frequency = int(_clamp(snapped, MIN_FREQ, MAX_FREQ))

        if self._running:
            self._apply()

        if self._debug:
            print(f"[SineWave] frequency -> {self._frequency} Hz")

    def set_amplitude(self, amplitude_vpp):
        self._amp_v = _clamp(float(amplitude_vpp), 0.0, max(AMP_CAL_TABLE.keys()))

        # Keep PWM depth full scale unless you intentionally want software amplitude shaping too.
        self._amplitude = 1.0 if self._amp_v > 0 else 0.0

        if self._running:
            self._apply()

        if self._debug:
            print(
                f"[SineWave] amplitude -> {self._amp_v:.2f} Vpp "
                f"(PWM fraction={self._amplitude:.3f})"
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
        self._pi.spi_close(self._spi)

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

    gen.set_frequency(5000)
    gen.set_amplitude(5.0)
    gen.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    gen.cleanup()
    pi.stop()
