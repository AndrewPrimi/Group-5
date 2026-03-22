"""
Driver.py – Deliverable 7

Voltmeter comparator output -> GPIO 23
Ohmmeter comparator output  -> GPIO 24
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

COMPARATOR1_PIN = 23  # Voltmeter
# COMPARATOR2_PIN imported from ohmmeter.py = 24

DIGIPOT_SPI_CHANNEL = 0
DIGIPOT_SPI_SPEED   = 50_000
DIGIPOT_SPI_FLAGS   = 0

MEASURE_INTERVAL = 0.5

pi = pigpio.pi()
if not pi.connected:
    print("Cannot connect to pigpio daemon. Run 'sudo pigpiod' first.")
    exit(1)

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
pi.set_glitch_filter(ROTARY_BTN_PIN, 10_000)

# Comparator GPIOs
pi.set_mode(COMPARATOR1_PIN, pigpio.INPUT)
pi.set_mode(COMPARATOR2_PIN, pigpio.INPUT)

# Voltmeter path can remain external-pull-up based
pi.set_pull_up_down(COMPARATOR1_PIN, pigpio.PUD_OFF)

# Ohmmeter path: TEST WITH ONLY INTERNAL PULL-UP
pi.set_pull_up_down(COMPARATOR2_PIN, pigpio.PUD_UP)

state = {
    'menu_selection':    1,
    'isMainPage':        True,
    'isOhmPage':         False,
    'button_last_tick':  None,
    'active_callbacks':  [],
}

setup_callbacks(state, pi, lcd)


def show_main_menu():
    lcd.put_line(0, 'Main Menu')
    lcd.put_line(1, 'Mode Select:')
    lcd.put_line(2, '  Ohmmeter')
    lcd.put_line(3, '  Voltmeter')


def run_main_menu():
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
    state['isOhmPage']        = True
    state['button_last_tick'] = None
    clear_callbacks(state)

    lcd.put_line(0, 'Ohmmeter')
    lcd.put_line(1, 'Measuring...')
    lcd.put_line(2, '')
    lcd.put_line(3, 'Hold btn: main menu')

    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, ohm_button_callback)
    state['active_callbacks'] = [cb_btn]

    last_update = 0.0

    while state['isOhmPage']:
        now = time.time()
        if now - last_update >= MEASURE_INTERVAL:
            last_update = now

            step = averaged_measure(pi, adc_handle, COMPARATOR2_PIN, n=11)

            l0, l1, l2, l3 = build_display_lines(step)
            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)

            print(f"[Ohmmeter] step={step}  {l1.strip()}  {l2.strip()}")

        time.sleep(0.05)

    clear_callbacks(state)


def run_voltmeter():
    while True:
        choice = run_source_menu(state, pi, lcd)
        if choice in (SRC_BACK, SRC_MAIN):
            break

        run_measurement(
            state,
            pi,
            lcd,
            adc_handle,
            source_label=SOURCE_LABELS[choice]
        )


def format_ohms(ohms, width=8):
    if ohms >= 1000:
        s = f'{ohms / 1000:.2f}k'
    else:
        s = f'{ohms:.0f}'
    return s.ljust(width)


def build_display_lines(step):
    r = step_to_resistance(step)
    tol = tolerance(step)

    line0 = 'Ohmmeter'

    if step <= 0:
        line1 = 'Short circuit'
        line2 = ''
    elif step >= MCP4131_MAX_STEPS:
        line1 = 'Open circuit'
        line2 = ''
    elif r < R_MIN_OHMS:
        line1 = f'{format_ohms(r).strip()} Ohms'
        line2 = 'Below 500 Ohm range'
    elif r > R_MAX_OHMS:
        line1 = f'{format_ohms(r).strip()} Ohms'
        line2 = 'Above 10k Ohm range'
    else:
        r_str   = format_ohms(r).strip()
        tol_str = format_ohms(tol).strip()
        line1 = f'{r_str} Ohms'
        line2 = f'+/- {tol_str} Ohms'

    line3 = 'Hold btn: main menu'
    return line0, line1, line2, line3


print("Starting Deliverable 7 driver...")

try:
    while True:
        run_main_menu()

        if state['menu_selection'] == 1:
            run_ohmmeter()
        elif state['menu_selection'] == 2:
            run_voltmeter()

except KeyboardInterrupt:
    print("\nStopping...")

    clear_callbacks(state)
    lcd.close()
    close_adc(pi, adc_handle)
    pi.spi_close(digipot_handle)
    pi.stop()
