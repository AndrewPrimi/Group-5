"""
sqaure_wave.py  –  Square-wave generator module
================================================
Uses:
  • pigpio   – precise 50 % duty-cycle waveform on GPIO_PIN
  • spidev   – MCP4921 12-bit SPI DAC for amplitude control (SPI0 CE0)

Hardware requirements for ±10 V output
---------------------------------------
  GPIO_PIN (default 4) carries a 0 / 3.3 V digital square wave.
  An external bipolar op-amp circuit (requiring a ±12 V or ±15 V supply)
  converts that logic signal into a ±VAMP analogue output, where VAMP is
  set by the MCP4921 DAC:

      MCP4921 VREF = 5 V, GA pin pulled LOW  →  2× gain
      VDAC = 10 V × (dac_value / 4095)       →  range 0–10 V

  Op-amp mapping:
      GPIO HIGH (3.3 V)  →  +VDAC
      GPIO LOW  (0 V)    →  −VDAC

SPI wiring (Raspberry Pi hardware SPI 0):
      MOSI  GPIO 10  (pin 19)
      MISO  GPIO  9  (pin 21)  – not used by DAC
      SCLK  GPIO 11  (pin 23)
      CE0   GPIO  8  (pin 24)  → MCP4921 /CS
"""

import pigpio
import spidev

# ── Hardware constants ────────────────────────────────────────────────────────
GPIO_PIN   = 12        # BCM pin for digital square-wave output
SPI_BUS    = 0
SPI_DEVICE = 0

# ── Signal limits ─────────────────────────────────────────────────────────────
MIN_FREQ  = 100         # Hz
MAX_FREQ  = 10_000      # Hz
FREQ_STEP = 10          # Hz  (frequency resolution)
MAX_AMP   = 10.0        # V   (peak amplitude, output swings ±MAX_AMP)

# ── DAC constants (MCP4921) ───────────────────────────────────────────────────
_DAC_BITS = 12
_DAC_MAX  = (1 << _DAC_BITS) - 1   # 4095


class SquareWaveGenerator:
    """
    Controls a bipolar square wave generator.

    Frequency range : 100 Hz – 10 kHz  (10 Hz resolution)
    Amplitude range : 0 – 10 V peak    (output swings ±amplitude)
    Duty cycle      : 50 % fixed
    """

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def __init__(self):
        self._pi = pigpio.pi()
        if not self._pi.connected:
            raise RuntimeError(
                "Cannot connect to pigpio daemon.\n"
                "Start it with:  sudo pigpiod"
            )

        self._pi.set_mode(GPIO_PIN, pigpio.OUTPUT)
        self._pi.write(GPIO_PIN, 0)

        self._spi = spidev.SpiDev()
        self._spi.open(SPI_BUS, SPI_DEVICE)
        self._spi.max_speed_hz = 1_000_000
        self._spi.mode = 0b00          # CPOL=0, CPHA=0

        self._wid       = None
        self._frequency = 1000         # Hz  (default)
        self._amplitude = 0.0          # V
        self._running   = False

        self._write_dac(0)             # ensure DAC starts at 0 V

    def cleanup(self):
        """Stop output and release all hardware resources."""
        self.stop()
        try:
            self._spi.close()
        except Exception:
            pass
        try:
            self._pi.stop()
        except Exception:
            pass

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def frequency(self):
        return self._frequency

    @property
    def amplitude(self):
        return self._amplitude

    @property
    def running(self):
        return self._running

    # ── Public control ────────────────────────────────────────────────────────
    def set_frequency(self, freq_hz):
        """
        Set output frequency.

        freq_hz is clamped to [MIN_FREQ, MAX_FREQ] and rounded to the
        nearest FREQ_STEP (10 Hz).  If the output is running the waveform
        is rebuilt immediately with the new frequency.
        """
        freq_hz = int(round(freq_hz / FREQ_STEP) * FREQ_STEP)
        freq_hz = max(MIN_FREQ, min(MAX_FREQ, freq_hz))
        self._frequency = freq_hz
        if self._running:
            self._rebuild_wave()

    def set_amplitude(self, volts):
        """
        Set peak amplitude (0.0 – 10.0 V).

        The output will swing from −volts to +volts via the external
        op-amp circuit.  The DAC is updated immediately.
        """
        volts = max(0.0, min(MAX_AMP, float(volts)))
        self._amplitude = volts
        dac_val = int((volts / MAX_AMP) * _DAC_MAX)
        self._write_dac(dac_val)

    def start(self):
        """Enable waveform output."""
        if not self._running:
            self._running = True
            self._rebuild_wave()

    def stop(self):
        """Disable waveform output and zero the DAC."""
        self._running = False
        self._teardown_wave()
        self._pi.write(GPIO_PIN, 0)
        self._write_dac(0)

    # ── Private helpers ───────────────────────────────────────────────────────
    def _rebuild_wave(self):
        """(Re)create and send the pigpio waveform for the current frequency."""
        self._teardown_wave()
        half_us = max(1, int(500_000 // self._frequency))   # half-period in µs
        pulses = [
            pigpio.pulse(1 << GPIO_PIN, 0,            half_us),  # HIGH
            pigpio.pulse(0,            1 << GPIO_PIN, half_us),  # LOW
        ]
        self._pi.wave_add_generic(pulses)
        self._wid = self._pi.wave_create()
        if self._wid >= 0:
            self._pi.wave_send_repeat(self._wid)

    def _teardown_wave(self):
        """Stop transmission and free the current wave (if any)."""
        self._pi.wave_tx_stop()
        if self._wid is not None and self._wid >= 0:
            try:
                self._pi.wave_delete(self._wid)
            except Exception:
                pass
            self._wid = None

    def _write_dac(self, value):
        """
        Send a 12-bit value to the MCP4921 DAC via SPI.

        MCP4921 16-bit command word (MSB first):
          Bits [15:12]  Configuration:
              Bit 15  = 0  (write command)
              Bit 14  = 0  (channel A  / don't-care on single-channel part)
              Bit 13  = 0  (BUF = 0, unbuffered VREF)
              Bit 12  = 0  (~GA = 0 → 2× gain;  VOUT = 2·VREF·D/4096)
          Bits [11:0]   D11..D0  (12-bit data)

        With VREF = 5 V and 2× gain:  VOUT = 10 V × value / 4095.
        """
        value = max(0, min(_DAC_MAX, value))
        high_byte = (value >> 8) & 0x0F    # D11..D8  (upper config nibble = 0000)
        low_byte  =  value       & 0xFF    # D7..D0
        self._spi.xfer2([high_byte, low_byte])
