"""
Driver.py – Deliverable 9
==========================
LCD + rotary-encoder UI for Checkpoint B.

Navigation:
  Rotate      →  move menu cursor
  Short press →  select / confirm
  Hold 2 s    →  (not used — button press exits pages)

Menu structure:
  Main Menu
  ├── Ohmmeter   → continuous resistance reading, press btn to return
  └── Voltmeter
        Source menu (External | Int. Reference | Back)
          └── Live measurement, press btn to return to source menu

Hardware:
  LCD          : I2C 20×4 at address 0x27
  Rotary enc.  : A = GPIO 22, B = GPIO 27, button = GPIO 17
  Digipots     : SPI CE0 (GPIO 8)
  MCP4131 DAC  : SPI CE1 (GPIO 7)  — shared by ohmmeter and voltmeter
  Ohmmeter cmp : GPIO 23
  Voltmeter cmp: GPIO 24
"""

import pigpio
import time

import i2c_lcd
import rotary_encoder
from callbacks import (
    setup_callbacks, clear_callbacks,
    
    # ── Checkpoint C ─────────────────────────────────────────────────────────
    menu_direction_callback, menu_button_callback,
    varconst_direction_callback, varconst_button_callback,
    
    pot_direction_callback, callback_set_digi,
    constant_direction_callback, constant_button_callback, 
    
    ohm_button_callback, _redraw_main_menu,
    PIN_A, PIN_B, ROTARY_BTN_PIN,
)

# ── Checkpoint B ─────────────────────────────────────────────────────────
from square_wave import (
    SquareWaveGenerator,
    MIN_FREQ, MAX_FREQ, FREQ_STEP, MAX_AMP,
)

from dc_reference import DCReferenceGenerator
from sar_logic import SAR_ADC
        
from ohmmeter import (
    open_adc, close_adc,
    write_dac,
    sar_measure, averaged_measure,
    interp, calibrate_resistance,
    step_to_raw_resistance,
    step_to_resistance, tolerance,
    COMPARATOR2_PIN as OHM_COMPARATOR_PIN,
    MCP4131_MAX_STEPS,
    R_MIN_OHMS, R_MAX_OHMS,
)
from voltmeter import (
    write_dac, sar_measure,
    averaged_measure,
)

# ── Timing ────────────────────────────────────────────────────────────────────
MEASURE_INTERVAL = 0.5   # seconds between ohmmeter display refreshes

# ── Initialise pigpio ─────────────────────────────────────────────────────────
pi = pigpio.pi()
if not pi.connected:
    print("Cannot connect to pigpio daemon.  Run 'sudo pigpiod' first.")
    exit(1)

# ── Peripherals ───────────────────────────────────────────────────────────────
lcd        = i2c_lcd.lcd(pi, width=20)
adc_handle = open_adc(pi)   # SPI CE1 — used by both ohmmeter and voltmeter

print(f"ADC SPI handle: {adc_handle}")

# ── GPIO setup ────────────────────────────────────────────────────────────────
for pin in (PIN_A, PIN_B):
    pi.set_mode(pin, pigpio.INPUT)
    pi.set_pull_up_down(pin, pigpio.PUD_UP)

pi.set_mode(ROTARY_BTN_PIN, pigpio.INPUT)
pi.set_pull_up_down(ROTARY_BTN_PIN, pigpio.PUD_UP)
pi.set_glitch_filter(ROTARY_BTN_PIN, 10_000)   # 10 ms hardware debounce

# Ohmmeter comparator (GPIO 23) pull-up set by open_adc()
# Voltmeter comparator (GPIO 24) pull-up
pi.set_mode(24, pigpio.INPUT)
pi.set_pull_up_down(24, pigpio.PUD_UP)

# ── Shared application state ──────────────────────────────────────────────────
state = {
    'menu_selection':    0,       # 0 = Function Generator, 1 = Ohmmeter, 2 = Voltmeter, 3 = DC Reference, 4, Frequency Measurement
    'isMainPage':        True,
    'isOhmPage':         False,
    'active_callbacks':  [],
    
    'button_last_tick':  None,
    'button_press_tick': None,
    'button_pressed':    False,
    'button_held':       False,
    
    # Deliverable 8
    'wave_type':         'Square',
    'frequency':         1000,
    'amplitude':         0.0,
    'output_on':         False,
    'dc_voltage':        0.0,
    'dc_output_on':      False,
    'encoder_delta':     0,
}

