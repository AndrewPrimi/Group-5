"""
sar_logic.py – Performs successive-approximation (SAR) logic.
"""

import time
import pigpio

MAX_CODE = 127   # 7-bit digipot (0–127)


class SAR_ADC:
    def __init__(self, pi, spi_handle, comparator_pin,
                 selected_pot=0, settle_time=0.002,
                 invert_comparator=False,
                 invert_dac=True):
        self.pi = pi
        self.spi_handle = spi_handle
        self.compare_pin = comparator_pin
        self.selected_pot = selected_pot
        self.settle_time = settle_time
        self.invert = invert_comparator
        self.invert_dac = invert_dac

        self.pi.set_mode(self.compare_pin, pigpio.INPUT)

    # ================================
    # Write to digipot
    # ================================
    def _write_step(self, step):
        step = max(0, min(MAX_CODE, int(step)))

        # Flip direction if needed
        if self.invert_dac:
            step = MAX_CODE - step

        cmd = 0x00 if self.selected_pot == 0 else 0x10
        self.pi.spi_write(self.spi_handle, bytes([cmd, step]))

        time.sleep(self.settle_time)

    # ================================
    # Read comparator
    # ================================
    def _read_comparator(self):
        val = self.pi.read(self.compare_pin)

        if self.invert:
            val ^= 1

        return val

    # ================================
    # SAR binary search
    # ================================
    def read_step(self):
        low = 0
        high = MAX_CODE

        while low <= high:
            mid = (low + high) // 2

            self._write_step(mid)
            time.sleep(self.settle_time)

            comp = self._read_comparator()

            # comparator HIGH = DAC too high
            if comp == 1:
                high = mid - 1
            else:
                low = mid + 1

        return max(0, min(MAX_CODE, high))

    # ================================
    # Voltage (0 to Vref)
    # ================================
    def read_voltage(self, Vref):
        step = self.read_step()
        voltage = Vref * (step / MAX_CODE)
        return voltage, step

    # ================================
    # Ohmmeter
    # ================================
    def read_ohms(self, Vref, R_known):
        Vin, step = self.read_voltage(Vref)

        if Vin <= 0:
            return 0.0, step

        if Vin >= Vref:
            return float("inf"), step

        # Divider formula
        R_unknown = R_known * Vin / (Vref - Vin)

        # Scale correction (your system was halving values)
        R_unknown = R_unknown * 2.0

        return R_unknown, step
