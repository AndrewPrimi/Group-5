"""
Driver.py

Integrated LCD UI driver matching the UI tree from UI.md:

Mode Select
1. Function Generator
   a. Type        -> Square / Back / Main
   b. Frequency   -> Input / Back / Main
   c. Amplitude   -> Input / Back / Main
   d. Output      -> On / Off / Back / Main
2. Ohmmeter       -> live reading + Back / Main
3. Voltmeter
   a. Source      -> External / Int. Reference / Back / Main
4. DC Reference
   a. Set Voltage -> Input
   b. Output      -> On / Off / Back / Main
   c. Back
   d. Main

Integrates:
- square_wave.py   (SquareWaveGenerator on CE0)
- dc_reference.py  (DCReferenceGenerator on CE0)
- voltmeter.py     (SAR voltmeter on CE1)
- ohmmeter.py      (SAR ohmmeter on CE1)
- callbacks.py     (pick_menu, adjust_value, wait_for_back)
- i2c_lcd.py
- rotary_encoder.py
"""

import time
import pigpio

import i2c_lcd
import rotary_encoder

from callbacks import (
    PIN_A,
    PIN_B,
    ROTARY_BTN_PIN,
    setup_callbacks,
    clear_callbacks,
    pick_menu,
    adjust_value,
    wait_for_back,
)

from square_wave import SquareWaveGenerator, MIN_FREQ, MAX_FREQ, MAX_AMP, AMP_STEP, FREQ_STEP
from dc_reference import DCReferenceGenerator, MIN_VOLT, MAX_VOLT

from voltmeter import (
    COMPARATOR1_PIN,
    run_measurement,
    step_to_voltage,
    _averaged_measure as volt_averaged_measure,
)

from ohmmeter import (
    COMPARATOR2_PIN,
    averaged_measure as ohm_averaged_measure,
    step_to_resistance,
    tolerance as ohm_tolerance,
)


# ── Hardware setup ────────────────────────────────────────────────────────────

pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("pigpiod not running – run 'sudo pigpiod' first.")

lcd = i2c_lcd.lcd(pi, width=20)

# CE0: square wave MCP4131 + DC reference MCP4231 (never used simultaneously)
spi_ce0 = pi.spi_open(0, 50_000, 0)

# CE1: voltmeter + ohmmeter MCP4131 (never used simultaneously)
spi_ce1 = pi.spi_open(1, 50_000, 0)

print(f"SPI handles: CE0={spi_ce0}  CE1={spi_ce1}")

# GPIO setup for rotary encoder
pi.set_mode(PIN_A, pigpio.INPUT)
pi.set_mode(PIN_B, pigpio.INPUT)
pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)

pi.set_mode(ROTARY_BTN_PIN, pigpio.INPUT)
pi.set_pull_up_down(ROTARY_BTN_PIN, pigpio.PUD_UP)
pi.set_glitch_filter(ROTARY_BTN_PIN, 10_000)

# GPIO setup for comparators (external pull-ups only — disable internal pulls)
pi.set_mode(COMPARATOR1_PIN, pigpio.INPUT)
pi.set_mode(COMPARATOR2_PIN, pigpio.INPUT)
pi.set_pull_up_down(COMPARATOR1_PIN, pigpio.PUD_OFF)
pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)


# ── Hardware objects ──────────────────────────────────────────────────────────

sq_gen = SquareWaveGenerator(pi, spi_ce0, debug=True)
dc_ref = DCReferenceGenerator(pi, spi_ce0, settle_time=0.001)


# ── Shared state ──────────────────────────────────────────────────────────────

state = {
    'active_callbacks': [],
    'button_last_tick': None,
    'button_press_tick': None,
    'encoder_delta': 0,
    'button_pressed': False,
    'long_press': False,

    # Function generator
    'fg_freq': 1000,
    'fg_amp': 0.0,
    'fg_output_on': False,

    # DC Reference
    'dc_voltage': 0.0,
    'dc_output_on': False,
}

# Inject into callbacks module
setup_callbacks(state, pi, lcd)


# ── Function Generator ────────────────────────────────────────────────────────

def run_function_generator_menu():
    while True:
        choice = pick_menu(
            "Function Generator",
            ["Type", "Frequency", "Amplitude", "Output", "Back", "Main"],
        )

        if choice == "Type":
            result = run_fg_type()
            if result == "MAIN":
                return "MAIN"

        elif choice == "Frequency":
            result = run_fg_frequency()
            if result == "MAIN":
                return "MAIN"

        elif choice == "Amplitude":
            result = run_fg_amplitude()
            if result == "MAIN":
                return "MAIN"

        elif choice == "Output":
            result = run_fg_output()
            if result == "MAIN":
                return "MAIN"

        elif choice == "Back":
            return "BACK"

        elif choice == "Main":
            return "MAIN"


