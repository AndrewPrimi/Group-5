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

# Measured max Vpp going INTO the digipot
DIGIPOT_INPUT_MAX = 2.5

# Analog gain AFTER the digipot
POST_GAIN = 4.0


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


class SineWaveGenerator:
    def __init__(self, pi, debug=False):
        self._pi = pi
        self._frequency = MIN_FREQ
        self._amp = 0.0
        self._running = False
        self._wave_id = None
        self._debug = debug

        self._spi = pi.spi_open(SPI_CHANNEL, SPI_BAUD, 0)

        pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        pi.write(PWM_GPIO, 0)

    def _write_wiper(self, step):
        step = int(_clamp(step, 0, MAX_WIPER_STEP))
        self._pi.spi_write(self._spi, bytes([CMD_WRITE_WIPER0, step]))

        if self._debug:
            print(f"[Digipot] step = {step}")

    def _snap_amp(self, amp):
        snapped = round(float(amp) / AMP_STEP) * AMP_STEP
        return _clamp(round(snapped, 3), 0.0, MAX_AMP)

    def _amp_to_step(self, final_amp):
        """
        Convert desired FINAL amplitude to digipot step.

        final_amp = desired final output amplitude
        digipot_needed = final_amp / POST_GAIN
        step = 127 * digipot_needed / DIGIPOT_INPUT_MAX
        """
        final_amp = self._snap_amp(final_amp)

        digipot_needed = final_amp / POST_GAIN
        digipot_needed = _clamp(digipot_needed, 0.0, DIGIPOT_INPUT_MAX)

        step = round((digipot_needed / DIGIPOT_INPUT_MAX) * MAX_WIPER_STEP)
        return int(_clamp(step, 0, MAX_WIPER_STEP))

    def _build_wave(self):
        n = 64
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

            high_us = max(1, round(duty * slot_us))
            low_us = max(1, slot_us - high_us)

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
                f"N={n} period={actual_period}us pulses={len(pulses)} wave_id={wave_id}"
            )

        return wave_id

    def _apply(self):
        step = self._amp_to_step(self._amp)
        self._write_wiper(step)

        wave_id = self._build_wave()
        if wave_id < 0:
            print(f"[SineWave] wave_create failed (error {wave_id})")
            return

        self._pi.wave_send_repeat(wave_id)
        self._wave_id = wave_id

        if self._debug:
            digipot_out = DIGIPOT_INPUT_MAX * (step / MAX_WIPER_STEP)
            final_out = digipot_out * POST_GAIN
            print(
                f"[SineWave] target={self._amp:.3f}Vpp "
                f"step={step} "
                f"digipot≈{digipot_out:.3f}Vpp "
                f"final≈{final_out:.3f}Vpp"
            )

    def set_frequency(self, frequency):
        snapped = round(int(frequency) / FREQ_STEP) * FREQ_STEP
        self._frequency = int(_clamp(snapped, MIN_FREQ, MAX_FREQ))

        if self._running:
            self._apply()

        if self._debug:
            print(f"[SineWave] frequency -> {self._frequency} Hz")

    def set_amplitude(self, amp):
        self._amp = self._snap_amp(amp)

        if self._running:
            self._apply()

        if self._debug:
            print(f"[SineWave] amplitude target -> {self._amp:.3f} Vpp")

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
        return self._amp


if __name__ == "__main__":
    import time

    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    gen = SineWaveGenerator(pi, debug=True)

    gen.set_frequency(1000)
    gen.set_amplitude(10.0)
    gen.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    gen.cleanup()
    pi.stop()
