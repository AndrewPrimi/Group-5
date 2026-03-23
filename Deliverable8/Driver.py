"""
Driver.py  –  Function Generator LCD UI
========================================
LCD + rotary-encoder UI for the SquareWaveGenerator and DCReferenceGenerator.
"""

import pigpio
import time

import i2c_lcd
import rotary_encoder
from square_wave import (
    SquareWaveGenerator,
    MIN_FREQ, MAX_FREQ, FREQ_STEP, MAX_AMP,
)
from dc_reference import DCReferenceGenerator
from sar_logic import SAR_ADC

PIN_A = 22
PIN_B = 27
ROTARY_BTN_PIN = 17

DEBOUNCE_US = 200_000
HOLD_US = 2_000_000

AMP_STEP = 0.1

MIN_DC_VOLT = -5.0
MAX_DC_VOLT = 5.0
DC_VOLT_STEP = 0.625
DC_SPI_CHANNEL = 0
DC_SPI_SPEED = 50_000
DC_SPI_FLAGS = 0

COMPARATOR_PIN = 24
VREF = 5.0
VM_SPI_CHANNEL = 1
VM_SPI_SPEED = 50_000
VM_SPI_FLAGS = 0

pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("Cannot connect to pigpio daemon. Run 'sudo pigpiod' first.")

lcd = i2c_lcd.lcd(pi, width=20)

spi_dc = pi.spi_open(DC_SPI_CHANNEL, DC_SPI_SPEED, DC_SPI_FLAGS)
print(f"[DEBUG] spi_dc handle = {spi_dc}")
if spi_dc < 0:
    raise SystemExit(f"spi_open failed with error {spi_dc}")

gen = SquareWaveGenerator(pi, spi_dc, debug=True)
gen.set_frequency(1000)

dc_ref = DCReferenceGenerator(pi, spi_dc, debug=True)

spi_vm = pi.spi_open(VM_SPI_CHANNEL, VM_SPI_SPEED, VM_SPI_FLAGS)
voltmeter = SAR_ADC(pi, spi_vm, COMPARATOR_PIN)

for pin in (PIN_A, PIN_B):
    pi.set_mode(pin, pigpio.INPUT)
    pi.set_pull_up_down(pin, pigpio.PUD_UP)

pi.set_mode(ROTARY_BTN_PIN, pigpio.INPUT)
pi.set_pull_up_down(ROTARY_BTN_PIN, pigpio.PUD_UP)
pi.set_glitch_filter(ROTARY_BTN_PIN, 10_000)

state = {
    'wave_type': 'Square',
    'frequency': 1000,
    'amplitude': 0.0,
    'output_on': False,
    'dc_voltage': 0.0,
    'dc_output_on': False,
    'active_callbacks': [],
    'button_last_tick': None,
    'button_press_tick': None,
    'button_pressed': False,
    'button_held': False,
    'encoder_delta': 0,
}


def clear_callbacks():
    for cb in state['active_callbacks']:
        cb.cancel()
    state['active_callbacks'] = []


def _button_cb(gpio, level, tick):
    if level == 0:
        last = state['button_last_tick']
        if last is not None and pigpio.tickDiff(last, tick) < DEBOUNCE_US:
            return
        state['button_last_tick'] = tick
        state['button_press_tick'] = tick

    elif level == 1:
        press_tick = state['button_press_tick']
        if press_tick is not None:
            if pigpio.tickDiff(press_tick, tick) >= HOLD_US:
                state['button_held'] = True
            else:
                state['button_pressed'] = True
            state['button_press_tick'] = None


def _encoder_cb(direction):
    state['encoder_delta'] += direction


def _attach_callbacks():
    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, _encoder_cb)
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.EITHER_EDGE, _button_cb)
    state['active_callbacks'] = [decoder, cb_btn]


def _reset_input():
    state['button_pressed'] = False
    state['button_held'] = False
    state['encoder_delta'] = 0


def _ensure_modes_do_not_conflict(prefer):
    """
    Only one owner should actively drive the shared MCP4231 at a time.
    """
    if prefer == 'square' and state['dc_output_on']:
        dc_ref.stop(clear_to_zero=False)
        state['dc_output_on'] = False
        print("[Driver] DC reference paused because square wave output was enabled")

    elif prefer == 'dc' and state['output_on']:
        gen.stop(clear_wipers=False)
        state['output_on'] = False
        print("[Driver] Square wave paused because DC reference was enabled")


