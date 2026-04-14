"""
Driver.py

Integrated LCD UI driver matching the UI tree from UI.md.

Integrates:
- square_wave.py          (SquareWaveGenerator on CE0)
- dc_reference_single.py  (DCReferenceSingleGenerator on CE0)
- voltmeter.py            (SAR voltmeter on CE1)
- ohmmeter.py             (SAR ohmmeter on CE1)
- callbacks.py            (pick_menu, adjust_value, wait_for_back)
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
from dc_reference_single import DCReferenceSingleGenerator, MIN_VOLT, MAX_VOLT

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

from Sinewave import (
    SineWaveGenerator,
    MIN_FREQ as SINE_MIN_FREQ,
    MAX_FREQ as SINE_MAX_FREQ,
    FREQ_STEP as SINE_FREQ_STEP,
    MAX_AMP as SINE_MAX_AMP,
    AMP_STEP as SINE_AMP_STEP,
)
from Sinewave_measurement import FrequencyMeter


pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("pigpiod not running – run 'sudo pigpiod' first.")

lcd = i2c_lcd.lcd(pi, width=20)

# CE0: square wave MCP4131 + DC reference MCP4231 (never used at the same time)
spi_ce0 = pi.spi_open(0, 50_000, 0)

# CE1: voltmeter + ohmmeter MCP4131 (never used at the same time)
spi_ce1 = pi.spi_open(1, 50_000, 0)


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


sq_gen   = SquareWaveGenerator(pi, spi_ce0, debug=True)
dc_ref   = DCReferenceSingleGenerator(pi, spi_ce0, settle_time=0.001)
sine_gen = SineWaveGenerator(pi, debug=True)


state = {
    'active_callbacks': [],
    'button_last_tick': None,
    'button_press_tick': None,
    'encoder_delta': 0,
    'button_pressed': False,
    'long_press': False,

    # Function generator
    'fg_type': 'square',
    'fg_freq': 1000,
    'fg_amp': 0.0,
    'fg_output_on': False,

    # DC Reference
    'dc_voltage': 0.0,
    'dc_output_on': False,
}

# Inject into callbacks module
setup_callbacks(state, pi, lcd)


def ensure_all_off():
    """Safely shut down all outputs and turn off the LCD."""
    sq_gen.stop()
    sine_gen.stop()
    dc_ref.stop()
    state['fg_output_on'] = False
    state['dc_output_on'] = False
    lcd.clear()
    lcd.backlight(False)
    lcd._inst(0x08)  # display off


def run_top_screen():
    """Top-level screen: OFF / Mode Select. Returns when Mode Select is chosen."""
    while True:
        # Turn LCD back on for the menu
        lcd.backlight(True)
        lcd._inst(0x0C)  # display on

        choice = pick_menu("System", ["OFF", "Mode Select"])

        if choice == "OFF":
            ensure_all_off()

        elif choice == "Mode Select":
            return


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
    choice = pick_menu("Type", ["Sine", "Square", "Back", "Main"])
    if choice == "Sine":
        state['fg_type'] = 'sine'
        return "BACK"
    elif choice == "Square":
        state['fg_type'] = 'square'
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
            gen = sine_gen if state['fg_type'] == 'sine' else sq_gen
            gen.set_frequency(state['fg_freq'])
            gen.set_amplitude(state['fg_amp'])
            gen.start()
            state['fg_output_on'] = True

            type_label = "Sine" if state['fg_type'] == 'sine' else "Square"
            wait_for_back(lambda: (
                f"Output: ON ({type_label})",
                f"Freq: {state['fg_freq']} Hz",
                f"Amp:  {state['fg_amp']:.4f} V",
                "Btn: back",
            ))
            gen.stop()
            state['fg_output_on'] = False

        elif choice == "Off":
            sq_gen.stop()
            sine_gen.stop()
            state['fg_output_on'] = False

        elif choice == "Back":
            sq_gen.stop()
            sine_gen.stop()
            state['fg_output_on'] = False
            return "BACK"

        elif choice == "Main":
            sq_gen.stop()
            sine_gen.stop()
            state['fg_output_on'] = False
            return "MAIN"


def run_frequency_measurement():
    """Live frequency reading on GPIO 5 with Back/Main navigation."""
    state['encoder_delta'] = 0
    state['button_pressed'] = False
    state['button_last_tick'] = None
    clear_callbacks(state)

    DEBOUNCE_US = 200_000
    nav_options = ["Back", "Main"]
    nav_idx = 0

    def _on_rotate(direction):
        state['encoder_delta'] = state.get('encoder_delta', 0) - direction

    def _on_button(_gpio, level, tick):
        if level != 0:
            return
        last = state.get('button_last_tick')
        if last is not None and pigpio.tickDiff(last, tick) < DEBOUNCE_US:
            return
        state['button_last_tick'] = tick
        state['button_pressed'] = True

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, _on_rotate)
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
    state['active_callbacks'] = [decoder, cb_btn]

    freq_meter = FrequencyMeter(pi)

    def _draw_nav():
        if nav_idx == 0:
            lcd.put_line(2, ">Back")
            lcd.put_line(3, " Main")
        else:
            lcd.put_line(2, " Back")
            lcd.put_line(3, ">Main")

    lcd.put_line(0, "Freq Measurement")
    lcd.put_line(1, "Waiting...")
    _draw_nav()

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
            if now - last_update >= 0.5:
                last_update = now
                freq = freq_meter.get_frequency()
                if freq > 0:
                    lcd.put_line(1, f"{freq:.1f} Hz")
                else:
                    lcd.put_line(1, "No signal")

            time.sleep(0.05)
    finally:
        freq_meter.cleanup()
        state['button_pressed'] = False
        clear_callbacks(state)


def run_ohmmeter():
    """Live resistance reading with Back/Main on the same screen."""
    state['encoder_delta'] = 0
    state['button_pressed'] = False
    state['button_last_tick'] = None
    clear_callbacks(state)

    DEBOUNCE_US = 200_000
    nav_options = ["Back", "Main"]
    nav_idx = 0

    def _on_rotate(direction):
        _delta = -direction  # match global inversion
        state['encoder_delta'] = state.get('encoder_delta', 0) + _delta

    def _on_button(_gpio, level, tick):
        if level != 0:
            return
        last = state.get('button_last_tick')
        if last is not None and pigpio.tickDiff(last, tick) < DEBOUNCE_US:
            return
        state['button_last_tick'] = tick
        state['button_pressed'] = True

    import rotary_encoder as _re
    decoder = _re.decoder(pi, PIN_A, PIN_B, _on_rotate)
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
    state['active_callbacks'] = [decoder, cb_btn]

    def _draw_nav():
        if nav_idx == 0:
            lcd.put_line(2, ">Back")
            lcd.put_line(3, " Main")
        else:
            lcd.put_line(2, " Back")
            lcd.put_line(3, ">Main")

    lcd.put_line(0, "Ohmmeter")
    lcd.put_line(1, "Measuring...")
    _draw_nav()

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
            if now - last_update >= 0.5:
                last_update = now
                step = ohm_averaged_measure(pi, spi_ce1, COMPARATOR2_PIN, n=11)
                resistance = step_to_resistance(step)
                tol = ohm_tolerance(step)

                if resistance < 500 or resistance > 10000:
                    lcd.put_line(1, "Not in range")
                else:
                    lcd.put_line(1, f"{resistance:.0f}+/-{tol:.0f} ohm")
                print(f"[Ohmmeter] step={step}  R={resistance:.0f}  tol={tol:.0f}")

            time.sleep(0.05)
    finally:
        state['button_pressed'] = False
        clear_callbacks(state)


def run_voltmeter_menu():
    """Voltmeter -> Source -> External / Internal Reference / Back / Main."""
    while True:
        choice = pick_menu(
            "Source",
            ["External", "Internal Reference", "Back", "Main"],
        )

        if choice == "External":
            result = run_measurement(state, pi, lcd, spi_ce1, source_label="External")
            if result == "MAIN":
                return "MAIN"

        elif choice == "Internal Reference":
            result = run_dc_reference_menu()
            if result == "MAIN":
                return "MAIN"

        elif choice == "Back":
            return "BACK"

        elif choice == "Main":
            return "MAIN"


def run_dc_reference_menu():
    while True:
        choice = pick_menu(
            "DC Reference",
            ["Voltage Value Input", "Output", "Back", "Main"],
        )

        if choice == "Voltage Value Input":
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


print("Starting...")
ensure_all_off()
try:
    while True:
        run_top_screen()

        while True:
            choice = pick_menu(
                "Mode Select",
                ["Function Generator", "Ohmmeter", "Voltmeter", "DC Reference", "Frequency Meas.", "Back", "Main"],
            )

            if choice == "Function Generator":
                result = run_function_generator_menu()

            elif choice == "Ohmmeter":
                result = run_ohmmeter()

            elif choice == "Voltmeter":
                result = run_voltmeter_menu()

            elif choice == "DC Reference":
                result = run_dc_reference_menu()

            elif choice == "Frequency Meas.":
                result = run_frequency_measurement()

            elif choice in ("Back", "Main"):
                break  # go back to top screen

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    print("Cleaning up...")
    sq_gen.cleanup()
    sine_gen.cleanup()
    dc_ref.cleanup()
    clear_callbacks(state)
    lcd.close()
    pi.spi_close(spi_ce0)
    pi.spi_close(spi_ce1)
    pi.stop()
