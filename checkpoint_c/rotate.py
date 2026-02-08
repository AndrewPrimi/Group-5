class Rotate:

    # Pin A connected to CLK, Pin B connected to DT
    PIN_A = 22
    PIN_B = 27

    last_tick = None

    pi.set_mode(PIN_A, pigpio.INPUT)
    pi.set_mode(PIN_B, pigpio.INPUT)
    pi.set_pull_up_down(PIN_A, pigpio.PUD_UP)
    pi.set_pull_up_down(PIN_B, pigpio.PUD_UP)

    def encoder_callback(gpio, level, tick):
        global last_tick, ohms

        if last_tick is not None:
            dt = pigpio.tickDiff(last_tick, tick)

            # Debounce
            if dt < 2000:
                last_tick = tick
                return

            speed = min(1_000_000 / dt, 1000)
            # Set dt to 1000 to clamp the speed
            speed = min(1_000_000 / dt, 1000)  # pulses per second
            print(f"speed: {speed}")

            if pi.read(PIN_B) == 0:
                direction = 1
                print("CW")
            else:
                direction = -1
                print("CCW")

            if speed <= SPEED_LIMIT:
                change_steps(direction, speed)

        last_tick = tick

    def change_steps(direction, speed):
        global ohms

        if speed < 10:
            change = 10
        else:
            change = 100

        resulting_ohms = ohms + change * direction
        if resulting_ohms >= MINIMUM_OHMS and resulting_ohms <= MAXIMUM_OHMS:
            ohms = ohms + change * direction
            print(f"Current Ohms: {ohms}")
            set_lcd()
        else:
            print("ohm value is out of range...")
