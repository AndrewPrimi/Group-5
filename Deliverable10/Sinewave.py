import math
import pigpio

PWM_GPIO = 12

MIN_FREQ = 1000
MAX_FREQ = 10_000
FREQ_STEP = 500

MAX_AMP = 10.0
AMP_STEP = 0.625

SPI_CHANNEL = 0
SPI_BAUD = 1_000_000

CMD_WRITE_WIPER0 = 0x00
MAX_WIPER_STEP = 127

# These tables are:
# desired amplitude on LCD -> corrected command amplitude
#
# Built from your newest measured data after removing one RC stage.
#
# Notes:
# - Some low amplitudes are already too large even at the minimum nonzero setting.
#   In those cases the corrected command is clamped to 0.625.
# - At 10 kHz, 10.0 Vpp is only barely reachable, so that entry stays at 10.0.
CAL_TABLES = {
    1000: {
        0.625: 0.625,
        1.250: 0.625,
        2.500: 2.148,
        5.000: 4.542,
        7.500: 6.923,
        10.000: 9.327,
    },
    2500: {
        0.625: 0.625,
        1.250: 0.625,
        2.500: 1.814,
        5.000: 3.902,
        7.500: 5.968,
        10.000: 7.941,
    },
    5000: {
        0.625: 0.625,
        1.250: 0.643,
        2.500: 1.671,
        5.000: 3.420,
        7.500: 5.068,
        10.000: 5.912,
    },
    7500: {
        0.625: 0.625,
        1.250: 0.703,
        2.500: 1.505,
        5.000: 3.023,
        7.500: 4.477,
        10.000: 6.081,
    },
    10000: {
        0.625: 0.625,
        1.250: 0.638,
        2.500: 1.420,
        5.000: 2.700,
        7.500: 3.950,
        10.000: 10.000,
    },
}


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _interp(x, xp, fp):
    if x <= xp[0]:
        return fp[0]
    if x >= xp[-1]:
        return fp[-1]

    for i in range(1, len(xp)):
        if x <= xp[i]:
            x0, x1 = xp[i - 1], xp[i]
            y0, y1 = fp[i - 1], fp[i]
            if x1 == x0:
                return y0
            frac = (x - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)

    return fp[-1]


