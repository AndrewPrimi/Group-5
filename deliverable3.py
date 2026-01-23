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

# Glitch filter acts as a hardware-level debounce (3000 microseconds)
pi.set_glitch_filter(ROTARY_PIN, 3000)

led_state = False

def toggle_callback(gpio, level, tick):
    global led_state
    # level 0 means the button was pressed (pulled to ground)
    if level == 0:
        led_state = not led_state
        pi.write(LED_PIN, led_state)
        print(f"LED is now {'ON' if led_state else 'OFF'}")

# Set up the interrupt/callback
cb = pi.callback(ROTARY_PIN, pigpio.FALLING_EDGE, toggle_callback)

try:
    print("System Ready. Press the encoder button to toggle...")
    while True:
        time.sleep(1) # Keep the main thread alive
except KeyboardInterrupt:
    print("\nCleaning up...")
    pi.write(LED_PIN, 0)
    cb.cancel()
    pi.stop()