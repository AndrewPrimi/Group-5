"""
callbacks.py – rotary encoder and button callbacks for Deliverable 9.

Pages handled:
  Main menu  : menu_direction_callback, menu_button_callback
  Ohmmeter   : ohm_button_callback  (press to return to main menu)
"""

import pigpio

# Module-level references injected by setup_callbacks().
# _s  = shared state dict (ohms, selections, flags, etc.)
# _pi = pigpio.pi() instance for GPIO / SPI access
# _lcd = i2c_lcd.lcd instance for writing to the 2004A display
_s   = None   # state dict
_pi  = None   # pigpio.pi instance
_lcd = None   # i2c_lcd.lcd instance

|# Rotary encoder GPIO pin assignments (active-low with pull-ups)
PIN_A               = 22     # CLK
PIN_B               = 27     # DT
ROTARY_BTN_PIN      = 17     # Rotary encoder push-button

# Debounce threshold (microseconds)
BUTTON_DEBOUNCE_US  = 200_000    # 200 ms  – ignore repeat presses
HOLD_US             = 2_000_000  # 2 s button hold

# Number of selectable items on the main menu
MENU_ITEMS = 4   # Function Generator, Ohmmeter, Voltmeter, DC Reference

def setup_callbacks(state, pi, lcd):
    """Give callbacks access to shared state, pi, and lcd."""
    global _s, _pi, _lcd
    _s   = state
    _pi  = pi
    _lcd = lcd


def clear_callbacks():
    """Cancel and remove all active pigpio callbacks / decoder objects."""
    for cb in _s.get('active_callbacks', []):
        cb.cancel()
    _s['active_callbacks'] = []

# ── Rotary encoder input callbacks ─────────────────────────────────────────

def _button_cb(gpio, level, tick):
    if level == 0:                          # press (falling edge)
        last = state['button_last_tick']
        if last is not None and pigpio.tickDiff(last, tick) < DEBOUNCE_US:
            return
        state['button_last_tick']  = tick
        state['button_press_tick'] = tick
    elif level == 1:                        # release (rising edge)
        press_tick = state['button_press_tick']
        if press_tick is not None:
            if pigpio.tickDiff(press_tick, tick) >= HOLD_US:
                state['button_held']    = True
            else:
                state['button_pressed'] = True
            state['button_press_tick'] = None

def _encoder_cb(direction):
    state['encoder_delta'] += direction


def _attach_callbacks():
    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, _encoder_cb)
    cb_btn  = pi.callback(ROTARY_BTN_PIN, pigpio.EITHER_EDGE, _button_cb)
    state['active_callbacks'] = [decoder, cb_btn]


def _reset_input():
    state['button_pressed'] = False
    state['button_held']    = False
    state['encoder_delta']  = 0


# ── Menu helper ───────────────────────────────────────────────────────────────

def pick_menu(title, options):
    """
    Scrolling 3-item menu on the 20x4 LCD.
    Returns the selected option string, or 'Back' on hold.
    """
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


# ── Value adjuster ────────────────────────────────────────────────────────────

def adjust_value(title, value, min_val, max_val, step, fmt):
    """
    Rotary-encoder value adjuster.
    Returns the confirmed value, or None if the user held to cancel.
    """
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
            value  = max(min_val, min(max_val, value))
            value  = round(round(value / step) * step, 10)
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


# ── Function Generator ─────────────────────────────────────────────────────────

def run_function_generator():
    while True:
        choice = pick_menu(
            'FUNC GENERATOR',
            ['Type', 'Frequency', 'Amplitude', 'Output', 'Back']
        )

        if choice == 'Type':
            run_type_menu()

        elif choice == 'Frequency':
            run_frequency_menu()

        elif choice == 'Amplitude':
            run_amplitude_menu()

        elif choice == 'Output':
            run_output_menu()

        elif choice == 'Back':
            if _s['output_on']:
                gen.stop()
                _s['output_on'] = False
            return


# ── Main Menu ───────────────────────────────────────────────────────── 

