import pigpio
import time

LED_PIN = 18
ROTARY_PIN = 17

pi = pigpio.pi()

# Check if connection was successful
if not pi.connected:
    exit()

pi.set_mode(ROTARY_PIN, pigpio.INPUT)
pi.set_mode(LED_PIN, pigpio.OUTPUT)

#NEED TO SET PULL DOWN RESISTOR
pi.set_pull_up_down(ROTARY_PIN, pigpio.PUD_DOWN)

button_state = 0

def light_on():
    global button_state  # This allows the function to update the variable outside
    
    current_read = pi.read(ROTARY_PIN)
    
    if current_read == 1 and button_state == 0:
        print("Button Pressed!")
        button_state = 1
        pi.write(LED_PIN, 1) # Turn LED ON
    elif current_read == 0 and button_state == 1:
        print("Button Released!")
        button_state = 0
        pi.write(LED_PIN, 0) # Turn LED OFF
    
def loop():
    print("Starting loop... Press Ctrl+C to stop.")
    try:
        while True:
            light_on()
            time.sleep(0.01) # Small delay to save CPU and help debounce
    except KeyboardInterrupt:
        pi.stop()

loop()
