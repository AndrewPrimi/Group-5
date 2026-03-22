"""
voltmeter.py

Wrapper helpers for bipolar voltmeter operation.
"""

from sar_logic import SAR_ADC


FULL_SCALE_VOLTAGE = 6.0   # final displayed range: -6V to +6V


def read_voltmeter_value(sar: SAR_ADC):
    """
    Returns (voltage, code) for bipolar voltmeter mode.
    """
    return sar.read_voltage_bipolar(FULL_SCALE_VOLTAGE)