class SineWaveGenerator:
    def __init__(self, pi, debug=False):
        self._pi = pi
        self._frequency = MIN_FREQ
        self._amp_v = 0.0
        self._running = False
        self._wave_id = None
        self._debug = debug

        self._spi = pi.spi_open(SPI_CHANNEL, SPI_BAUD, 0)

        pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        pi.write(PWM_GPIO, 0)

    def _get_samples(self):
        f = self._frequency
        if f <= 1500:
            return 48
        if f <= 3000:
            return 32
        if f <= 6000:
            return 16
        return 8

    def _write_wiper0(self, step):
        step = int(_clamp(step, 0, MAX_WIPER_STEP))
        self._pi.spi_write(self._spi, bytes([CMD_WRITE_WIPER0, step]))

        if self._debug:
            print(f"[Digipot] Wiper 0 -> step {step}")

    def _snap_amplitude(self, amplitude_vpp):
        snapped = round(float(amplitude_vpp) / AMP_STEP) * AMP_STEP
        return _clamp(round(snapped, 3), 0.0, MAX_AMP)

    def _find_bracketing_freqs(self, freq):
        freqs = sorted(CAL_TABLES.keys())

        if freq <= freqs[0]:
            return freqs[0], freqs[0]
        if freq >= freqs[-1]:
            return freqs[-1], freqs[-1]

        for i in range(1, len(freqs)):
            if freq <= freqs[i]:
                return freqs[i - 1], freqs[i]

        return freqs[-1], freqs[-1]

    def _corrected_cmd_at_freq(self, target_amp, freq):
        table = CAL_TABLES[freq]
        targets = sorted(table.keys())
        corrected = [table[t] for t in targets]
        return _interp(target_amp, targets, corrected)

    def _target_to_corrected_cmd(self, target_amp):
        f0, f1 = self._find_bracketing_freqs(self._frequency)

        c0 = self._corrected_cmd_at_freq(target_amp, f0)
        c1 = self._corrected_cmd_at_freq(target_amp, f1)

        if f0 == f1:
            return c0

        frac = (self._frequency - f0) / (f1 - f0)
        return c0 + frac * (c1 - c0)

    def _amp_to_step(self, target_amp):
        target_amp = self._snap_amplitude(target_amp)
        corrected_cmd = self._target_to_corrected_cmd(target_amp)
        corrected_cmd = _clamp(corrected_cmd, 0.0, MAX_AMP)

        if self._debug:
            print(
                f"[Cal] freq={self._frequency}Hz "
                f"target={target_amp:.3f}Vpp "
                f"corrected_cmd={corrected_cmd:.3f}"
            )

        step = round((corrected_cmd / MAX_AMP) * MAX_WIPER_STEP)
        return int(_clamp(step, 0, MAX_WIPER_STEP))

    def _build_wave(self):
        n = self._get_samples()
        lut = [math.sin(2 * math.pi * i / n) for i in range(n)]

        period_us = 1_000_000.0 / self._frequency

        slot_list = []
        acc = 0.0
        used = 0

        for _ in range(n):
            acc += period_us / n
            slot = int(round(acc - used))
            if slot < 1:
                slot = 1
            slot_list.append(slot)
            used += slot

        target_total = int(round(period_us))
        error = target_total - sum(slot_list)
        slot_list[-1] += error

        if slot_list[-1] < 1:
            slot_list[-1] = 1

        on_mask = 1 << PWM_GPIO
        off_mask = 1 << PWM_GPIO
        pulses = []

        for sample, slot_us in zip(lut, slot_list):
            duty = _clamp(0.5 + 0.5 * sample, 0.0, 1.0)

            high_us = int(round(duty * slot_us))
            low_us = slot_us - high_us

            if high_us > 0:
                pulses.append(pigpio.pulse(on_mask, 0, high_us))
            if low_us > 0:
                pulses.append(pigpio.pulse(0, off_mask, low_us))

        self._pi.wave_tx_stop()

        if self._wave_id is not None:
            try:
                self._pi.wave_delete(self._wave_id)
            except pigpio.error:
                pass
            self._wave_id = None

        self._pi.wave_clear()
        self._pi.wave_add_generic(pulses)
        wave_id = self._pi.wave_create()

        if self._debug:
            actual_period = sum(slot_list)
            actual_freq = 1_000_000.0 / actual_period
            print(
                f"[SineWave] req={self._frequency}Hz "
                f"actual={actual_freq:.2f}Hz "
                f"N={n} period={actual_period}us pulses={len(pulses)} wave_id={wave_id}"
            )

        return wave_id

    def _apply(self):
        step = self._amp_to_step(self._amp_v)
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
                f"target_amp={self._amp_v:.3f}Vpp step={step}"
            )

    def set_frequency(self, frequency):
        snapped = round(int(frequency) / FREQ_STEP) * FREQ_STEP
        self._frequency = int(_clamp(snapped, MIN_FREQ, MAX_FREQ))

        if self._running:
            self._apply()

        if self._debug:
            print(f"[SineWave] frequency -> {self._frequency} Hz")

    def set_amplitude(self, amplitude_vpp):
        self._amp_v = self._snap_amplitude(amplitude_vpp)

        if self._running:
            self._apply()

        if self._debug:
            print(f"[SineWave] amplitude target -> {self._amp_v:.3f} Vpp")

    def start(self):
        self._running = True
        self._apply()

        if self._debug:
            print("[SineWave] started")

    def stop(self):
        self._pi.wave_tx_stop()
        self._pi.write(PWM_GPIO, 0)

        if self._wave_id is not None:
            try:
                self._pi.wave_delete(self._wave_id)
            except pigpio.error:
                pass
            self._wave_id = None

        self._pi.wave_clear()
        self._running = False

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
