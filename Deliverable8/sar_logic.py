"""
sar_logic.py – Performs successive-approximation (SAR) logic.

This module estimates the value of Vin to the LM339 quad comparator.

SAR performs binary search over the step values until it reaches
the step closest to the actual Vin. 

"""

import time
import pigpio
from ohms_steps import MAX_STEPS, step_to_ohms

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

        self.pi.set_mode(self.compare_pin, 0)  # input

    # ── Write step value ─────────────────────────────────────────────

    def _write_step(self, step):
        step = max(0, min(MAX_STEPS - 1, step))
        cmd = 0x00 if self.selected_pot == 0 else 0x10
        self.pi.spi_write(self.spi_handle, [cmd, step])
        time.sleep(self.settle_time)

    # ── Read step value in binary search ─────────────────────────────

    def read_step(self):
        """
        Perform SAR search in step space.
        Returns the best step value.
        """
        low = 0
        high = MAX_STEPS - 1
        
        # Binary search algorithm
        while low <= high:
            mid = (low + high) // 2

            self._write_step(mid)
            time.sleep(self.settle_time)

            comp = self.pi.read(self.compare_pin)

            if self.invert:
                comp = 1 - comp

            # Assume Vdac > Vin, else Vdac <= Vin
            if comp == 1:
                high = mid - 1
            else:
                low = mid + 1

        return high        
        
    # ── Read comparator ──────────────────── 
    
    def _read_comparator(self):
        val = self.pi.read(self.compare_pin)
        
        if self.invert:
            val ^= 1
            
        return val

    
    # ── Voltmeter: Return Vin approximation or MAX_VOLTAGE  ────────────────────

    def read_voltage(self, Vref):
        """
        Perform SAR and return estimated Vin voltage.
        """
        step = self.read_step()
        # voltage is a fraction of Vref
        voltage = -Vref + (2 * Vref) * (step / MAX_STEPS)

        # voltage must be within the range [-6, 6] 
        if voltage > MAX_VOLTAGE:
            return MAX_VOLTAGE, step
        elif voltage < MIN_VOLTAGE:
            return MIN_VOLTAGE, step
        
        return voltage, step
    
    # ── Ohmmeter: Return resistance approximation ──────────────────────────────

    def read_ohms(self, Vref, R_known):
        """
        Perform SAR and return estimated R_unknown resistance.
        """
        Vin, step = self.read_voltage(Vref)

        if Vin <= 0 or Vin >= Vref:
            return None, step
        # The R_unknown R_known voltage divider formula
        R_unknown = R_known * Vin / (Vref - Vin)
        #R_unknown = 10000 - R_unknown
        return R_unknown, step
