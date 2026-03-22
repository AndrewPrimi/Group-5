"""
ohms_steps.py – Constants and conversion helpers for the MCP4231 digital pot.

The MCP4231 is a 7-bit (128-step) SPI-controlled dual potentiometer.
This module defines the resistance range, step count, SPI bus settings,
preset values, and two functions that convert between ohms and step values.
"""

# ── Potentiometer range ──────────────────────────────────
MINIMUM_OHMS = 100        # lowest settable resistance (ohms)
MAXIMUM_OHMS = 10000      # full-scale resistance (ohms)
MAX_STEPS = 128           # 7-bit wiper: 0 to 128 inclusive
DEFAULT_OHMS = 5000       # starting resistance on page load

# ── Debounce ─────────────────────────────────────────────
BUTTON_DEBOUNCE_US = 200000    # 200 ms – ignore button presses within this window

# ── Constant-resistance presets ──────────────────────────
# Four quick-select values shown on the "Constant" page.
CONSTANT_OHMS = [100, 1000, 5000, 10000]
CONSTANT_LABELS = ['100', '1k', '5k', '10k']

# ── SPI bus configuration for the MCP4231 ────────────────
SPI_CHANNEL = 0       # CE1 chip-select line
SPI_SPEED = 50000     # 50 kHz clock (well within MCP4231's 10 MHz max)
SPI_FLAGS = 0         # default SPI mode 0,0


listOfOhms = {
    213.6 : 100,
    288.4 : 200,
    363.4 : 300,
    517 : 400,
    591.6 : 500,
    663 : 600,
    736.5 : 700,
    875.2 : 800,
    945.1 : 900,
    1014.3 : 1000,
    1158.9 : 1100,
    1160.2 : 1200,
    1233.7 : 1300,
    1304.5 : 1400,
    1447.1 : 1500,
    1517.3 : 1600,
    1588.1 : 1700,
    1730.7 : 1800,
    1806.3 : 1900,
    1877 : 2000,
    1947.8 : 2100,
    2090.4 : 2200,
    2161.1 : 2300,
    2232.5 : 2400,
    2380.1 : 2500,
    2450.9 : 2600,
    2522.2 : 2700,
    2593.4 : 2800,
    2738.8 : 2900,
    2810.1 : 3000,
    2881.3 : 3100,
    2957.3 : 3200,
    3099.4 : 3300,
    3170.5 : 3400,
    3243.5 : 3500,
    3385.5 : 3600,
    3456.6 : 3700,
    3530 : 3800,
    3600.7 : 3900,
    3743.1 : 4000,
    3820.1 : 4100,
    3890.7 : 4200,
    4022.1 : 4300,
    4105.6 : 4400,
    4176.2 : 4500,
    4247.5 : 4600,
    4390.2 : 4700,
    4460.8 : 4800,
    4532 : 4900,
    4679 : 5000,
    4749.5 : 5100,
    4820.8 : 5200,
    4891.9 : 5300,
    5038.7 : 5400,
    5109.9 : 5500,
    5180.9 : 5600,
    5256.5 : 5700,
    5398.2 : 5800,
    5469.2 : 5900,
    5540 : 6000,
    5681.6 : 6100,
    5752.6 : 6200,
    5826 : 6300,
    5896.6 : 6400,
    6038.6 : 6500,
    6113.4 : 6600,
    6183.8 : 6700,
    6325.8 : 6800,
    6400.7 : 6900,
    6471.1 : 7000,
    6542.2 : 7100,
    6684.7 : 7200,
    6755.2 : 7300,
    6826.2 : 7400,
    6971.6 : 7500,
    7042 : 7600,
    7113 : 7700,
    7183.8 : 7800,
    7325.7 : 7900,
    7396.7 : 8000,
    7467.5 : 8100,
    7538.7 : 8200,
    7680 : 8300,
    7750.8 : 8400,
    7825.5 : 8500,
    7966.7 : 8600,
    8037.4 : 8700,
    8112.7 : 8800,
    8183.9 : 8900,
    8324.5 : 9000,
    8397.6 : 9100,
    8467.8 : 9200,
    8609.3 : 9300,
    8682 : 9400,
    8752.2 : 9500,
    8823 : 9600,
    8968.1 : 9700,
    9038.3 : 9800,
    9109.1 : 9900,
    9250.6 : 10000
}    

'''
def ohms_to_step(ohms):
    """Convert a desired resistance (ohms) to a wiper step (0-128).

    Clamps the input to [0, MAXIMUM_OHMS] before converting so out-of-range
    values don't produce invalid steps.
    """
    
    step = int((ohms / MAXIMUM_OHMS) * MAX_STEPS)
    return step
'''

def ohms_to_step(ohms):
    """Convert desired resistance to best step using calibration."""

    # Clamp input
    ohms = max(MINIMUM_OHMS, min(MAXIMUM_OHMS, ohms))

    # Find closest available calibrated point
    closest = min(listOfOhms.keys(), key=lambda k: abs(k - ohms))

    # Convert that to step
    step = int((closest / MAXIMUM_OHMS) * MAX_STEPS)

    return step

'''
def step_to_ohms(step):
    """Convert a wiper step (0-128) back to an approximate resistance (ohms).

    This is the inverse of ohms_to_step (with minor rounding differences).
    """
    #raw_ohms = int((step / MAX_STEPS) * MAXIMUM_OHMS)
    #closest_key = min(listOfOhms.keys(), key=lambda k: abs(k - raw_ohms))
    #return listOfOhms[closest_key]
    return 0
'''


def step_to_ohms(step):
    """Convert step to approximate ohms using calibration."""

    # Convert step → ideal ohms
    ideal = (step / MAX_STEPS) * MAXIMUM_OHMS

    # Snap to nearest calibrated value
    closest = min(listOfOhms.keys(), key=lambda k: abs(k - ideal))

    return closest

if __name__ == "__main__":
    ohms = 9100
    x = ohms_to_step(ohms)
    print("Step: ", x)
    y = step_to_ohms(x)
    print("Back to Ohms: ", y)
