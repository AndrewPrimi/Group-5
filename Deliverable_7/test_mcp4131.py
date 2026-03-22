#!/usr/bin/env python3

import spidev
import time

SPI_BUS = 0
SPI_DEVICE = 1
SPI_SPEED = 100000

CMD_WRITE_WIPER0 = 0x00

def write_wiper(spi, value):
    value = max(0, min(127, int(value)))

    # Flip the direction
    actual_value = 127 - value

    spi.xfer2([CMD_WRITE_WIPER0, actual_value])

def expected_voltage(value, vdd=3.3):
    return (value / 127.0) * vdd

def main():
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEVICE)
    spi.max_speed_hz = SPI_SPEED
    spi.mode = 0

    print("\n=== MCP4131 DIGIPOT TEST (FLIPPED DIRECTION) ===")
    print("0 should now be near 0 V, and 127 should be near 3.3 V.\n")

    test_points = [0, 32, 64, 96, 127]

    try:
        print("Fixed-point test starting...\n")
        for val in test_points:
            write_wiper(spi, val)
            print(f"Wiper set to {val:3d} | Expected ≈ {expected_voltage(val):.3f} V")
            time.sleep(5)

        print("\nSweep test starting. Press Ctrl+C to stop.\n")

        while True:
            for val in range(0, 128):
                write_wiper(spi, val)
                time.sleep(0.03)

            for val in range(127, -1, -1):
                write_wiper(spi, val)
                time.sleep(0.03)

    except KeyboardInterrupt:
        print("\nStopping test...")
        write_wiper(spi, 0)

    finally:
        spi.close()
        print("SPI closed. Done.")

if __name__ == "__main__":
    main()
