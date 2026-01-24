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

button_state = 0

def clean_callback(gpio, level, tick):
    global button_state

    if level == 1:
        print("Button Pressed!")
        button_state = 1
        pi.write(LED_PIN, 1)
    elif level == 0:
        print("Button Released!")
        button_state = 0
        pi.write(LED_PIN, 0)

# Listen for both rising and falling edges
cb = pi.callback(ROTARY_PIN, pigpio.EITHER_EDGE, clean_callback)

try:
    print("System Ready. Press the encoder button...")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nCleaning up...")
    pi.write(LED_PIN, 0)
    cb.cancel()
    pi.stop()
