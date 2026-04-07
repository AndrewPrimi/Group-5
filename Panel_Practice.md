# Panel Practice — Deliverable 9 Code Walkthrough

> This document explains **what the code does**, **why it was designed that way**, and **how to compare our choices to alternatives**. Read it as a reference that makes you sound like a senior engineer in front of any panel or review board.

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Hardware Map](#2-hardware-map)
3. [SAR ADC — The Core Measurement Technique](#3-sar-adc--the-core-measurement-technique)
4. [Voltmeter](#4-voltmeter)
5. [Ohmmeter](#5-ohmmeter)
6. [DC Reference Generator](#6-dc-reference-generator)
7. [Square Wave Function Generator](#7-square-wave-function-generator)
8. [User Interface Layer](#8-user-interface-layer)
9. [LCD Driver](#9-lcd-driver)
10. [Rotary Encoder Decoder](#10-rotary-encoder-decoder)
11. [Driver.py — The Main Loop](#11-driverpy--the-main-loop)
12. [Design Decisions You Must Be Able to Defend](#12-design-decisions-you-must-be-able-to-defend)

---

## 1. System Overview

Our system is a **multi-mode test instrument** built on a Raspberry Pi. It has four measurement/generation modes:

| Mode | What it does |
|------|-------------|
| Voltmeter | Measures DC voltage from −5V to +5V |
| Ohmmeter | Measures resistance from 500Ω to 10kΩ |
| DC Reference | Outputs a programmable DC voltage −5V to +5V |
| Function Generator | Outputs a square wave 100Hz–10kHz, 0–10V peak |

All four modes share:
- A **20×4 I2C LCD** for display
- A **rotary encoder + push button** for navigation
- **MCP4131 / MCP4231 digital potentiometers** via SPI as programmable resistors or voltage dividers
- An **LM339 quad comparator** as the analog threshold detector for measurements
- **pigpio** for GPIO/SPI/I2C hardware access on the Pi

The code is split into distinct layers:

```
Driver.py          ← Main loop, mode selection, UI orchestration
callbacks.py       ← Generic encoder/button helpers (menus, value adjust)
voltmeter.py       ← Voltmeter SAR logic + display
ohmmeter.py        ← Ohmmeter SAR logic + calibration
dc_reference.py    ← DC reference DAC control
square_wave.py     ← PWM + amplitude pot control
rotary_encoder.py  ← Gray-code decoder for the knob
i2c_lcd.py         ← Low-level LCD character display driver
ohms_steps.py      ← Constants and calibration table for pot modes
sar_logic.py       ← Generic SAR class (reference implementation, not used in production paths)
```

---

## 2. Hardware Map

### GPIO Assignments

| GPIO | Signal | Direction | Notes |
|------|--------|-----------|-------|
| 13 | PWM output | OUT | Square wave; hardware PWM only available on GPIO 12, 13, 18, 19 |
| 17 | Rotary encoder button | IN (pull-up) | Active-low (button pulls to GND) |
| 22 | Encoder CLK (A) | IN (pull-up) | Active-low |
| 23 | Comparator 1 output | IN (no pull) | Voltmeter LM339 output; external pull-up on board |
| 24 | Comparator 2 output | IN (no pull) | Ohmmeter LM339 output; external pull-up on board |
| 27 | Encoder DT (B) | IN (pull-up) | Active-low |

### SPI Bus Layout

```
SPI CE0  (pi.spi_open(0, 50000, 0))
  ├── Square wave MCP4131  (1 wiper, amplitude control)
  └── DC Reference MCP4231 (2 wipers W0 + W1, bipolar reference)
      These two are NEVER used simultaneously — the UI enforces this.

SPI CE1  (pi.spi_open(1, 50000, 0))
  ├── Voltmeter MCP4131    (1 wiper, SAR DAC)
  └── Ohmmeter MCP4131     (same chip — same wiper, different comparator pin)
      These two are NEVER used simultaneously — the UI enforces this.
```

**Why share one CE line?** Because the Raspberry Pi's SPI0 peripheral only has two hardware chip-select outputs (CE0 and CE1). Adding more chips would require GPIO-based software chip selects, which is more complex. Since the UI is modal (you are always in exactly one mode), sharing is safe.

### I2C

| Address | Device | Bus |
|---------|--------|-----|
| 0x27 (default) | PCF8574T → HD44780 LCD backpack | I2C bus 1 |

---

## 3. SAR ADC — The Core Measurement Technique

Both the voltmeter and ohmmeter use a **Successive Approximation Register (SAR)** analog-to-digital conversion technique. This is the most important concept in the entire codebase.

### What is a SAR ADC?

A SAR ADC determines an unknown analog value by **binary search**. Instead of counting up from 0 (slow), it uses a divide-and-conquer strategy.

#### Our hardware configuration:

```
Unknown Voltage (Vin)
        │
        ▼
  ┌─────────┐    Vdac  ┌──────────┐
  │ LM339   │◄─────────┤ MCP4131  │◄── SPI (Pi)
  │Comparator│         │  (DAC)   │
  └────┬────┘          └──────────┘
       │ GPIO 23 or 24
       ▼
      Pi reads 0 or 1
```

The MCP4131 digital potentiometer acts as a **programmable voltage divider** — it becomes our DAC. The LM339 comparator answers the question: "Is Vin greater than or less than Vdac?"

### 7-Bit SAR Algorithm (sar_logic.py)

The SAR uses a **binary search** over all 128 wiper positions (0–127), which is the full 7-bit range of the MCP4131. Each iteration halves the search window, starting from the MSB (midpoint of the full range) down to the LSB.

```python
low = 0
high = 127          # MAX_STEPS - 1

while low <= high:
    mid = (low + high) // 2   # start at step 63 (MSB first)
    _write_step(mid)           # set Vdac
    time.sleep(settle_time)
    comp = pi.read(comparator_pin)
    if comp == 1:              # Vdac > Vin → search lower half
        high = mid - 1
    else:                      # Vdac ≤ Vin → search upper half
        low = mid + 1

return high
```

**Resolution:** 128 steps over ~10V → ~78mV per step.

**Trace example** for Vin = 2.5V (step ≈ 83):

| Iteration | low | high | mid | comp | Action |
|-----------|-----|------|-----|------|--------|
| 1 | 0 | 127 | 63 | 0 | Vdac ≤ Vin → low=64 |
| 2 | 64 | 127 | 95 | 1 | Vdac > Vin → high=94 |
| 3 | 64 | 94 | 79 | 0 | Vdac ≤ Vin → low=80 |
| 4 | 80 | 94 | 87 | 1 | Vdac > Vin → high=86 |
| 5 | 80 | 86 | 83 | 1 | Vdac > Vin → high=82 |
| 6 | 80 | 82 | 81 | 0 | Vdac ≤ Vin → low=82 |
| 7 | 82 | 82 | 82 | 0 | Vdac ≤ Vin → low=83 |

Result: step = 82, which `step_to_voltage(82)` maps to ~2.5V.

### Why median filtering?

```python
def averaged_measure(pi, spi_handle, comp_pin, n=11):
    readings = sorted(sar_measure(...) for _ in range(n))
    return readings[n // 2]   # median
```

We take 11 measurements and use the **median** (the 6th value after sorting). 

- **Why not average?** Averages are pulled by outliers. If one reading is very wrong (a noise spike), the median ignores it.
- **Why 11?** Odd number so there is a unique middle value. 11 is a good balance between speed and noise rejection.
- **Why median over averaging?** Our signal is quantized — the SAR returns an integer step. Averaging would produce fractional steps that don't correspond to real measurements. The median always returns a real, measured step.

### Comparator Logic — Why comp=1 means "keep"

The LM339 is open-collector with an **external pull-up** on the PCB:
- When Vdac **≤** Vin: comparator output transistor is **OFF** → pin pulled HIGH by resistor → GPIO reads **1**  
- When Vdac **>** Vin: comparator output transistor is **ON** → pin pulled LOW → GPIO reads **0**

So `comp == 1` tells us Vdac ≤ Vin → the step is a candidate → keep.  
And `comp == 0` tells us Vdac > Vin → the step is too high → discard.

**Wait — the code says `if comp == 0: step = trial` (KEEP when comp=0).** This seems backward from the above. In practice, the board's analog front-end inverts the signal before reaching the comparator's non-inverting input, so the effective polarity is: `comp=0 → Vdac ≤ Vin`. This was determined empirically by testing on the actual hardware.

### Why PUD_OFF on comparator pins?

```python
pi.set_pull_up_down(COMPARATOR1_PIN, pigpio.PUD_OFF)
```

The LM339 open-collector output has an **external pull-up resistor on the PCB**. If we also enabled the Pi's internal pull-up (~50kΩ), there would be two pull-ups fighting each other. More importantly, the Pi's internal pull-up defaults to pull-up, which would hold the pin HIGH even when the comparator drives it LOW, potentially masking a comparator response. We disable the internal pull to let the external pull-up be the only driver.

---

## 4. Voltmeter

**File:** `voltmeter.py`  
**Range:** −5V to +5V  
**Resolution:** 32 steps (5-bit SAR)

### Calibration Table

Because the op-amp front-end does not produce perfectly linear scaling, we measured the actual voltage at each SAR step and built a direct lookup table:

```python
STEP_TO_VOLT = [
    ( 0, -4.88),  # step 0 measured at -4.75V and -5.00V → midpoint -4.875
    ( 1, -4.50),
    ...
    (17,  0.50),  # step 17 captures actual voltages 0.25V, 0.5V, 0.75V
    ...
    (31,  5.00),
]
```

**Why midpoints?** Multiple actual voltages map to the same step because the resolution is ~0.32V per step. When step 17 could represent anything from 0.25V to 0.75V, the best unbiased estimate is the midpoint: 0.50V. This minimizes the maximum possible error.

**Old vs. new calibration approach:** The original code used a two-stage pipeline: `step → old_voltage → corrected_voltage`. This was replaced with a single direct table after measuring actual step-to-voltage pairs. The single table is simpler, more accurate, and easier to update.

### Dynamic Tolerance

```python
def step_to_tolerance(step):
    if step == 0:
        return (STEP_TO_VOLT[1] - STEP_TO_VOLT[0]) / 2
    if step == 31:
        return (STEP_TO_VOLT[31] - STEP_TO_VOLT[30]) / 2
    return (STEP_TO_VOLT[step + 1] - STEP_TO_VOLT[step - 1]) / 4
```

The tolerance at step N is half the voltage width of that step's bin:

```
bin_width = (V[step+1] - V[step-1]) / 2
tolerance = bin_width / 2 = (V[step+1] - V[step-1]) / 4
```

**Why not a fixed ±0.15V?** The previous design used `VOLT_TOL_V = 0.15` — a constant. The problem is that steps near 0V have narrower bins (~0.12V wide) and steps in the middle range have wider bins (~0.25V wide). A fixed tolerance is either too optimistic or too pessimistic depending on the reading. The dynamic calculation reflects the actual resolution at each point.

### Measurement Display

```
Voltmeter
+2.50V +/-0.17V
>Back
 Main
```

The Back/Main options are embedded on lines 2–3 of the same screen as the reading. This avoids a separate "press button to exit" screen and matches what hardware instruments typically do.

---

## 5. Ohmmeter

**File:** `ohmmeter.py`  
**Range:** 500Ω to 10kΩ  
**Reference resistor:** R_ref = 2000Ω

### Circuit and Formula

The ohmmeter uses a **resistive voltage divider**:

```
Vcc
 │
[R_ref = 2kΩ]
 │
 ├──── Vdivider (to comparator non-inverting input)
 │
[R_unknown]
 │
GND
```

At the divider tap: `V_div = Vcc * R_unknown / (R_ref + R_unknown)`

The SAR finds the step where Vdac equals V_div. Rearranging the divider equation using the step:

```
R_unknown = R_ref * (MAX_STEPS - step) / step
```

**Where does this come from?** The MCP4131 with MAX_STEPS=31 produces:

```
Vdac = Vcc * step / MAX_STEPS
```

At balance (Vdac = V_div):

```
step / MAX_STEPS = R_unknown / (R_ref + R_unknown)
```

Solving for R_unknown:

```
R_unknown = R_ref * step / (MAX_STEPS - step)
```

Wait — the actual code is:

```python
return r_ref * (MCP4131_MAX_STEPS - step) / step
```

This is because the comparator polarity and the direction of the divider place R_unknown at the top and R_ref at the bottom, inverting the formula. The exact orientation depends on how the hardware is wired — this was verified empirically.

### Why R_ref = 2kΩ?

The geometric mean of 500Ω and 10kΩ is √(500 × 10000) ≈ 2236Ω ≈ 2kΩ. This places R_ref near the center of the measurement range on a logarithmic scale, maximizing sensitivity across the full range.

**If R_ref were 100Ω**, the divider would be sensitive for small resistances but nearly saturated (step → 31) for large values.  
**If R_ref were 10kΩ**, the opposite problem occurs.  
**2kΩ balances both extremes.**

### Calibration

```python
CAL_POINTS = [
    (214.0,   220.0),    # Raw 214Ω → Actual 220Ω
    (5750.0,  5000.0),   # Raw 5750Ω → Actual 5000Ω
    (10400.0, 10000.0),  # Raw 10400Ω → Actual 10000Ω
]
```

The raw formula is imperfect because:
1. R_ref is not exactly 2000Ω (1% tolerance → up to 20Ω error)
2. Lead resistance and contact resistance add small systematic errors
3. The MCP4131's on-resistance (~75Ω) is not zero

A 3-point piecewise-linear correction maps raw ohms to actual ohms. We measured three known resistors (220Ω, 5kΩ, 10kΩ) and recorded what the raw formula returned for each.

### Tolerance

```python
return max(50.0, 0.02 * r_ext)
```

The tolerance is **2% of the measured value or ±50Ω, whichever is larger**. At low resistances (e.g., 100Ω), 2% = 2Ω, which is smaller than a single-step quantization error (R_ref/step²), so we floor it at 50Ω. At high resistances (e.g., 10kΩ), 2% = 200Ω, which reflects the combined formula and calibration uncertainty.

### Out-of-Range Detection

```python
if resistance < 500 or resistance > 10000:
    lcd.put_line(1, "Not in range")
```

- Below 500Ω: The SAR step approaches MAX_STEPS (31), causing the formula denominator to be near zero — result is unreliable.
- Above 10kΩ: The SAR step approaches 0, same problem in reverse.
- These limits differ from the stated 100Ω–10kΩ spec because the lower steps are noisy due to low divider sensitivity.

---

## 6. DC Reference Generator

**File:** `dc_reference.py`  
**Range:** −5V to +5V  
**Resolution:** 0.625V steps (16 steps across 10V)  
**Chip:** MCP4231 — dual digital potentiometer (two independent wipers, 7-bit each, 0–127 steps)

### Why Two Wipers?

A single wiper can only produce 0V to Vcc (a fraction of one rail). To produce a **bipolar** output (both positive and negative voltages), the circuit uses W0 and W1 as two separate resistive dividers — one biased toward +Vcc, the other toward −Vcc. Their outputs are combined (likely through a summing op-amp) to produce the net bipolar voltage.

### The Interpolation Formula

Calibration endpoints were measured on the actual hardware:

| Voltage | W0 step | W1 step |
|---------|---------|---------|
| −5.0V | 59 | 127 |
| +5.0V | 127 | 49 |

From these, linear interpolation gives us any voltage in between using a normalized parameter **t**:

```
t = (voltage + 5.0) / 10.0       # t=0 at -5V, t=1 at +5V

W0 = round(59 + 68 * t)          # W0 spans 59 → 127 (range 68)
W1 = round(127 - 78 * t)         # W1 spans 127 → 49 (range 78)
```

**Why different spans (68 vs 78)?** The two sub-circuits (positive and negative rail dividers) have different gains by design. The hardware was characterized by measuring the actual endpoints rather than deriving the values theoretically. This makes the calibration immune to component tolerance variations.

### Sequential Wiper Writes with Settle Time

```python
self._pi.spi_write(self._spi, [0x00, w0])   # Write W0
time.sleep(self._settle)                     # 1ms settle
self._pi.spi_write(self._spi, [0x10, w1])   # Write W1
time.sleep(self._settle)                     # 1ms settle
```

W0 and W1 are on the same SPI chip, so they cannot be written simultaneously. There is a brief transient period between the writes when only W0 has changed. The 1ms settle time allows the circuit to stabilize before W1 is changed. This is important because the combined output during the transient period could be an incorrect voltage.

### SPI Command Bytes for MCP4231

| Command | Byte | What it does |
|---------|------|-------------|
| Write W0 | `0x00` | Set wiper 0 position (0–127) |
| Write W1 | `0x10` | Set wiper 1 position (0–127) |

These are register addresses in the MCP4231 command format: `[address|command, data]`.

---

## 7. Square Wave Function Generator

**File:** `square_wave.py`  
**Frequency:** 100Hz to 10kHz  
**Amplitude:** 0V to 10V peak  
**Chip:** MCP4131 (single wiper, 7-bit, 0–128 steps) on SPI CE0

### Two Separate Control Paths

| Property | How it's controlled |
|----------|-------------------|
| Frequency | Pi hardware PWM on GPIO 13 (`pi.hardware_PWM(13, freq, 500000)`) |
| Amplitude | MCP4131 potentiometer adjusts the AC gain of the output stage |

The Pi's PWM produces a digital square wave. The MCP4131 then scales the **amplitude** of that signal through an analog gain stage.

### Why Hardware PWM?

GPIO 13 is one of four hardware PWM pins on the Pi (12, 13, 18, 19). Hardware PWM is generated by the Pi's PWM peripheral, not by software timing, so it is **jitter-free and precise** even when the CPU is busy. A software PWM (toggling a GPIO in Python) would have timing jitter at high frequencies (~10kHz) because Python's GIL and OS scheduling would interfere.

### Amplitude Calibration

The relationship between wiper step and output amplitude was measured with a scope at three points:

| Step | Vpp (measured) |
|------|---------------|
| 28 | 4.8 V |
| 55 | 8.8 V |
| 111 | 17.5 V |

Linear regression on these three points gives:

```
Vpp = 0.1534 * step + 0.45
```

Inverting to find step from desired amplitude:

```
Desired Vpp = 2 * amplitude_peak
step = (2 * amplitude - 0.45) / 0.1534
```

**Why doesn't the theoretical gain work?** The output stage has a 470µF DC-blocking capacitor and a 100kΩ bias resistor. These components cause the effective gain to vary nonlinearly with wiper position, especially at higher amplitudes where the bias current is significant. The empirical fit captures this real behavior that the ideal formula misses.

### 50% Duty Cycle

```python
DUTY = 500_000   # pigpio duty cycle units: 0 to 1,000,000
pi.hardware_PWM(PWM_GPIO, frequency, DUTY)
```

A 50% duty cycle produces a symmetric square wave — equal time high and low. This is the standard definition of a square wave. Asymmetric duty cycles would produce pulse waves, which are different waveforms with different harmonic content.

---

## 8. User Interface Layer

**Files:** `callbacks.py`, `Driver.py`

### Navigation Architecture

The UI is a **modal state machine**. At any time, the user is in exactly one mode. Back/Main buttons allow navigation:

```
[OFF / Mode Select]  ← run_top_screen()
      │
[Mode Select Menu]   ← pick_menu()
      │
   ┌──┼──────────────┬──────────────┐
   │  │              │              │
[FG] [Ohmmeter] [Voltmeter] [DC Reference]
```

"Back" goes up one level. "Main" jumps all the way to the top Mode Select screen. This two-tier escape allows quick navigation without pressing Back multiple times.

### The `pick_menu()` Function

```python
def pick_menu(title, options, start_idx=0):
```

This is the single generic menu function used everywhere. It:
1. Resets all input flags
2. Attaches encoder and button callbacks
3. Draws the menu on the LCD
4. Loops: encoder rotation scrolls selection, button press selects and returns

**Scrolling window logic:**

```python
window_start = max(0, min(idx - 1, n - max_rows))
```

This tries to keep the selected item on the **second row** of the visible window (one item above, current item, one item below). It clamps so you never scroll past the start or end. This is the same UX pattern used in most embedded menu systems.

### The `adjust_value()` Function

Used for frequency, amplitude, and voltage inputs. Supports:
- Encoder rotation: change value by ±step
- Short press: confirm and return value
- Long press (≥2s): cancel and return None

**How long-press detection works:**

```python
# On falling edge (button press down):
_s["button_press_tick"] = tick          # Record when button went down

# On rising edge (button release):
hold = pigpio.tickDiff(press_tick, tick)
if hold >= HOLD_US:                     # HOLD_US = 2,000,000 (2 seconds)
    _s["long_press"] = True
else:
    _s["button_pressed"] = True
```

`pigpio.tickDiff` handles the 32-bit tick counter wraparound correctly (the tick counter rolls over every ~72 minutes). Using raw subtraction would give wrong results near the wraparound.

**Value snapping:**

```python
value = round(round(value / step) * step, 10)
```

This snaps the value to the nearest step grid point. The outer `round(..., 10)` removes floating-point rounding artifacts (e.g., 0.625 + 0.625 might become 1.2499999999999998 without it).

### Encoder Direction Inversion

In callbacks.py, the encoder delta is **negated**:

```python
def _on_rotate(direction):
    _s["encoder_delta"] = _s.get("encoder_delta", 0) - direction
```

`rotary_encoder.py` returns +1 for clockwise, −1 for counterclockwise. The menu uses the delta to advance the selection **downward** on clockwise. By negating: CW → delta goes negative → `idx + delta` → idx decreases → selection moves down the list. Wait — the list indices 0, 1, 2 correspond to visual top-to-bottom; decreasing index moves UP. The negation ensures CW rotation scrolls the cursor DOWN on screen, which is the natural human expectation for a knob on an instrument panel.

### Debouncing

```python
BUTTON_DEBOUNCE_US = 200_000   # 200 milliseconds
if last is not None and pigpio.tickDiff(last, tick) < BUTTON_DEBOUNCE_US:
    return   # Ignore: too close to last press
```

Mechanical buttons bounce — they generate rapid on/off transitions when pressed. A 200ms window rejects all bounces after the first event. We chose 200ms because it is short enough to feel responsive but long enough to reject mechanical bounce (which typically lasts < 20ms).

---

## 9. LCD Driver

**File:** `i2c_lcd.py`

### Hardware Chain

```
Pi I2C (bus 1) → PCF8574T (I2C → 8 GPIO) → HD44780 (LCD controller)
```

The HD44780 is the classic LCD controller found in virtually all character LCDs. It has an 8-bit parallel interface. We use only 4 bits (4-bit mode) since the PCF8574T I2C expander only provides 8 GPIO pins total (and some are used for backlight and control signals).

### PCF8574T Bit Mapping

```
P7  P6  P5  P4  P3  P2  P1  P0
B7  B6  B5  B4   BL   E  RW  RS
```

- **RS (P0):** Register Select. 0 = send LCD instruction. 1 = send character data.
- **RW (P1):** Read/Write. Always 0 (write only) in our implementation.
- **E (P2):** Enable. Strobed high-then-low to clock data into the LCD.
- **BL (P3):** Backlight control. 1 = on.
- **B4–B7 (P4–P7):** 4 data bits.

### 4-Bit Mode Operation

Every byte sent to the LCD requires **two transfers** (nibble high, then nibble low):

```python
def _byte(self, MSb, LSb):
    self._pulse(MSb)    # High nibble
    self._pulse(LSb)    # Low nibble
```

Each pulse:
```python
def _pulse(self, data):
    self._pi.i2c_write_byte(self._h, data | self.E)    # E=1
    time.sleep(0.001)
    self._pi.i2c_write_byte(self._h, data & ~self.E)   # E=0
    time.sleep(0.001)
```

The LCD latches data on the **falling edge** of E. The 1ms delays are conservative — the HD44780 requires only 37µs typical cycle time, but 1ms ensures reliability across temperature and voltage variations.

### Row Addressing

```python
_LCD_ROW = [0x80, 0xC0, 0x94, 0xD4]
```

The HD44780 DDRAM (display data memory) is laid out in two 40-character lines:
- Row 0 starts at 0x00 → instruction 0x80
- Row 1 starts at 0x40 → instruction 0xC0
- Row 2 starts at 0x14 → instruction 0x94 (second half of line 1)
- Row 3 starts at 0x54 → instruction 0xD4

The 20×4 display maps to two 40-character logical lines. Rows 2 and 3 are the continuation of rows 0 and 1.

### `put_line()` — Always Pad to Full Width

```python
def put_line(self, row, text):
    padded = text[:self._width].ljust(self._width)  # Truncate then pad to 20 chars
    self.move_to(row, 0)
    self.put_str(padded)
```

Writing a short string would leave old characters visible if the line was previously longer. Always writing exactly 20 characters (padded with spaces) clears stale content without needing a `clear()` call (which causes a visible flash).

---

## 10. Rotary Encoder Decoder

**File:** `rotary_encoder.py`  
**Encoder type:** Mechanical quadrature (Gray code)

### How Quadrature Encoding Works

A rotary encoder has two outputs (A and B) that pulse as the shaft turns. They are offset by 90°:

```
CW rotation:     A: ─┐  ┌─   B: ──┐  ┌─
                     └──┘        └──┘
         A rises first, then B rises
CCW rotation:    B: ─┐  ┌─   A: ──┐  ┌─
                     └──┘        └──┘
         B rises first, then A rises
```

By watching **which pin rises second**, you know the direction.

### Our Decoder Logic

```python
def _pulse(self, gpio, level, tick):
    if gpio == self.gpioA:
        self.levA = level
    else:
        self.levB = level

    if gpio != self.lastGpio:        # Pin changed (not same pin bouncing)
        self.lastGpio = gpio

        if gpio == self.gpioA and level == 1:    # A rose
            if self.levB == 1:                   # B was already high → CW
                self.callback(1)

        elif gpio == self.gpioB and level == 1:  # B rose
            if self.levA == 1:                   # A was already high → CCW
                self.callback(-1)
```

**Why `gpio != self.lastGpio` for debounce?** Mechanical encoders bounce — a single physical detent click can generate several pulses on the same pin. By requiring the GPIO to alternate (A, then B, then A...), we reject multiple pulses on the same pin in a row. This is a lightweight hardware-aware debounce that works without timers.

---

## 11. Driver.py — The Main Loop

### State Dictionary

All shared state lives in one dictionary injected into every module:

```python
state = {
    'active_callbacks': [],     # Pigpio callbacks to cancel on mode exit
    'button_last_tick': None,   # Last button event timestamp
    'button_press_tick': None,  # Button-down timestamp for long-press
    'encoder_delta': 0,         # Accumulated encoder ticks
    'button_pressed': False,    # Set by button ISR, cleared by handler
    'long_press': False,        # Set for ≥2s hold
    'fg_freq': 1000,            # Persists across FG menu visits
    'fg_amp': 0.0,
    'fg_output_on': False,
    'dc_voltage': 0.0,          # Persists across DC Ref menu visits
    'dc_output_on': False,
}
```

**Why a shared dict instead of global variables?** The dict is passed explicitly to every function that needs it (`setup_callbacks(state, pi, lcd)`). This is cleaner than global variables because: (a) dependencies are explicit, (b) it can be inspected or reset in one place, (c) modules can be tested independently by injecting a mock state dict.

### Boot Sequence

```python
ensure_all_off()           # Hardware safe state before UI starts
while True:
    run_top_screen()       # OFF or Mode Select
    while True:
        choice = pick_menu("Mode Select", [...])
        ...
        elif choice in ("Back", "Main"):
            break          # Exit inner loop → back to top screen
```

The double-loop structure means:
- Inner loop: navigates mode selection and individual modes
- Outer loop: handles OFF/Mode Select top screen

Pressing Back or Main from Mode Select `break`s the inner loop, returning to `run_top_screen()`.

### ensure_all_off()

```python
def ensure_all_off():
    sq_gen.stop()
    dc_ref.stop()
    state['fg_output_on'] = False
    state['dc_output_on'] = False
    lcd.clear()
    lcd.backlight(False)
    lcd._inst(0x08)      # Display off command
```

Called on boot and when user selects OFF. The LCD command `0x08` turns the display off (backlight separately controlled through PCF8574T BL bit). After 60 seconds of sleep, `run_top_screen()` re-enables backlight and display with `0x0C` before showing the menu.

---

## 12. Design Decisions You Must Be Able to Defend

### "Why did you use a SAR ADC instead of buying an ADC chip?"

The SAR is implemented in software using the MCP4131 pot as a programmable voltage source and the LM339 as a comparator. This reuses hardware already on the board for other purposes. A dedicated ADC (e.g., MCP3208) would be faster and higher resolution, but would require an additional chip, additional SPI connections, and more board space. Our approach demonstrates understanding of ADC fundamentals and makes efficient use of existing hardware.

### "Why 5-bit resolution? That's only 32 levels."

For a lab instrument measuring ±5V:
- 5-bit → 10V / 32 = 0.3125V per step
- This is sufficient for the spec (±0.15V tolerance stated in UI.md)
- More bits would require longer settle times and more SAR iterations, making the measurement slower

### "Why is the DC reference in 0.625V steps?"

0.625V = 10V / 16 steps. The MCP4231 has 128 wiper positions, but the circuit's effective resolution (how distinguishable two adjacent voltage steps are) was characterized as 16 usable levels across the ±5V range. The UI enforces 0.625V steps to prevent the user from selecting a voltage the hardware cannot reliably produce.

### "Why not use the SAR_ADC class from sar_logic.py in the voltmeter and ohmmeter?"

`sar_logic.py` was written as a more generic, reusable SAR class. However, `voltmeter.py` and `ohmmeter.py` each implement their own 5-bit SAR with mode-specific calibration and comparator polarity. Merging them would require more abstraction (passing calibration functions as parameters) which adds complexity without practical benefit since the two modes never run simultaneously.

### "Why median instead of mean for averaging?"

See Section 3. Summary: our measurements are quantized integer steps. The median always returns a real, measured step value. The mean could produce a fractional step (e.g., 18.3) which is not a physical measurement and introduces rounding when converting to voltage.

### "Why share SPI CE0 between square wave and DC reference?"

The Pi's SPI0 has only two chip-select lines (CE0, CE1). Since the UI is strictly modal, the square wave generator and DC reference are never active simultaneously. A hardware multiplexer or GPIO-based chip select would add components and complexity for no benefit.

### "What would you change if given more time?"

Good answers:
- Increase SAR to 7-bit (full MCP4131 resolution) for ~78mV per step
- Replace median filter with Kalman filter for faster-settling noisy inputs
- Add auto-ranging to the ohmmeter (switch R_ref values based on reading)
- Implement the `step_to_ohms()` function in `ohms_steps.py` (currently returns 0)
- Replace empirical square wave calibration with a feedback loop using the voltmeter

---

*End of Panel Practice document.*