def run_main_menu():
    while True:
        choice = pick_menu(
            'Main Menu',
            [
                'Function Generator',
                'Ohmmeter',
                'Voltmeter',
                'DC Reference',
                'Quit'
            ]
        )

        if choice == 'Function Generator':
            run_function_generator()

        elif choice == 'Ohmmeter':
            run_ohmmeter()

        elif choice == 'Voltmeter':
            run_voltmeter()

        elif choice == 'DC Reference':
            go_main = run_dc_reference_menu()
            if go_main:
                continue

        elif choice in ('Quit', 'Back'):
            if _s['output_on']:
                gen.stop()
            if _s['dc_output_on']:
                dc_ref.stop()

            _lcd.put_line(0, 'Goodbye!')
            _lcd.put_line(1, '')
            _lcd.put_line(2, '')
            _lcd.put_line(3, '')
            return





















        
    
            
# ── Main-menu callbacks (Deliverable 7) ───────────────────────────────────────

def menu_direction_callback(direction):
    """Rotate encoder on main menu → move the cursor between items."""
    old = _s['menu_selection']
    if old not in (1, 2):
        old = 1
    _s['menu_selection'] = 1 + ((old - 1 + direction) % MENU_ITEMS)
    _redraw_main_menu()


def menu_button_callback(gpio, level, tick):
    """Button press on main menu → enter the highlighted page."""
    if level != 0:          # only act on falling edge
        return
    if _debounce(tick):
        return
    if _s['menu_selection'] in (1, 2):
        _s['isMainPage'] = False


# ── Ohmmeter-page callbacks ───────────────────────────────────────────────────

def ohm_button_callback(gpio, level, tick):
    """Button press on the ohmmeter page → return to main menu."""
    if level != 0:
        return
    if _debounce(tick):
        return
    _s['isOhmPage'] = False


# ── Page runners (Deliverable 8) ───────────────────────────────────────────────

def run_type_menu():
    while True:
        choice = pick_menu(f"TYPE: {state['wave_type']}", ['Square', 'Back'])
        if choice == 'Square':
            state['wave_type'] = 'Square'
            lcd.put_line(0, 'Type set: Square')
            lcd.put_line(1, ''); lcd.put_line(2, ''); lcd.put_line(3, '')
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
            f"AMP: +/-{state['amplitude']:.1f}V",
            ['Adjust', 'Back'],
        )
        if choice == 'Adjust':
            new_val = adjust_value(
                'AMPLITUDE',
                state['amplitude'],
                0.0, MAX_AMP, AMP_STEP,
                lambda v: f"+/- {v:.1f} V",
            )
            if new_val is not None:
                state['amplitude'] = round(new_val, 1)
                gen.set_amplitude(state['amplitude'])
        elif choice == 'Back':
            return


def run_live_display():
    """Live readout while output is ON.  Hold button 2 s to return."""
    _reset_input()

    def _redraw():
        period_ms = 1000.0 / state['frequency']
        pk_pk     = 2 * state['amplitude']
        lcd.put_line(0, f"LIVE OUT  {state['frequency']}Hz")
        lcd.put_line(1, f"Amp:+/-{state['amplitude']:.1f}V Pk:{pk_pk:.1f}V")
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
            gen.set_frequency(state['frequency'])
            gen.set_amplitude(state['amplitude'])
            gen.start()
            state['output_on'] = True
            run_live_display()
        elif choice == 'Off':
            gen.stop()
            state['output_on'] = False
        elif choice == 'Back':
            if state['output_on']:
                gen.stop()
                state['output_on'] = False
            return


def run_dc_live_display():
    """Live DC output readout with voltmeter.  Hold button 2 s to return."""
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
    """
    Returns True if the user chose 'Main' (caller should return to main menu),
    False otherwise.
    """
    while True:
        status = 'ON' if state['dc_output_on'] else 'OFF'
        choice = pick_menu(f"DC OUTPUT: {status}", ['On', 'Off', 'Back', 'Main'])
        if choice == 'On':
            dc_ref.set_voltage(state['dc_voltage'])
            dc_ref.start()
            state['dc_output_on'] = True
            run_dc_live_display()
            # returning from live display (hold) turns output off
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


