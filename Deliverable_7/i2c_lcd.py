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
    This class provides simple functions to display text on an I2C LCD
    based on the PCF8574T I2C 8-bit port expander.

    PCF8574T P7   P6   P5   P4   P3   P2   P1   P0
    HD44780  B7   B6   B5   B4   BL   E    RW   RS

    This code defaults to working with an adapter with the above
    configuration.

    If yours is different you will have to specify the mapping
    when you instantiate the LCD.
    """

    """
    Commands

    LCD_CLEARDISPLAY = 0x01
    LCD_RETURNHOME = 0x02
    LCD_ENTRYMODESET = 0x04
    LCD_DISPLAYCONTROL = 0x08
    LCD_CURSORSHIFT = 0x10
    LCD_FUNCTIONSET = 0x20
    LCD_SETCGRAMADDR = 0x40
    LCD_SETDDRAMADDR = 0x80

    Flags for display entry mode

    LCD_ENTRYRIGHT = 0x00
    LCD_ENTRYLEFT = 0x02
    LCD_ENTRYSHIFTINCREMENT = 0x01
    LCD_ENTRYSHIFTDECREMENT = 0x00

    Flags for display on/off control

    LCD_DISPLAYON = 0x04
    LCD_DISPLAYOFF = 0x00
    LCD_CURSORON = 0x02
    LCD_CURSOROFF = 0x00
    LCD_BLINKON = 0x01
    LCD_BLINKOFF = 0x00

    Flags for display/cursor shift

    LCD_DISPLAYMOVE = 0x08
    LCD_CURSORMOVE = 0x00
    LCD_MOVERIGHT = 0x04
    LCD_MOVELEFT = 0x00

    Flags for function set

    LCD_8BITMODE = 0x10
    LCD_4BITMODE = 0x00
    LCD_2LINE = 0x08
    LCD_1LINE = 0x00
    LCD_5x10DOTS = 0x04
    LCD_5x8DOTS = 0x00

    Flags for backlight control

    LCD_BACKLIGHT = 0x08
    LCD_NOBACKLIGHT = 0x00
    """

    _LCD_ROW = [0x80, 0xC0, 0x94, 0xD4]

    def __init__(self, pi, bus=1, addr=0x27, width=20, backlight_on=True,
                 RS=0,
                 #RW=1,
                 E=2, BL=3, B4=4, debug=True):

        self.pi = pi
        self.width = width
        self.backlight_on = backlight_on
        self.debug = debug

        self.RS = (1 << RS)
        self.E = (1 << E)
        self.BL = (1 << BL)
        self.B4 = B4

        self._h   = None
        self.addr = addr

        if addr is None:
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
                    print(f"LCD initialization successful at {hex(candidate)}")

                return

            except Exception as e:
                last_error = e
                if self.debug:
                    print(f"LCD init failed at {hex(candidate)}: {e}")

                try:
                    if self._h is not None:
                        self.pi.i2c_close(self._h)
                except Exception:
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
        '''try:
            self._byte(0x00, 0x00)
        except Exception:
            pass'''

    """
    def _init(self):

        Initialize LCD in 4-bit mode with conservative delays.

        time.sleep(0.05)

        self._inst(0x33) # Initialise 1
        #time.sleep(0.005)

        self._inst(0x32) # Initialise 2
        #time.sleep(0.005)

        self._inst(0x28)   # 4-bit, 2 line, 5x8 font
        #time.sleep(0.001)

        self._inst(0x0C)   # display on, cursor off, blink off
        #time.sleep(0.001)

        self._inst(0x06)   # entry mode set: increment
        #time.sleep(0.001)

        self._inst(0x01)   # clear display
        #time.sleep(0.002)

        self._inst(0x33) # Initialise 1
        self._inst(0x32) # Initialise 2
        self._inst(0x06) # Cursor increment
        self._inst(0x0C) # Display on, cursor off, blink off
        self._inst(0x28) # 4-bits, 1 line, 5x8 font
        self._inst(0x01) # Clear display
    """

    def _init(self):
        time.sleep(0.1)

        for _ in range(3):
            self._write4bits(0x03)
            time.sleep(0.005)

        self._write4bits(0x02)
        time.sleep(0.005)

        self._inst(0x28)
        time.sleep(0.001)

        # Display OFF
        self._inst(0x08)
        time.sleep(0.001)

        # Clear Display
        self._inst(0x01)
        time.sleep(0.005)

        # Entry mode
        self._inst(0x06)
        time.sleep(0.005)

        # Display ON
        self._inst(0x0C)
        time.sleep(0.001)
        """self._write4bits(0x03)
        time.sleep(0.005)

        self._write4bits(0x03)
        time.sleep(0.005)

        self._write4bits(0x03)
        time.sleep(0.005)

        self._write4bits(0x02)  # 4-bit mode

        self._inst(0x28)
        self._inst(0x08)
        self._inst(0x01)
        time.sleep(0.005)
        self._inst(0x06)
        self._inst(0x0C)"""
        
    def _byte(self, MSb, LSb):

        if self.backlight_on:
            MSb |= self.BL
            LSb |= self.BL

        # Send high nibble
        self._pulse(MSb)

        # Send low nibble
        self._pulse(LSb)

    def _pulse(self, data):
        data &= 0xFF

        # Enable HIGH
        self.pi.i2c_write_device(self._h, [data | self.E])
        time.sleep(0.001)

        # Enable LOW
        self.pi.i2c_write_device(self._h, [(data & ~self.E) & 0xFF])
        time.sleep(0.001)

    def _inst(self, bits):
        """
        Send instruction byte.
        """
        msn = (bits >> 4) & 0x0F
        lsn = bits & 0x0F

        MSb = msn << self.B4
        LSb = lsn << self.B4

        self._byte(MSb, LSb)

    def _write4bits(self, nibble):
        data = (nibble << self.B4) & 0xFF

        if self.backlight_on:
            data |= self.BL

        self._pulse(data)

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
        '''try:
            self.clear()
        except Exception:
            pass

        if self._h is not None:
            try:
                self.pi.i2c_close(self._h)
            except pigpio.error:
                pass
            self._h = None'''

        self._inst(0x01)
        if self._h is not None:
            try:
                self.pi.i2c_close(self._h)
            except pigpio.error:
                pass
            self._h = None


if __name__ == "__main__":

    import i2c_lcd
    import pigpio
    import time

    pi = pigpio.pi()
    if not pi.connected:
        print("pigpio is not connected. Start it with: sudo pigpiod")
        raise SystemExit(1)

    try:
        # Leave addr=None so it auto-tries common LCD addresses.
        # If you want to force one, use addr=0x27 or addr=0x24, etc.
        #lcd_display = lcd(pi, addr=None, width=20)

        lcd_display = lcd(pi, addr=0x27, width=20, RS=0,
                          #RW=1,
                          E=2, BL=3, B4=4, debug=True)

        lcd_display.backlight(True)
        #lcd_display.clear()
        #time.sleep(2)
        
        lcd_display.put_line(0, "LCD Test")
        lcd_display.put_line(1, f"Addr: {hex(lcd_display.addr)}")
        lcd_display.put_line(2, "Hello World")
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
