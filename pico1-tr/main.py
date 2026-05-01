from machine import Pin, SPI
import time

# -------- LED --------
led = Pin(25, Pin.OUT)

# -------- SPI --------
spi = SPI(0, baudrate=500000, polarity=0, phase=0,
          sck=Pin(18), mosi=Pin(19), miso=Pin(16))

cs    = Pin(17, Pin.OUT, value=1)
reset = Pin(20, Pin.OUT)
dio0  = Pin(21, Pin.IN)

# -------- REGISTERS --------
REG_FIFO           = 0x00
REG_OP_MODE        = 0x01
REG_FRF_MSB        = 0x06
REG_FRF_MID        = 0x07
REG_FRF_LSB        = 0x08
REG_FIFO_ADDR_PTR  = 0x0D
REG_FIFO_TX_BASE   = 0x0E
REG_IRQ_FLAGS      = 0x12
REG_PAYLOAD_LENGTH = 0x22
REG_VERSION        = 0x42
REG_DIO_MAPPING_1  = 0x40

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

# -------- INIT --------
reset_lora()

version = read_reg(REG_VERSION)
print("Version:", hex(version))

if version != 0x12:
    print("❌ LoRa not detected!")
    raise SystemExit

# Set LoRa mode
write_reg(REG_OP_MODE, 0x80)
time.sleep(0.01)
write_reg(REG_OP_MODE, 0x81)

set_frequency(433000000)
write_reg(REG_DIO_MAPPING_1, 0x40)  # TxDone on DIO0

print("✅ Transmitter test ready")

# -------- TEST LOOP --------
while True:
    print("\n--- TX TEST START ---")

    # Load data
    message = "TEST"
    data = message.encode()

    write_reg(REG_FIFO_ADDR_PTR, 0x00)

    for b in data:
        write_reg(REG_FIFO, b)

    write_reg(REG_PAYLOAD_LENGTH, len(data))
    write_reg(REG_IRQ_FLAGS, 0xFF)

    # Start TX
    write_reg(REG_OP_MODE, 0x83)

    led.value(1)

    # Wait TX Done
    timeout = 3000
    start = time.ticks_ms()

    while dio0.value() == 0:
        if time.ticks_diff(time.ticks_ms(), start) > timeout:
            print("❌ TX FAILED (No DIO0)")
            led.value(0)
            break

    if dio0.value() == 1:
        print("✅ TX SUCCESS (DIO0 Triggered)")
        write_reg(REG_IRQ_FLAGS, 0xFF)

    led.value(0)

    time.sleep(3)