"""
voltmeter.py
SAR ADC voltmeter — measures DC voltage over ±5 V and displays
the reading plus ±½-LSB tolerance on the 20×4 I2C LCD.

Hardware (same MCP4131 SAR DAC as ohmmeter):
  SPI CE1  → MCP4131 (P0A = 3.3 V, P0B = GND, P0W = scaled DAC out)
  Op-amp scaling circuit maps 0–3.3 V wiper → ±5 V DAC reference
  LM339 compares Vin against scaled DAC output → GPIO 23

Measurement range : ±5 V
Resolution        : 10 V / 32 = 0.3125 V per step  (5-bit SAR)
Tolerance (±½ LSB): ±0.3125 V

Source menu items:
  0 – External       (measure voltage from external supply)
  1 – Int. Reference (measure voltage from onboard DC reference)
  2 – Back           (return to previous menu)
  3 – Main           (return to main menu)
"""

import time
import pigpio

from ohmmeter import averaged_measure, MCP4131_MAX_STEPS, COMPARATOR_PIN
from callbacks import clear_callbacks, PIN_A, PIN_B, ROTARY_BTN_PIN
import rotary_encoder

# ── Voltage range ─────────────────────────────────────────────────────────────
V_MAX       =  5.0
V_MIN       = -5.0
V_RANGE     = V_MAX - V_MIN          # 10 V total span

_N_LEVELS   = MCP4131_MAX_STEPS + 1  # 32 levels
VOLT_STEP_V = V_RANGE / _N_LEVELS    # 0.3125 V per step
VOLT_TOL_V  = VOLT_STEP_V            # ±0.3125 V

# ── Source menu ───────────────────────────────────────────────────────────────
SRC_EXTERNAL  = 0
SRC_INTERNAL  = 1
SRC_BACK      = 2
SRC_MAIN      = 3
SOURCE_LABELS = ["External", "Int. Reference", "Back", "Main"]
NUM_SOURCES   = len(SOURCE_LABELS)

_DEBOUNCE_US  = 200_000   # 200 ms button debounce


# ── Conversion maths ──────────────────────────────────────────────────────────

def step_to_voltage(step):
    """Convert a 5-bit SAR step (0–31) to a voltage (V).

    Mapping:
        step  0 → -5.00 V
        step 16 →  0.00 V
        step 31 → +4.69 V  (within ±0.31 V of +5 V)
    """
    step = max(0, min(step, MCP4131_MAX_STEPS))
    return V_MIN + V_RANGE * step / _N_LEVELS


# ── Display helpers ───────────────────────────────────────────────────────────

def _fmt_v(v):
    """Format voltage as '+2.50V' or '-0.31V'."""
    return f"{v:+.2f}V"


def build_source_menu_lines(selection):
    """Return four 20-char LCD lines for the source selection menu.

    Line 0 : 'Voltmeter' (title)
    Lines 1-3 : scrolling 3-item window of SOURCE_LABELS with '>' cursor.
    """
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
    """Return four 20-char LCD lines for the live measurement page.

    Line 0 : 'Voltmeter'
    Line 1 : 'Src: <source_label>'
    Line 2 : '+2.50V +/-0.3125V'
    Line 3 : 'Btn: back'
    """
    v = step_to_voltage(step)

    if step <= 0:
        line2 = f"{_fmt_v(V_MIN)} (at min)"
    elif step >= MCP4131_MAX_STEPS:
        line2 = f"{_fmt_v(step_to_voltage(MCP4131_MAX_STEPS))} (at max)"
    else:
        line2 = f"{_fmt_v(v)} +/-{VOLT_TOL_V:.4f}V"

    return "Voltmeter", f"Src: {source_label}", line2, "Btn: back"


# ── Page runners (called from Driver.py) ─────────────────────────────────────

def run_source_menu(state, pi, lcd):
    """Show source selection menu; block until user selects an option.

    Returns one of: SRC_EXTERNAL, SRC_INTERNAL, SRC_BACK, SRC_MAIN
    """
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
            step = averaged_measure(pi, adc_handle, COMPARATOR_PIN, n=5)
            l0, l1, l2, l3 = build_measurement_lines(step, source_label)
            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)
            print(f"[Voltmeter] step={step}  {l2.strip()}")
        time.sleep(0.05)

    clear_callbacks(state)
