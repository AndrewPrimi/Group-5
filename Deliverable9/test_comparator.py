import time
import pigpio

ADC_SPI_CHANNEL   = 1
ADC_SPI_SPEED     = 50_000
ADC_SPI_FLAGS     = 0

COMPARATOR2_PIN   = 24
MCP4131_MAX_STEPS = 31
HOLD_TIME_S       = 2

def write_dac(pi, spi_handle, step):
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])
    return dac_code

def main():
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod not running. Run sudo pigpiod")

    pi.set_mode(COMPARATOR2_PIN, pigpio.INPUT)
    pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)

    spi_handle = pi.spi_open(ADC_SPI_CHANNEL, ADC_SPI_SPEED, ADC_SPI_FLAGS)

    try:
        for step in [0, 4, 8, 12, 16, 20, 24, 28, 31]:
            dac_code = write_dac(pi, spi_handle, step)
            time.sleep(0.2)
            comp = pi.read(COMPARATOR2_PIN)
            print(f"step={step:2d}   dac_code={dac_code:3d}   comp={comp}")
            time.sleep(HOLD_TIME_S)

    finally:
        pi.spi_close(spi_handle)
        pi.stop()

if __name__ == "__main__":
    main()
