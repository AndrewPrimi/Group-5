import i2c_lcd


class PotLCD:
    """Handles all LCD display logic for the pot controller.

    Uses flag-based updates to prevent I2C race conditions
    when callbacks fire rapidly.
    """

    def __init__(self, pi, width=20):
        self.lcd = i2c_lcd.lcd(pi, width=width)
        self.width = width

        # Display state
        self.selected_pot = 0
        self.menu_selection = 0
        self.ohms = 0.0

        # Flag-based update system to avoid I2C race conditions
        self._needs_main_page_update = False
        self._needs_pot_page_update = False
        self._needs_confirmation = False
        self._confirmation_pot = 0

    # --- Flag setters (safe to call from callbacks) ---

    def request_main_page_update(self, menu_selection):
        """Called from encoder callback to request a main page redraw."""
        self.menu_selection = menu_selection
        self._needs_main_page_update = True

    def request_pot_page_update(self, ohms, selected_pot):
        """Called from encoder callback to request a pot page redraw."""
        self.ohms = ohms
        self.selected_pot = selected_pot
        self._needs_pot_page_update = True

    def request_confirmation(self, selected_pot):
        """Called from button callback to show value set confirmation."""
        self._confirmation_pot = selected_pot
        self._needs_confirmation = True

    # --- Immediate draws (call from main loop only, not from callbacks) ---

    def draw_main_page(self):
        """Draw the main page with > indicator on the selected pot."""
        self.lcd.put_line(0, 'Select a Pot:')
        if self.menu_selection == 0:
            self.lcd.put_line(1, '> Pot 1')
            self.lcd.put_line(2, '  Pot 2')
        else:
            self.lcd.put_line(1, '  Pot 1')
            self.lcd.put_line(2, '> Pot 2')
        self.lcd.put_line(3, '')

    def draw_pot_page(self):
        """Draw the pot control page with current ohms value."""
        self.lcd.put_line(0, f'Pot {self.selected_pot + 1}')
        self.lcd.put_line(1, f'Ohms: {self.ohms:.1f}')
        self.lcd.put_line(2, '')
        self.lcd.put_line(3, '')

    def draw_confirmation(self):
        """Draw confirmation that value was sent to digi pot."""
        self.lcd.put_line(2, 'Value set!')
        self.lcd.put_line(3, f'Pot {self._confirmation_pot + 1} updated')

    # --- Process pending updates (call from main loop) ---

    def process_updates(self):
        """Check flags and perform any pending LCD writes.

        Call this from the main loop to safely batch LCD updates.
        Returns True if an update was performed.
        """
        updated = False

        if self._needs_main_page_update:
            self._needs_main_page_update = False
            self.draw_main_page()
            updated = True

        if self._needs_pot_page_update:
            self._needs_pot_page_update = False
            self.draw_pot_page()
            updated = True

        if self._needs_confirmation:
            self._needs_confirmation = False
            self.draw_confirmation()
            updated = True

        return updated

    def close(self):
        """Close the LCD and release resources."""
        self.lcd.close()
