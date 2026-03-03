import pigpio

lcd = i2c_open(1,0-0x7F,0)

pi = pigpio.pi()

pi.i2c_write_device(handle, data)



