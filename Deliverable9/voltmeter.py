"""
voltmeter.py
SAR ADC voltmeter — measures DC voltage over ±5 V and displays
the reading plus approximate tolerance on the 20×4 I2C LCD.

Hardware:
  Comparator 1 on LM339:
    Pin 4 = inverting input  (DAC reference from TL081 output)
    Pin 5 = non-inverting input (scaled voltmeter op-amp output)
    Pin 2 = output -> GPIO 23
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

    Comparator behavior used here:
      GPIO LOW  (0) -> Vin_scaled < DAC -> DAC too high -> DISCARD bit
      GPIO HIGH (1) -> Vin_scaled > DAC -> DAC too low  -> KEEP bit
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


# ── Voltage range / calibration ───────────────────────────────────────────────
V_MAX = 5.0
V_MIN = -5.0

# Calibration points from your measured behavior can be adjusted later if needed
CAL_POINTS = [
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

VOLT_TOL_V = 0.35


# ── Source menu ───────────────────────────────────────────────────────────────
SRC_EXTERNAL  = 0
SRC_INTERNAL  = 1
SRC_BACK      = 2
SRC_MAIN      = 3
SOURCE_LABELS = ["External", "Int. Reference", "Back", "Main"]
NUM_SOURCES   = len(SOURCE_LABELS)

_DEBOUNCE_US = 200_000


# ── Conversion maths ──────────────────────────────────────────────────────────

def step_to_voltage(step):
    """
    Convert a 5-bit SAR step (0–31) to voltage using piecewise-linear
    interpolation through measured calibration points.
    """
    step = max(0, min(step, MCP4131_MAX_STEPS))

    if step <= CAL_POINTS[0][0]:
        return CAL_POINTS[0][1]

    if step >= CAL_POINTS[-1][0]:
        return CAL_POINTS[-1][1]

    for (s0, v0), (s1, v1) in zip(CAL_POINTS, CAL_POINTS[1:]):
        if s0 <= step <= s1:
            if s1 == s0:
                return v0
            frac = (step - s0) / (s1 - s0)
            return v0 + frac * (v1 - v0)

    return 0.0


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

    if step <= 0:
        line2 = f"{_fmt_v(V_MIN)} (at min)"
    elif step >= MCP4131_MAX_STEPS:
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
    state['volt_meas_active'] = True
    state['button_last_tick'] = None
    clear_callbacks(state)

    def _on_button(_gpio, level, tick):
        if level != 0:
            return
        last = state.get('button_last_tick')
        if last is not None and pigpio.tickDiff(last, tick) < _DEBOUNCE_US:
            return
        state['button_last_tick'] = tick
        state['volt_meas_active'] = False

    lcd.put_line(0, "Voltmeter")
    lcd.put_line(1, f"Src: {source_label}")
    lcd.put_line(2, "Measuring...")
    lcd.put_line(3, "Btn: back")

    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
    state['active_callbacks'] = [cb_btn]

    last_update = 0.0
    while state['volt_meas_active']:
        now = time.time()
        if now - last_update >= interval:
            last_update = now
            step = _averaged_measure(pi, adc_handle, COMPARATOR1_PIN, n=11)
            l0, l1, l2, l3 = build_measurement_lines(step, source_label)
            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)
            print(f"[Voltmeter] step={step}  {l2.strip()}")
        time.sleep(0.05)

    clear_callbacks(state)
