"""
sar_logic.py

Successive-approximation logic for:
- voltmeter mode
- ohmmeter mode

This version is written for:
- pigpio SPI
- 7-bit MCP4231 / MCP4131 style DAC reference
- one comparator GPIO input

Assumptions:
- comparator output is digital
- DAC/reference range is 0..Vref
- for bipolar voltmeter mode, your analog front-end scales the input
  into 0..Vref, and we map it back afterward
"""

import time
import pigpio

from ohms_steps import MAX_CODE, clamp_code, fix_ohms


class SAR_ADC:
    def __init__(
        self,
        pi,
        spi_handle,
        comparator_pin,
        selected_pot=0,
        settle_time=0.003,
        invert_comparator=False,
        invert_dac=True,
        comparator_high_means_input_gt_dac=True,
    ):
        """
        pi: pigpio.pi() instance
        spi_handle: handle returned by pi.spi_open(...)
        comparator_pin: GPIO connected to comparator output
        selected_pot: 0 or 1 for MCP4231 dual pot
        settle_time: seconds to wait after each DAC update
        invert_comparator: flips comparator input logic if needed
        invert_dac: flips DAC direction if code 0 currently gives high voltage
        comparator_high_means_input_gt_dac:
            True  -> comparator HIGH means Vin > Vdac
            False -> comparator HIGH means Vin <= Vdac
        """
        self.pi = pi
        self.spi_handle = spi_handle
        self.compare_pin = comparator_pin
        self.selected_pot = selected_pot
        self.settle_time = settle_time
        self.invert_comparator = invert_comparator
        self.invert_dac = invert_dac
        self.comparator_high_means_input_gt_dac = comparator_high_means_input_gt_dac

        self.pi.set_mode(self.compare_pin, pigpio.INPUT)

    # =========================================================
    # Low-level DAC / comparator helpers
    # =========================================================

    def _build_command_byte(self) -> int:
        """
        MCP4231 volatile wiper write:
        pot 0 -> 0x00
        pot 1 -> 0x10
        """
        return 0x00 if self.selected_pot == 0 else 0x10

    def _write_code(self, code: int) -> None:
        """
        Write 0..127 to selected digital pot.
        """
        code = clamp_code(code)

        if self.invert_dac:
            actual_code = MAX_CODE - code
        else:
            actual_code = code

        cmd = self._build_command_byte()
        self.pi.spi_write(self.spi_handle, bytes([cmd, actual_code]))
        time.sleep(self.settle_time)

    def _read_comparator(self) -> int:
        """
        Read comparator GPIO and optionally invert its logic.
        """
        val = self.pi.read(self.compare_pin)
        if self.invert_comparator:
            val ^= 1
        return val

    # =========================================================
    # SAR core
    # =========================================================

    def read_code(self) -> int:
        """
        Perform a 7-bit SAR conversion.
        Returns best code in 0..127.
        """
        code = 0

        for bit in range(6, -1, -1):
            trial = code | (1 << bit)
            self._write_code(trial)

            comp = self._read_comparator()

            # If comparator HIGH means Vin > Vdac:
            # keep the bit when comparator is HIGH
            if self.comparator_high_means_input_gt_dac:
                if comp == 1:
                    code = trial
            else:
                # keep the bit when comparator is LOW
                if comp == 0:
                    code = trial

        return clamp_code(code)

    # =========================================================
    # Conversion helpers
    # =========================================================

    @staticmethod
    def code_to_voltage_unipolar(code: int, vref: float) -> float:
        """
        Map code 0..127 to 0..Vref
        """
        code = clamp_code(code)
        return (code / MAX_CODE) * vref

    @staticmethod
    def code_to_voltage_bipolar(code: int, full_scale_voltage: float) -> float:
        """
        Map code 0..127 to -full_scale_voltage .. +full_scale_voltage
        Example:
            full_scale_voltage = 6
            output range = -6V .. +6V
        """
        code = clamp_code(code)
        return -full_scale_voltage + (2.0 * full_scale_voltage * code / MAX_CODE)

    # =========================================================
    # Public measurement methods
    # =========================================================

    def read_voltage_unipolar(self, vref: float = 3.3):
        """
        Read a 0..Vref signal.
        Returns (voltage, code)
        """
        code = self.read_code()
        voltage = self.code_to_voltage_unipolar(code, vref)
        return voltage, code

    def read_voltage_bipolar(self, full_scale_voltage: float = 6.0):
        """
        Read a signal that your analog front-end has scaled such that:
        code 0   -> -full_scale_voltage
        code 127 -> +full_scale_voltage

        Returns (voltage, code)
        """
        code = self.read_code()
        voltage = self.code_to_voltage_bipolar(code, full_scale_voltage)
        return voltage, code

    def read_ohms(self, vref: float, r_known: float, apply_calibration: bool = False):
        """
        Use voltage divider formula:
            Vout = Vref * R_unknown / (R_known + R_unknown)

        Solve for R_unknown:
            R_unknown = R_known * Vout / (Vref - Vout)

        Returns (resistance_ohms, code)
        """
        vout, code = self.read_voltage_unipolar(vref)

        if vout <= 0:
            return 0.0, code

        if vout >= vref:
            return float("inf"), code

        r_unknown = r_known * vout / (vref - vout)

        if apply_calibration:
            r_unknown = fix_ohms(r_unknown)

        return r_unknown, code
