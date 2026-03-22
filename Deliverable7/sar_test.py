"""
sar_test.py

Standalone test script for SAR ADC logic.

Make sure:
- pigpiod is running
- SPI is enabled
- SPI channel matches your wiring
"""

import pigpio
from ohms_steps import SPI_CHANNEL, SPI_SPEED, SPI_FLAGS
from sar_logic import SAR_ADC


# ===== Comparator GPIO pins =====
VOLTAGE_COMPARATOR_PIN = 18
CURRENT_COMPARATOR_PIN = 23


def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("Cannot connect to pigpio daemon.")
        print("Run: sudo pigpiod")
        return

    spi_handle = pi.spi_open(SPI_CHANNEL, SPI_SPEED, SPI_FLAGS)

    # ---- Voltage SAR object ----
    voltage_sar = SAR_ADC(
        pi=pi,
        spi_handle=spi_handle,
        comparator_pin=VOLTAGE_COMPARATOR_PIN,
        selected_pot=0,
        settle_time=0.003,
        invert_comparator=False,
        invert_dac=True,   # keep True since your digipot direction was reversed
        comparator_high_means_input_gt_dac=True,
    )

    # ---- Ohmmeter SAR object ----
    ohms_sar = SAR_ADC(
        pi=pi,
        spi_handle=spi_handle,
        comparator_pin=CURRENT_COMPARATOR_PIN,
        selected_pot=0,
        settle_time=0.003,
        invert_comparator=False,
        invert_dac=True,
        comparator_high_means_input_gt_dac=True,
    )

    try:
        # Voltage Test
        voltage, code_v = voltage_sar.read_voltage_bipolar(6.0)
        print(f"Voltage reading: {voltage:.3f} V | code = {code_v}")

        # Ohmmeter Test
        ohms, code_o = ohms_sar.read_ohms(vref=3.3, r_known=1000.0, apply_calibration=False)
        print(f"Ohms reading: {ohms:.3f} ohms | code = {code_o}")

    finally:
        pi.spi_close(spi_handle)
        pi.stop()


if __name__ == "__main__":
    main()
