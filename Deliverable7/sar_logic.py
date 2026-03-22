"""
sar_logic.py
Performs successive-approximation (SAR) logic for voltmeter and ohmmeter.
"""

import time
import pigpio

print("USING sar_logic.py FROM:", __file__)

MAX_CODE = 127  # 7-bit digipot: 0..127


class SAR_ADC:
    def __init__(self, pi, spi_handle, comparator_pin,
                 selected_pot=0, settle_time=0.003,
                 invert_comparator=False,
                 invert_dac=True):
        self.pi = pi
        self.spi_handle = spi_handle
        self.compare_pin = comparator_pin
        self.selected_pot = selected_pot
        self.settle_time = settle_time
        self.invert_comparator = invert_comparator
        self.invert_dac = invert_dac

        self.pi.set_mode(self.compare_pin, pigpio.INPUT)

    def _write_step(self, step):
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
        if self.invert_comparator:
            val ^= 1
        return val

    def read_step(self):
        low = 0
        high = MAX_CODE

        while low <= high:
            mid = (low + high) // 2
            self._write_step(mid)
            time.sleep(self.settle_time)

            comp = self._read_comparator()

            # comp == 1 means DAC/reference is too high
            if comp == 1:
                high = mid - 1
            else:
                low = mid + 1

        return max(0, min(MAX_CODE, high))

    def read_voltage(self, Vref):
        step = self.read_step()
        voltage = Vref * (step / MAX_CODE)
        print(f"[DEBUG] read_voltage -> step={step}, Vref={Vref}, voltage={voltage:.6f}")
        return voltage, step

    def read_voltage_bipolar(self, full_scale_voltage):
        step = self.read_step()
        voltage = -full_scale_voltage + (2.0 * full_scale_voltage * step / MAX_CODE)
        print(f"[DEBUG] read_voltage_bipolar -> step={step}, full_scale={full_scale_voltage}, voltage={voltage:.6f}")
        return voltage, step

    def read_ohms(self, Vref, R_known):
        Vin, step = self.read_voltage(Vref)

        if Vin <= 0:
            print("[DEBUG] read_ohms -> Vin <= 0, returning 0.0")
            return 0.0, step

        if Vin >= Vref:
            print("[DEBUG] read_ohms -> Vin >= Vref, returning inf")
            return float("inf"), step

        R_unknown_raw = R_known * Vin / (Vref - Vin)
        R_unknown = 2.0 * R_unknown_raw

        print(
            f"[DEBUG] read_ohms -> step={step}, Vin={Vin:.6f}, "
            f"R_known={R_known}, raw={R_unknown_raw:.6f}, corrected={R_unknown:.6f}"
        )

        return R_unknown, step
