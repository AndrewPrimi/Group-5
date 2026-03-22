"""
Driver.py – Deliverable 7

Comparator mapping:
  Voltmeter -> GPIO 23
  Ohmmeter  -> GPIO 24
"""

import pigpio
import time

import i2c_lcd
import rotary_encoder
from callbacks import (
    setup_callbacks, clear_callbacks,
    menu_direction_callback, menu_button_callback,
    ohm_button_callback, _redraw_main_menu,
    PIN_A, PIN_B, ROTARY_BTN_PIN,
)
from ohmmeter import (
    open_adc, close_adc,
    averaged_measure,
    step_to_resistance,
    tolerance,
    COMPARATOR2_PIN, MCP4131_MAX_STEPS,
    R_MIN_OHMS, R_MAX_OHMS,
)
from voltmeter import (
    run_source_menu, run_measurement,
    SRC_BACK, SRC_MAIN, SOURCE_LABELS,
)

COMPARATOR1_PIN = 23

DIGIPOT_SPI_CHANNEL = 0
DIGIPOT_SPI_SPEED   = 50000
DIGIPOT_SPI_FLAGS   = 0

MEASURE_INTERVAL = 0.5

pi = pigpio.pi()
if not pi.connected:
    print("Run: sudo pigpiod")
    exit()

lcd = i2c_lcd.lcd(pi, width=20)

digipot_handle = pi.spi_open(
    DIGIPOT_SPI_CHANNEL,
    DIGIPOT_SPI_SPEED,
    DIGIPOT_SPI_FLAGS
)

adc_handle = open_adc(pi)

print(f"Digipot SPI handle : {digipot_handle}")
print(f"ADC SPI handle     : {adc_handle}")

for pin in (PIN_A, PIN_B):
    pi.set_mode(pin, pigpio.INPUT)
    pi.set_pull_up_down(pin, pigpio.PUD_UP)

pi.set_mode(ROTARY_BTN_PIN, pigpio.INPUT)
pi.set_pull_up_down(ROTARY_BTN_PIN, pigpio.PUD_UP)
pi.set_glitch_filter(ROTARY_BTN_PIN, 10000)

pi.set_mode(COMPARATOR1_PIN, pigpio.INPUT)
pi.set_mode(COMPARATOR2_PIN, pigpio.INPUT)

# External pull-ups only
pi.set_pull_up_down(COMPARATOR1_PIN, pigpio.PUD_OFF)
pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_OFF)

state = {
    'menu_selection': 1,
    'isMainPage': True,
    'isOhmPage': False,
    'button_last_tick': None,
    'active_callbacks': [],
}

setup_callbacks(state, pi, lcd)


def show_main_menu():
    lcd.put_line(0, 'Main Menu')
    lcd.put_line(1, 'Mode Select:')
    lcd.put_line(2, '  Ohmmeter')
    lcd.put_line(3, '  Voltmeter')


def run_main_menu():
    state['isMainPage'] = True
    state['menu_selection'] = 1
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
    state['isOhmPage'] = True
    state['button_last_tick'] = None
    clear_callbacks(state)

    lcd.put_line(0, 'Ohmmeter')
    lcd.put_line(1, 'Measuring...')
    lcd.put_line(2, '')
    lcd.put_line(3, 'Hold btn: main')

    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, ohm_button_callback)
    state['active_callbacks'] = [cb_btn]

    last_update = 0

    while state['isOhmPage']:
        if time.time() - last_update >= MEASURE_INTERVAL:
            last_update = time.time()

            step = averaged_measure(pi, adc_handle, COMPARATOR2_PIN, n=11)

            l0, l1, l2, l3 = build_display_lines(step)
            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)

            print(f"[Ohmmeter] step={step}")

        time.sleep(0.05)

    clear_callbacks(state)


def run_voltmeter():
    while True:
        choice = run_source_menu(state, pi, lcd)
        if choice in (SRC_BACK, SRC_MAIN):
            break

        run_measurement(state, pi, lcd, adc_handle,
                        source_label=SOURCE_LABELS[choice])


def format_ohms(ohms):
    if ohms >= 1000:
        return f'{ohms/1000:.2f}k'
    return f'{ohms:.0f}'


def build_display_lines(step):
    r = step_to_resistance(step)
    tol = tolerance(step)

    if step <= 0:
        return "Ohmmeter", "Short circuit", "", "Hold btn: main"

    if step >= MCP4131_MAX_STEPS:
        return "Ohmmeter", "Open circuit", "", "Hold btn: main"

    r_str = format_ohms(r)
    tol_str = format_ohms(tol)

    return (
        "Ohmmeter",
        f"{r_str} Ohms",
        f"+/- {tol_str}",
        "Hold btn: main"
    )


print("Starting system...")

try:
    while True:
        run_main_menu()

        if state['menu_selection'] == 1:
            run_ohmmeter()
        else:
            run_voltmeter()

except KeyboardInterrupt:
    print("\nStopping...")

    clear_callbacks(state)
    lcd.close()
    close_adc(pi, adc_handle)
    pi.spi_close(digipot_handle)
    pi.stop()
