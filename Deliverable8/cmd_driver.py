"""
cmd_driver.py  –  Temporary command-line UI (LCD replacement)
=============================================================
Mirrors the LCD menu from Driver.py entirely in the terminal.
Run this instead of Driver.py when the LCD is unavailable.

Navigation:
  Type a number to select a menu item.
  Press Enter to confirm a value, 'c' to cancel.
  Type 'b' or select Back to go up a level.
  Press Enter during a live display to stop.

Menu structure (identical to LCD):
  Main
  ├── Type
  ├── Frequency
  ├── Amplitude
  ├── Output        → live display
  ├── DC Reference
  │     Voltage
  │     Output      → live display w/ voltmeter
  ├── Ohmmeter      → live display
  └── Quit
"""

import os
import sys
import select
import time
import pigpio

from square_wave import SquareWaveGenerator, MIN_FREQ, MAX_FREQ, FREQ_STEP, MAX_AMP
from dc_reference import DCReferenceGenerator
from sar_logic import SAR_ADC
from ohms_steps import CONSTANT_OHMS, MAX_STEPS

# ── Hardware constants ────────────────────────────────────────────────────────
DC_SPI_CHANNEL = 0
DC_SPI_SPEED   = 50_000
DC_SPI_FLAGS   = 0

VM_SPI_CHANNEL = 1
VM_SPI_SPEED   = 50_000
VM_SPI_FLAGS   = 0

COMPARATOR_PIN = 24
VREF           = 1.6
AMP_STEP       = 0.1

MIN_DC_VOLT    = -5.0
MAX_DC_VOLT    =  5.0
DC_VOLT_STEP   =  0.625


# ── Display helpers ───────────────────────────────────────────────────────────
WIDTH          = 20
_DISPLAY_LINES = 6        # 4 data rows + 2 border rows
_rendered_once = False


def _render(rows):
    """Draw a 20×4 LCD-style box in-place using ANSI cursor movement."""
    global _rendered_once
    if _rendered_once:
        sys.stdout.write(f'\033[{_DISPLAY_LINES}A')
    border = '+' + '-' * WIDTH + '+'
    sys.stdout.write(border + '\n')
    for r in list(rows)[:4]:
        sys.stdout.write('|' + str(r).ljust(WIDTH)[:WIDTH] + '|\n')
    sys.stdout.write(border + '\n')
    sys.stdout.flush()
    _rendered_once = True


def _clear():
    """Full screen clear — call between menu transitions."""
    global _rendered_once
    os.system('clear')
    _rendered_once = False


def _enter_pressed():
    """Non-blocking check: return True if Enter is waiting on stdin."""
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if ready:
        sys.stdin.readline()
        return True
    return False


# ── Core UI primitives ────────────────────────────────────────────────────────

def pick_menu(title, options):
    """
    Show an LCD-style box previewing the first 3 options, then a
    numbered list.  Returns the chosen option string, or 'Back'.
    """
    _clear()
    rows = [title]
    for i in range(3):
        if i < len(options):
            rows.append(('> ' if i == 0 else '  ') + options[i])
        else:
            rows.append('')
    _render(rows)

    print()
    for i, opt in enumerate(options):
        print(f'  {i + 1}. {opt}')
    print('  b. Back')

    while True:
        raw = input('\nChoice: ').strip().lower()
        if raw == 'b':
            return 'Back'
        try:
            n = int(raw) - 1
            if 0 <= n < len(options):
                return options[n]
        except ValueError:
            pass
        print('  Invalid choice, try again.')


def adjust_value(title, value, min_val, max_val, step, fmt):
    """
    Show the current value in the LCD box, let the user type a new one.
    Returns the confirmed value, or None to cancel.
    """
    while True:
        _clear()
        _render([title, fmt(value), 'Enter to confirm', 'c to cancel'])
        print(f'\n  Range: {fmt(min_val)} to {fmt(max_val)},  step: {step}')
        raw = input(f'  [{fmt(value)}]  Enter value (or Enter/c): ').strip()

        if raw == '':
            return value
        if raw.lower() == 'c':
            return None
        try:
            new   = float(raw)
            new   = max(min_val, min(max_val, new))
            value = round(round(new / step) * step, 10)
        except ValueError:
            print('  Invalid number, try again.')
            time.sleep(0.6)


# ── Autoranging ohmmeter ─────────────────────────────────────────────────────

