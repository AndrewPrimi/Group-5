import math
import pigpio

PWM_GPIO = 12

MIN_FREQ = 1000
MAX_FREQ = 10_000
FREQ_STEP = 500

MAX_AMP  = 10.0
AMP_STEP = 0.625

SPI_CHANNEL = 0
SPI_BAUD    = 1_000_000

CMD_WRITE_WIPER0 = 0x00
CMD_WRITE_WIPER1 = 0x10

# A = PWM signal
# B = ground
# W = output
#
# With this wiring, larger desired amplitude should move the wiper
# closer to A, so the step mapping is reversed from the earlier version.
#
# Replace these calibration values with measured ones from your scope.
AMP_CAL_TABLE = {
    0.000: 127,
    0.625: 119,
    1.250: 111,
    1.875: 103,
    2.500: 95,
    3.125: 87,
    3.750: 79,
    4.375: 71,
    5.000: 63,
    5.625: 55,
    6.250: 47,
    6.875: 39,
    7.500: 31,
    8.125: 23,
    8.750: 15,
    9.375: 7,
    10.000: 6,
}


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


class SineWaveGenerator:
    def __init__(self, pi, debug=False):
        self._pi        = pi
        self._frequency = MIN_FREQ
        self._amp_v     = 0.0
        self._running   = False
        self._wave_id   = None
        self._debug     = debug

        self._spi = pi.spi_open(SPI_CHANNEL, SPI_BAUD, 0)

        pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        pi.write(PWM_GPIO, 0)

    def _get_samples(self):
        # Keep this fixed so waveform shape stays more consistent.
        return 64

    def _write_wiper0(self, step):
        step = int(_clamp(step, 0, 127))
        self._pi.spi_write(self._spi, bytes([CMD_WRITE_WIPER0, step]))

        if self._debug:
            print(f"[Digipot] Wiper 0 -> step {step}")

    def _snap_amplitude(self, amplitude_vpp):
        snapped = round(float(amplitude_vpp) / AMP_STEP) * AMP_STEP
        return _clamp(round(snapped, 3), 0.0, MAX_AMP)

    def _amp_to_step(self, amplitude_vpp):
        amplitude_vpp = self._snap_amplitude(amplitude_vpp)
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

                frac = (amplitude_vpp - x0) / (x1 - x0)
                step = y0 + frac * (y1 - y0)
                return int(round(step))

        return AMP_CAL_TABLE[keys[0]]

    def _build_wave(self):
        N = self._get_samples()
        lut = [math.sin(2 * math.pi * i / N) for i in range(N)]

        period_us = 1_000_000.0 / self._frequency

        slot_list = []
        acc = 0.0
        used = 0

        for _ in range(N):
            acc += period_us / N
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

        on_mask  = 1 << PWM_GPIO
        off_mask = 1 << PWM_GPIO
        pulses = []

        # Full-scale PWM waveform.
        # Let the digipot control amplitude in hardware.
        for sample, slot_us in zip(lut, slot_list):
            duty = _clamp(0.5 + 0.5 * sample, 0.0, 1.0)

            high_us = max(1, round(duty * slot_us))
            low_us  = max(1, slot_us - high_us)

            pulses.append(pigpio.pulse(on_mask, 0, high_us))
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
                f"N={N} period={actual_period}us pulses={len(pulses)} wave_id={wave_id}"
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
                f"amp={self._amp_v:.3f}Vpp step={step}"
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
            print(f"[SineWave] amplitude -> {self._amp_v:.3f} Vpp")

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
