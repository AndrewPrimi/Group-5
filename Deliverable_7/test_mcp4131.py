#!/usr/bin/env python3

import spidev
import time

# =========================
# MCP41X1 test configuration
# =========================
SPI_BUS = 0
SPI_DEVICE = 1      # CE1 usually = GPIO7
SPI_SPEED = 1000000 # 1 MHz is fine
DELAY = 2.0         # seconds between fixed test points

# MCP4131 command bytes
# Command format:
#   upper nibble = command
#   lower bits   = pot address bits
#
# Write data to pot 0 = 0x00, then send value byte
CMD_WRITE_POT0 = 0x00

def write_wiper(spi, value):
    """Write 7-bit/8-bit value to MCP41X1 wiper."""
    value = max(0, min(255, int(value)))
    spi.xfer2([CMD_WRITE_POT0, value])

def voltage_estimate(value, vdd=3.3):
    """Estimated output voltage if P0A=0V and P0B=VDD."""
    return (value / 255.0) * vdd

def main():
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_DEVICE)
    spi.max_speed_hz = SPI_SPEED
    spi.mode = 0

    print("\nMCP41X1 test starting")
    print(f"SPI bus={SPI_BUS}, device={SPI_DEVICE}, speed={SPI_SPEED}")
    print("Wire for this test:")
    print("  P0A -> GND")
    print("  P0B -> 3.3V")
    print("  Measure P0W to GND with a voltmeter\n")

    # Fixed-point test
    test_points = [0, 32, 64, 96, 128, 160, 192, 224, 255]

    print("Fixed-point test:")
    for val in test_points:
        write_wiper(spi, val)
        vout = voltage_estimate(val)
        print(f"  Wiper={val:3d}   Expected Vw ~ {vout:.3f} V")
        time.sleep(DELAY)

    print("\nSweep test starting. Press Ctrl+C to stop.\n")

    try:
        while True:
            for val in range(0, 256, 4):
                write_wiper(spi, val)
                print(f"Wiper={val:3d}   Expected Vw ~ {voltage_estimate(val):.3f} V", end="\r")
                time.sleep(0.05)

            for val in range(255, -1, -4):
                write_wiper(spi, val)
                print(f"Wiper={val:3d}   Expected Vw ~ {voltage_estimate(val):.3f} V", end="\r")
                time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n\nStopping test...")
        write_wiper(spi, 0)
        spi.close()
        print("Done. Wiper reset to 0.")

if __name__ == "__main__":
    main()
