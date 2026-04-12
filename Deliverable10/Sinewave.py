import math
import pigpio

PWM_GPIO = 26

MIN_FREQ = 1000
MAX_FREQ = 10_000
FREQ_STEP = 500

MAX_AMP  = 10.0
AMP_STEP = 0.625

SPI_CHANNEL = 0
SPI_BAUD    = 1_000_000

CMD_WRITE_WIPER0 = 0x00
CMD_WRITE_WIPER1 = 0x10


# Measured data you provided:
# (LCD request Vpp, actual measured output Vpp)
#
# This is used to invert the calibration so that when you request
# a target amplitude, the software picks the command value that most
# closely produces it on your current hardware.
MEASURED_POINTS = [
    (0.00, 0.00),
    (0.62, 0.68),
    (1.25, 1.05),
    (1.88, 1.45),
    (2.50, 1.85),
    (3.12, 2.25),
    (3.75, 2.65),
    (4.38, 3.10),
    (5.00, 3.50),
    (5.62, 3.90),
    (6.50, 4.22),
    (6.80, 4.74),
    (7.50, 5.11),
    (8.12, 5.39),
    (8.75, 5.87),
    (9.38, 6.09),
    (10.00, 6.50),
]


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _interp(x, xp, fp):
    """
    Simple linear interpolation.
    xp must be sorted ascending.
    """
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
        self._pi        = pi
        self._frequency = MIN_FREQ
        self._amp_v     = 0.0
        self._running   = False
        self._wave_id   = None
        self._debug     = debug

        self._spi = pi.spi_open(SPI_CHANNEL, SPI_BAUD, 0)

        pi.set_mode(PWM_GPIO, pigpio.OUTPUT)
        pi.write(PWM_GPIO, 0)

        # Build inverse calibration:
        # desired actual output -> needed LCD-equivalent command
        self._measured_cmds   = [p[0] for p in MEASURED_POINTS]
        self._measured_actual = [p[1] for p in MEASURED_POINTS]

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
        step = int(_clamp(step, 0, 127))
        self._pi.spi_write(self._spi, bytes([CMD_WRITE_WIPER0, step]))

        if self._debug:
            print(f"[Digipot] Wiper 0 -> step {step}")

    def _snap_amplitude(self, amplitude_vpp):
        snapped = round(float(amplitude_vpp) / AMP_STEP) * AMP_STEP
        return _clamp(round(snapped, 3), 0.0, MAX_AMP)

    def _amp_to_step(self, desired_actual_vpp):
        """
        Convert desired ACTUAL output amplitude to digipot step using your
        measured calibration data.

        Your measured data only reaches about 6.5 Vpp actual at a command
        of 10.0 Vpp, so requests above that will clamp to full scale.
        """
        desired_actual_vpp = self._snap_amplitude(desired_actual_vpp)

        # Invert the measured curve:
        # desired actual output -> command value that should produce it
        needed_cmd = _interp(
            desired_actual_vpp,
            self._measured_actual,
            self._measured_cmds
        )

        # Convert the command scale 0..10 to step scale 0..127
        step = round((needed_cmd / 10.0) * 127.0)
        step = int(_clamp(step, 0, 127))

        if self._debug:
            max_actual = self._measured_actual[-1]
            if desired_actual_vpp > max_actual:
                print(
                    f"[Cal] requested {desired_actual_vpp:.3f} Vpp, "
                    f"but measured hardware max is about {max_actual:.3f} Vpp. "
                    f"Clamping to full scale."
                )
            print(
                f"[Cal] target_actual={desired_actual_vpp:.3f} Vpp "
                f"-> cmd≈{needed_cmd:.3f} -> step={step}"
            )

        return step

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

        on_mask  = 1 << PWM_GPIO
        off_mask = 1 << PWM_GPIO
        pulses = []

        for sample, slot_us in zip(lut, slot_list):
            duty = _clamp(0.5 + 0.5 * sample, 0.0, 1.0)

            high_us = int(round(duty * slot_us))
            low_us  = slot_us - high_us

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
