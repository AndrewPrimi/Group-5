"""
Measures frequency of a sine wave by repeatedly sampling through the
existing SAR ADC (CE1 / MCP4131 on GPIO 23), detecting threshold crossings,
and using linear interpolation for sub-sample timing accuracy.

Hardware (same as CheckpointB voltmeter):
  SPI CE1 -> MCP4131 DAC  (GPIO 7 chip-select)
  GPIO 23 -> LM339 comparator 1 output

Usage:
  pi      = pigpio.pi()
  spi_ce1 = pi.spi_open(1, 50_000, 0)
  freq, conf = measure_frequency(pi, spi_ce1)
  print(f"{freq:.1f} Hz")
"""

import time
import pigpio

from voltmeter import _sar_measure, COMPARATOR1_PIN, step_to_voltage
from ohmmeter  import MCP4131_MAX_STEPS

# Step 15 ~ -0.13V, step 16 ~ +0.19V, so this straddles 0V on the +-5V scale
THRESHOLD_STEP   = 15
DEFAULT_CROSSINGS = 8
TIMEOUT_S        = 5.0



def _single_sar(pi, spi_handle):
    step = _sar_measure(pi, spi_handle, COMPARATOR1_PIN)
    t    = time.monotonic()
    return step, t


def measure_frequency(pi, spi_handle, num_crossings=DEFAULT_CROSSINGS):
    """
    Detects rising-edge zero-crossings and computes frequency from the
    average period between them.

    Returns (frequency_hz, confidence) where confidence is 0.0-1.0.
    Returns (0.0, 0.0) on timeout or no signal.
    """
    crossing_times = []
    prev_step, prev_t = _single_sar(pi, spi_handle)
    deadline = time.monotonic() + TIMEOUT_S

    while len(crossing_times) < num_crossings:
        if time.monotonic() > deadline:
            print("[freq_meter_sw] Timeout - not enough crossings detected.")
            return 0.0, 0.0

        curr_step, curr_t = _single_sar(pi, spi_handle)

        # Rising edge: previous sample was below threshold, current is above
        if prev_step <= THRESHOLD_STEP < curr_step:
            # Linear interpolation to estimate the exact crossing time.
            # Instead of using curr_t directly, we estimate where between
            # prev_t and curr_t the threshold was actually crossed.
            # fraction = (threshold - prev) / (curr - prev)
            fraction = (THRESHOLD_STEP - prev_step) / (curr_step - prev_step)
            crossing_times.append(prev_t + fraction * (curr_t - prev_t))

        prev_step = curr_step
        prev_t    = curr_t

    periods = [
        crossing_times[i + 1] - crossing_times[i]
        for i in range(len(crossing_times) - 1)
    ]

    avg_period = sum(periods) / len(periods)
    if avg_period <= 0:
        return 0.0, 0.0

    frequency = 1.0 / avg_period

    # Coefficient of variation - lower means more consistent periods = better signal
    if len(periods) >= 2:
        variance   = sum((p - avg_period) ** 2 for p in periods) / len(periods)
        cv         = (variance ** 0.5) / avg_period
        confidence = max(0.0, 1.0 - cv * 10)
    else:
        confidence = 0.5

    return frequency, confidence


if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod not running - run 'sudo pigpiod' first.")

    pi.set_mode(COMPARATOR1_PIN, pigpio.INPUT)
    pi.set_pull_up_down(COMPARATOR1_PIN, pigpio.PUD_OFF)

    spi = pi.spi_open(1, 50_000, 0)

    print("Frequency Meter - Method 2 (Software Zero-Crossing)")
    print(f"Threshold: step {THRESHOLD_STEP} (~{step_to_voltage(THRESHOLD_STEP):.2f} V)")
    print()

    try:
        for trial in range(5):
            freq, conf = measure_frequency(pi, spi)
            if freq > 0:
                print(f"  [{trial+1}] {freq:8.1f} Hz   confidence={conf:.0%}")
            else:
                print(f"  [{trial+1}] measurement failed")
    finally:
        pi.spi_close(spi)
        pi.stop()
