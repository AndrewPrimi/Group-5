"""
Driver.py  –  Function Generator UI
=====================================
Terminal UI (curses) for the SquareWaveGenerator.

Navigation:
  ↑ / ↓      move selection
  Enter / Spc  confirm
  Q           quit from any menu

Menu structure:
  Main
  ├── Type
  │     Square | Back | Main
  ├── Frequency
  │     Input Frequency | Back | Main
  ├── Amplitude
  │     Input Amplitude | Back | Main
  └── Output
        On   → live display (press any key to return)
        Off
        Back  (turns output OFF)
        Main  (turns output OFF)
"""

import curses
import time

from sqaure_wave import (
    SquareWaveGenerator,
    MIN_FREQ, MAX_FREQ, FREQ_STEP, MAX_AMP,
)

# Sentinel return values for menu navigation
_BACK = "__BACK__"
_MAIN = "__MAIN__"
_QUIT = "__QUIT__"


class FunctionGeneratorUI:

    def __init__(self):
        self._gen        = None
        self._wave_type  = "Square"
        self._frequency  = 1000       # Hz
        self._amplitude  = 0.0        # V
        self._output_on  = False

    # ── Entry point ───────────────────────────────────────────────────────────
    def run(self):
        curses.wrapper(self._curses_main)

    def _curses_main(self, scr):
        curses.curs_set(0)
        scr.keypad(True)

        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN,  -1)   # ON / success
            curses.init_pair(2, curses.COLOR_RED,    -1)   # OFF / error
            curses.init_pair(3, curses.COLOR_YELLOW, -1)   # prompt / subtitle
            curses.init_pair(4, curses.COLOR_CYAN,   -1)   # header

        try:
            self._gen = SquareWaveGenerator()
        except RuntimeError as err:
            scr.clear()
            scr.addstr(0, 0, f"Hardware error: {err}")
            scr.addstr(2, 0, "Press any key to exit.")
            scr.refresh()
            scr.getch()
            return

        try:
            self._menu_main(scr)
        finally:
            if self._gen:
                self._gen.cleanup()

    # ── Shared drawing helpers ────────────────────────────────────────────────
    def _draw_status_bar(self, scr):
        """Clear screen and draw the persistent top status bar."""
        h, w = scr.getmaxyx()
        scr.clear()

        # Title
        title = " FUNCTION GENERATOR "
        hdr_attr = curses.color_pair(4) | curses.A_BOLD | curses.A_REVERSE \
                   if curses.has_colors() else curses.A_BOLD | curses.A_REVERSE
        scr.addstr(0, max(0, (w - len(title)) // 2), title, hdr_attr)

        # Live parameter line
        out_attr = (curses.color_pair(1) | curses.A_BOLD) if self._output_on \
                   else (curses.color_pair(2) | curses.A_BOLD) \
                   if curses.has_colors() else curses.A_BOLD
        scr.addstr(2, 2, f"Type: {self._wave_type:<8}")
        scr.addstr(2, 22, f"Freq: {self._frequency:>5} Hz")
        scr.addstr(2, 40, f"Amp: +/-{self._amplitude:4.1f} V")
        scr.addstr(2, 58, "Output: ")
        scr.addstr(2, 66, "ON " if self._output_on else "OFF", out_attr)

        scr.addstr(3, 0, "─" * max(0, w - 1))

    def _pick_menu(self, scr, title, options, subtitle=""):
        """
        Arrow-key menu.  Returns the label of the chosen option, or
        _BACK / _MAIN / _QUIT for those navigation items.
        """
        idx = 0
        while True:
            self._draw_status_bar(scr)
            h, w = scr.getmaxyx()

            scr.addstr(5, 2, title, curses.A_BOLD)
            if subtitle:
                sub_attr = curses.color_pair(3) if curses.has_colors() \
                           else curses.A_NORMAL
                scr.addstr(6, 2, subtitle, sub_attr)

            row0 = 8 if subtitle else 7
            for i, opt in enumerate(options):
                if row0 + i >= h - 2:
                    break
                if i == idx:
                    scr.addstr(row0 + i, 4, f" > {opt} ",
                               curses.A_REVERSE | curses.A_BOLD)
                else:
                    scr.addstr(row0 + i, 4, f"   {opt}")

            hint_row = row0 + len(options) + 1
            if hint_row < h - 1:
                scr.addstr(hint_row, 2,
                           "UP/DOWN: navigate    ENTER: select    Q: quit")
            scr.refresh()

            key = scr.getch()
            if key in (curses.KEY_UP, ord('k')):
                idx = (idx - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord('j')):
                idx = (idx + 1) % len(options)
            elif key in (curses.KEY_ENTER, ord('\n'), ord('\r'), ord(' ')):
                sel = options[idx]
                if sel == "Back":
                    return _BACK
                if sel == "Main":
                    return _MAIN
                return sel
            elif key in (ord('q'), ord('Q')):
                return _QUIT

    def _prompt_input(self, scr, label, row=8):
        """Show a text prompt and return the entered string."""
        self._draw_status_bar(scr)
        h, w = scr.getmaxyx()
        scr.addstr(row,     2, label,
                   curses.color_pair(3) if curses.has_colors() else curses.A_NORMAL)
        scr.addstr(row + 1, 2, "> ")
        curses.echo()
        curses.curs_set(1)
        scr.refresh()
        try:
            raw = scr.getstr(row + 1, 4, 20)
            return raw.decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""
        finally:
            curses.noecho()
            curses.curs_set(0)

    def _flash(self, scr, msg, row=10, color=1, delay=1.2):
        """Display a short timed message then return."""
        attr = curses.color_pair(color) if curses.has_colors() else curses.A_NORMAL
        scr.addstr(row, 2, msg, attr)
        scr.refresh()
        time.sleep(delay)

    # ── Top-level menu ────────────────────────────────────────────────────────
    def _menu_main(self, scr):
        while True:
            choice = self._pick_menu(
                scr, "MAIN MENU",
                ["Type", "Frequency", "Amplitude", "Output", "Quit"],
            )
            if choice == "Type":
                self._menu_type(scr)
            elif choice == "Frequency":
                self._menu_frequency(scr)
            elif choice == "Amplitude":
                self._menu_amplitude(scr)
            elif choice == "Output":
                self._menu_output(scr)
            elif choice in ("Quit", _BACK, _MAIN, _QUIT):
                if self._output_on:
                    self._gen.stop()
                    self._output_on = False
                return

    # ── Type menu ─────────────────────────────────────────────────────────────
    def _menu_type(self, scr):
        while True:
            choice = self._pick_menu(
                scr, "TYPE",
                ["Square", "Back", "Main"],
                subtitle=f"Current: {self._wave_type}",
            )
            if choice == "Square":
                self._wave_type = "Square"
                self._flash(scr, "Wave type set to Square.", color=1)
            elif choice in (_BACK, _MAIN, _QUIT):
                return

    # ── Frequency menu ────────────────────────────────────────────────────────
    def _menu_frequency(self, scr):
        while True:
            sub = (f"Current: {self._frequency} Hz  "
                   f"[{MIN_FREQ} – {MAX_FREQ} Hz, step {FREQ_STEP} Hz]")
            choice = self._pick_menu(
                scr, "FREQUENCY",
                ["Input Frequency", "Back", "Main"],
                subtitle=sub,
            )
            if choice == "Input Frequency":
                self._input_frequency(scr)
            elif choice in (_BACK, _MAIN, _QUIT):
                return

    def _input_frequency(self, scr):
        raw = self._prompt_input(
            scr,
            f"Enter frequency ({MIN_FREQ}–{MAX_FREQ} Hz, {FREQ_STEP} Hz steps):",
        )
        try:
            freq = int(raw)
            freq = int(round(freq / FREQ_STEP) * FREQ_STEP)
            freq = max(MIN_FREQ, min(MAX_FREQ, freq))
            self._frequency = freq
            self._gen.set_frequency(freq)
            self._flash(scr, f"Frequency set to {freq} Hz.", color=1)
        except ValueError:
            self._flash(scr, "Invalid input — frequency unchanged.", color=2)

    # ── Amplitude menu ────────────────────────────────────────────────────────
    def _menu_amplitude(self, scr):
        while True:
            sub = (f"Current: +/-{self._amplitude:.1f} V  "
                   f"[0.0 – {MAX_AMP:.1f} V]")
            choice = self._pick_menu(
                scr, "AMPLITUDE",
                ["Input Amplitude", "Back", "Main"],
                subtitle=sub,
            )
            if choice == "Input Amplitude":
                self._input_amplitude(scr)
            elif choice in (_BACK, _MAIN, _QUIT):
                return

    def _input_amplitude(self, scr):
        raw = self._prompt_input(
            scr,
            f"Enter amplitude 0.0 – {MAX_AMP:.1f} V  (output will swing +/- V):",
        )
        try:
            amp = float(raw)
            amp = max(0.0, min(MAX_AMP, amp))
            self._amplitude = amp
            self._gen.set_amplitude(amp)
            self._flash(scr, f"Amplitude set to +/-{amp:.1f} V.", color=1)
        except ValueError:
            self._flash(scr, "Invalid input — amplitude unchanged.", color=2)

    # ── Output menu ───────────────────────────────────────────────────────────
    def _menu_output(self, scr):
        while True:
            sub = "Status: ON" if self._output_on else "Status: OFF"
            choice = self._pick_menu(
                scr, "OUTPUT",
                ["On", "Off", "Back", "Main"],
                subtitle=sub,
            )
            if choice == "On":
                self._gen.set_frequency(self._frequency)
                self._gen.set_amplitude(self._amplitude)
                self._gen.start()
                self._output_on = True
                self._live_display(scr)          # blocks until user presses a key
            elif choice == "Off":
                self._gen.stop()
                self._output_on = False
            elif choice in (_BACK, _MAIN, _QUIT):
                # Requirement: backing out of Output must turn off by default
                if self._output_on:
                    self._gen.stop()
                    self._output_on = False
                return

    # ── Live output display ───────────────────────────────────────────────────
    def _live_display(self, scr):
        """
        Full-screen live readout shown while the output is ON.
        Refreshes every 250 ms.  Any keypress returns to the Output menu.
        The output remains ON after returning (user can turn it off via "Off").
        """
        scr.nodelay(True)
        try:
            while True:
                h, w = scr.getmaxyx()
                scr.clear()

                # Header
                title = " LIVE OUTPUT "
                hdr_attr = (curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE) \
                            if curses.has_colors() else (curses.A_BOLD | curses.A_REVERSE)
                scr.addstr(0, max(0, (w - len(title)) // 2), title, hdr_attr)

                # Box
                r = 2
                box_w = 38
                period_ms  = 1000.0 / self._frequency
                pk_pk      = 2 * self._amplitude

                scr.addstr(r,     2, "+" + "─" * (box_w - 2) + "+")
                scr.addstr(r + 1, 2, f"| {'STATUS':12}  {'● ACTIVE':>20} |",
                           curses.color_pair(1) | curses.A_BOLD
                           if curses.has_colors() else curses.A_BOLD)
                scr.addstr(r + 2, 2, f"| {'Type':12}  {self._wave_type:>20} |")
                scr.addstr(r + 3, 2, f"| {'Frequency':12}  {str(self._frequency) + ' Hz':>20} |")
                scr.addstr(r + 4, 2, f"| {'Amplitude':12}  {f'+/-{self._amplitude:.2f} V':>20} |")
                scr.addstr(r + 5, 2, f"| {'Pk-Pk':12}  {f'{pk_pk:.2f} V':>20} |")
                scr.addstr(r + 6, 2, f"| {'Period':12}  {f'{period_ms:.4f} ms':>20} |")
                scr.addstr(r + 7, 2, f"| {'Duty Cycle':12}  {'50 %':>20} |")
                scr.addstr(r + 8, 2, "+" + "─" * (box_w - 2) + "+")

                scr.addstr(r + 10, 2, "Press any key to return to Output menu…")
                scr.refresh()

                key = scr.getch()
                if key != -1:
                    break

                time.sleep(0.25)
        finally:
            scr.nodelay(False)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ui = FunctionGeneratorUI()
    ui.run()
