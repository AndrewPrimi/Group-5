"""
test_digipot.py

Tests the MCP4131 digipot on CE1 by writing fixed step values
and printing the comparator state.

Measure the wiper voltage with a multimeter while this runs.

Expected:
- step changes from 0 to 31
- wiper voltage should move steadily from one end to the other
- comparator output may flip at some point depending on the input voltage
"""

import time
import pigpio

ADC_SPI_CHANNEL   = 1
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR2_PIN   = 24
MCP4131_MAX_STEPS = 31

HOLD_TIME_S = 5


def write_dac(pi, spi_handle, step):
    """
    Write a 5-bit logical step (0..31) to the 7-bit MCP4131 (0..127).
    This is the original direction, not flipped.
    """
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])
    return dac_code


def main():
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod not running. Run: sudo pigpiod")

    pi.set_mode(COMPARATOR2_PIN, pigpio.INPUT)
    pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)

    spi_handle = pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)

    print("Starting digipot test")
    print("Measure the wiper voltage to ground")
    print("")

    try:
        test_steps = [0, 4, 8, 12, 16, 20, 24, 28, 31]

        while True:
            for step in test_steps:
                dac_code = write_dac(pi, spi_handle, step)
                comp = pi.read(COMPARATOR2_PIN)

                print(
                    f"step={step:2d}   "
                    f"dac_code={dac_code:3d}   "
                    f"comparator={comp}"
                )
                print(f"Hold this for {HOLD_TIME_S} seconds and measure the wiper.")
                print("")

                time.sleep(HOLD_TIME_S)

    except KeyboardInterrupt:
        print("\nStopping test.")

    finally:
        pi.spi_close(spi_handle)
        pi.stop()


if __name__ == "__main__":
    main()
