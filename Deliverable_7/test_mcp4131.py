#!/usr/bin/env python3

import spidev
import time

SPI_BUS = 0
SPI_DEVICE = 1      # GPIO7 = CE1
SPI_SPEED = 1000000

CMD_WRITE = 0x00

def write_wiper(spi, value):
    value = max(0, min(255, int(value)))
    spi.xfer2([CMD_WRITE, value])

def main():
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEVICE)
    spi.max_speed_hz = SPI_SPEED
    spi.mode = 0

    print("\n=== MCP4131 TEST START ===")
    print("Wiring for this test:")
    print("Pin 8 (VDD) -> 3.3V")
    print("Pin 4 (VSS) -> GND")
    print("Pin 5 (P0A) -> GND")
    print("Pin 7 (P0B) -> 3.3V")
    print("Pin 6 (P0W) -> multimeter red lead")
    print("Multimeter black lead -> GND")
    print("Measure VOLTAGE, not resistance\n")

    test_points = [0, 64, 128, 192, 255]

    try:
        for val in test_points:
            write_wiper(spi, val)
            expected = (val / 255.0) * 3.3
            print(f"Set wiper = {val:3d}   Expected ≈ {expected:.3f} V")
            time.sleep(4)

        print("\nSweeping continuously now. Press Ctrl+C to stop.\n")

        while True:
            for val in range(0, 256, 5):
                write_wiper(spi, val)
                time.sleep(0.05)

            for val in range(255, -1, -5):
                write_wiper(spi, val)
                time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopping test...")
        write_wiper(spi, 0)
        spi.close()
        print("Done.")

if __name__ == "__main__":
    main()
