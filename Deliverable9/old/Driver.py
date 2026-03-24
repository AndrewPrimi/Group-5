"""
Driver.py

Integrated LCD UI driver following this structure:

Mode Select
1. Function Generator
2. Ohmmeter
3. Voltmeter
4. DC Reference
5. Back
6. Main

Function Generator
- Type
- Frequency
- Amplitude
- Output
- Back
- Main

Voltmeter
- Source
- Back
- Main

DC Reference
- Voltage Value Input
- Output
- Back
- Main

This version integrates:
- i2c_lcd.py
- rotary_encoder.py (through callbacks.py)
- ohmmeter.py
- ohms_steps.py
- dc_reference.py
- sar_logic.py

It also keeps a placeholder function-generator branch so the UI tree
matches your required structure even if the waveform path is still being
finished.
"""

import time
import pigpio

import i2c_lcd

from callbacks import (
    PIN_A,
    PIN_B,
    ROTARY_BTN_PIN,
    setup_callbacks,
    pick_menu,
    adjust_value,
    wait_for_back_page,
    clear_callbacks,
)

from ohmmeter import (
    open_adc,
    close_adc,
    averaged_measure as ohm_averaged_measure,
    step_to_resistance,
    tolerance as ohm_tolerance,
    COMPARATOR2_PIN as OHM_COMPARATOR_PIN,
    MCP4131_MAX_STEPS,
)

from ohms_steps import (
    MINIMUM_OHMS,
    MAXIMUM_OHMS,
    ohms_to_step,
    step_to_ohms,
)

from dc_reference import DCReferenceGenerator
from sar_logic import SAR_ADC

from square_wave import (
    SquareWaveGenerator,
    MIN_FREQ,
    MAX_FREQ,
    FREQ_STEP,
    MAX_AMP,
)

# Optional function generator integration
try:
    from square_wave import (
        SquareWaveGenerator,
        MIN_FREQ,
        MAX_FREQ,
        FREQ_STEP,
        MAX_AMP,
    )
    HAVE_SQUARE_WAVE = True
except Exception:
    SquareWaveGenerator = None
    MIN_FREQ = 100
    MAX_FREQ = 10000
    FREQ_STEP = 10
    MAX_AMP = 10.0
    HAVE_SQUARE_WAVE = False


# ─────────────────────────────────────────────────────────────────────────────
# Hardware constants
# ─────────────────────────────────────────────────────────────────────────────

MEASURE_INTERVAL = 0.4

# CE1 used by open_adc() for measurement-side digipot / SAR path
# CE0 used separately for bipolar DC reference
DCREF_SPI_CHANNEL = 0
DCREF_SPI_SPEED = 50_000
DCREF_SPI_FLAGS = 0

VOLT_COMPARATOR_PIN = 23
VOLT_VREF = 5.0


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def fmt_ohms(value):
    if value == float("inf"):
        return "Open"
    if value >= 1000:
        return f"{value / 1000:.2f}k"
    return f"{value:.0f}"


def fmt_volts(value):
    return f"{value:+.2f}V"


def fmt_hz(value):
    return f"{int(round(value))} Hz"


# ─────────────────────────────────────────────────────────────────────────────
# Function generator wrappers
# ─────────────────────────────────────────────────────────────────────────────

def fg_apply_settings(state):
    gen = state.get("fg_obj")
    if gen is None:
        return

    freq = state["fg_frequency"]
    amp = state["fg_amplitude"]

    # Try common method names safely.
    for method_name in ("set_frequency", "set_freq"):
        method = getattr(gen, method_name, None)
        if callable(method):
            try:
                method(freq)
            except Exception:
                pass
            break

    for method_name in ("set_amplitude", "set_amp"):
        method = getattr(gen, method_name, None)
        if callable(method):
            try:
                method(amp)
            except Exception:
                pass
            break


def fg_start(state):
    gen = state.get("fg_obj")
    if gen is None:
        return
    fg_apply_settings(state)
    try:
        gen.start()
        state["fg_output_on"] = True
    except Exception:
        state["fg_output_on"] = False


def fg_stop(state):
    gen = state.get("fg_obj")
    if gen is None:
        state["fg_output_on"] = False
        return
    try:
        gen.stop()
    except Exception:
        pass
    state["fg_output_on"] = False


