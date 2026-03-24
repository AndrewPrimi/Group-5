"""
voltmeter.py
SAR ADC voltmeter — measures DC voltage over approximately ±5 V and displays
the reading plus approximate tolerance on the 20×4 I2C LCD.

Hardware:
  Comparator 1 on LM339:
    pin 4 = inverting input  (DAC reference from TL081 output)
    pin 5 = non-inverting input (scaled voltmeter op-amp output)
    pin 2 = output -> GPIO 23
"""

import time
import pigpio

from ohmmeter import MCP4131_MAX_STEPS, _SETTLE_S
from callbacks import clear_callbacks, PIN_A, PIN_B, ROTARY_BTN_PIN
import rotary_encoder

COMPARATOR1_PIN = 23


# ── SAR measurement (voltmeter-specific) ─────────────────────────────────────

def _write_dac(pi, spi_handle, step):
    """
    Write 5-bit SAR step (0..31) to MCP4131 7-bit register (0..127).
    """
    step = max(0, min(step, MCP4131_MAX_STEPS))
    pi.spi_write(spi_handle, [0x00, round(step * 127 / MCP4131_MAX_STEPS)])


def _sar_measure(pi, spi_handle, comp_pin):
    """
    5-bit SAR conversion for voltmeter.

    Current working logic:
      comp == 0 -> keep bit
      comp == 1 -> discard bit
    """
    step = 0

    for bit_pos in range(4, -1, -1):
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        if pi.read(comp_pin) == 0:
            step = trial

    _write_dac(pi, spi_handle, step)
    return step


def _averaged_measure(pi, spi_handle, comp_pin, n=11):
    """Return the median step from n SAR conversions."""
    readings = sorted(_sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


# ── Calibration data ──────────────────────────────────────────────────────────
# Based on your measured behavior:
#
# actual input -> displayed by old code
#  5.0 ->  5.00
#  4.5 ->  4.33
#  4.0 ->  3.67
#  3.5 ->  3.33
#  3.0 ->  2.75
#  2.5 ->  2.25
#  2.0 ->  2.00
#  1.5 ->  1.33
#  1.0 ->  0.67
#  0.5 ->  0.33
#  0.0 -> -0.33
# -0.5 -> -1.00
# -1.0 -> -1.33
# -1.5 -> -2.00
# -2.0 -> -2.50
# -2.5 -> -3.00
# -3.0 -> -3.33
# -3.5 -> -4.00
# -4.0 -> -5.00
#
# We invert that mapping here:
# old_displayed_value -> actual_value
CAL_POINTS = [
    (-5.00, -5.00),
    (-4.00, -3.50),
    (-3.33, -3.00),
    (-3.00, -2.50),
    (-2.50, -2.00),
    (-2.00, -1.50),
    (-1.33, -1.00),
    (-1.00, -0.50),
    (-0.33,  0.00),
    ( 0.33,  0.50),
    ( 0.67,  1.00),
    ( 1.33,  1.50),
    ( 2.00,  2.00),
    ( 2.25,  2.50),
    ( 2.75,  3.00),
    ( 3.33,  3.50),
    ( 3.67,  4.00),
    ( 4.33,  4.50),
    ( 5.00,  5.00),
]

V_MIN = -5.0
V_MAX = 5.0
VOLT_TOL_V = 0.15  # tighter displayed tolerance after calibration


# ── Source menu ───────────────────────────────────────────────────────────────
SRC_EXTERNAL  = 0
SRC_INTERNAL  = 1
SRC_BACK      = 2
SRC_MAIN      = 3
SOURCE_LABELS = ["External", "Int. Reference", "Back", "Main"]
NUM_SOURCES   = len(SOURCE_LABELS)

_DEBOUNCE_US = 200_000


# ── Conversion helpers ────────────────────────────────────────────────────────

def _interp(x, x0, y0, x1, y1):
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def _old_step_to_voltage(step):
    """
    The old step-to-voltage mapping that produced the readings you gave.
    This is kept only as an intermediate before calibration correction.
    """
    # Previous calibration table that roughly matched your old displayed values
    old_points = [
        (0,  -5.00),
        (2,  -4.00),
        (5,  -3.00),
        (9,  -2.00),
        (12, -1.00),
        (15,  0.00),
        (18,  1.00),
        (21,  2.00),
        (25,  3.00),
        (28,  4.00),
        (31,  5.00),
    ]

    step = max(0, min(step, MCP4131_MAX_STEPS))

    if step <= old_points[0][0]:
        return old_points[0][1]

    if step >= old_points[-1][0]:
        return old_points[-1][1]

    for (s0, v0), (s1, v1) in zip(old_points, old_points[1:]):
        if s0 <= step <= s1:
            return _interp(step, s0, v0, s1, v1)

    return 0.0


def step_to_voltage(step):
    """
    Convert SAR step to corrected voltage.

    Flow:
      step -> old displayed voltage estimate -> calibrated actual voltage
    """
    raw_v = _old_step_to_voltage(step)

    if raw_v <= CAL_POINTS[0][0]:
        return CAL_POINTS[0][1]

    if raw_v >= CAL_POINTS[-1][0]:
        return CAL_POINTS[-1][1]

    for (x0, y0), (x1, y1) in zip(CAL_POINTS, CAL_POINTS[1:]):
        if x0 <= raw_v <= x1:
            return _interp(raw_v, x0, y0, x1, y1)

    return raw_v


# ── Display helpers ───────────────────────────────────────────────────────────

def _fmt_v(v):
    return f"{v:+.2f}V"


def build_source_menu_lines(selection):
    window = max(0, min(selection - 1, NUM_SOURCES - 3))
    rows = ["Voltmeter"]
    for i in range(3):
        idx = window + i
        if idx < NUM_SOURCES:
            prefix = "> " if idx == selection else "  "
            rows.append(prefix + SOURCE_LABELS[idx])
        else:
            rows.append("")
    return tuple(rows)


def build_measurement_lines(step, source_label="External"):
    v = step_to_voltage(step)

    if v <= V_MIN:
        line2 = f"{_fmt_v(V_MIN)} (at min)"
    elif v >= V_MAX:
        line2 = f"{_fmt_v(V_MAX)} (at max)"
    else:
        line2 = f"{_fmt_v(v)} +/-{VOLT_TOL_V:.2f}V"

    return "Voltmeter", f"Src: {source_label}", line2, "Btn: back"


# ── Page runners ──────────────────────────────────────────────────────────────

def run_source_menu(state, pi, lcd):
    state['volt_source_sel']  = SRC_EXTERNAL
    state['volt_source_done'] = False
    state['button_last_tick'] = None
    clear_callbacks(state)

    def _on_rotate(direction):
        state['volt_source_sel'] = (state['volt_source_sel'] + direction) % NUM_SOURCES
        _redraw()

    def _on_button(_gpio, level, tick):
        if level != 0:
            return
        last = state.get('button_last_tick')
        if last is not None and pigpio.tickDiff(last, tick) < _DEBOUNCE_US:
            return
        state['button_last_tick'] = tick
        state['volt_source_done'] = True

    def _redraw():
        for row, text in enumerate(build_source_menu_lines(state['volt_source_sel'])):
            lcd.put_line(row, text)

    _redraw()

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, _on_rotate)
    cb_btn  = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
    state['active_callbacks'] = [decoder, cb_btn]

    while not state['volt_source_done']:
        time.sleep(0.05)

    clear_callbacks(state)
    return state['volt_source_sel']


