#!/usr/bin/env python

# integrator_adc.py (HX711.py refactored)
# Replaces the HX711 24-bit serial driver with a driver for a custom
# dual-slope integrating ADC built from an Op-Amp and LM339 comparator.
#
# Original HX711 driver by joan2937 (Public Domain).
# Source: https://abyz.me.uk/rpi/pigpio/examples.html
# Refactored for 5-bit dual-slope integrator ADC by Group 5.

"""
How the dual-slope integrating ADC works
-----------------------------------------
1. Integrate phase:  Pi pulls TRIG HIGH for a fixed time T_INT_US.
                     The Op-Amp ramps its output up proportional to V_in.

2. De-integrate phase: Pi pulls TRIG LOW.
                     The integrator ramps back down at a rate set by the
                     reference (digital pot via SPI).  The LM339 comparator
                     monitors the ramp and flips COMP_OUT when it crosses zero.

3. Measurement:      Pi records the elapsed time T_deint from TRIG LOW
                     until the COMP_OUT edge.

4. Conversion:       5-bit value = round((T_deint / T_INT_US) * 31), clamped 0-31.

The digital potentiometer (MCP4231/4131, controlled in checkpoint_c via SPI)
sets the de-integration reference resistance, acting as the gain/range control.
"""

import time
import pigpio

# ── ADC resolution ──────────────────────────────────────
DATA_BITS = 5                    # 5-bit output → values 0 to 31
MAX_VALUE = (1 << DATA_BITS) - 1 # 31

# ── Timing ───────────────────────────────────────────────
T_INT_US = 50000                 # integration phase duration in microseconds (50 ms)
                                 # Increase for higher resolution / slower readings.
POLL_INTERVAL_S = 0.1            # default time between triggered readings (100 ms)


class IntegratorADC:
    """Driver for a 5-bit dual-slope integrating ADC.

    Uses two GPIO pins:
      TRIG     – output to the integrator circuit (HIGH = integrate, LOW = de-integrate)
      COMP_OUT – input from the LM339 comparator (edge signals end of de-integrate)

    Parameters
    ----------
    pi           : pigpio.pi instance
    TRIG         : BCM pin number for the integration trigger output
    COMP_OUT     : BCM pin number for the LM339 comparator output input
    interval_s   : seconds between readings when trigger() is called externally
                   (not used internally — caller drives the timing via trigger())
    callback     : optional function(count, value) called on each new reading
    """

    def __init__(self, pi, TRIG, COMP_OUT, interval_s=POLL_INTERVAL_S, callback=None):
        self.pi = pi
        self.TRIG = TRIG
        self.COMP_OUT = COMP_OUT
        self.interval_s = interval_s
        self.callback = callback

        # Internal state
        self._count = 0             # incremented on every valid reading
        self._value = 0             # most recent 5-bit result
        self._deint_start = None    # tick when de-integrate phase began
        self._paused = True         # True until start() is called

        # Configure GPIO pins
        self.pi.set_mode(TRIG, pigpio.OUTPUT)
        self.pi.write(TRIG, 0)                          # ensure TRIG starts LOW
        self.pi.set_mode(COMP_OUT, pigpio.INPUT)
        self.pi.set_pull_up_down(COMP_OUT, pigpio.PUD_UP)

        # Watch for comparator edge (either direction for robustness)
        self._cb = self.pi.callback(COMP_OUT, pigpio.EITHER_EDGE, self._comp_callback)

        self.start()

    # ── Public API ─────────────────────────────────────

    def get_reading(self):
        """Return the most recent (count, value) pair.

        count is incremented on every new reading.
        value is a 5-bit integer in the range 0-31.
        Poll this in a loop and compare count to detect new readings.
        """
        return self._count, self._value

    def set_callback(self, callback):
        """Set or replace the per-reading callback function(count, value).

        Pass None to remove the callback.
        """
        self.callback = callback

    def trigger(self):
        """Kick off one integrate -> de-integrate cycle.

        Call this from your main loop at whatever rate you want readings.
        Ignored if paused.
        """
        if self._paused:
            return

        # ── Integrate phase ─────────────────────────────
        # Pull TRIG HIGH and hold for T_INT_US microseconds.
        # The Op-Amp ramps its output during this window.
        self.pi.write(self.TRIG, 1)
        time.sleep(T_INT_US / 1_000_000)   # convert µs to seconds

        # ── De-integrate phase ──────────────────────────
        # Pull TRIG LOW and record the tick so _comp_callback can
        # measure elapsed time when the comparator fires.
        self.pi.write(self.TRIG, 0)
        self._deint_start = self.pi.get_current_tick()

    def start(self):
        """Resume taking readings."""
        self._paused = False
        self._deint_start = None

    def pause(self):
        """Pause readings and pull TRIG LOW to abort any in-progress cycle."""
        self._paused = True
        self.pi.write(self.TRIG, 0)
        self._deint_start = None

    def cancel(self):
        """Stop all activity and release GPIO resources."""
        self.pause()
        if self._cb is not None:
            self._cb.cancel()
            self._cb = None

    # ── Internal callback ───────────────────────────────

    def _comp_callback(self, _gpio, _level, tick):
        """Called on every edge of COMP_OUT (the LM339 comparator output).

        Measures T_deint (time from TRIG LOW to this edge), converts it to
        a 5-bit value, stores it, and calls the user callback if set.
        """
        # Ignore if we're paused or no de-integrate phase is in progress
        if self._paused or self._deint_start is None:
            return

        # Measure elapsed de-integration time in microseconds
        t_deint = pigpio.tickDiff(self._deint_start, tick)
        self._deint_start = None   # clear so duplicate edges are ignored

        # Convert timing ratio to 5-bit integer (0-31)
        raw = round((t_deint / T_INT_US) * MAX_VALUE)
        self._value = max(0, min(raw, MAX_VALUE))   # clamp to valid range
        self._count += 1

        if self.callback is not None:
            self.callback(self._count, self._value)


# ── Demo / self-test ────────────────────────────────────

if __name__ == '__main__':

    # Pin assignments — update these to match your wiring
    TRIG_PIN     = 20   # GPIO pin driving the integrator trigger
    COMP_OUT_PIN = 21   # GPIO pin reading the LM339 comparator output

    def on_reading(count, value):
        print(f"[{count:4d}]  raw 5-bit value: {value:2d}  ({value / MAX_VALUE * 100:.1f}% FS)")

    pi = pigpio.pi()
    if not pi.connected:
        exit(0)

    adc = IntegratorADC(pi, TRIG=TRIG_PIN, COMP_OUT=COMP_OUT_PIN, callback=on_reading)

    print(f"Integrator ADC started  (T_INT={T_INT_US} µs, 5-bit, 0-{MAX_VALUE})")
    print("Press Ctrl-C to stop.\n")

    try:
        while True:
            adc.trigger()               # start one integrate/de-integrate cycle
            time.sleep(POLL_INTERVAL_S) # wait before next reading

    except KeyboardInterrupt:
        print("\nStopping...")

    adc.cancel()
    pi.stop()
