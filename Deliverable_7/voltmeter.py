"""
voltmeter.py
SAR ADC voltmeter — measures DC voltage over ±5 V and displays
the reading plus approximate tolerance on the 20×4 I2C LCD.

Hardware:
  SPI CE1  → MCP4131 (P0A = 3.3 V, P0B = GND, P0W = DAC out)
  Op-amp 1 buffers digipot wiper (0–3.3 V) → comparator
  Input scaling circuit maps Vin (±5 V) → 0–3.3 V before comparator
  LM339 compares scaled Vin against DAC output → GPIO 23
"""

import time
import pigpio

from ohmmeter import MCP4131_MAX_STEPS, COMPARATOR_PIN, _SETTLE_S
from callbacks import clear_callbacks, PIN_A, PIN_B, ROTARY_BTN_PIN
import rotary_encoder


# ── SAR measurement (voltmeter-specific) ─────────────────────────────────────

def _write_dac(pi, spi_handle, step):
    """
    Write 5-bit SAR step (0..31) to MCP4131 7-bit register (0..127).

    This keeps the same DAC direction as your working ohmmeter/voltmeter path.
    """
    step = max(0, min(step, MCP4131_MAX_STEPS))
    pi.spi_write(spi_handle, [0x00, round(step * 127 / MCP4131_MAX_STEPS)])


def _sar_measure(pi, spi_handle, comp_pin):
    """
    5-bit SAR conversion.

    Uses the same logic as your working path:
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


# ── Voltage range / calibration ───────────────────────────────────────────────
V_MAX       =  5.0
V_MIN       = -5.0
V_RANGE     = V_MAX - V_MIN

# Based on your measured calibration trend:
# -5V -> step ~0
# -4V -> step ~2
# -3V -> step ~5
# -2V -> step ~9
# -1V -> step ~12
#  0V -> step ~15
# +1V -> step ~18
# +2V -> step ~21
# +3V -> step ~25
# +4V -> step ~28
# +5V -> step ~31
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

ZERO_STEP   = 15
VOLT_TOL_V  = 0.35


# ── Source menu ───────────────────────────────────────────────────────────────
SRC_EXTERNAL  = 0
SRC_INTERNAL  = 1
SRC_BACK      = 2
SRC_MAIN      = 3
SOURCE_LABELS = ["External", "Int. Reference", "Back", "Main"]
NUM_SOURCES   = len(SOURCE_LABELS)

_DEBOUNCE_US  = 200_000


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
    """Format voltage as '+2.50V' or '-0.31V'."""
    return f"{v:+.2f}V"


def build_source_menu_lines(selection):
    """Return four 20-char LCD lines for the source selection menu."""
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
    """Return four 20-char LCD lines for the live measurement page."""
    v = step_to_voltage(step)

    if step <= 0:
        line2 = f"{_fmt_v(V_MIN)} (at min)"
    elif step >= MCP4131_MAX_STEPS:
        line2 = f"{_fmt_v(V_MAX)} (at max)"
    else:
        line2 = f"{_fmt_v(v)} +/-{VOLT_TOL_V:.2f}V"

    return "Voltmeter", f"Src: {source_label}", line2, "Btn: back"


# ── Page runners (called from Driver.py) ─────────────────────────────────────

def run_source_menu(state, pi, lcd):
    """Show source selection menu; block until user selects an option."""
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
    """Continuously measure and display voltage; press button to exit."""
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
            step = _averaged_measure(pi, adc_handle, COMPARATOR_PIN, n=11)
            l0, l1, l2, l3 = build_measurement_lines(step, source_label)
            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)
            print(f"[Voltmeter] step={step}  {l2.strip()}")
        time.sleep(0.05)

    clear_callbacks(state)
