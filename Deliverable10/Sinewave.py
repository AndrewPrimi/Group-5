import math
import pigpio

PWM_GPIO = 12

MIN_FREQ = 1000
MAX_FREQ = 10_000
FREQ_STEP = 500

# Project-required final output amplitude range
FINAL_MAX_AMP = 10.0

# Keep MAX_AMP so sine_ui.py can still import it
MAX_AMP = FINAL_MAX_AMP
AMP_STEP = 0.625

SPI_CHANNEL = 0
SPI_BAUD = 1_000_000

CMD_WRITE_WIPER0 = 0x00
CMD_WRITE_WIPER1 = 0x10

MAX_WIPER_STEP = 127

# Measured maximum signal going INTO the digipot
DIGIPOT_INPUT_MAX_VPP = 2.5

# Gain after the digipot
POST_DIGIPOT_GAIN = 4.0


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


class SineWaveGenerator:
    def __init__(self, pi, debug=False):
        self._pi = pi
        self._frequency = MIN_FREQ
        self._final_amp_vpp = 0.0
        self._running = False
        self._wave_id = None
        self._debug = debug

        self._spi = pi.spi_open(SPI_CHANNEL, SPI_BAUD, 0)

        pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        pi.write(PWM_GPIO, 0)

    def _get_samples(self):
        return 64

    def _write_wiper0(self, step):
        step = int(_clamp(step, 0, MAX_WIPER_STEP))
        self._pi.spi_write(self._spi, bytes([CMD_WRITE_WIPER0, step]))

        if self._debug:
            print(f"[Digipot] Wiper 0 -> step {step}")

    def _snap_amplitude(self, amplitude_vpp):
        snapped = round(float(amplitude_vpp) / AMP_STEP) * AMP_STEP
        return _clamp(round(snapped, 3), 0.0, FINAL_MAX_AMP)

    def _final_amp_to_digipot_step(self, requested_final_vpp):
        """
        Convert desired FINAL output amplitude to digipot step.

        Assumptions:
          digipot_output_vpp ~= DIGIPOT_INPUT_MAX_VPP * (step / 127)
          final_output_vpp   ~= digipot_output_vpp * POST_DIGIPOT_GAIN
        """
        requested_final_vpp = self._snap_amplitude(requested_final_vpp)

        if POST_DIGIPOT_GAIN <= 0 or DIGIPOT_INPUT_MAX_VPP <= 0:
            return 0

        needed_digipot_vpp = requested_final_vpp / POST_DIGIPOT_GAIN
        needed_digipot_vpp = _clamp(
            needed_digipot_vpp,
            0.0,
            DIGIPOT_INPUT_MAX_VPP
        )

        step = round(
            MAX_WIPER_STEP * (needed_digipot_vpp / DIGIPOT_INPUT_MAX_VPP)
        )
        return int(_clamp(step, 0, MAX_WIPER_STEP))

    def _build_wave(self):
        n_samples = self._get_samples()
        lut = [math.sin(2 * math.pi * i / n_samples) for i in range(n_samples)]

        period_us = 1_000_000.0 / self._frequency

        slot_list = []
        acc = 0.0
        used = 0

        for _ in range(n_samples):
            acc += period_us / n_samples
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
                f"N={n_samples} period={actual_period}us "
                f"pulses={len(pulses)} wave_id={wave_id}"
            )

        return wave_id

    def _apply(self):
        step = self._final_amp_to_digipot_step(self._final_amp_vpp)
        self._write_wiper0(step)

        wave_id = self._build_wave()
        if wave_id < 0:
            print(f"[SineWave] wave_create failed (error {wave_id})")
            return

        self._pi.wave_send_repeat(wave_id)
        self._wave_id = wave_id

        if self._debug:
            est_digipot_out = DIGIPOT_INPUT_MAX_VPP * (step / MAX_WIPER_STEP)
            est_final_out = est_digipot_out * POST_DIGIPOT_GAIN
            print(
                f"[SineWave] applied "
                f"freq={self._frequency}Hz "
                f"target_final={self._final_amp_vpp:.3f}Vpp "
                f"step={step} "
                f"est_digipot_out={est_digipot_out:.3f}Vpp "
                f"est_final_out={est_final_out:.3f}Vpp"
            )

    def set_frequency(self, frequency):
        snapped = round(int(frequency) / FREQ_STEP) * FREQ_STEP
        self._frequency = int(_clamp(snapped, MIN_FREQ, MAX_FREQ))

        if self._running:
            self._apply()

        if self._debug:
            print(f"[SineWave] frequency -> {self._frequency} Hz")

    def set_amplitude(self, amplitude_vpp):
        self._final_amp_vpp = self._snap_amplitude(amplitude_vpp)

        if self._running:
            self._apply()

        if self._debug:
            print(
                f"[SineWave] final amplitude target -> "
                f"{self._final_amp_vpp:.3f} Vpp"
            )

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
        return self._final_amp_vpp


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
