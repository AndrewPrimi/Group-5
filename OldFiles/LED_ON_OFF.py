import pigpio
import time

LED_PIN = 18 # This is the pin on the Raspbery Pi that connects to the LED 
ROTARY_PIN = 17 # This is the pin on the Raspberry Pi that takes the input signal from rotary encoder SW pin
 
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
    #When system boots up this print statement is used to notify the user the program started running correctly
    print("System Ready. Press the encoder button...")
    while True:
        time.sleep(1) # this serves as an idle loop to keep the program running. without the sleep the loop would run millions of times per second using %100 of the CPU
except KeyboardInterrupt: # when Ctrl+C is signal is caught instead of crashing
    print("\nShutdown in progress...")
    pi.write(LED_PIN, 0) #turns off led
    cb.cancel() # unregisters callback so that it stops listening
    pi.stop() #disconnects from pigpio daemon
