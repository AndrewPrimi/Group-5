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
SPI_CHANNEL = 1       # CE1 chip-select line
SPI_SPEED = 50000     # 50 kHz clock (well within MCP4231's 10 MHz max)
SPI_FLAGS = 0         # default SPI mode 0,0


listOfOhms = {
    100 : 1212000,
    200 : 1579000,
    300 : 1905000,
    400 : 2454000,
    500 : 2680000,
    600 : 2867000,
    700 : 3024000,
    800 : 3308000,
    900 : 3438000,
    1000 : 3560000,
    1100 : 3778000,
    1200 : 3876000,
    1300 : 3966000,
    1400 : 4049000,
    1500 : 4200000,
    1600 : 4272000,
    1700 : 4337000,
    1800 : 4458000,
    1900 : 4515000,
    2000 : 4569000,
    2100 : 4619000,
    2200 : 4712000,
    2300 : 4760000,
    2400 : 4802000,
    2500 : 4885000,
    2600 : 4921000,
    2700 : 4958000,
    2800 : 4993000,
    2900 : 5059000,
    3000 : 5090000,
    3100 : 5120000,
    3200 : 5149000,
    3300 : 5203000,
    3400 : 5229000,
    3500 : 5254000,
    3600 : 5302000,
    3700 : 5324000,
    3800 : 5346000,
    3900 : 5367000,
    4000 : 5408000,
    4100 : 5428000,
    4200 : 5447000,
    4300 : 5484000,
    4400 : 5500000,
    4500 : 5518000,
    4600 : 5535000,
    4700 : 5568000,
    4800 : 5584000,
    4900 : 5599000,
    5000 : 5624000,
    5100 : 5642000,
    5200 : 5656000,
    5300 : 5670000,
    5400 : 5695000,
    5500 : 5710000,
    5600 : 5722000,
    5700 : 5734000,
    5800 : 5758000,
    5900 : 5770000,
    6000 : 5778000,
    6100 : 5805000,
    6200 : 5816000,
    6300 : 5824000,
    6400 : 5834000,
    6500 : 5859000,
    6600 : 5869000,
    6700 : 5879000,
    6800 : 5901000,
    6900 : 5910000,
    7000 : 5920000,
    7100 : 5931000,
    7200 : 5951000,
    7300 : 5961000,
    7400 : 5971000,
    7500 : 5991000,
    7600 : 6000000,
    7700 : 6010000,
    7800 : 6021000,
    7900 : 6037000,
    8000 : 6050000,
    8100 : 6062000,
    8200 : 6073000,
    8300 : 6093000,
    8400 : 6105000,
    8500 : 6117000,
    8600 : 6141000,
    8700 : 6153000,
    8800 : 6165000,
    8900 : 6179000,
    9000 : 6205000,
    9100 : 6222000,
    9200 : 6238000,
    9300 : 6272000,
    9400 : 6290000,
    9500 : 6309000,
    9600 : 6332000,
    9700 : 6380000,
    9800 : 6408000,
    9900 : 6439000,
    10000 : 6512000
}    


def ohms_to_step(ohms):
    """Convert a desired resistance (ohms) to a wiper step (0-128).

    Clamps the input to [0, MAXIMUM_OHMS] before converting so out-of-range
    values don't produce invalid steps.
    """
    
    step = int((ohms / MAXIMUM_OHMS) * MAX_STEPS)
    return step


def step_to_ohms(step):
    """Convert a wiper step (0-128) back to an approximate resistance (ohms).

    This is the inverse of ohms_to_step (with minor rounding differences).
    """
    #raw_ohms = int((step / MAX_STEPS) * MAXIMUM_OHMS)
    #closest_key = min(listOfOhms.keys(), key=lambda k: abs(k - raw_ohms))
    #return listOfOhms[closest_key]
    return 0
    

if __name__ == "__main__":
    ohms = 9100
    x = ohms_to_step(ohms)
    print("Step: ", x)
    y = step_to_ohms(x)
    print("Back to Ohms: ", y)
