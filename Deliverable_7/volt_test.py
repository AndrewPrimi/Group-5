"""
volt_test.py  –  Find the step that converges at a given Vin.

Run this with a known voltage (e.g. 0V, 1V, 2.5V) applied to the
comparator V+ input (the Vin wire going into the comparator).

Prints the converged step and the voltage the formula maps it to.
Press Ctrl+C to stop.
"""

import time
import pigpio
from ohmmeter import (
    COMPARATOR_PIN, ADC_SPI_CHANNEL, ADC_SPI_SPEED,
    ADC_SPI_FLAGS, MCP4131_MAX_STEPS, _SETTLE_S
)

# ── Formula constants (must match voltmeter.py) ───────────────────────────────
V_RANGE   =  10.0
N_LEVELS  =  MCP4131_MAX_STEPS + 1   # 32
ZERO_STEP =  2                        # step that reads 0V — update after calibration

def step_to_voltage(step):
    return V_RANGE * (step - ZERO_STEP) / N_LEVELS


def _write_dac(pi, spi, step):
    step = max(0, min(step, MCP4131_MAX_STEPS))
    pi.spi_write(spi, [0x00, round(step * 127 / MCP4131_MAX_STEPS)])


def sar_measure(pi, spi, comp_pin):
    step = 0
    for bit_pos in range(4, -1, -1):
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi, trial)
        time.sleep(_SETTLE_S)
        comp = pi.read(comp_pin)
        kept = comp == 0
        if kept:
            step = trial
        print(f"  bit {bit_pos}: trial={trial:2d}  comp={comp}  -> {'KEEP' if kept else 'DISCARD'}")
    _write_dac(pi, spi, step)
    return step


# ── Main ─────────────────────────────────────────────────────────────────────
pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("pigpiod not running — sudo pigpiod")

pi.set_pull_up_down(COMPARATOR_PIN, pigpio.PUD_UP)
spi = pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)

print(f"Comparator pin: GPIO {COMPARATOR_PIN}")
print(f"Measure voltage at: comparator V+ input (Vin wire)")
print("Apply your test voltage now. Press Ctrl+C to stop.\n")

try:
    reading = 1
    while True:
        print(f"── Reading {reading} ──────────────────────")
        step = sar_measure(pi, spi, COMPARATOR_PIN)
        voltage = step_to_voltage(step)
        print(f"  Converged step : {step}")
        print(f"  Formula voltage: {voltage:+.4f} V")
        print()
        reading += 1
        time.sleep(1)

except KeyboardInterrupt:
    print("\nDone.")

finally:
    pi.spi_close(spi)
    pi.stop()