# ─────────────────────────────────────────────────────────────────────────────
# Ohmmeter helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_ohm_lines(pi, adc_handle):
    step = ohm_averaged_measure(pi, adc_handle, OHM_COMPARATOR_PIN, n=11)

    if step <= 0:
        return (
            "Ohmmeter",
            "Reading: Open",
            "Threshold: ---",
            "Btn: Back",
        )

    if step >= MCP4131_MAX_STEPS:
        return (
            "Ohmmeter",
            "Reading: Short",
            "Threshold: ---",
            "Btn: Back",
        )

    measured = step_to_resistance(step)
    tol = ohm_tolerance(step)

    mapped_code = round(step * 127 / MCP4131_MAX_STEPS)
    approx_pot_ohms = fix_ohms(step_to_ohms(mapped_code))

    if measured < MINIMUM_OHMS:
        threshold = f"Below {MINIMUM_OHMS} ohm"
    elif measured > MAXIMUM_OHMS:
        threshold = f"Above {MAXIMUM_OHMS//1000}0k ohm"
    else:
        threshold = f"+/- {fmt_ohms(tol)}"

    return (
        "Ohmmeter",
        f"R: {fmt_ohms(measured)}",
        threshold[:20],
        f"S:{step:02d} P:{fmt_ohms(approx_pot_ohms)}"[:20],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Voltmeter helpers
# ─────────────────────────────────────────────────────────────────────────────

def build_volt_lines(state):
    sar = state["sar_adc"]
    voltage, step = sar.read_voltage(VOLT_VREF)
    source = state.get("volt_source_label", "External")

    return (
        "Voltmeter",
        f"Src: {source}"[:20],
        f"Vin: {fmt_volts(voltage)}  S:{step}"[:20],
        "Thr: +/-0.15 V",
    )


# ─────────────────────────────────────────────────────────────────────────────
# DC reference helpers
# ─────────────────────────────────────────────────────────────────────────────

def dc_apply_voltage(state):
    dc_ref = state.get("dc_ref_obj")
    if dc_ref is None:
        return
    dc_ref.set_voltage(state["dc_voltage"])


def dc_start(state):
    dc_ref = state.get("dc_ref_obj")
    if dc_ref is None:
        return
    dc_ref.set_voltage(state["dc_voltage"])
    dc_ref.start()
    state["dc_output_on"] = True


def dc_stop(state):
    dc_ref = state.get("dc_ref_obj")
    if dc_ref is None:
        state["dc_output_on"] = False
        return
    dc_ref.stop()
    state["dc_output_on"] = False


def build_dc_output_lines(state):
    # Use the voltmeter SAR path to display generated output, per your requirement.
    sar = state["sar_adc"]
    voltage, step = sar.read_voltage(VOLT_VREF)

    return (
        "DC Ref Output",
        f"Set: {fmt_volts(state['dc_voltage'])}"[:20],
        f"Read:{fmt_volts(voltage)}"[:20],
        f"Step:{step} Btn:Back"[:20],
    )


def build_fg_output_lines(state):
    return (
        "Function Output",
        f"Type: {state['fg_type']}"[:20],
        f"F:{fmt_hz(state['fg_frequency'])}"[:20],
        f"A:{state['fg_amplitude']:.1f}V Btn"[:20],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Menus
# ─────────────────────────────────────────────────────────────────────────────

def run_function_generator_menu(state):
    while True:
        choice = pick_menu(
            "Function Generator",
            ["Type", "Frequency", "Amplitude", "Output", "Back", "Main"],
        )

        if choice == "Type":
            result = pick_menu("Type", ["Square", "Back", "Main"])
            if result == "Square":
                state["fg_type"] = "Square"
            elif result == "Main":
                fg_stop(state)
                return "MAIN"

        elif choice == "Frequency":
            result = pick_menu("Frequency", ["Input Frequency", "Back", "Main"])
            if result == "Input Frequency":
                new_val = adjust_value(
                    "Input Frequency",
                    state["fg_frequency"],
                    MIN_FREQ,
                    MAX_FREQ,
                    FREQ_STEP,
                    fmt_hz,
                )
                if new_val is not None:
                    state["fg_frequency"] = int(new_val)
                    fg_apply_settings(state)
            elif result == "Main":
                fg_stop(state)
                return "MAIN"

        elif choice == "Amplitude":
            result = pick_menu("Amplitude", ["Input Amplitude", "Back", "Main"])
            if result == "Input Amplitude":
                new_val = adjust_value(
                    "Input Amplitude",
                    state["fg_amplitude"],
                    0.0,
                    MAX_AMP,
                    0.1,
                    lambda v: f"{v:.1f} V",
                )
                if new_val is not None:
                    state["fg_amplitude"] = float(new_val)
                    fg_apply_settings(state)
            elif result == "Main":
                fg_stop(state)
                return "MAIN"

        elif choice == "Output":
            out_choice = pick_menu("FG Output", ["On", "Off", "Back", "Main"])

            if out_choice == "On":
                fg_start(state)
                wait_for_back_page(lambda: build_fg_output_lines(state), refresh_s=0.25)
                # per your requirement, leaving the live output page turns it off by default
                fg_stop(state)

            elif out_choice == "Off":
                fg_stop(state)

            elif out_choice == "Main":
                fg_stop(state)
                return "MAIN"

        elif choice == "Back":
            fg_stop(state)
            return "BACK"

        elif choice == "Main":
            fg_stop(state)
            return "MAIN"


def run_ohmmeter_menu(state, pi, adc_handle):
    while True:
        choice = pick_menu("Ohmmeter", ["Back", "Main"])

        if choice == "Back":
            # Show live reading first, then go back one level
            wait_for_back_page(lambda: build_ohm_lines(pi, adc_handle), refresh_s=MEASURE_INTERVAL)
            return "BACK"

        elif choice == "Main":
            wait_for_back_page(lambda: build_ohm_lines(pi, adc_handle), refresh_s=MEASURE_INTERVAL)
            return "MAIN"


def run_ohmmeter_live(state, pi, adc_handle):
    wait_for_back_page(lambda: build_ohm_lines(pi, adc_handle), refresh_s=MEASURE_INTERVAL)


def run_voltmeter_menu(state):
    while True:
        choice = pick_menu("Voltmeter", ["Source", "Back", "Main"])

        if choice == "Source":
            src = pick_menu("Source", ["External", "Internal Ref", "Back", "Main"])

            if src == "External":
                state["volt_source_label"] = "External"
                wait_for_back_page(lambda: build_volt_lines(state), refresh_s=MEASURE_INTERVAL)

            elif src == "Internal Ref":
                state["volt_source_label"] = "Int Ref"
                result = run_dc_reference_menu(state, from_voltmeter=True)
                if result == "MAIN":
                    return "MAIN"

            elif src == "Main":
                return "MAIN"

        elif choice == "Back":
            return "BACK"

        elif choice == "Main":
            return "MAIN"


def run_dc_reference_menu(state, from_voltmeter=False):
    while True:
        choice = pick_menu(
            "DC Reference",
            ["Voltage Input", "Output", "Back", "Main"],
        )

        if choice == "Voltage Input":
            new_val = adjust_value(
                "Voltage Value Input",
                state["dc_voltage"],
                -5.0,
                5.0,
                0.1,
                lambda v: f"{v:+.1f} V",
            )
            if new_val is not None:
                state["dc_voltage"] = float(new_val)
                dc_apply_voltage(state)

        elif choice == "Output":
            out_choice = pick_menu("DC Output", ["On", "Off", "Back", "Main"])

            if out_choice == "On":
                dc_start(state)
                wait_for_back_page(lambda: build_dc_output_lines(state), refresh_s=MEASURE_INTERVAL)
                # per your requirement, backing out turns it off by default
                dc_stop(state)

            elif out_choice == "Off":
                dc_stop(state)

            elif out_choice == "Main":
                dc_stop(state)
                return "MAIN"

        elif choice == "Back":
            dc_stop(state)
            return "BACK"

        elif choice == "Main":
            dc_stop(state)
            return "MAIN"

        
# ─────────────────────────────────────────────────────────────
# Potentiometer Menu
# ─────────────────────────────────────────────────────────────

def run_potentiometer_menu(state):
    while True:
        choice = pick_menu(
            "Potentiometer",
            ["Variable", "Constant", "Back", "Main"],
        )

        if choice == "Variable":
            run_pot_variable(state)

        elif choice == "Constant":
            run_pot_constant(state)

        elif choice == "Back":
            return "BACK"

        elif choice == "Main":
            return "MAIN"


def run_pot_variable(state):
    value = state.get("pot_ohms", 1000)

    new_val = adjust_value(
        "Set Resistance",
        value,
        MINIMUM_OHMS,
        MAXIMUM_OHMS,
        10,
        lambda v: f"{int(v)} ohm",
    )

    if new_val is None:
        return

    value = int(new_val)
    state["pot_ohms"] = value

    step = ohms_to_step(value)
    state["pot_step"] = step

    wait_for_back_page(lambda: (
        "Potentiometer",
        f"Set: {value} ohm",
        f"Step: {step}",
        "Btn: Back",
    ))


def run_pot_constant(state):
    presets = [100, 1000, 5000, 10000]

    labels = [f"{p} ohm" for p in presets]

    choice = pick_menu("Const Res", labels + ["Back", "Main"])

    if choice in ("Back", "Main"):
        return

    value = presets[labels.index(choice)]

    state["pot_ohms"] = value
    step = ohms_to_step(value)
    state["pot_step"] = step

    wait_for_back_page(lambda: (
        "Const Mode",
        f"Set: {value} ohm",
        f"Step: {step}",
        "Btn: Back",
    ))

        

def run_main_menu(state, pi, adc_handle):
    while True:
        choice = pick_menu(
            "Mode Select",
            ["Function Generator", "Ohmmeter", "Voltmeter", "DC Reference", "Potentiometer", "Back", "Main"],
        )

        if choice == "Function Generator":
            result = run_function_generator_menu(state)
            if result == "MAIN":
                continue

        elif choice == "Ohmmeter":
            # direct live reading matches your note that UI shows reading and threshold
            run_ohmmeter_live(state, pi, adc_handle)

        elif choice == "Voltmeter":
            result = run_voltmeter_menu(state)
            if result == "MAIN":
                continue

        elif choice == "DC Reference":
            result = run_dc_reference_menu(state)
            if result == "MAIN":
                continue

        elif choice == "Potentiometer":
            result = run_potentiometer_menu(state)
            if result == "MAIN":
                continue
            
        elif choice == "Back":
            fg_stop(state)
            dc_stop(state)

        elif choice == "Main":
            fg_stop(state)
            dc_stop(state)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("Cannot connect to pigpio daemon. Run: sudo pigpiod")
        raise SystemExit(1)

    lcd = None
    adc_handle = None
    dc_spi_handle = None

    try:
        lcd = i2c_lcd.lcd(pi, width=20)

        adc_handle = open_adc(pi)
        dc_spi_handle = pi.spi_open(DCREF_SPI_CHANNEL, DCREF_SPI_SPEED, DCREF_SPI_FLAGS)

        # GPIO setup
        for pin in (PIN_A, PIN_B):
            pi.set_mode(pin, pigpio.INPUT)
            pi.set_pull_up_down(pin, pigpio.PUD_UP)

        pi.set_mode(ROTARY_BTN_PIN, pigpio.INPUT)
        pi.set_pull_up_down(ROTARY_BTN_PIN, pigpio.PUD_UP)
        pi.set_glitch_filter(ROTARY_BTN_PIN, 10_000)

        pi.set_mode(VOLT_COMPARATOR_PIN, pigpio.INPUT)
        pi.set_pull_up_down(VOLT_COMPARATOR_PIN, pigpio.PUD_OFF)

        # Objects
        sar_adc = SAR_ADC(
            pi=pi,
            spi_handle=adc_handle,
            comparator_pin=VOLT_COMPARATOR_PIN,
            selected_pot=0,
            settle_time=0.002,
            invert_comparator=False,
        )

        dc_ref = DCReferenceGenerator(
            pi=pi,
            spi_handle=dc_spi_handle,
            settle_time=0.001,
        )

        fg_obj = None
        if HAVE_SQUARE_WAVE and SquareWaveGenerator is not None:
            try:
                # If your constructor differs, adjust here.
                fg_obj = SquareWaveGenerator(pi)
            except Exception:
                fg_obj = None

        state = {
            "active_callbacks": [],
            "button_last_tick": None,
            "button_press_tick": None,
            "button_pressed": False,
            "button_held": False,
            "encoder_delta": 0,

            "fg_type": "Square",
            "fg_frequency": 1000,
            "fg_amplitude": 0.0,
            "fg_output_on": False,
            "fg_obj": fg_obj,

            "dc_voltage": 0.0,
            "dc_output_on": False,
            "dc_ref_obj": dc_ref,

            "volt_source_label": "External",
            "sar_adc": sar_adc,

            #"pot_ohms": 5000,
            #"pot_step": 0,
        }

        setup_callbacks(state, pi, lcd)

        print("Starting integrated driver...")
        run_main_menu(state, pi, adc_handle)

    except KeyboardInterrupt:
        print("\nStopping program...")

    finally:
        try:
            fg_stop(state)  # safe if state exists
        except Exception:
            pass

        try:
            dc_stop(state)
        except Exception:
            pass

        clear_callbacks()

        if lcd is not None:
            try:
                lcd.close()
            except Exception:
                pass

        if adc_handle is not None:
            try:
                close_adc(pi, adc_handle)
            except Exception:
                pass

        if dc_spi_handle is not None:
            try:
                pi.spi_close(dc_spi_handle)
            except Exception:
                pass

        pi.stop()


if __name__ == "__main__":
    main()
