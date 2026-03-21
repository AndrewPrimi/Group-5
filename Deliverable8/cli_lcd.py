"""
cli_lcd.py  –  Terminal drop-in for i2c_lcd.lcd
================================================
Renders a 4-row LCD-style box in the terminal using ANSI cursor movement
so the display updates in-place without flickering.

Drop-in replacement: same put_line / put_str / put_chr / move_to / close API.
"""

import sys
import threading

_DISPLAY_LINES = 6   # 4 data rows + 2 border rows


class lcd:
    def __init__(self, pi=None, width=20, **kwargs):
        self.width = width
        self._rows = [' ' * width] * 4
        self._initialized = False
        self._lock = threading.Lock()

    # ── public API (mirrors i2c_lcd.lcd) ─────────────────────────────────────

    def put_line(self, row, text):
        text = str(text).ljust(self.width)[:self.width]
        with self._lock:
            self._rows[row] = text
            self._render()

    def move_to(self, row, column):
        pass   # no cursor concept in CLI mode

    def put_str(self, text):
        pass   # Driver.py only uses put_line; kept for API compatibility

    def put_chr(self, char):
        pass

    def put_symbol(self, index):
        pass

    def backlight(self, on):
        pass

    def close(self):
        pass

    # ── internal rendering ────────────────────────────────────────────────────

    def _render(self):
        """Redraw the 4-row box in-place using ANSI escape codes."""
        if self._initialized:
            # Move cursor up to the top of the box and overwrite
            sys.stdout.write(f"\033[{_DISPLAY_LINES}A")
        border = '+' + '-' * self.width + '+'
        sys.stdout.write(border + '\n')
        for row in self._rows:
            sys.stdout.write('|' + row + '|\n')
        sys.stdout.write(border + '\n')
        sys.stdout.flush()
        self._initialized = True
