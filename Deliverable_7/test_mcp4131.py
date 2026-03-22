#!/usr/bin/env python3

import spidev
import time

# =========================
# CONFIG (CHANGE IF NEEDED)
# =========================
SPI_BUS = 0

# IMPORTANT:
# If CS → GPIO8 (CE0) → use 0
# If CS → GPIO7 (CE1) → use 1
SPI_DEVICE = 1  

SPI_SPEED = 1000000  # 1 MHz

# MCP4131 command to write wiper (pot0)
CMD_WRITE = 0x00

def write_wiper(spi, value):
    """Set digipot wiper (0–255)."""
    value = max(0, min(255, int(value)))
    spi.xfer2([CMD_WRITE, value])

def main():
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEVICE)
    spi.max_speed_hz = SPI_SPEED
    spi.mode = 0

    print("\n=== MCP4131 TEST START ===")
    print("Make sure:")
    print("P0A → GND")
    print("P0B → 3.3V")
    print("Measure P0W → GND (VOLTS, not ohms)\n")

    test_points = [0, 64, 128, 192, 255]

    try:
        for val in test_points:
            write_wiper(spi, val)

            expected = (val / 255.0) * 3.3

            print(f"\nSet wiper = {val}")
            print(f"Expected voltage ≈ {expected:.2f} V")
            print("→ Measure NOW")

            time.sleep(4)

        print("\nNow sweeping... watch voltage change smoothly\n")

        while True:
            for val in range(0, 256, 5):
                write_wiper(spi, val)
                time.sleep(0.05)

            for val in range(255, -1, -5):
                write_wiper(spi, val)
                time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopping... resetting to 0")
        write_wiper(spi, 0)
        spi.close()

if __name__ == "__main__":
    main()