def _autorange_read_ohms(voltmeter):
    """
    Try each preset R_known value (100, 1k, 5k, 10k Ω from the digi pot).
    Score each by how centred the SAR step is — a step near MAX_STEPS/2 means
    Vin ≈ Vref/2, i.e. R_unknown ≈ R_known, which gives the most accurate reading.
    Returns the ohms value from the best-scoring range, or None if all are OL.
    """
    best_ohms   = None
    best_margin = -1.0

    for r_known in CONSTANT_OHMS:          # [100, 1000, 5000, 10000]
        ohms, step = voltmeter.read_ohms(VREF, r_known)
        if ohms is None:
            continue
        margin = 1.0 - abs(step - MAX_STEPS / 2) / (MAX_STEPS / 2)
        if margin > best_margin:
            best_margin = margin
            best_ohms   = ohms

    return best_ohms


# ── Live displays ─────────────────────────────────────────────────────────────

def run_live_display(state):
    """Square-wave live readout.  Press Enter to return."""
    _clear()
    print('  Press Enter to stop.\n')
    while True:
        period_ms = 1000.0 / state['frequency']
        pk_pk     = 2 * state['amplitude']
        _render([
            f"LIVE OUT  {state['frequency']}Hz",
            f"Amp:+/-{state['amplitude']:.1f}V Pk:{pk_pk:.1f}V",
            f"T:{period_ms:.2f}ms  DC:50%",
            'Enter: back',
        ])
        if _enter_pressed():
            break
        time.sleep(0.25)


def run_dc_live_display(state, voltmeter):
    """DC reference live readout with voltmeter.  Press Enter to return."""
    _clear()
    print('  Press Enter to stop.\n')
    while True:
        measured, _ = voltmeter.read_voltage(VREF)
        _render([
            'DC REF ON',
            f"Set:  {state['dc_voltage']:.3f} V",
            f"Meas: {measured:.3f} V",
            'Enter: back',
        ])
        if _enter_pressed():
            break
        time.sleep(0.25)


def run_ohm_live_display(voltmeter):
    """Ohmmeter live readout.  Press Enter to return."""
    _clear()
    print('  Press Enter to stop.\n')
    while True:
        ohms = _autorange_read_ohms(voltmeter)
        if ohms is None:
            ohm_str = 'OL  (open circuit)'
        elif ohms >= 1_000:
            ohm_str = f'{ohms / 1000:.2f} kOhm'
        else:
            ohm_str = f'{ohms:.1f} Ohm'
        _render([
            'OHMMETER',
            ohm_str,
            f'Vref={VREF}V  autorange',
            'Enter: back',
        ])
        if _enter_pressed():
            break
        time.sleep(0.25)


# ── Page runners ──────────────────────────────────────────────────────────────

def run_type_menu(state):
    while True:
        choice = pick_menu(f"TYPE: {state['wave_type']}", ['Square', 'Back'])
        if choice == 'Square':
            state['wave_type'] = 'Square'
            _clear()
            _render(['Type set: Square', '', '', ''])
            time.sleep(0.8)
            return
        elif choice == 'Back':
            return


def run_frequency_menu(state, gen):
    while True:
        choice = pick_menu(f"FREQ: {state['frequency']}Hz", ['Adjust', 'Back'])
        if choice == 'Adjust':
            new_val = adjust_value(
                'FREQUENCY',
                float(state['frequency']),
                MIN_FREQ, MAX_FREQ, FREQ_STEP,
                lambda v: f'{int(v)} Hz',
            )
            if new_val is not None:
                state['frequency'] = int(new_val)
                gen.set_frequency(state['frequency'])
        elif choice == 'Back':
            return


def run_amplitude_menu(state, gen):
    while True:
        choice = pick_menu(f"AMP: +/-{state['amplitude']:.1f}V", ['Adjust', 'Back'])
        if choice == 'Adjust':
            new_val = adjust_value(
                'AMPLITUDE',
                state['amplitude'],
                0.0, MAX_AMP, AMP_STEP,
                lambda v: f'+/- {v:.1f} V',
            )
            if new_val is not None:
                state['amplitude'] = round(new_val, 1)
                gen.set_amplitude(state['amplitude'])
        elif choice == 'Back':
            return


def run_output_menu(state, gen):
    while True:
        status = 'ON' if state['output_on'] else 'OFF'
        choice = pick_menu(f'OUTPUT: {status}', ['On', 'Off', 'Back'])
        if choice == 'On':
            gen.set_frequency(state['frequency'])
            gen.set_amplitude(state['amplitude'])
            gen.start()
            state['output_on'] = True
            run_live_display(state)
        elif choice == 'Off':
            gen.stop()
            state['output_on'] = False
        elif choice == 'Back':
            if state['output_on']:
                gen.stop()
                state['output_on'] = False
            return


