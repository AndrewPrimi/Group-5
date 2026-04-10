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


def _write_dac(pi, spi_handle, step):
    """Scale 5-bit step (0..31) to MCP4131 7-bit register DAC (0..127)."""
    step = max(0, min(step, MCP4131_MAX_STEPS))
    dac_code = round(step * 127 / MCP4131_MAX_STEPS)
    pi.spi_write(spi_handle, [0x00, dac_code])


def _sar_measure(pi, spi_handle, comp_pin):
    """5-bit SAR: comp == 0 keeps bit, comp == 1 discards."""
    step = 0
    
    for bit_pos in range(4, -1, -1):
        """The trial is the step value plus the next significant bit."""
        trial = min(step | (1 << bit_pos), MCP4131_MAX_STEPS)
        _write_dac(pi, spi_handle, trial)
        time.sleep(_SETTLE_S)

        """The comp_pin read determines keep (0) or delete (1).""" 
        if pi.read(comp_pin) == 0:
            step = trial

    """Write the final step value to convert to analog.""" 
    _write_dac(pi, spi_handle, step)
    return step


def _averaged_measure(pi, spi_handle, comp_pin, n=11):
    """Return the median step from n SAR conversions."""
    readings = sorted(_sar_measure(pi, spi_handle, comp_pin) for _ in range(n))
    return readings[n // 2]


# Complete step -> actual voltage calibration (all 32 steps measured)
# Where multiple actual voltages map to the same step, midpoint is used.
STEP_TO_VOLT = [
    -4.88,  #  0: actual -5.00, -4.75
    -4.50,  #  1: actual -4.50
    -4.25,  #  2: actual -4.25
    -4.00,  #  3: actual -4.00
    -3.63,  #  4: actual -3.75, -3.50
    -3.25,  #  5: actual -3.25
    -2.88,  #  6: actual -3.00, -2.75
    -2.50,  #  7: actual -2.50
    -2.25,  #  8: actual -2.25
    -2.00,  #  9: actual -2.00
    -1.63,  # 10: actual -1.75, -1.50
    -1.25,  # 11: actual -1.25
    -1.00,  # 12: actual -1.00
    -0.75,  # 13: actual -0.75
    -0.50,  # 14: actual -0.50
    -0.13,  # 15: actual -0.25, 0.00
     0.19,  # 16: interpolated
     0.50,  # 17: actual 0.25, 0.50, 0.75
     1.00,  # 18: actual 1.00
     1.25,  # 19: actual 1.25
     1.50,  # 20: actual 1.50
     1.88,  # 21: actual 1.75, 2.00
     2.25,  # 22: actual 2.25
     2.50,  # 23: actual 2.50
     2.75,  # 24: actual 2.75
     3.13,  # 25: actual 3.00, 3.25
     3.50,  # 26: actual 3.50
     3.75,  # 27: actual 3.75
     4.13,  # 28: actual 4.00, 4.25
     4.50,  # 29: actual 4.50
     4.75,  # 30: actual 4.75
     5.00,  # 31: actual 5.00
]

V_MIN = -5.0
V_MAX = 5.0


SRC_EXTERNAL  = 0
SRC_INTERNAL  = 1
SRC_BACK      = 2
SRC_MAIN      = 3
SOURCE_LABELS = ["External", "Int. Reference", "Back", "Main"]
NUM_SOURCES   = len(SOURCE_LABELS)

_DEBOUNCE_US = 200_000


def step_to_voltage(step):
    """Convert SAR step to calibrated voltage via STEP_TO_VOLT lookup."""
    step = max(0, min(step, MCP4131_MAX_STEPS))
    return STEP_TO_VOLT[step]


def step_to_tolerance(step):
    """Tolerance based on voltage gap between neighboring steps."""
    step = max(0, min(step, MCP4131_MAX_STEPS))
    if step == 0:
        # use first 2 values of the lookup table
        return (STEP_TO_VOLT[1] - STEP_TO_VOLT[0]) / 2
    if step == MCP4131_MAX_STEPS:
        # use last 2 values of the lookup table
        return (STEP_TO_VOLT[-1] - STEP_TO_VOLT[-2]) / 2
    # use the surrounding 2 values of the step
    return (STEP_TO_VOLT[step + 1] - STEP_TO_VOLT[step - 1]) / 4


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
    tol = step_to_tolerance(step)

    if v <= V_MIN:
        line2 = f"{_fmt_v(V_MIN)} (at min)"
    elif v >= V_MAX:
        line2 = f"{_fmt_v(V_MAX)} (at max)"
    else:
        line2 = f"{_fmt_v(v)} +/-{tol:.2f}V"

    return "Voltmeter", f"Src: {source_label}", line2, "Btn: back"


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
            delta = state.get('encoder_delta', 0)
            if delta != 0:
                nav_idx = (nav_idx + delta) % len(nav_options)
                state['encoder_delta'] = 0
                _draw_nav()

            if state.get('button_pressed'):
                state['button_pressed'] = False
                return "BACK" if nav_idx == 0 else "MAIN"

            now = time.time()
            if now - last_update >= interval:
                last_update = now
                step = _averaged_measure(pi, adc_handle, COMPARATOR1_PIN, n=11)
                v = step_to_voltage(step)
                tol = step_to_tolerance(step)

                if v <= V_MIN:
                    lcd.put_line(1, f"{_fmt_v(V_MIN)} (at min)")
                elif v >= V_MAX:
                    lcd.put_line(1, f"{_fmt_v(V_MAX)} (at max)")
                else:
                    lcd.put_line(1, f"{_fmt_v(v)} +/-{tol:.2f}V")
                print(f"[Voltmeter] step={step}  voltage={v:+.2f} V  comp_now={pi.read(COMPARATOR1_PIN)}")

            time.sleep(0.05)
    finally:
        state['button_pressed'] = False
        clear_callbacks(state)
