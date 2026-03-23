"""
Driver.py – Deliverable 9
=========================

LCD + rotary-encoder UI for:
  - Ohmmeter
  - Voltmeter

Integrated modules:
  - rotary_encoder.py
  - ohmmeter.py
  - ohms_steps.py

Navigation:
  Rotate      -> move menu cursor
  Short press -> select / confirm
  Button press on live pages -> return

Hardware:
  LCD          : I2C 20x4 at address 0x27
  Rotary enc.  : A = GPIO 22, B = GPIO 27, button = GPIO 17
  MCP4131 DAC  : SPI CE1 (GPIO 7)
  Ohmmeter cmp : GPIO 24
  Voltmeter cmp: GPIO 23
"""

import time
import pigpio

import i2c_lcd
import rotary_encoder

from callbacks import (
    setup_callbacks,
    clear_callbacks,
    menu_direction_callback,
    menu_button_callback,
    ohm_button_callback,
    PIN_A,
    PIN_B,
    ROTARY_BTN_PIN,
    _redraw_main_menu,
)

from ohmmeter import (
    open_adc,
    close_adc,
    averaged_measure as ohm_averaged_measure,
    step_to_resistance,
    tolerance,
    COMPARATOR2_PIN as OHM_COMPARATOR_PIN,
    MCP4131_MAX_STEPS,
)

from ohms_steps import (
    MINIMUM_OHMS,
    MAXIMUM_OHMS,
    step_to_ohms as pot_step_to_ohms,
    fix_ohms as pot_fix_ohms,
)

from voltmeter import (
    run_source_menu,
    run_measurement,
    SRC_BACK,
    SOURCE_LABELS,
)

MEASURE_INTERVAL = 0.5  # seconds


# ── Initialise pigpio ────────────────────────────────────────────────────────
pi = pigpio.pi()
if not pi.connected:
    print("Cannot connect to pigpio daemon. Run 'sudo pigpiod' first.")
    raise SystemExit(1)


# ── Peripherals ──────────────────────────────────────────────────────────────
lcd = i2c_lcd.lcd(pi, width=20)
adc_handle = open_adc(pi)   # opens SPI CE1 and configures ohmmeter comparator

print(f"ADC SPI handle: {adc_handle}")


# ── GPIO setup ───────────────────────────────────────────────────────────────
for pin in (PIN_A, PIN_B):
    pi.set_mode(pin, pigpio.INPUT)
    pi.set_pull_up_down(pin, pigpio.PUD_UP)

pi.set_mode(ROTARY_BTN_PIN, pigpio.INPUT)
pi.set_pull_up_down(ROTARY_BTN_PIN, pigpio.PUD_UP)
pi.set_glitch_filter(ROTARY_BTN_PIN, 10_000)  # 10 ms

# Voltmeter comparator pin
pi.set_mode(23, pigpio.INPUT)
pi.set_pull_up_down(23, pigpio.PUD_UP)


# ── Shared application state ────────────────────────────────────────────────
state = {
    'menu_selection': 1,       # 1 = Ohmmeter, 2 = Voltmeter
    'isMainPage': True,
    'isOhmPage': False,
    'active_callbacks': [],

    'button_last_tick': None,
    'button_press_tick': None,
    'button_pressed': False,
    'button_held': False,

    'encoder_delta': 0,
}

setup_callbacks(state, pi, lcd)


# ── Display helpers ──────────────────────────────────────────────────────────
def _fmt_ohms(ohms):
    """Compact ohms formatter for LCD."""
    if ohms == float("inf"):
        return "Open"
    if ohms >= 1000:
        return f"{ohms / 1000:.2f}k"
    return f"{ohms:.0f}"


def build_ohm_lines(step):
    """
    Build four LCD lines for ohmmeter page.

    Integrates:
      - ohmmeter.py for calibrated external resistance
      - ohms_steps.py for helper conversion/debug-style equivalent pot reading
    """
    if step <= 0:
        return (
            "Ohmmeter",
            "Open circuit",
            "Step: 0",
            "Btn: main menu",
        )

    if step >= MCP4131_MAX_STEPS:
        return (
            "Ohmmeter",
            "Short circuit",
            f"Step: {step}",
            "Btn: main menu",
        )

    measured_r = step_to_resistance(step)
    tol_r = tolerance(step)

    # Map 5-bit SAR step (0..31) to 7-bit style pot code (0..127) so that
    # ohms_steps.py helpers are genuinely used in the integration.
    pot_code = round(step * 127 / MCP4131_MAX_STEPS)
    pot_est = pot_fix_ohms(pot_step_to_ohms(pot_code))

    line1 = f"R: {_fmt_ohms(measured_r)} Ohm"
    line2 = f"+/- {_fmt_ohms(tol_r)}"

    # Keep a useful debug/calibration line that uses ohms_steps.py
    if measured_r < MINIMUM_OHMS:
        line2 = "Below min range"
    elif measured_r > MAXIMUM_OHMS:
        line2 = "Above max range"

    line3 = f"S:{step:02d} P:{_fmt_ohms(pot_est)}"

    return (
        "Ohmmeter",
        line1[:20],
        line2[:20],
        line3[:20],
    )


# ── Main menu ────────────────────────────────────────────────────────────────
def show_main_menu():
    lcd.put_line(0, "Main Menu")
    lcd.put_line(1, "Mode Select:")
    _redraw_main_menu()


def run_main_menu():
    """Block until user selects Ohmmeter or Voltmeter."""
    state['isMainPage'] = True
    state['menu_selection'] = 1
    state['button_last_tick'] = None

    clear_callbacks(state)
    show_main_menu()

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, menu_direction_callback)
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, menu_button_callback)
    state['active_callbacks'] = [decoder, cb_btn]

    while state['isMainPage']:
        time.sleep(0.05)

    clear_callbacks(state)


# ── Ohmmeter page ────────────────────────────────────────────────────────────
def run_ohmmeter():
    """Continuously measure and display resistance; button returns to main menu."""
    state['isOhmPage'] = True
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

            step = ohm_averaged_measure(pi, adc_handle, OHM_COMPARATOR_PIN, n=11)
            l0, l1, l2, l3 = build_ohm_lines(step)

            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)

            print(f"[Ohmmeter] step={step:02d} | {l1.strip()} | {l2.strip()} | {l3.strip()}")

        time.sleep(0.05)

    clear_callbacks(state)


# ── Voltmeter page ───────────────────────────────────────────────────────────
def run_voltmeter():
    """Voltmeter source menu then live measurement."""
    while True:
        choice = run_source_menu(state, pi, lcd)
        if choice == SRC_BACK:
            break

        run_measurement(
            state,
            pi,
            lcd,
            adc_handle,
            source_label=SOURCE_LABELS[choice],
        )


# ── Main loop ────────────────────────────────────────────────────────────────
print("Starting Deliverable 9 driver...")

try:
    while True:
        run_main_menu()

        if state['menu_selection'] == 1:
            run_ohmmeter()
        elif state['menu_selection'] == 2:
            run_voltmeter()

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    clear_callbacks(state)
    lcd.close()
    close_adc(pi, adc_handle)
    pi.stop()
