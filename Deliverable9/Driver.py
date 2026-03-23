"""
Driver.py

Integrated UI driver for:
- Ohmmeter      (ohmmeter.py + ohms_steps.py)
- Voltmeter     (sar_logic.py)
- DC Reference  (dc_reference.py)

Works with:
- i2c_lcd.py
- rotary_encoder.py
- callbacks.py
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
    show_main_menu,
    show_dc_reference_page,
    menu_direction_callback,
    menu_button_callback,
    ohm_button_callback,
    volt_button_callback,
    dc_ref_direction_callback,
    dc_ref_button_callback,
)

from ohmmeter import (
    open_adc,
    close_adc,
    averaged_measure,
    step_to_resistance,
    tolerance,
    COMPARATOR2_PIN,
    MCP4131_MAX_STEPS,
)

from ohms_steps import (
    MINIMUM_OHMS,
    MAXIMUM_OHMS,
    step_to_ohms,
    fix_ohms,
)

from sar_logic import SAR_ADC
from dc_reference import DCReferenceGenerator

# ─────────────────────────────────────────────────────────────────────────────
# Hardware / system constants
# ─────────────────────────────────────────────────────────────────────────────

MEASURE_INTERVAL = 0.5

# Separate SPI handle for MCP4231 bipolar DC reference
DCREF_SPI_CHANNEL = 0
DCREF_SPI_SPEED = 50_000
DCREF_SPI_FLAGS = 0

# Comparator pin for voltmeter SAR logic
VOLT_COMPARATOR_PIN = 23

# SAR voltage reference used by read_voltage()
VOLT_VREF = 5.0


# ─────────────────────────────────────────────────────────────────────────────
# Helper formatting
# ─────────────────────────────────────────────────────────────────────────────

def fmt_ohms(value):
    if value == float("inf"):
        return "Open"
    if value >= 1000:
        return f"{value / 1000:.2f}k"
    return f"{value:.0f}"


def fmt_volts(value):
    return f"{value:+.2f}V"


def build_ohmmeter_lines(step):
    """
    Build LCD lines for ohmmeter page.

    Uses:
    - ohmmeter.py for actual calibrated resistance measurement
    - ohms_steps.py for helper conversion / display integration
    """
    if step <= 0:
        return (
            "Ohmmeter",
            "Open circuit",
            "Step: 0",
            "Btn: back",
        )

    if step >= MCP4131_MAX_STEPS:
        return (
            "Ohmmeter",
            "Short circuit",
            f"Step: {step}",
            "Btn: back",
        )

    measured = step_to_resistance(step)
    tol = tolerance(step)

    # Map 5-bit SAR step (0..31) to 7-bit code (0..127) so ohms_steps.py
    # is integrated into the display meaningfully.
    mapped_code = round(step * 127 / MCP4131_MAX_STEPS)
    approx_pot_ohms = fix_ohms(step_to_ohms(mapped_code))

    if measured < MINIMUM_OHMS:
        status = "Below range"
    elif measured > MAXIMUM_OHMS:
        status = "Above range"
    else:
        status = f"+/- {fmt_ohms(tol)}"

    line1 = f"R: {fmt_ohms(measured)}"
    line2 = status
    line3 = f"S:{step:02d} P:{fmt_ohms(approx_pot_ohms)}"

    return (
        "Ohmmeter",
        line1[:20],
        line2[:20],
        line3[:20],
    )


def build_voltmeter_lines(voltage, step):
    return (
        "Voltmeter",
        f"Vin: {fmt_volts(voltage)}"[:20],
        f"Step: {step:03d}"[:20],
        "Btn: back",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page runners
# ─────────────────────────────────────────────────────────────────────────────

def run_main_menu(state, pi, lcd):
    state["isMainPage"] = True
    state["menu_selection"] = 0
    state["button_last_tick"] = None

    clear_callbacks(state)
    show_main_menu()

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, menu_direction_callback)
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, menu_button_callback)

    state["active_callbacks"] = [decoder, cb_btn]

    while state["isMainPage"]:
        time.sleep(0.05)

    clear_callbacks(state)
    return state.get("selected_mode", 0)


def run_ohmmeter(state, pi, lcd, adc_handle):
    state["isOhmPage"] = True
    state["button_last_tick"] = None

    clear_callbacks(state)

    lcd.put_line(0, "Ohmmeter")
    lcd.put_line(1, "Measuring...")
    lcd.put_line(2, "")
    lcd.put_line(3, "Btn: back")

    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, ohm_button_callback)
    state["active_callbacks"] = [cb_btn]

    last_update = 0.0

    while state["isOhmPage"]:
        now = time.time()
        if now - last_update >= MEASURE_INTERVAL:
            last_update = now

            step = averaged_measure(pi, adc_handle, COMPARATOR2_PIN, n=11)
            l0, l1, l2, l3 = build_ohmmeter_lines(step)

            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)

            print(f"[Ohmmeter] step={step:02d} | {l1.strip()} | {l2.strip()} | {l3.strip()}")

        time.sleep(0.05)

    clear_callbacks(state)


def run_voltmeter(state, pi, lcd, sar_adc):
    state["isVoltPage"] = True
    state["button_last_tick"] = None

    clear_callbacks(state)

    lcd.put_line(0, "Voltmeter")
    lcd.put_line(1, "Measuring...")
    lcd.put_line(2, "")
    lcd.put_line(3, "Btn: back")

    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, volt_button_callback)
    state["active_callbacks"] = [cb_btn]

    last_update = 0.0

    while state["isVoltPage"]:
        now = time.time()
        if now - last_update >= MEASURE_INTERVAL:
            last_update = now

            voltage, step = sar_adc.read_voltage(VOLT_VREF)
            l0, l1, l2, l3 = build_voltmeter_lines(voltage, step)

            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)

            print(f"[Voltmeter] voltage={voltage:+.3f} V | step={step}")

        time.sleep(0.05)

    clear_callbacks(state)


def run_dc_reference(state, pi, lcd, dc_ref):
    state["isDCRefPage"] = True
    state["button_last_tick"] = None
    state["dc_ref_obj"] = dc_ref
    state["dc_ref_enabled"] = True

    clear_callbacks(state)

    # Start output at current stored voltage
    dc_ref.start()
    show_dc_reference_page()

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, dc_ref_direction_callback)
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, dc_ref_button_callback)

    state["active_callbacks"] = [decoder, cb_btn]

    while state["isDCRefPage"]:
        time.sleep(0.05)

    clear_callbacks(state)

    # Return safely to 0 V when exiting page
    state["dc_ref_enabled"] = False
    dc_ref.stop()


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
        # LCD
        lcd = i2c_lcd.lcd(pi, width=20)

        # Shared measurement SPI handle from ohmmeter.py (CE1)
        adc_handle = open_adc(pi)

        # Separate SPI handle for bipolar DC reference (CE0)
        dc_spi_handle = pi.spi_open(DCREF_SPI_CHANNEL, DCREF_SPI_SPEED, DCREF_SPI_FLAGS)

        # GPIO setup
        for pin in (PIN_A, PIN_B):
            pi.set_mode(pin, pigpio.INPUT)
            pi.set_pull_up_down(pin, pigpio.PUD_UP)

        pi.set_mode(ROTARY_BTN_PIN, pigpio.INPUT)
        pi.set_pull_up_down(ROTARY_BTN_PIN, pigpio.PUD_UP)
        pi.set_glitch_filter(ROTARY_BTN_PIN, 10_000)

        # Voltmeter comparator input
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

        state = {
            "menu_selection": 0,
            "selected_mode": 0,
            "active_callbacks": [],
            "button_last_tick": None,

            "isMainPage": True,
            "isOhmPage": False,
            "isVoltPage": False,
            "isDCRefPage": False,

            "dc_ref_voltage": 0.0,
            "dc_ref_step_size": 0.1,
            "dc_ref_enabled": False,
            "dc_ref_obj": None,
        }

        setup_callbacks(state, pi, lcd)

        print("Starting integrated driver...")

        while True:
            mode = run_main_menu(state, pi, lcd)

            if mode == 0:
                run_ohmmeter(state, pi, lcd, adc_handle)

            elif mode == 1:
                run_voltmeter(state, pi, lcd, sar_adc)

            elif mode == 2:
                run_dc_reference(state, pi, lcd, dc_ref)

    except KeyboardInterrupt:
        print("\nStopping program...")

    finally:
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
