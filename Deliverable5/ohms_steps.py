"""
ohms_steps.py – Constants and conversion helpers for the MCP4231 digital pot.

This version uses interpolation between your calibration points so you can ask
for values like 5010, 5020, 5030 ohms even if they are not explicitly listed
in the table.
"""

from bisect import bisect_left

# ── Potentiometer range ──────────────────────────────────
MINIMUM_OHMS = 100
MAXIMUM_OHMS = 10000

# 7-bit device: 128 total positions -> valid codes 0..127
MAX_STEPS = 128
MAX_CODE = 127

DEFAULT_OHMS = 5000

# ── Debounce ─────────────────────────────────────────────
BUTTON_DEBOUNCE_US = 200000

# ── Constant-resistance presets ──────────────────────────
CONSTANT_OHMS = [100, 1000, 5000, 10000]
CONSTANT_LABELS = ['100', '1k', '5k', '10k']

# ── SPI bus configuration for the MCP4231 ────────────────
SPI_CHANNEL = 0
SPI_SPEED = 50000
SPI_FLAGS = 0

# ------------------------------------------------------------------
# Calibration table
#
# key   = corrected/internal ohms to use before converting to step
# value = actual desired/output ohms
#
# Example:
#   4679.0 : 5000
# means:
#   if you want about 5000 ohms in reality, use 4679 "internal" ohms
#   for the step conversion
# ------------------------------------------------------------------
CAL_TABLE = {
    213.6: 100,
    288.4: 200,
    363.4: 300,
    517.0: 400,
    591.6: 500,
    663.0: 600,
    736.5: 700,
    875.2: 800,
    945.1: 900,
    1014.3: 1000,
    1158.9: 1100,
    1160.2: 1200,
    1233.7: 1300,
    1304.5: 1400,
    1447.1: 1500,
    1517.3: 1600,
    1588.1: 1700,
    1730.7: 1800,
    1806.3: 1900,
    1877.0: 2000,
    1947.8: 2100,
    2090.4: 2200,
    2161.1: 2300,
    2232.5: 2400,
    2380.1: 2500,
    2450.9: 2600,
    2522.2: 2700,
    2593.4: 2800,
    2738.8: 2900,
    2810.1: 3000,
    2881.3: 3100,
    2957.3: 3200,
    3099.4: 3300,
    3170.5: 3400,
    3243.5: 3500,
    3385.5: 3600,
    3456.6: 3700,
    3530.0: 3800,
    3600.7: 3900,
    3743.1: 4000,
    3820.1: 4100,
    3890.7: 4200,
    4022.1: 4300,
    4105.6: 4400,
    4176.2: 4500,
    4247.5: 4600,
    4390.2: 4700,
    4460.8: 4800,
    4532.0: 4900,
    4679.0: 5000,
    4749.5: 5100,
    4820.8: 5200,
    4891.9: 5300,
    5038.7: 5400,
    5109.9: 5500,
    5180.9: 5600,
    5256.5: 5700,
    5398.2: 5800,
    5469.2: 5900,
    5540.0: 6000,
    5681.6: 6100,
    5752.6: 6200,
    5826.0: 6300,
    5896.6: 6400,
    6038.6: 6500,
    6113.4: 6600,
    6183.8: 6700,
    6325.8: 6800,
    6400.7: 6900,
    6471.1: 7000,
    6542.2: 7100,
    6684.7: 7200,
    6755.2: 7300,
    6826.2: 7400,
    6971.6: 7500,
    7042.0: 7600,
    7113.0: 7700,
    7183.8: 7800,
    7325.7: 7900,
    7396.7: 8000,
    7467.5: 8100,
    7538.7: 8200,
    7680.0: 8300,
    7750.8: 8400,
    7825.5: 8500,
    7966.7: 8600,
    8037.4: 8700,
    8112.7: 8800,
    8183.9: 8900,
    8324.5: 9000,
    8397.6: 9100,
    8467.8: 9200,
    8609.3: 9300,
    8682.0: 9400,
    8752.2: 9500,
    8823.0: 9600,
    8968.1: 9700,
    9038.3: 9800,
    9109.1: 9900,
    9250.6: 10000,
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


# ------------------------------------------------------------------
# Precompute sorted lists for interpolation
# ------------------------------------------------------------------

# Sorted by ACTUAL desired ohms
"""_DESIRED_TO_CORRECTED = sorted((actual, corrected) for corrected, actual in CAL_TABLE.items())
DESIRED_VALUES = [pair[0] for pair in _DESIRED_TO_CORRECTED]
CORRECTED_FOR_DESIRED = [pair[1] for pair in _DESIRED_TO_CORRECTED]

# Sorted by CORRECTED/internal ohms
_CORRECTED_TO_DESIRED = sorted((corrected, actual) for corrected, actual in CAL_TABLE.items())
CORRECTED_VALUES = [pair[0] for pair in _CORRECTED_TO_DESIRED]
DESIRED_FOR_CORRECTED = [pair[1] for pair in _CORRECTED_TO_DESIRED]


def _clamp(value, low, high):
    return max(low, min(high, value))


def _interp(x, x0, y0, x1, y1):
    """Simple linear interpolation."""
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def _interp_from_sorted_lists(x, xs, ys):
    """
    Interpolate y from monotonic sorted xs and matching ys.
    Clamps outside the range.
    """
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]

    i = bisect_left(xs, x)

    x0, x1 = xs[i - 1], xs[i]
    y0, y1 = ys[i - 1], ys[i]

    return _interp(x, x0, y0, x1, y1)


# ------------------------------------------------------------------
# Main conversion helpers
# ------------------------------------------------------------------

def desired_ohms_to_corrected_ohms(desired_ohms):
    """
    Convert desired actual ohms -> corrected/internal ohms using interpolation.

    Example:
        desired 5000 -> about 4679
        desired 5010 -> interpolated between 5000 and 5100 points
    """
    desired_ohms = _clamp(float(desired_ohms), MINIMUM_OHMS, MAXIMUM_OHMS)
    return _interp_from_sorted_lists(desired_ohms, DESIRED_VALUES, CORRECTED_FOR_DESIRED)


def corrected_ohms_to_desired_ohms(corrected_ohms):
    """
    Convert corrected/internal ohms -> estimated actual ohms using interpolation.
    Useful for converting a step back to displayed ohms.
    """
    corrected_ohms = _clamp(float(corrected_ohms), CORRECTED_VALUES[0], CORRECTED_VALUES[-1])
    return _interp_from_sorted_lists(corrected_ohms, CORRECTED_VALUES, DESIRED_FOR_CORRECTED)


def ohms_to_step(desired_ohms):
    """
    Convert desired actual ohms to digipot step/code.

    Flow:
        desired actual ohms
          -> corrected/internal ohms via interpolation
          -> digipot code 0..127
    """
    corrected_ohms = desired_ohms_to_corrected_ohms(desired_ohms)
    code = round((corrected_ohms / MAXIMUM_OHMS) * MAX_CODE)
    return int(_clamp(code, 0, MAX_CODE))


def step_to_corrected_ohms(step):
    """
    Convert digipot step/code -> corrected/internal ohms.
    """
    step = int(_clamp(step, 0, MAX_CODE))
    return (step / MAX_CODE) * MAXIMUM_OHMS


def step_to_ohms(step):
    """
    Convert digipot step/code -> estimated actual ohms using interpolation.
    """
    corrected_ohms = step_to_corrected_ohms(step)
    return corrected_ohms_to_desired_ohms(corrected_ohms)


def generate_dense_lookup(start=100, stop=10000, increment=10):
    """
    Generate a dense lookup table:
        desired ohms -> corrected/internal ohms

    Example output entry:
        5010 : 4686.05
    """
    table = {}
    for desired in range(start, stop + 1, increment):
        table[desired] = desired_ohms_to_corrected_ohms(desired)
    return table


if __name__ == "__main__":
    # Example tests
    tests = [500, 1000, 2500, 5000, 5010, 5020, 7500, 9990]

    print("Desired -> Corrected -> Step -> Back to estimated actual\n")
    for ohms in tests:
        corrected = desired_ohms_to_corrected_ohms(ohms)
        step = ohms_to_step(ohms)
        back = step_to_ohms(step)

        print(
            f"desired={ohms:5.0f}  "
            f"corrected={corrected:8.2f}  "
            f"step={step:3d}  "
            f"estimated_actual={back:8.2f}"
        )"""

    # If you want a dense 10-ohm table:
    # dense = generate_dense_lookup()
    # print(dense[5000], dense[5010], dense[5020])
