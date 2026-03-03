<<<<<<< HEAD
"""

ohmmeter.py 

This is a Python implementation of the ohmmeter.

"""

# ── Equation Constants ──────────────────────────────────
VREF = 5
BITS = 5

RKNOWN = 1000  # example code autoranging
=======
import pigpio
import time
import i2c_lcd


# Connect to the pigpio daemon 
pi = pigpio.pi()
if not pi.connected:
    exit()


class SApproxADConverter():

    def __init__(self, n_bits, ref_voltage):
        
        self.n_bits = n_bits
        self.bit_array = np.zeros(n_bits)
        self.ref_voltage = ref_voltage
>>>>>>> 862576e1712254cf99f905753b3f3a4efee007e1
