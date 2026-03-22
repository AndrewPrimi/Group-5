"""
sar_logic.py – Performs successive-approximation (SAR) logic.
"""

import time
import pigpio
from ohms_steps import MAX_STEPS, MAX_CODE, step_to_ohms, fix_ohms


MAX_VOLTAGE = 6
MIN_VOLTAGE = -6


class SAR_ADC:
    def __init__(self, pi, spi_handle, comparator_pin,
                 selected_pot=0, settle_time=0.001,
                 invert_comparator=False,
                 invert_dac=True):
        """
        pi                 : pigpio instance
        spi_handle         : SPI handle
        comparator_pin     : GPIO connected to comparator
        selected_pot       : 0 or 1 (MCP4231 wiper)
        settle_time        : DAC settling delay (seconds)
        invert_comparator  : True if comparator logic reversed
        invert_dac         : True if code 0 gives high voltage and 127 gives low voltage
        """
        self.pi = pi
        self.spi_handle = spi_handle
        self.compare_pin = comparator_pin
        self.selected_pot = selected_pot
        self.settle_time = settle_time
        self.invert = invert_comparator
        self.invert_dac = invert_dac

        self.pi.set_mode(self.compare_pin, pigpio.INPUT)

    def _write_step(self, step):
        """
        Write digipot code 0..127.
        """
        step = max(0, min(MAX_CODE, int(step)))

        if self.invert_dac:
            actual_step = MAX_CODE - step
        else:
            actual_step = step

        cmd = 0x00 if self.selected_pot == 0 else 0x10
        self.pi.spi_write(self.spi_handle, bytes([cmd, actual_step]))
        time.sleep(self.settle_time)

    def _read_comparator(self):
        val = self.pi.read(self.compare_pin)
        if self.invert:
            val ^= 1
        return val

    def read_step(self):
        """
        Perform SAR search in step space.
        Returns best step value.
        """
        low = 0
        high = MAX_CODE

        while low <= high:
            mid = (low + high) // 2

            self._write_step(mid)
            time.sleep(self.settle_time)

            comp = self._read_comparator()

            # This matches your original assumption:
            # comp == 1 means DAC/reference is too high
            if comp == 1:
                high = mid - 1
            else:
                low = mid + 1

        return max(0, min(MAX_CODE, high))

    def read_voltage(self, Vref):
        """
        Unipolar read: return voltage from 0..Vref
        This is the one to use for the ohmmeter.
        """
        step = self.read_step()
        voltage = Vref * (step / MAX_CODE)
        return voltage, step

    def read_voltage_bipolar(self, Vref):
        """
        Bipolar read: return voltage from -Vref..+Vref
        Use this only if your voltmeter front-end is designed for it.
        """
        step = self.read_step()
        voltage = -Vref + (2 * Vref) * (step / MAX_CODE)

        if voltage > MAX_VOLTAGE:
            return MAX_VOLTAGE, step
        elif voltage < MIN_VOLTAGE:
            return MIN_VOLTAGE, step

        return voltage, step

    def read_ohms(self, Vref, R_known, apply_calibration=False):
        """
        Perform SAR and return estimated R_unknown resistance.
        Uses the divider:
            Vout = Vref * R_unknown / (R_known + R_unknown)
        so
            R_unknown = R_known * Vout / (Vref - Vout)
        """
        Vin, step = self.read_voltage(Vref)

        if Vin <= 0:
            return 0.0, step

        if Vin >= Vref:
            return float("inf"), step

        R_unknown = R_known * Vin / (Vref - Vin)

        if apply_calibration:
            R_unknown = fix_ohms(R_unknown)

        return R_unknown, step
