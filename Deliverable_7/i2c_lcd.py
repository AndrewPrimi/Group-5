#!/usr/bin/env python3

# i2c_lcd.py
# Updated version with:
# - safer initialization timing
# - optional auto-detection across common LCD backpack addresses
# - simple startup diagnostics

import pigpio
import time


class lcd:
    """
    LCD driver for HD44780 displays using a PCF8574/PCF8574T style I2C backpack.

    Default backpack bit mapping assumed:
        PCF8574T P7   P6   P5   P4   P3   P2   P1   P0
        HD44780  B7   B6   B5   B4   BL   E    RW   RS

    If your backpack differs, change the constructor mapping pins.
    """

    _LCD_ROW = [0x80, 0xC0, 0x94, 0xD4]

    def __init__(self, pi, bus=1, addr=None, width=20, backlight_on=True,
                 RS=0, RW=1, E=2, BL=3, B4=4, debug=True):

        self.pi = pi
        self.width = width
        self.backlight_on = backlight_on
        self.debug = debug

        self.RS = (1 << RS)
        self.E = (1 << E)
        self.BL = (1 << BL)
        self.B4 = B4

        self._h = None
        self.addr = None

        if addr is None:
            # Try common PCF8574 / PCF8574A address ranges
            candidate_addrs = [
                0x27, 0x26, 0x25, 0x24,
                0x23, 0x22, 0x21, 0x20,
                0x3F, 0x3E, 0x3D, 0x3C,
                0x3B, 0x3A, 0x39, 0x38
            ]
        else:
            candidate_addrs = [addr]

        last_error = None

        for candidate in candidate_addrs:
            try:
                handle = self.pi.i2c_open(bus, candidate)
                self._h = handle
                self.addr = candidate

                if self.debug:
                    print(f"LCD I2C opened at address {hex(candidate)} with handle {handle}")

                time.sleep(0.05)
                self._init()

                if self.debug:
                    print(f"LCD initialization attempted at {hex(candidate)}")

                return

            except pigpio.error as e:
                last_error = e
                try:
                    if self._h is not None:
                        self.pi.i2c_close(self._h)
                except pigpio.error:
                    pass
                self._h = None
                self.addr = None

        raise RuntimeError(
            f"Could not open/init LCD on any tested I2C address. Last error: {last_error}"
        )

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

    def _init(self):
        """
        Initialize LCD in 4-bit mode with conservative delays.
        """
        time.sleep(0.05)

        self._inst(0x33)
        time.sleep(0.005)

        self._inst(0x32)
        time.sleep(0.005)

        self._inst(0x28)   # 4-bit, 2 line, 5x8 font
        time.sleep(0.001)

        self._inst(0x0C)   # display on, cursor off, blink off
        time.sleep(0.001)

        self._inst(0x06)   # entry mode set: increment
        time.sleep(0.001)

        self._inst(0x01)   # clear display
        time.sleep(0.002)

    def _byte(self, MSb, LSb):
        """
        Send upper and lower nibble.
        """
        if self.backlight_on:
            MSb |= self.BL
            LSb |= self.BL

        data = [
            MSb | self.E, MSb & ~self.E,
            LSb | self.E, LSb & ~self.E
        ]

        for _ in range(3):
            try:
                self.pi.i2c_write_device(self._h, data)
                time.sleep(0.001)
                return
            except pigpio.error:
                time.sleep(0.01)

        raise RuntimeError(f"LCD I2C write failed at {hex(self.addr)} with data {data}")

    def _inst(self, bits):
        """
        Send instruction byte.
        """
        msn = (bits >> 4) & 0x0F
        lsn = bits & 0x0F

        MSb = msn << self.B4
        LSb = lsn << self.B4

        self._byte(MSb, LSb)

    def _data(self, bits):
        """
        Send data byte.
        """
        msn = (bits >> 4) & 0x0F
        lsn = bits & 0x0F

        MSb = (msn << self.B4) | self.RS
        LSb = (lsn << self.B4) | self.RS

        self._byte(MSb, LSb)

    def move_to(self, row, column):
        """
        Position cursor at row and column (0-based).
        """
        if row < 0 or row >= len(self._LCD_ROW):
            raise ValueError("row must be 0, 1, 2, or 3")
        self._inst(self._LCD_ROW[row] + column)

    def clear(self):
        """
        Clear display.
        """
        self._inst(0x01)
        time.sleep(0.002)

    def put_inst(self, byte):
        """
        Write an instruction byte.
        """
        self._inst(byte)

    def put_symbol(self, index):
        """
        Write the symbol with index at the current cursor position.
        """
        self._data(index)

    def put_chr(self, char):
        """
        Write a character at the current cursor position.
        """
        self._data(ord(char))

    def put_str(self, text):
        """
        Write a string at the current cursor position.
        """
        for ch in str(text):
            self.put_chr(ch)

    def put_line(self, row, text):
        """
        Replace an LCD row with a new string.
        """
        text = str(text).ljust(self.width)[:self.width]
        self.move_to(row, 0)
        self.put_str(text)

    def close(self):
        """
        Clear and close LCD.
        """
        try:
            self.clear()
        except Exception:
            pass

        if self._h is not None:
            try:
                self.pi.i2c_close(self._h)
            except pigpio.error:
                pass
            self._h = None


if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        print("pigpio is not connected. Start it with: sudo pigpiod")
        raise SystemExit(1)

    try:
        # Leave addr=None so it auto-tries common LCD addresses.
        # If you want to force one, use addr=0x27 or addr=0x24, etc.
        lcd_display = lcd(pi, addr=0x26, width=20, debug=True)

        lcd_display.backlight(True)
        lcd_display.clear()

        lcd_display.put_line(0, "LCD Test")
        lcd_display.put_line(1, f"Addr: {hex(lcd_display.addr)}")
        lcd_display.put_line(2, "Hello Logan")
        lcd_display.put_line(3, "It is working")

        time.sleep(5)

        count = 1
        while True:
            lcd_display.put_line(0, "pigpio LCD test")
            lcd_display.put_line(1, f"Addr: {hex(lcd_display.addr)}")
            lcd_display.put_line(2, time.strftime("%b %d %H:%M:%S"))
            lcd_display.put_line(3, f"Count: {count}")
            count += 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nExiting on Ctrl+C")

    except Exception as e:
        print("LCD test failed:", e)

    finally:
        try:
            lcd_display.close()
        except Exception:
            pass
        pi.stop()
   
   