def run_measurement(state, pi, lcd, adc_handle,
                    source_label="External", interval=0.5):
    """Live voltage reading with Back/Main on the same screen."""
    state['encoder_delta'] = 0
    state['button_pressed'] = False
    state['button_last_tick'] = None
    clear_callbacks(state)

    nav_options = ["Back", "Main"]
    nav_idx = 0

    def _on_rotate(direction):
        state['encoder_delta'] = state.get('encoder_delta', 0) - direction

    def _on_button(_gpio, level, tick):
        if level != 0:
            return
        last = state.get('button_last_tick')
        if last is not None and pigpio.tickDiff(last, tick) < _DEBOUNCE_US:
            return
        state['button_last_tick'] = tick
        state['button_pressed'] = True

    def _draw_nav():
        if nav_idx == 0:
            lcd.put_line(2, ">Back")
            lcd.put_line(3, " Main")
        else:
            lcd.put_line(2, " Back")
            lcd.put_line(3, ">Main")

    lcd.put_line(0, "Voltmeter")
    lcd.put_line(1, "Measuring...")
    _draw_nav()

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, _on_rotate)
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
    state['active_callbacks'] = [decoder, cb_btn]

    last_update = 0.0
    try:
        while True:
            # Handle encoder navigation between Back/Main
            delta = state.get('encoder_delta', 0)
            if delta != 0:
                nav_idx = (nav_idx + delta) % len(nav_options)
                state['encoder_delta'] = 0
                _draw_nav()

            # Handle button press
            if state.get('button_pressed'):
                state['button_pressed'] = False
                return "BACK" if nav_idx == 0 else "MAIN"

            # Live measurement update
            now = time.time()
            if now - last_update >= interval:
                last_update = now
                step = _averaged_measure(pi, adc_handle, COMPARATOR1_PIN, n=11)
                v = step_to_voltage(step)

                if v <= V_MIN:
                    lcd.put_line(1, f"{_fmt_v(V_MIN)} (at min)")
                elif v >= V_MAX:
                    lcd.put_line(1, f"{_fmt_v(V_MAX)} (at max)")
                else:
                    lcd.put_line(1, f"{_fmt_v(v)} +/-{VOLT_TOL_V:.2f}V")
                print(f"[Voltmeter] step={step}  voltage={v:+.2f} V  comp_now={pi.read(COMPARATOR1_PIN)}")

            time.sleep(0.05)
    finally:
        state['button_pressed'] = False
        clear_callbacks(state)
