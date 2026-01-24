import pigpio
import time

LED_PIN = 18
ROTARY_PIN = 17

pi = pigpio.pi()
if not pi.connected:
    exit()

pi.set_mode(LED_PIN, pigpio.OUTPUT)
pi.set_mode(ROTARY_PIN, pigpio.INPUT)
# Most encoders pull to GND when pressed, so we use PUD_UP
pi.set_pull_up_down(ROTARY_PIN, pigpio.PUD_UP)

# Hardware-level debouncing using pigpio's glitch filter
# Ignores pulses shorter than 50000 microseconds (50ms)
# This filters out electrical noise/bounce at the hardware level
pi.set_glitch_filter(ROTARY_PIN, 50000)

led_on = False

def toggle_callback(gpio, level, tick):
    global led_on

    # Button press is falling edge (0) because of pull-up resistor
    if level == 0:
        led_on = not led_on
        pi.write(LED_PIN, 1 if led_on else 0)
        print(f"LED {'ON' if led_on else 'OFF'}")

# Listen for falling edge only (button press)
cb = pi.callback(ROTARY_PIN, pigpio.FALLING_EDGE, toggle_callback)

try:
    print("System Ready. Press the encoder button...")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nCleaning up...")
    pi.write(LED_PIN, 0)
    cb.cancel()
    pi.stop()
