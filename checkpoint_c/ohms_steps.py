import pot_lcd


def ohms_to_step(ohms):
    """Convert desired Ohms to a step value (0-128)."""
    ohms = max(0, min(ohms, pot_lcd.MAXIMUM_OHMS))
    step = int((ohms / pot_lcd.MAXIMUM_OHMS) * pot_lcd.MAX_STEPS)
    return step


def step_to_ohms(step):
    """Convert step value to approximate Ohms."""
    return (step / pot_lcd.MAX_STEPS) * pot_lcd.MAXIMUM_OHMS


def set_digipot_step(step_value):
    """Write data bytes to the currently selected MCP4131's SPI device handle."""
    if 0 <= step_value <= pot_lcd.MAX_STEPS:
        h = pot_lcd.handle_pot1 if pot_lcd.selected_pot == 0 else pot_lcd.handle_pot2
        pot_lcd.pi.spi_write(h, [0x00, step_value])
        approx_ohms = step_to_ohms(step_value)
        print(
            f"Pot {pot_lcd.selected_pot + 1} | Step: {step_value:3d} | Approx: {approx_ohms:7.1f} Ohms")
    else:
        print(f"Invalid step: {step_value} (must be 0-{pot_lcd.MAX_STEPS})")
