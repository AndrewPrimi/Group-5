#!/usr/bin/env python3

import spidev
import time

# =========================
# MCP4131 TEST CONFIG
# =========================
SPI_BUS = 0
SPI_DEVICE = 1       # GPIO7 = CE1
SPI_SPEED = 100000   # slower speed for reliable testing

# MCP4131 write command for pot 0
CMD_WRITE_WIPER0 = 0x00

def write_wiper(spi, value):
    """
    Write a value to the MCP4131 wiper.
    MCP4131 is 7-bit, so valid range is 0 to 127.
    """
    value = max(0, min(127, int(value)))
    spi.xfer2([CMD_WRITE_WIPER0, value])

def expected_voltage(value, vdd=3.3):
    """
    Returns expected wiper voltage if:
    P0A = GND
    P0B = 3.3V
    """
    return (value / 127.0) * vdd

def main():
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEVICE)
    spi.max_speed_hz = SPI_SPEED
    spi.mode = 0

    print("\n=== MCP4131 DIGIPOT TEST ===")
    print("Make sure wiring is:")
    print("Pin 1 (CS)  -> GPIO7 / CE1")
    print("Pin 2 (SCK) -> GPIO11 / SCLK")
    print("Pin 3 (SDI) -> GPIO10 / MOSI")
    print("Pin 4 (VSS) -> GND")
    print("Pin 5 (P0A) -> GND")
    print("Pin 6 (P0W) -> multimeter red probe")
    print("Pin 7 (P0B) -> 3.3V")
    print("Pin 8 (VDD) -> 3.3V")
    print("Multimeter black probe -> GND")
    print("Measure VOLTAGE, not resistance.\n")

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
