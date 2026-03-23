"""
sar_logic.py – Performs successive-approximation (SAR) logic.

This module estimates the value of Vin to the LM339 quad comparator.

SAR performs binary search over the step values until it reaches
the step closest to the actual Vin.
"""

import time
import pigpio
from ohms_steps import MAX_STEPS, MAX_STEP_INDEX, step_to_ohms

MAX_VOLTAGE = 6
MIN_VOLTAGE = -6


class SAR_ADC:
    def __init__(self, pi, spi_handle, comparator_pin,
                 selected_pot=0, settle_time=0.001,
                 invert_comparator=False):
        """
        pi                 : pigpio instance
        spi_handle         : SPI handle
        comparator_pin     : GPIO connected to comparator
        selected_pot       : 0 or 1 (MCP4231 wiper)
        settle_time        : DAC settling delay (seconds)
        invert_comparator  : True if comparator logic reversed
        """
        self.pi = pi
        self.spi_handle = spi_handle
        self.compare_pin = comparator_pin
        self.selected_pot = selected_pot
        self.settle_time = settle_time
        self.invert = invert_comparator

        self.pi.set_mode(self.compare_pin, pigpio.INPUT)

    def _write_step(self, step):
        step = max(0, min(MAX_STEP_INDEX, step))
        cmd = 0x00 if self.selected_pot == 0 else 0x10
        self.pi.spi_write(self.spi_handle, [cmd, step])
        time.sleep(self.settle_time)

    def read_step(self):
        """
        Perform SAR search in step space.
        Returns the best step value.
        """
        low = 0
        high = MAX_STEP_INDEX

        while low <= high:
            mid = (low + high) // 2

            self._write_step(mid)
            time.sleep(self.settle_time)

            comp = self.pi.read(self.compare_pin)

            if self.invert:
                comp = 1 - comp

            if comp == 1:
                high = mid - 1
            else:
                low = mid + 1

        return max(0, high)

    def _read_comparator(self):
        val = self.pi.read(self.compare_pin)
        if self.invert:
            val ^= 1
        return val

    def read_voltage(self, Vref):
        """
        Perform SAR and return estimated Vin voltage.
        """
        step = self.read_step()

        # Map 0..127 to -Vref..+Vref
        voltage = -Vref + (2 * Vref) * (step / MAX_STEP_INDEX)

        if voltage > MAX_VOLTAGE:
            return MAX_VOLTAGE, step
        elif voltage < MIN_VOLTAGE:
            return MIN_VOLTAGE, step

        return voltage, step

    def read_ohms(self, Vref, R_known):
        """
        Perform SAR and return estimated R_unknown resistance.
        """
        Vin, step = self.read_voltage(Vref)

        if Vin <= 0 or Vin >= Vref:
            return None, step

        R_unknown = R_known * Vin / (Vref - Vin)
        return R_unknown, step
