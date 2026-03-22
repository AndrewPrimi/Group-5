import pigpio
import time

PIN = 24  # testing GPIO 24 (physical pin 18)

pi = pigpio.pi()
if not pi.connected:
    print("Run: sudo pigpiod")
    exit()

# Set as input, no internal pull-up/down
pi.set_mode(PIN, pigpio.INPUT)
pi.set_pull_up_down(PIN, pigpio.PUD_OFF)

print("Testing GPIO 24...")
print("Touch pin to 3.3V or GND and watch output\n")

try:
    while True:
        value = pi.read(PIN)
        print(f"GPIO 24 = {value}")
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nDone")

finally:
    pi.stop()