setup_callbacks(state, pi, lcd)


# ── Ohmmeter display helper ───────────────────────────────────────────────────

def _fmt_ohms(ohms, width=8):
    """Auto-range: display in Ω below 1 kΩ, kΩ above."""
    if ohms >= 1000:
        s = f"{ohms / 1000:.2f}k"
    else:
        s = f"{ohms:.0f}"
    return s.ljust(width)


def build_ohm_lines(step):
    """Return four 20-char LCD lines for the ohmmeter page."""
    r   = step_to_resistance(step)
    tol = tolerance(step)

    #if step <= 0:
        #return "Ohmmeter", "Short circuit", "", "Hold btn: main menu"
    #if step >= MCP4131_MAX_STEPS:
        #return "Ohmmeter", "Open circuit", "", "Hold btn: main menu"
    if step >= MCP4131_MAX_STEPS:
        return "Ohmmeter", "Short circuit", "", "Hold btn: main menu"
    if step <= 0:
        return "Ohmmeter", "Open circuit", "", "Hold btn: main menu"

    r_str   = _fmt_ohms(r).strip()
    tol_str = _fmt_ohms(tol).strip()

    if r < R_MIN_OHMS:
        line1 = f"{r_str} Ohms"
        line2 = "Below 500 Ohm range"
    elif r > R_MAX_OHMS:
        line1 = f"{r_str} Ohms"
        line2 = "Above 10k Ohm range"
    else:
        line1 = f"{r_str} Ohms"
        line2 = f"+/- {tol_str} Ohms"

    return "Ohmmeter", line1, line2, "Btn: main menu"


# ── Page runners ──────────────────────────────────────────────────────────────

def show_main_menu():
    lcd.put_line(0, "Main Menu")
    lcd.put_line(1, "Mode Select:")
    lcd.put_line(2, "  Ohmmeter")
    lcd.put_line(3, "  Voltmeter")


def run_main_menu():
    """Block until the user selects Ohmmeter or Voltmeter."""
    state['isMainPage']       = True
    state['menu_selection']   = 1
    state['button_last_tick'] = None
    clear_callbacks(state)

    show_main_menu()
    _redraw_main_menu()

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, menu_direction_callback)
    cb_btn  = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, menu_button_callback)
    state['active_callbacks'] = [decoder, cb_btn]

    while state['isMainPage']:
        time.sleep(0.05)

    clear_callbacks(state)


def run_ohmmeter():
    """Continuously measure and display resistance; press button to exit."""
    state['isOhmPage']        = True
    state['button_last_tick'] = None
    clear_callbacks(state)

    lcd.put_line(0, "Ohmmeter")
    lcd.put_line(1, "Measuring...")
    lcd.put_line(2, "")
    lcd.put_line(3, "Btn: main menu")

    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, ohm_button_callback)
    state['active_callbacks'] = [cb_btn]

    last_update = 0.0
    while state['isOhmPage']:
        now = time.time()
        if now - last_update >= MEASURE_INTERVAL:
            last_update = now
            step = averaged_measure(pi, adc_handle, OHM_COMPARATOR_PIN, n=11)
            l0, l1, l2, l3 = build_ohm_lines(step)
            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)
            print(f"[Ohmmeter] step={step}  {l1.strip()}  {l2.strip()}")
        time.sleep(0.05)

    clear_callbacks(state)


def run_voltmeter():
    """Show source menu then measure voltage; loops until Back selected."""
    while True:
        choice = run_source_menu(state, pi, lcd)
        if choice == SRC_BACK:
            break
        run_measurement(state, pi, lcd, adc_handle,
                        source_label=SOURCE_LABELS[choice])


# ── Main loop ─────────────────────────────────────────────────────────────────

print("Starting Deliverable 9 driver...")

try:
    while True:
        run_main_menu()
        if state['menu_selection'] == 0:
            run_function_generator()
        elif state['menu_selection'] == 1:
            run_ohmmeter()
        elif state['menu_selection'] == 2:
            run_voltmeter()
        elif state['menu_selection'] == 3:
            run_dc_reference()
            

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    clear_callbacks(state)
    lcd.close()
    close_adc(pi, adc_handle)
    pi.stop()
