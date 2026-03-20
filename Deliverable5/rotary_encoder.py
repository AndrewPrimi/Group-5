# rotary_encoder.py
# Originally written by joan2937 as part of the pigpio library examples.
# Source: https://abyz.me.uk/rpi/pigpio/examples.html
# License: Public Domain
"""
rotary_encoder.py – Gray-code decoder for a mechanical rotary encoder.

A standard rotary encoder outputs two square-wave signals (A and B) that are
90 degrees out of phase.  By tracking which signal transitions first, we can
determine the direction of rotation.

This decoder registers EITHER_EDGE callbacks on both pins and uses a simple
state-machine approach:
  - Record the current level of each pin on every edge.
  - Only act when the *other* pin fired last (eliminates same-pin bounce).
  - When pin A rises and pin B is already high -> clockwise  (+1).
  - When pin B rises and pin A is already high -> counter-clockwise (-1).
"""

import pigpio


class decoder:
    """Decode mechanical rotary encoder pulses into direction callbacks.

    Parameters
    ----------
    pi       : pigpio.pi instance
    gpioA    : BCM pin number for encoder channel A (CLK)
    gpioB    : BCM pin number for encoder channel B (DT)
    callback : function(direction) called on each detent,
               direction is +1 (CW) or -1 (CCW)
    """

    def __init__(self, pi, gpioA, gpioB, callback):
        self.pi = pi
        self.gpioA = gpioA
        self.gpioB = gpioB
        self.callback = callback

        # Current level of each channel (updated on every edge)
        self.levA = 0
        self.levB = 0

        # Last GPIO that fired – used to reject same-pin bounce
        self.lastGpio = None

        # Register edge callbacks on both encoder channels
        self.cbA = self.pi.callback(gpioA, pigpio.EITHER_EDGE, self._pulse)
        self.cbB = self.pi.callback(gpioB, pigpio.EITHER_EDGE, self._pulse)

    def _pulse(self, gpio, level, tick):
        """Called on every edge of either encoder channel.

        Updates the stored level, then checks the Gray-code transition
        to determine direction.  The `lastGpio != gpio` guard acts as
        a debounce filter: if the same pin fires twice in a row, the
        second edge is ignored.
        """
        # Track current level of whichever pin just changed
        #print("gpio", gpio)
        #print("self.gpioA", self.gpioA)
        #print("self.lastGpio", self.lastGpio)
        
        if gpio == self.gpioA:
            self.levA = level
        else:
            self.levB = level

        # Only process if a *different* pin fired than last time (debounce)
        if gpio != self.lastGpio:
            self.lastGpio = gpio

            # Pin A rising while B is already high -> clockwise
            if gpio == self.gpioA and level == 1:
                if self.levB == 1:
                    self.callback(1)

            # Pin B rising while A is already high -> counter-clockwise
            elif gpio == self.gpioB and level == 1:
                if self.levA == 1:
                    self.callback(-1)

    def cancel(self):
        """Unregister both pigpio edge callbacks."""
        self.cbA.cancel()
        self.cbB.cancel()
