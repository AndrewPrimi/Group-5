import pigpio
import time

# =========================
# CONFIG
# =========================
COMP_GPIO = 5          # LM339 output
DAC_GPIO  = 18         # PWM pin for reference voltage

VREF      = 3.3
ADC_BITS  = 7
ADC_LEVELS = 2 ** ADC_BITS   # 128 levels

PWM_FREQ  = 100_000   # high freq for smoother analog
SETTLE_US = 50        # allow RC filter to settle

# =========================
# CLASS
# =========================
class SineWaveMeasurer:
    def __init__(self, pi, debug=False):
        self.pi = pi
        self.debug = debug

        pi.set_mode(COMP_GPIO, pigpio.INPUT)
        pi.set_pull_up_down(COMP_GPIO, pigpio.PUD_OFF)

        pi.set_mode(DAC_GPIO, pigpio.OUTPUT)
        pi.set_PWM_frequency(DAC_GPIO, PWM_FREQ)
        pi.set_PWM_range(DAC_GPIO, 255)

    def _set_reference_voltage(self, value):
        """
        Set DAC reference using PWM duty cycle
        value: 0–127 (7-bit)
        """
        duty = int((value / (ADC_LEVELS - 1)) * 255)
        self.pi.set_PWM_dutycycle(DAC_GPIO, duty)

    def read_sample(self):
        """
        Perform one ADC conversion using ramp method.
        Returns: digital value (0–127)
        """
        for level in range(ADC_LEVELS):
            self._set_reference_voltage(level)
            time.sleep(SETTLE_US / 1_000_000)

            comp = self.pi.read(COMP_GPIO)

            # Comparator flips when Vref exceeds Vin
            if comp == 0:
                if self.debug:
                    print(f"[ADC] threshold at level {level}")
                return level

        return ADC_LEVELS - 1

    def read_voltage(self):
        """
        Returns measured voltage
        """
        value = self.read_sample()
        voltage = (value / (ADC_LEVELS - 1)) * VREF

        if self.debug:
            print(f"[ADC] value={value} voltage={voltage:.3f}V")

        return voltage

    def measure_wave(self, samples=100):
        """
        Capture multiple samples of sine wave
        """
        data = []
        for _ in range(samples):
            v = self.read_voltage()
            data.append(v)
        return data


# =========================
# MAIN TEST
# =========================
if __name__ == "__main__":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("Run 'sudo pigpiod' first.")

    adc = SineWaveMeasurer(pi, debug=True)

    print("Measuring sine wave...")
    data = adc.measure_wave(50)

    print("Samples:")
    for v in data:
        print(f"{v:.3f} V")

    pi.stop()
