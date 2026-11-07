import time
import board, busio
import displayio
import terminalio
import analogio
from fourwire import FourWire
from adafruit_display_text.label import Label
from adafruit_st7735r import ST7735R


# ==========================================================
#  TARATURA DERIVATA DAI TEST SU STRADA
#  v_ms = 17.50 * V - 1.00
# ==========================================================

K = 20.0     # coefficiente m/s per Volt
Q = -1.00     # offset m/s
ALPHA = 0.12  # filtro esponenziale


# --------------------------
# ADC su A0
# --------------------------
adc = analogio.AnalogIn(board.A0)

def v_in():
    return (adc.value / 65535) * adc.reference_voltage


# --------------------------
# DISPLAY (come tuo hardware)
# --------------------------
clk_pin   = board.GP2
mosi_pin  = board.GP3
reset_pin = board.GP4
cs_pin    = board.GP5
dc_pin    = board.GP16

displayio.release_displays()

spi = busio.SPI(clock=clk_pin, MOSI=mosi_pin)

display_bus = FourWire(
    spi,
    command=dc_pin,
    reset=reset_pin,
    chip_select=cs_pin
)

display = ST7735R(display_bus,
                  width=160,
                  height=128,
                  rotation=270,
                  bgr=True)

root = displayio.Group()
display.root_group = root
display.auto_refresh = True


# --------------------------
# INTERFACCIA GRAFICA
# --------------------------
ms_label = Label(terminalio.FONT, text="0.00 m/s", color=0xFFFFFF, scale=3)
ms_label.x = 2
ms_label.y = 15
root.append(ms_label)

kmh_label = Label(terminalio.FONT, text="0.0 km/h", color=0xFFFFFF, scale=3)
kmh_label.x = 2
kmh_label.y = 55
root.append(kmh_label)

v_label = Label(terminalio.FONT, text="V 0.000", color=0xFFFFFF, scale=3)
v_label.x = 2
v_label.y = 95
root.append(v_label)


# --------------------------
# LOOP PRINCIPALE
# --------------------------
v_ms_filt = 0.0

print("=== Anemometro calibrato ===")
print("Formula: v_ms = 17.50 * V - 1.00")
print("Ref ADC =", adc.reference_voltage)

while True:

    # Media su 30 campioni per ridurre jitter ADC
    acc = 0.0
    for _ in range(30):
        acc += v_in()
        time.sleep(0.001)
    v = acc / 30

    # Conversione lineare
    v_ms = K * v + Q

    # Clamp a zero (niente velocità negative)
    if v_ms < 0:
        v_ms = 0.0

    # Filtro esponenziale
    v_ms_filt = (1 - ALPHA) * v_ms_filt + ALPHA * v_ms

    v_kmh = v_ms_filt * 3.6

    # Aggiorna display
    ms_label.text  = f"{v_ms_filt:0.2f} m/s"
    kmh_label.text = f"{v_kmh:0.1f} km/h"
    v_label.text   = f"V {v:0.3f}"

    # Debug seriale
    print(f"V={v:0.3f}  m/s={v_ms_filt:0.2f}  km/h={v_kmh:0.1f}")

    time.sleep(0.2)

