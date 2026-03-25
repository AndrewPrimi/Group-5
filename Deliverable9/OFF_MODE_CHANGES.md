# OFF Mode — Implementation Guide

Apply these changes to add a top-level OFF / Mode Select screen to the testbench Driver.

## Overview

- On boot, the system starts in OFF state (all outputs disabled, LCD off)
- A new top-level screen shows two options: **OFF** and **Mode Select**
- **OFF** safely shuts down all outputs (square wave, DC reference) and turns off the LCD (backlight + display)
- **Mode Select** turns the LCD back on and enters the existing Mode Select menu
- From Mode Select, **Back** and **Main** return to this top-level screen
- All other sub-menus are unchanged — their "Main" still goes to Mode Select as before

---

## Change 1: Fix `lcd.backlight()` in `i2c_lcd.py`

The `backlight()` method has the I2C write commented out. Uncomment it so toggling the backlight actually takes effect on hardware.

**Find this** (around line 145):

```python
def backlight(self, on):
    """
    Switch backlight on (True) or off (False).
    """
    self.backlight_on = on
    # Push a harmless write so the state changes on the backpack
    '''try:
        self._byte(0x00, 0x00)
    except Exception:
        pass'''
```

**Replace with:**

```python
def backlight(self, on):
    """
    Switch backlight on (True) or off (False).
    """
    self.backlight_on = on
    # Push a harmless write so the state changes on the backpack
    try:
        self._byte(0x00, 0x00)
    except Exception:
        pass
```

---

## Change 2: Add `ensure_all_off()` and `run_top_screen()` to `Driver.py`

Add these two functions **after** `setup_callbacks(state, pi, lcd)` and **before** `run_function_generator_menu()`.

**Find this:**

```python
setup_callbacks(state, pi, lcd)


def run_function_generator_menu():
```

**Replace with:**

```python
setup_callbacks(state, pi, lcd)


def ensure_all_off():
    """Safely shut down all outputs and turn off the LCD."""
    sq_gen.stop()
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
```

---

## Change 3: Modify the main loop in `Driver.py`

Wrap the existing Mode Select loop inside a `run_top_screen()` call, and call `ensure_all_off()` on boot.

**Find this** (at the bottom of Driver.py):

```python
print("Starting...")
try:
    while True:
        choice = pick_menu(
            "Mode Select",
            ["Function Generator", "Ohmmeter", "Voltmeter", "DC Reference", "Back", "Main"],
        )

        if choice == "Function Generator":
            result = run_function_generator_menu()

        elif choice == "Ohmmeter":
            result = run_ohmmeter()

        elif choice == "Voltmeter":
            result = run_voltmeter_menu()

        elif choice == "DC Reference":
            result = run_dc_reference_menu()

        elif choice in ("Back", "Main"):
            pass
```

**Replace with:**

```python
print("Starting...")
ensure_all_off()
try:
    while True:
        run_top_screen()

        while True:
            choice = pick_menu(
                "Mode Select",
                ["Function Generator", "Ohmmeter", "Voltmeter", "DC Reference", "Back", "Main"],
            )

            if choice == "Function Generator":
                result = run_function_generator_menu()

            elif choice == "Ohmmeter":
                result = run_ohmmeter()

            elif choice == "Voltmeter":
                result = run_voltmeter_menu()

            elif choice == "DC Reference":
                result = run_dc_reference_menu()

            elif choice in ("Back", "Main"):
                break  # go back to top screen
```

---

## Key Details

- `0x08` is the HD44780 instruction for **display off** (turns off the display without losing content)
- `0x0C` is the HD44780 instruction for **display on, cursor off, blink off**
- `lcd.backlight(False)` sets the PCF8574T backlight pin low via I2C
- `ensure_all_off()` is called on boot so the hardware always starts in a known-off state
- The `finally` block at the bottom of Driver.py (cleanup on exit) is **not changed**
- No sub-menu functions are changed — only the top-level flow is modified