def run_fg_type():
    choice = pick_menu("Waveform Type", ["Square", "Back", "Main"])
    if choice == "Square":
        # Only square is supported; just confirm
        wait_for_back(lambda: (
            "Type: Square",
            "Only square wave",
            "is supported.",
            "Btn: back",
        ))
        return "BACK"
    elif choice == "Main":
        return "MAIN"
    return "BACK"


def run_fg_frequency():
    choice = pick_menu("Frequency", ["Input Frequency", "Back", "Main"])
    if choice == "Input Frequency":
        val = adjust_value(
            "Input Frequency",
            state['fg_freq'],
            MIN_FREQ, MAX_FREQ, FREQ_STEP,
            lambda v: f"{int(v)} Hz",
        )
        if val is not None:
            state['fg_freq'] = int(val)
            sq_gen.set_frequency(state['fg_freq'])
        return "BACK"
    elif choice == "Main":
        return "MAIN"
    return "BACK"


def run_fg_amplitude():
    choice = pick_menu("Amplitude", ["Input Amplitude", "Back", "Main"])
    if choice == "Input Amplitude":
        val = adjust_value(
            "Input Amplitude",
            state['fg_amp'],
            0.0, MAX_AMP, AMP_STEP,
            lambda v: f"{v:.4f} V",
        )
        if val is not None:
            state['fg_amp'] = val
            sq_gen.set_amplitude(state['fg_amp'])
        return "BACK"
    elif choice == "Main":
        return "MAIN"
    return "BACK"


def run_fg_output():
    """Output on/off — turns off automatically on Back or Main."""
    while True:
        choice = pick_menu("Output", ["On", "Off", "Back", "Main"])

        if choice == "On":
            sq_gen.set_frequency(state['fg_freq'])
            sq_gen.set_amplitude(state['fg_amp'])
            sq_gen.start()
            state['fg_output_on'] = True

            # Show live output values, wait for button to go back
            wait_for_back(lambda: (
                "Output: ON",
                f"Freq: {state['fg_freq']} Hz",
                f"Amp:  {state['fg_amp']:.4f} V",
                "Btn: back",
            ))
            sq_gen.stop()
            state['fg_output_on'] = False

        elif choice == "Off":
            sq_gen.stop()
            state['fg_output_on'] = False

        elif choice == "Back":
            sq_gen.stop()
            state['fg_output_on'] = False
            return "BACK"

        elif choice == "Main":
            sq_gen.stop()
            state['fg_output_on'] = False
            return "MAIN"


# ── Ohmmeter ──────────────────────────────────────────────────────────────────

def run_ohmmeter():
    """Live resistance reading with Back/Main options."""
    while True:
        # Show live measurement until user presses button
        state['button_pressed'] = False
        state['button_last_tick'] = None
        clear_callbacks(state)

        DEBOUNCE_US = 200_000

        def _on_button(_gpio, level, tick):
            if level != 0:
                return
            last = state.get('button_last_tick')
            if last is not None and pigpio.tickDiff(last, tick) < DEBOUNCE_US:
                return
            state['button_last_tick'] = tick
            state['button_pressed'] = True

        lcd.put_line(0, "Ohmmeter")
        lcd.put_line(1, "Measuring...")
        lcd.put_line(2, "")
        lcd.put_line(3, "Btn: menu")

        cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
        state['active_callbacks'] = [cb_btn]

        last_update = 0.0
        try:
            while not state['button_pressed']:
                now = time.time()
                if now - last_update >= 0.5:
                    last_update = now
                    step = ohm_averaged_measure(pi, spi_ce1, COMPARATOR2_PIN, n=11)
                    resistance = step_to_resistance(step)
                    tol = ohm_tolerance(step)

                    lcd.put_line(0, "Ohmmeter")
                    lcd.put_line(1, f"R: {resistance:.0f} ohm")
                    lcd.put_line(2, f"+/- {tol:.0f} ohm")
                    lcd.put_line(3, "Btn: menu")
                    print(f"[Ohmmeter] step={step}  R={resistance:.0f}  tol={tol:.0f}")
                time.sleep(0.05)
        finally:
            state['button_pressed'] = False
            clear_callbacks(state)

        # After button press, show Back/Main options
        choice = pick_menu("Ohmmeter", ["Resume", "Back", "Main"])

        if choice == "Resume":
            continue
        elif choice == "Back":
            return "BACK"
        elif choice == "Main":
            return "MAIN"


# ── Voltmeter ─────────────────────────────────────────────────────────────────

def run_voltmeter_menu():
    while True:
        choice = pick_menu(
            "Voltmeter",
            ["Source", "Back", "Main"],
        )

        if choice == "Source":
            result = run_voltmeter_source()
            if result == "MAIN":
                return "MAIN"

        elif choice == "Back":
            return "BACK"

        elif choice == "Main":
            return "MAIN"


