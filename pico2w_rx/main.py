print("📡 AUTO START RECEIVER")

from machine import Pin, SPI
import time

# -------- LED --------
led = Pin(25, Pin.OUT)

# -------- SPI --------
spi = SPI(0, baudrate=500000, polarity=0, phase=0,
          sck=Pin(18), mosi=Pin(19), miso=Pin(16))

cs    = Pin(17, Pin.OUT, value=1)
reset = Pin(20, Pin.OUT)

# -------- REGISTERS --------
REG_FIFO            = 0x00
REG_OP_MODE         = 0x01
REG_FRF_MSB         = 0x06
REG_FRF_MID         = 0x07
REG_FRF_LSB         = 0x08
REG_FIFO_ADDR_PTR   = 0x0D
REG_FIFO_RX_BASE    = 0x0F
REG_FIFO_RX_CURRENT = 0x10
REG_IRQ_FLAGS       = 0x12
REG_RX_NB_BYTES     = 0x13
REG_MODEM_CONFIG_1  = 0x1D
REG_MODEM_CONFIG_2  = 0x1E
REG_MODEM_CONFIG_3  = 0x26
REG_PKT_SNR_VALUE   = 0x19
REG_PKT_RSSI_VALUE  = 0x1A
REG_VERSION         = 0x42

# -------- FUNCTIONS --------
def write_reg(addr, val):
    cs.value(0)
    spi.write(bytearray([addr | 0x80, val]))
    cs.value(1)

def read_reg(addr):
    cs.value(0)
    spi.write(bytearray([addr & 0x7F]))
    val = spi.read(1)[0]
    cs.value(1)
    return val

def reset_lora():
    reset.value(0)
    time.sleep(0.1)
    reset.value(1)
    time.sleep(0.1)

def set_frequency(freq):
    frf = int((freq / 32000000.0) * 524288)
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8)  & 0xFF)
    write_reg(REG_FRF_LSB,  frf        & 0xFF)

# ==============================
# PARSER FUNCTION
# ==============================
def parse_packet(message):
    """
    Parses: T:31.9,H:40.6,AQ:8177,AX:1.02,AY:0.03,AZ:0.07,GX:-2.6,GY:2.5,GZ:0.1
    Returns a dict with all values
    """
    data = {}
    try:
        parts = message.strip().split(",")
        for part in parts:
            key, val = part.split(":")
            data[key.strip()] = val.strip()
    except Exception as e:
        print("⚠️ Parse error:", e)
    return data

# ==============================
# PRETTY PRINT FUNCTION
# ==============================
def pretty_print(data, rssi, snr, packet_count):
    print("\n" + "="*45)
    print("  📦 PACKET #{}".format(packet_count))
    print("="*45)

    # --- Environment ---
    print("  🌡️  ENVIRONMENT")
    t = data.get("T", "ERR")
    h = data.get("H", "ERR")
    aq = data.get("AQ", "ERR")

    if t != "ERR":
        print("      Temperature : {} °C".format(t))
    else:
        print("      Temperature : ❌ Sensor Error")

    if h != "ERR":
        print("      Humidity    : {} %".format(h))
    else:
        print("      Humidity    : ❌ Sensor Error")

    # MQ-135 air quality interpretation
    if aq != "ERR":
        aq_val = int(aq)
        if aq_val < 10000:
            aq_label = "🟢 Clean"
        elif aq_val < 30000:
            aq_label = "🟡 Moderate"
        else:
            aq_label = "🔴 Poor"
        print("      Air Quality : {} ({})".format(aq_val, aq_label))

    # --- Motion ---
    print("  📐 ACCELEROMETER (g)")
    print("      X : {}".format(data.get("AX", "ERR")))
    print("      Y : {}".format(data.get("AY", "ERR")))
    print("      Z : {}".format(data.get("AZ", "ERR")))

    print("  🔄 GYROSCOPE (°/s)")
    print("      X : {}".format(data.get("GX", "ERR")))
    print("      Y : {}".format(data.get("GY", "ERR")))
    print("      Z : {}".format(data.get("GZ", "ERR")))

    # --- LoRa Signal Quality ---
    print("  📶 SIGNAL")
    print("      RSSI : {} dBm".format(rssi))
    print("      SNR  : {} dB".format(snr))
    print("="*45 + "\n")

# ==============================
# INIT
# ==============================
reset_lora()

version = read_reg(REG_VERSION)
print("Version:", hex(version))

if version != 0x12:
    print("❌ LoRa not detected!")
    raise SystemExit

write_reg(REG_OP_MODE, 0x80)
time.sleep(0.01)
write_reg(REG_OP_MODE, 0x81)

set_frequency(433000000)

write_reg(REG_MODEM_CONFIG_1, 0x72)
write_reg(REG_MODEM_CONFIG_2, 0x74)
write_reg(REG_MODEM_CONFIG_3, 0x04)

write_reg(REG_FIFO_RX_BASE, 0x00)
write_reg(REG_FIFO_ADDR_PTR, 0x00)

write_reg(REG_IRQ_FLAGS, 0xFF)
write_reg(REG_OP_MODE, 0x85)  # RX continuous

print("✅ Receiver Ready - Waiting...\n")

# ==============================
# MAIN LOOP
# ==============================
packet_count = 0

while True:
    irq = read_reg(REG_IRQ_FLAGS)

    if (irq & 0x40):  # RxDone
        led.value(1)
        write_reg(REG_IRQ_FLAGS, 0xFF)

        # --- Read RSSI and SNR ---
        rssi = read_reg(REG_PKT_RSSI_VALUE) - 164
        raw_snr = read_reg(REG_PKT_SNR_VALUE)
        snr = raw_snr / 4.0
        if raw_snr > 127:
            snr = (raw_snr - 256) / 4.0

        # --- Read payload ---
        length = read_reg(REG_RX_NB_BYTES)
        addr   = read_reg(REG_FIFO_RX_CURRENT)
        write_reg(REG_FIFO_ADDR_PTR, addr)

        raw = bytearray()
        for _ in range(length):
            raw.append(read_reg(REG_FIFO))

        message = raw.decode("utf-8", "ignore")

        # --- Parse and display ---
        packet_count += 1
        data = parse_packet(message)
        pretty_print(data, rssi, snr, packet_count)

        led.value(0)

    time.sleep(0.2)