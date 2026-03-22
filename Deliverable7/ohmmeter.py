"""
ohmmeter.py

Wrapper helpers for ohmmeter operation.
"""

from sar_logic import SAR_ADC

OHMMETER_VREF = 3.3
R_KNOWN = 1000.0


def read_ohmmeter_value(sar: SAR_ADC, vref: float = OHMMETER_VREF, r_known: float = R_KNOWN):
    """
    Returns (resistance_ohms, code)
    """
    return sar.read_ohms(vref, r_known, apply_calibration=False)