def run_dc_voltage_menu(state, dc_ref):
    while True:
        choice = pick_menu(f"DC VOLT: {state['dc_voltage']:.3f}V", ['Adjust', 'Back'])
        if choice == 'Adjust':
            new_val = adjust_value(
                'DC VOLTAGE (-5 to 5V)',
                state['dc_voltage'],
                MIN_DC_VOLT, MAX_DC_VOLT, DC_VOLT_STEP,
                lambda v: f'{v:.3f} V',
            )
            if new_val is not None:
                state['dc_voltage'] = round(new_val, 3)
                dc_ref.set_voltage(state['dc_voltage'])
        elif choice == 'Back':
            return


def run_dc_output_menu(state, dc_ref, voltmeter):
    """Returns True if the user chose Main, False otherwise."""
    while True:
        status = 'ON' if state['dc_output_on'] else 'OFF'
        choice = pick_menu(f'DC OUTPUT: {status}', ['On', 'Off', 'Back', 'Main'])
        if choice == 'On':
            dc_ref.set_voltage(state['dc_voltage'])
            dc_ref.start()
            state['dc_output_on'] = True
            run_dc_live_display(state, voltmeter)
            dc_ref.stop()
            state['dc_output_on'] = False
        elif choice == 'Off':
            dc_ref.stop()
            state['dc_output_on'] = False
        elif choice == 'Back':
            if state['dc_output_on']:
                dc_ref.stop()
                state['dc_output_on'] = False
            return False
        elif choice == 'Main':
            if state['dc_output_on']:
                dc_ref.stop()
                state['dc_output_on'] = False
            return True


def run_dc_reference_menu(state, dc_ref, voltmeter):
    """Returns True if the user navigated directly to Main."""
    while True:
        choice = pick_menu('DC REFERENCE', ['Voltage', 'Output', 'Back'])
        if choice == 'Voltage':
            run_dc_voltage_menu(state, dc_ref)
        elif choice == 'Output':
            if run_dc_output_menu(state, dc_ref, voltmeter):
                return True
        elif choice == 'Back':
            if state['dc_output_on']:
                dc_ref.stop()
                state['dc_output_on'] = False
            return False


def run_ohmmeter_menu(voltmeter):
    while True:
        choice = pick_menu('OHMMETER', ['Read', 'Back'])
        if choice == 'Read':
            run_ohm_live_display(voltmeter)
        elif choice == 'Back':
            return


def run_main_menu(state, gen, dc_ref, voltmeter):
    while True:
        choice = pick_menu(
            'FUNC GENERATOR',
            ['Type', 'Frequency', 'Amplitude', 'Output',
             'DC Reference', 'Ohmmeter', 'Quit'],
        )
        if choice == 'Type':
            run_type_menu(state)
        elif choice == 'Frequency':
            run_frequency_menu(state, gen)
        elif choice == 'Amplitude':
            run_amplitude_menu(state, gen)
        elif choice == 'Output':
            run_output_menu(state, gen)
        elif choice == 'DC Reference':
            run_dc_reference_menu(state, dc_ref, voltmeter)
        elif choice == 'Ohmmeter':
            run_ohmmeter_menu(voltmeter)
        elif choice in ('Quit', 'Back'):
            if state['output_on']:
                gen.stop()
            if state['dc_output_on']:
                dc_ref.stop()
            _clear()
            _render(['Goodbye!', '', '', ''])
            return


# ── Initialise hardware ───────────────────────────────────────────────────────
print("Starting cmd_driver (CLI mode)...")

pi = pigpio.pi()
if not pi.connected:
    raise SystemExit("Cannot connect to pigpio daemon.  Run 'sudo pigpiod' first.")

spi_dc    = pi.spi_open(DC_SPI_CHANNEL, DC_SPI_SPEED, DC_SPI_FLAGS)
gen       = SquareWaveGenerator(pi, spi_dc)
dc_ref    = DCReferenceGenerator(pi, spi_dc)
spi_vm    = pi.spi_open(VM_SPI_CHANNEL, VM_SPI_SPEED, VM_SPI_FLAGS)
voltmeter = SAR_ADC(pi, spi_vm, COMPARATOR_PIN)

state = {
    'wave_type':    'Square',
    'frequency':    1000,
    'amplitude':    0.0,
    'output_on':    False,
    'dc_voltage':   0.0,
    'dc_output_on': False,
}

# ── Main ──────────────────────────────────────────────────────────────────────
try:
    run_main_menu(state, gen, dc_ref, voltmeter)
except KeyboardInterrupt:
    print("\nStopping...")
finally:
    if state['output_on']:
        gen.stop()
    if state['dc_output_on']:
        dc_ref.stop()
    gen.cleanup()
    dc_ref.cleanup()
    pi.spi_close(spi_dc)
    pi.spi_close(spi_vm)
    pi.stop()
