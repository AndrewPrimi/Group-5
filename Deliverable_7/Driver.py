"""
Driver.py – Deliverable 7
Group 5

Main menu → Ohmeter page (SAR ADC, 500 Ω – 10 kΩ, autoranging display).

Hardware overview
-----------------
  LCD          : I2C (20-char × 4-line), addr 0x27
  Rotary enc.  : channel A = GPIO22, channel B = GPIO27, button = GPIO17
  Digipot      : MCP4231  on SPI CE0 (GPIO 8)  – retained from prev. deliverables
  SAR DAC      : MCP4131  on SPI CE1
                   Pin 1 (CS)  → GPIO 7  (CE1)
                   Pin 2 (SCK) → GPIO 11 (SCLK)
                   Pin 3 (SDI) → GPIO 10 (MOSI)
                   Pin 5 (P0A) → 3.3V
                   Pin 6 (P0W) → Op-Amp V−
                   Pin 7 (P0B) → GND
  Comparator   : Op-Amp output → GPIO 23 (internal pull-up enabled)

Page flow
---------
  Main Menu
    ├── (encoder selects "Ohmmeter")
    └── [button press] → Ohmmeter Page
                             └── [2-s button hold] → Main Menu
"""

import pigpio
import time

import i2c_lcd
import rotary_encoder
from callbacks import (
    setup_callbacks, clear_callbacks,
    menu_direction_callback, menu_button_callback,
    ohm_button_callback,
    PIN_A, PIN_B, ROTARY_BTN_PIN,
)
from ohmmeter import (
    open_adc, close_adc,
    averaged_measure, #build_display_lines,
    sar_measure,
    step_to_resistance,
    COMPARATOR_PIN,
)

# ── SPI for MCP4231 digipot (retained from checkpoint C) ─────────────────────
DIGIPOT_SPI_CHANNEL = 0
DIGIPOT_SPI_SPEED   = 50_000
DIGIPOT_SPI_FLAGS   = 0

# How often (seconds) the ohmmeter display refreshes
MEASURE_INTERVAL = 0.5

# ── Initialise pigpio ─────────────────────────────────────────────────────────
pi = pigpio.pi()
if not pi.connected:
    print("Cannot connect to pigpio daemon.  Run 'sudo pigpiod' first.")
    exit(1)

# ── Peripherals ───────────────────────────────────────────────────────────────
lcd = i2c_lcd.lcd(pi, width=20)

digipot_handle = pi.spi_open(DIGIPOT_SPI_CHANNEL, DIGIPOT_SPI_SPEED, DIGIPOT_SPI_FLAGS)
adc_handle     = open_adc(pi)

print(f"Digipot SPI handle : {digipot_handle}")
print(f"ADC SPI handle     : {adc_handle}")


# ── GPIO setup ────────────────────────────────────────────────────────────────
for pin in (PIN_A, PIN_B):
    pi.set_mode(pin, pigpio.INPUT)
    pi.set_pull_up_down(pin, pigpio.PUD_UP)

pi.set_mode(ROTARY_BTN_PIN, pigpio.INPUT)
pi.set_pull_up_down(ROTARY_BTN_PIN, pigpio.PUD_UP)
pi.set_glitch_filter(ROTARY_BTN_PIN, 10_000)   # 10 ms hardware debounce

# Comparator output – LM339 open-collector on GPIO23, needs pull-up
pi.set_mode(COMPARATOR_PIN, pigpio.INPUT)
pi.set_pull_up_down(COMPARATOR_PIN, pigpio.PUD_UP)

# ── Shared application state ──────────────────────────────────────────────────
state = {
    'menu_selection':   0,       # 0 = nothing highlighted, 1 = Ohmeter
    'isMainPage':       True,
    'isOhmPage':        False,
    'button_last_tick': None,
    'active_callbacks': [],
}

setup_callbacks(state, pi, lcd)


# ── Page helpers ──────────────────────────────────────────────────────────────

def show_main_menu():
    """Render the static portions of the main menu."""
    lcd.put_line(0, 'Main Menu')
    lcd.put_line(1, 'Mode Select:')
    lcd.put_line(2, '  Ohmmeter')
    lcd.put_line(3, '')


def run_main_menu():
    """Block until the user selects Ohmeter from the main menu."""
    state['isMainPage']       = True
    state['menu_selection']   = 0
    state['button_last_tick'] = None
    clear_callbacks(state)

    show_main_menu()

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, menu_direction_callback)
    cb_btn  = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, menu_button_callback)
    state['active_callbacks'] = [decoder, cb_btn]

    while state['isMainPage']:
        time.sleep(0.05)

    clear_callbacks(state)

def run_ohmmeter():
    """Continuously measure resistance and display; press button to exit."""
    state['isOhmPage']        = True
    state['button_last_tick'] = None
    clear_callbacks(state)

    # Title drawn once; measurement loop updates lines 1-3
    lcd.put_line(0, 'Ohmmeter')
    lcd.put_line(1, 'Measuring...')
    lcd.put_line(2, '')
    lcd.put_line(3, 'Press btn: main menu')

    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, ohm_button_callback)
    state['active_callbacks'] = [cb_btn]

    last_update = 0.0

    while state['isOhmPage']:
        now = time.time()
        if now - last_update >= MEASURE_INTERVAL:
            last_update = now
            step = averaged_measure(pi, adc_handle, COMPARATOR_PIN, n=5)
            #step = sar_measure(pi, adc_handle, COMPARATOR_PIN)
            l0, l1, l2, l3 = build_display_lines(step)
            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)
            print(f"[Ohmmeter] step={step}  {l1.strip()}  {l2.strip()}")
        time.sleep(0.05)

    clear_callbacks(state)

# ── Display helpers

def format_ohms(ohms, width=8):
    """Auto-range: display in Ω below 1 kΩ, kΩ above."""
    if ohms >= 1000:
        s = f'{ohms / 1000:.2f}k'
    else:
        s = f'{ohms:.0f}'
    return s.ljust(width)


def build_display_lines(step):
    """Return four 20-char LCD lines for the ohmmeter page.

    Line 0: page title
    Line 1: measured resistance (auto-ranged)
    Line 2: ±tolerance
    Line 3: user instruction
    """
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


    
# ── Main loop ─────────────────────────────────────────────────────────────────

print("Starting Deliverable 7 driver...")

try:
    while True:
        run_main_menu()
        run_ohmmeter()

except KeyboardInterrupt:
    print("\nStopping...")
    clear_callbacks(state)
    lcd.close()
    close_adc(pi, adc_handle)
    pi.spi_close(digipot_handle)
    pi.stop()
