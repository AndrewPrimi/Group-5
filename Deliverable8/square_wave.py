import pigpio
import math
import time

pi = pigpio.pi()

GPIO = 13
FREQ = 1000         # 1 kHz
DUTY = 500000       # 50% duty cycle 

pi.set_mode(GPIO, pigpio.OUTPUT)
pi.hardware_PWM(GPIO, FREQ, DUTY)

time.sleep(10000)

pi.hardware_PWM(GPIO, 0, 0)  # stop
pi.stop()
