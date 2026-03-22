"""
main.py

Simple combined test runner for voltmeter and ohmmeter.
"""

import time
import pigpio

from ohms_steps import SPI_CHANNEL, SPI_SPEED, SPI_FLAGS
from sar_logic import SAR_ADC
from voltmeter import read_voltmeter_value
from ohmmeter import read_ohmmeter_value


VOLTAGE_COMPARATOR_PIN = 18
CURRENT_COMPARATOR_PIN = 23


def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("Cannot connect to pigpio daemon.")
        print("Run: sudo pigpiod")
        return

    spi_handle = pi.spi_open(SPI_CHANNEL, SPI_SPEED, SPI_FLAGS)

    voltage_sar = SAR_ADC(
        pi=pi,
        spi_handle=spi_handle,
        comparator_pin=VOLTAGE_COMPARATOR_PIN,
        selected_pot=0,
        settle_time=0.003,
        invert_comparator=False,
        invert_dac=True,
    )

    ohms_sar = SAR_ADC(
        pi=pi,
        spi_handle=spi_handle,
        comparator_pin=CURRENT_COMPARATOR_PIN,
        selected_pot=0,
        settle_time=0.003,
        invert_comparator=False,
        invert_dac=True,
    )

    try:
        while True:
            print("\nChoose mode:")
            print("1 - Read voltmeter")
            print("2 - Read ohmmeter")
            print("3 - Read both")
            print("q - Quit")

            choice = input("> ").strip().lower()

            if choice == "1":
                voltage, code = read_voltmeter_value(voltage_sar)
                print(f"Voltage = {voltage:.3f} V | code = {code}")

            elif choice == "2":
                
                ohms, code = read_ohmmeter_value(ohms_sar, vref=3.3, r_known=1000.0)
                print(f"Resistance = {ohms:.3f} ohms | code = {code}")

            elif choice == "3":
                voltage, v_code = read_voltmeter_value(voltage_sar)

                
                ohms, o_code = read_ohmmeter_value(ohms_sar, vref=3.3, r_known=1000.0)

                print(f"Voltage    = {voltage:.3f} V | code = {v_code}")
                print(f"Resistance = {ohms:.3f} ohms | code = {o_code}")

            elif choice == "q":
                break

            else:
                print("Invalid choice.")

            time.sleep(0.2)

    finally:
        pi.spi_close(spi_handle)
        pi.stop()


if __name__ == "__main__":
    main()