def run_voltmeter_source():
    choice = pick_menu(
        "Volt Source",
        ["External", "Int. Reference", "Back", "Main"],
    )

    if choice == "External":
        run_measurement(state, pi, lcd, spi_ce1, source_label="External")
        return "BACK"

    elif choice == "Int. Reference":
        # Jump to DC Reference menu
        result = run_dc_reference_menu()
        return result

    elif choice == "Main":
        return "MAIN"

    return "BACK"


# ── DC Reference ──────────────────────────────────────────────────────────────

def run_dc_reference_menu():
    while True:
        choice = pick_menu(
            "DC Reference",
            ["Set Voltage", "Output", "Back", "Main"],
        )

        if choice == "Set Voltage":
            val = adjust_value(
                "DC Voltage",
                state['dc_voltage'],
                MIN_VOLT, MAX_VOLT, 0.625,
                lambda v: f"{v:+.3f} V",
            )
            if val is not None:
                state['dc_voltage'] = val
                dc_ref.set_voltage(val)

        elif choice == "Output":
            result = run_dc_output()
            if result == "MAIN":
                dc_ref.stop()
                state['dc_output_on'] = False
                return "MAIN"

        elif choice == "Back":
            dc_ref.stop()
            state['dc_output_on'] = False
            return "BACK"

        elif choice == "Main":
            dc_ref.stop()
            state['dc_output_on'] = False
            return "MAIN"


def run_dc_output():
    """DC reference output on/off with live voltmeter reading."""
    while True:
        choice = pick_menu("DC Output", ["On", "Off", "Back", "Main"])

        if choice == "On":
            dc_ref.set_voltage(state['dc_voltage'])
            dc_ref.start()
            state['dc_output_on'] = True

            # Live display: set voltage + measured voltage from voltmeter
            state['button_pressed'] = False
            state['button_last_tick'] = None
            clear_callbacks(state)

            DEBOUNCE_US = 200_000

            def _on_button(_gpio, level, tick):
                if level != 0:
                    return
                last = state.get('button_last_tick')
                if last is not None and pigpio.tickDiff(last, tick) < DEBOUNCE_US:
                    return
                state['button_last_tick'] = tick
                state['button_pressed'] = True

            lcd.put_line(0, "DC Ref: ON")
            lcd.put_line(1, f"Set: {state['dc_voltage']:+.3f} V")
            lcd.put_line(2, "Measuring...")
            lcd.put_line(3, "Btn: back")

            cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
            state['active_callbacks'] = [cb_btn]

            last_update = 0.0
            try:
                while not state['button_pressed']:
                    now = time.time()
                    if now - last_update >= 0.5:
                        last_update = now
                        step = volt_averaged_measure(pi, spi_ce1, COMPARATOR1_PIN, n=11)
                        measured = step_to_voltage(step)
                        lcd.put_line(0, "DC Ref: ON")
                        lcd.put_line(1, f"Set: {state['dc_voltage']:+.3f} V")
                        lcd.put_line(2, f"Meas: {measured:+.2f} V")
                        lcd.put_line(3, "Btn: back")
                        print(f"[DC Ref] set={state['dc_voltage']:+.3f}  meas={measured:+.2f}")
                    time.sleep(0.05)
            finally:
                state['button_pressed'] = False
                clear_callbacks(state)

            dc_ref.stop()
            state['dc_output_on'] = False

        elif choice == "Off":
            dc_ref.stop()
            state['dc_output_on'] = False

        elif choice == "Back":
            dc_ref.stop()
            state['dc_output_on'] = False
            return "BACK"

        elif choice == "Main":
            dc_ref.stop()
            state['dc_output_on'] = False
            return "MAIN"


# ── Main Loop ─────────────────────────────────────────────────────────────────

print("Starting...")
try:
    while True:
        choice = pick_menu(
            "Mode Select",
            ["Function Generator", "Ohmmeter", "Voltmeter", "DC Reference", "Back", "Main"],
        )

        if choice == "Function Generator":
            result = run_function_generator_menu()
            # MAIN or BACK both return to top

        elif choice == "Ohmmeter":
            result = run_ohmmeter()

        elif choice == "Voltmeter":
            result = run_voltmeter_menu()

        elif choice == "DC Reference":
            result = run_dc_reference_menu()

        elif choice in ("Back", "Main"):
            # At top level, both just redraw the main menu
            pass

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    print("Cleaning up...")
    sq_gen.cleanup()
    dc_ref.cleanup()
    clear_callbacks(state)
    lcd.close()
    pi.spi_close(spi_ce0)
    pi.spi_close(spi_ce1)
    pi.stop()
