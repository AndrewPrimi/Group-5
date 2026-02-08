import pigpio


class decoder:
    """Decode mechanical rotary encoder pulses.

    Tracks Gray code state transitions on both pins to reliably
    determine direction. Calls callback(direction) where
    direction is 1 (CW) or -1 (CCW).

    Based on pigpio rotary encoder example.
    """

    def __init__(self, pi, gpioA, gpioB, callback):
        self.pi = pi
        self.gpioA = gpioA
        self.gpioB = gpioB
        self.callback = callback

        self.levA = 0
        self.levB = 0
        self.lastGpio = None

        self.cbA = self.pi.callback(gpioA, pigpio.EITHER_EDGE, self._pulse)
        self.cbB = self.pi.callback(gpioB, pigpio.EITHER_EDGE, self._pulse)

    def _pulse(self, gpio, level, tick):
        if gpio == self.gpioA:
            self.levA = level
        else:
            self.levB = level

        if gpio != self.lastGpio:  # debounce
            self.lastGpio = gpio
            if gpio == self.gpioA and level == 1:
                if self.levB == 1:
                    self.callback(1)
            elif gpio == self.gpioB and level == 1:
                if self.levA == 1:
                    self.callback(-1)

    def cancel(self):
        self.cbA.cancel()
        self.cbB.cancel()