def run_dc_reference_menu():
    """Returns True if the user navigated directly to Main."""
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
                dc_ref.stop()
                state['dc_output_on'] = False
            return False

# ── Voltmeter-page callbacks ─────────────────────────────────────────────────── 
        
def run_source_menu(state, pi, lcd):
    state['volt_source_sel']  = SRC_EXTERNAL
    state['volt_source_done'] = False
    state['button_last_tick'] = None
    clear_callbacks(state)

    def _on_rotate(direction):
        state['volt_source_sel'] = (state['volt_source_sel'] + direction) % NUM_SOURCES
        _redraw()

    def _on_button(_gpio, level, tick):
        if level != 0:
            return
        last = state.get('button_last_tick')
        if last is not None and pigpio.tickDiff(last, tick) < _DEBOUNCE_US:
            return
        state['button_last_tick'] = tick
        state['volt_source_done'] = True

    def _redraw():
        for row, text in enumerate(build_source_menu_lines(state['volt_source_sel'])):
            lcd.put_line(row, text)

    _redraw()

    decoder = rotary_encoder.decoder(pi, PIN_A, PIN_B, _on_rotate)
    cb_btn  = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
    state['active_callbacks'] = [decoder, cb_btn]

    while not state['volt_source_done']:
        time.sleep(0.05)

    clear_callbacks(state)
    return state['volt_source_sel']


def run_measurement(state, pi, lcd, adc_handle,
                    source_label="External", interval=0.5):
    state['volt_meas_active'] = True
    state['button_last_tick'] = None
    clear_callbacks(state)

    def _on_button(_gpio, level, tick):
        if level != 0:
            return
        last = state.get('button_last_tick')
        if last is not None and pigpio.tickDiff(last, tick) < _DEBOUNCE_US:
            return
        state['button_last_tick'] = tick
        state['volt_meas_active'] = False

    lcd.put_line(0, "Voltmeter")
    lcd.put_line(1, f"Src: {source_label}")
    lcd.put_line(2, "Measuring...")
    lcd.put_line(3, "Btn: back")

    cb_btn = pi.callback(ROTARY_BTN_PIN, pigpio.FALLING_EDGE, _on_button)
    state['active_callbacks'] = [cb_btn]

    last_update = 0.0
    while state['volt_meas_active']:
        now = time.time()
        if now - last_update >= interval:
            last_update = now
            step = _averaged_measure(pi, adc_handle, COMPARATOR1_PIN, n=11)
            l0, l1, l2, l3 = build_measurement_lines(step, source_label)
            lcd.put_line(0, l0)
            lcd.put_line(1, l1)
            lcd.put_line(2, l2)
            lcd.put_line(3, l3)
            print(f"[Voltmeter] step={step}  voltage={step_to_voltage(step):+.2f} V")
        time.sleep(0.05)

    clear_callbacks(state)

        

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
                gen.stop()
            if state['dc_output_on']:
                dc_ref.stop()
            lcd.put_line(0, 'Goodbye!')
            lcd.put_line(1, ''); lcd.put_line(2, ''); lcd.put_line(3, '')
            return


# ── Private helpers ───────────────────────────────────────────────────────────

def _debounce(tick):
    """Return True (and skip) if this tick is too close to the last one."""
    last = _s.get('button_last_tick')
    if last is not None and pigpio.tickDiff(last, tick) < BUTTON_DEBOUNCE_US:
        return True
    _s['button_last_tick'] = tick
    return False


def _redraw_main_menu():
    """Redraw only the item rows (rows 2-3) of the main menu."""
    sel = _s['menu_selection']
    _lcd.put_line(2, '> Ohmmeter'  if sel == 1 else '  Ohmmeter')
    _lcd.put_line(3, '> Voltmeter' if sel == 2 else '  Voltmeter')
