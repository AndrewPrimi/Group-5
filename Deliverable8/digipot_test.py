import time
import pigpio

SPI_CHANNEL = 0
SPI_SPEED = 50000
SPI_FLAGS = 0

# Try these first
CMD_W0 = 0x00
CMD_W1 = 0x10

MAX_WIPER = 127


def write_wiper(pi, spi, cmd, value):
    value = max(0, min(127, int(value)))
    pi.spi_write(spi, [cmd, value])
    time.sleep(0.05)
    print(f"sent cmd=0x{cmd:02X}, value={value}")


if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    spi = pi.spi_open(SPI_CHANNEL, SPI_SPEED, SPI_FLAGS)

    try:
        print("Testing W0 only...")
        for val in [0, 32, 64, 96, 127]:
            write_wiper(pi, spi, CMD_W0, val)
            time.sleep(3)

        print("Testing W1 only...")
        for val in [0, 32, 64, 96, 127]:
            write_wiper(pi, spi, CMD_W1, val)
            time.sleep(3)

    finally:
        pi.spi_close(spi)
        pi.stop()
