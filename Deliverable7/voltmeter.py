import time
from ohms_steps import MAX_STEPS, step_to_ohms
from sar_logic import SAR_ADC

MAX_VOLTAGE = 6
MIN_VOLTAGE = -6

# GPIO output pins


 # ── Write step value ─────────────────────────────────────────────
 
 # ── Compare comparator outputs ────────────────────────────────────

 # IF Negative Comparator output is HIGH and Positive is LOW , then we increase the steps by of potentiometer one until we get a HIGH Output

 # IF Negative Comparator output is LOW and Positive is HIGH, then we do the same thing, except program checking for the output at the negative comparator gate.

 # IF they are both HIGH, then we can assume that our voltage is out of range from -5V - 5V, so we can default our read value to 0V.


pos_comparator = 0
neg_comparator = 0




