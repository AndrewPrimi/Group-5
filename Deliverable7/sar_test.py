import pigpio
from sar_logic import SAR_ADC

SPI_CHANNEL = 0
SPI_BAUD = 1000000
VOLTAGE_COMPARATOR_PIN = 18
CURRENT_COMPARATOR_PIN = 23

# Connect to pigpio daemon
pi = pigpio.pi()
if not pi.connected:
    print("Cannot connect to pigpio daemon. Is sudo pigpiod running?")
    exit()

# Open SPI channel
spi_handle = pi.spi_open(SPI_CHANNEL, SPI_BAUD, 0)

# Create SAR object
sar = SAR_ADC(pi, spi_handle, comparator_pin=VOLTAGE_COMPARATOR_PIN, selected_pot=0)

try:
    # Voltage Test
    voltage, step = sar.read_voltage(3.3)
    print(f"Measured voltage: {voltage:.3f} V, step: {step}")

    # Ohmmeter Test
    #ohm, step = sar.read_ohms(5, 4700)
    #print(f"Measured ohms: {ohm:.3f} Ohms, step: {step}") 
finally:
    # Close SPI and stop pigpio
    pi.spi_close(spi_handle)
    pi.stop()