def pick_menu(title, options):
    idx = 0
    _reset_input()

    def _redraw():
        window = max(0, min(idx - 1, len(options) - 3))
        lcd.put_line(0, title[:20])
        for row in range(3):
            i = window + row
            if i < len(options):
                prefix = '>' if i == idx else ' '
                lcd.put_line(row + 1, f"{prefix} {options[i]}"[:20])
            else:
                lcd.put_line(row + 1, '')

    _redraw()
    _attach_callbacks()

    while True:
        if state['encoder_delta'] != 0:
            idx = (idx + state['encoder_delta']) % len(options)
            state['encoder_delta'] = 0
            _redraw()

        if state['button_pressed']:
            state['button_pressed'] = False
            clear_callbacks()
            return options[idx]

        if state['button_held']:
            state['button_held'] = False
            clear_callbacks()
            return 'Back'

        time.sleep(0.02)


def adjust_value(title, value, min_val, max_val, step, fmt):
    _reset_input()

    def _redraw():
        lcd.put_line(0, title[:20])
        lcd.put_line(1, fmt(value)[:20])
        lcd.put_line(2, 'Turn to adjust'[:20])
        lcd.put_line(3, 'Btn:OK  Hold:cancel')

    _redraw()
    _attach_callbacks()

    while True:
        if state['encoder_delta'] != 0:
            value += state['encoder_delta'] * step
            value = max(min_val, min(max_val, value))
            value = round(round(value / step) * step, 10)
            state['encoder_delta'] = 0
            _redraw()

        if state['button_pressed']:
            state['button_pressed'] = False
            clear_callbacks()
            return value

        if state['button_held']:
            state['button_held'] = False
            clear_callbacks()
            return None

        time.sleep(0.02)


def run_type_menu():
    while True:
        choice = pick_menu(f"TYPE: {state['wave_type']}", ['Square', 'Back'])
        if choice == 'Square':
            state['wave_type'] = 'Square'
            lcd.put_line(0, 'Type set: Square')
            lcd.put_line(1, '')
            lcd.put_line(2, '')
            lcd.put_line(3, '')
            time.sleep(0.8)
            return
        elif choice == 'Back':
            return


def run_frequency_menu():
    while True:
        choice = pick_menu(
            f"FREQ: {state['frequency']}Hz",
            ['Adjust', 'Back'],
        )
        if choice == 'Adjust':
            new_val = adjust_value(
                'FREQUENCY',
                float(state['frequency']),
                MIN_FREQ, MAX_FREQ, FREQ_STEP,
                lambda v: f"{int(v)} Hz",
            )
            if new_val is not None:
                state['frequency'] = int(new_val)
                gen.set_frequency(state['frequency'])
        elif choice == 'Back':
            return


def run_amplitude_menu():
    while True:
        choice = pick_menu(
            f"AMP: {state['amplitude']:.1f} V",
            ['Adjust', 'Back'],
        )
        if choice == 'Adjust':
            new_val = adjust_value(
                'AMPLITUDE',
                state['amplitude'],
                0.0, MAX_AMP, AMP_STEP,
                lambda v: f"{v:.1f} V",
            )
            if new_val is not None:
                state['amplitude'] = round(new_val, 1)
                gen.set_amplitude(state['amplitude'])
                print(
                    f"[Driver] amplitude set to {state['amplitude']:.1f} V  "
                    f"W0={gen.last_w0}  W1={gen.last_w1}"
                )
        elif choice == 'Back':
            return


def run_live_display():
    _reset_input()

    def _redraw():
        period_ms = 1000.0 / state['frequency']
        amp = state['amplitude']

        lcd.put_line(0, f"LIVE OUT  {state['frequency']}Hz")
        lcd.put_line(1, f"Amp:{amp:.1f} V")
        lcd.put_line(2, f"T:{period_ms:.2f}ms  DC:50%")
        lcd.put_line(3, 'Hold btn: back')

    _redraw()
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.EITHER_EDGE, _button_cb)
    state['active_callbacks'] = [cb_btn]

    last_refresh = time.time()
    while True:
        if time.time() - last_refresh >= 0.25:
            _redraw()
            last_refresh = time.time()

        if state['button_held']:
            state['button_held'] = False
            clear_callbacks()
            return

        time.sleep(0.02)


def run_output_menu():
    while True:
        status = 'ON' if state['output_on'] else 'OFF'
        choice = pick_menu(f"OUTPUT: {status}", ['On', 'Off', 'Back'])
        if choice == 'On':
            _ensure_modes_do_not_conflict('square')
            gen.set_frequency(state['frequency'])
            gen.set_amplitude(state['amplitude'])
            gen.start()
            state['output_on'] = True
            run_live_display()
        elif choice == 'Off':
            gen.stop(clear_wipers=False)
            state['output_on'] = False
        elif choice == 'Back':
            if state['output_on']:
                gen.stop(clear_wipers=False)
                state['output_on'] = False
            return


def run_dc_live_display():
    _reset_input()

    def _redraw():
        measured, _ = voltmeter.read_voltage(VREF)
        lcd.put_line(0, 'DC REF ON')
        lcd.put_line(1, f"Set:  {state['dc_voltage']:.3f} V")
        lcd.put_line(2, f"Meas: {measured:.2f} V")
        lcd.put_line(3, 'Hold btn: back')

    _redraw()
    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.EITHER_EDGE, _button_cb)
    state['active_callbacks'] = [cb_btn]

    last_refresh = time.time()
    while True:
        if time.time() - last_refresh >= 0.25:
            _redraw()
            last_refresh = time.time()

        if state['button_held']:
            state['button_held'] = False
            clear_callbacks()
            return

        time.sleep(0.02)


def run_dc_voltage_menu():
    while True:
        choice = pick_menu(
            f"DC VOLT: {state['dc_voltage']:.3f}V",
            ['Adjust', 'Back'],
        )
        if choice == 'Adjust':
            new_val = adjust_value(
                'DC VOLTAGE (-5 to 5V)',
                state['dc_voltage'],
                MIN_DC_VOLT, MAX_DC_VOLT, DC_VOLT_STEP,
                lambda v: f"{v:.3f} V",
            )
            if new_val is not None:
                state['dc_voltage'] = round(new_val, 3)
                dc_ref.set_voltage(state['dc_voltage'])
        elif choice == 'Back':
            return


def run_dc_output_menu():
    while True:
        status = 'ON' if state['dc_output_on'] else 'OFF'
        choice = pick_menu(f"DC OUTPUT: {status}", ['On', 'Off', 'Back', 'Main'])
        if choice == 'On':
            _ensure_modes_do_not_conflict('dc')
            dc_ref.set_voltage(state['dc_voltage'])
            dc_ref.start()
            state['dc_output_on'] = True
            run_dc_live_display()
            dc_ref.stop(clear_to_zero=False)
            state['dc_output_on'] = False
        elif choice == 'Off':
            dc_ref.stop(clear_to_zero=False)
            state['dc_output_on'] = False
        elif choice == 'Back':
            if state['dc_output_on']:
                dc_ref.stop(clear_to_zero=False)
                state['dc_output_on'] = False
            return False
        elif choice == 'Main':
            if state['dc_output_on']:
                dc_ref.stop(clear_to_zero=False)
                state['dc_output_on'] = False
            return True


def run_dc_reference_menu():
    while True:
        choice = pick_menu('DC REFERENCE', ['Voltage', 'Output', 'Back'])
        if choice == 'Voltage':
            run_dc_voltage_menu()
        elif choice == 'Output':
            go_main = run_dc_output_menu()
            if go_main:
                return True
        elif choice == 'Back':
            if state['dc_output_on']:
                dc_ref.stop(clear_to_zero=False)
                state['dc_output_on'] = False
            return False


def run_main_menu():
    while True:
        choice = pick_menu(
            'FUNC GENERATOR',
            ['Type', 'Frequency', 'Amplitude', 'Output', 'DC Reference', 'Quit'],
        )
        if choice == 'Type':
            run_type_menu()
        elif choice == 'Frequency':
            run_frequency_menu()
        elif choice == 'Amplitude':
            run_amplitude_menu()
        elif choice == 'Output':
            run_output_menu()
        elif choice == 'DC Reference':
            run_dc_reference_menu()
        elif choice in ('Quit', 'Back'):
            if state['output_on']:
                gen.stop(clear_wipers=False)
            if state['dc_output_on']:
                dc_ref.stop(clear_to_zero=False)
            lcd.put_line(0, 'Goodbye!')
            lcd.put_line(1, '')
            lcd.put_line(2, '')
            lcd.put_line(3, '')
            return


print("Starting Deliverable 8 driver...")

try:
    run_main_menu()
except KeyboardInterrupt:
    print("\nStopping...")
finally:
    if state['output_on']:
        gen.stop(clear_wipers=False)
    if state['dc_output_on']:
        dc_ref.stop(clear_to_zero=False)

    gen.cleanup()
    dc_ref.cleanup()
    pi.spi_close(spi_dc)
    pi.spi_close(spi_vm)
    clear_callbacks()
    lcd.close()
    pi.stop()
