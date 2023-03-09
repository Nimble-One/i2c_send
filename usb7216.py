from smbus2 import SMBus, i2c_msg
import RPi.GPIO as GPIO
from enum import Enum
import time

RPI_GPIO_FLEX = 17
I2C_SLAVE_ADDR = 0x2d
BUS_ADDR = 1
USB7216_BASE_ADDR = 0xbf80_0000


# -----------------------------------------------------------------------------
def read_config_register(bus: SMBus, offset: int, count: int) -> list[int]:
    
    count += 1
    
    # ---
    # write the command block to the buffer area
    payload = [0x00, 0x00, # memory addr (???)
               0x06, # number of bytes to write to memory
               0x01, # read configuration register 
               count] # reading two bytes from register

    offset += USB7216_BASE_ADDR
    offset_bytes = [(offset >> 24) & 0xff, 
                    (offset >> 16) & 0xff, 
                    (offset >> 8) & 0xff, 
                    (offset & 0xff)]
    
    w = i2c_msg.write(I2C_SLAVE_ADDR, 
                      payload + offset_bytes)
    bus.i2c_rdwr(w)

    # ---
    # execute the 'Configuration Register Access' command
    config_register_access(bus)

    # ---
    # read the data from memory, starting at memory offset 06h, which is where the data byte starts
    w = i2c_msg.write(I2C_SLAVE_ADDR, 
                      [0x00, 0x06]) # for read access at offset 0006h      
    bus.i2c_rdwr(w)

    # ---
    # now do the reading
    r = i2c_msg.read(I2C_SLAVE_ADDR, count) # client addr and read bit
    bus.i2c_rdwr(r)

    # --- reverse output and discard last byte
    bytes = bytearray()
    for dat in r:
        bytes.append(dat)

    # ---
    # debug
    debug_bytearray(f"I²C: read {count} bytes from addr {hex(offset)}:", bytes)

    return bytes[::-1][:-1]
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def write_config_register(bus: SMBus, offset: int, bytes: bytearray, base_addr: int = USB7216_BASE_ADDR):
    
    count = len(bytes)

    # ---
    # write the command block to the buffer area
    payload = [0x00, 0x00, # memory addr (???)
               0x06 + count, # number of bytes to write to memory
               0x00, # write configuration register 
               count] # write count bytes to register

    offset += base_addr
    offset_bytes = [(offset >> 24) & 0xff, 
                    (offset >> 16) & 0xff, 
                    (offset >> 8) & 0xff, 
                    (offset & 0xff)]

    payload += offset_bytes + bytes
    w = i2c_msg.write(I2C_SLAVE_ADDR, 
                      payload)
    bus.i2c_rdwr(w)

    # ---
    # debug
    debug_bytearray(f"I²C: wrote {count + 4} bytes to addr {hex(offset)}:", payload)

    # ---
    # execute the 'Configuration Register Access' command
    config_register_access(bus)
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def config_register_access(bus):
    payload = [0x99, 0x37, 0x00] # command 9937h + 00h (command completion)
    w = i2c_msg.write(I2C_SLAVE_ADDR,
                      payload) 
    bus.i2c_rdwr(w)
    debug_bytearray(f"I²C: wrote 3 bytes:", payload)
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def usb_attach(bus: SMBus, during_runtime: bool = True):
    payload = [0xaa, 0x55 + (1 if during_runtime else 0), 0x00]
    w = i2c_msg.write(I2C_SLAVE_ADDR,
                      payload)
    bus.i2c_rdwr(w)
    debug_bytearray(f"I²C: wrote 3 bytes:", payload)
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def usb_set_vbus_pass_thru_pio(bus: SMBus):
    # see AN4550 section 3.3
    
    # config VBUS_PASS_THRU (to be done AFTER hub is attached)
    USB3_PASS_THRU = 0x00   # 0x00: The VBUS to USB3 Hub comes from Internal PIO24
    USB2_PASS_THRU = 0x00   # 0x00: The VBUS to USB2 Hub comes from Internal PIO32
    write_config_register(bus, 0x3c40, [(USB3_PASS_THRU << 2) | USB2_PASS_THRU])

    # configure 0xBF80_0903 and 0xBF80_0904 to set PIO24 / PIO32 as OUTPUT
    write_config_register(bus, 0x0903, [0x01, 0x01])
    
    # configure 0xBF80_0923 and 0xBF80_0924 to set PIO24 / PIO32 as HIGH
    write_config_register(bus, 0x0923, [0x01, 0x01])
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def usb_flex(bus: SMBus, port: int, usb2_enable: bool = True, usb3_enable: bool = True):
    # AN2935 page 15
    if port > 0 and port < 7:
        # flex usb2
        if usb2_enable:
            write_config_register(bus, 0x0808, [port])

        # flex usb3
        if usb3_enable:
            write_config_register(bus, 0x0828, [port])
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def debug_bytearray(msg: str, bytes: bytearray):
    print(msg)
    for b in bytes:
        print(hex(b) + " ", end="")
    print("")
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# TODO: use enums

class FlexPort(Enum):
    PORT2 = 0x3443
    PORT3 = 0x3444
    PORT4 = 0x3445


class FlexPin(Enum):
    PF6_GPIO70 =  (0x0c09, 0b000)
    PF7_GPIO71 =  (0x0c0a, 0b001)
    PF14_GPIO78 = (0x0c11, 0b010) 
    PF19_GPIO83 = (0x0c16, 0b011)
    PF26_GPIO90 = (0x0c1d, 0b100)
    PF27_GPIO91 = (0x0c1e, 0b101)
    PF28_GPIO92 = (0x0c1f, 0b110)
    PF29_GPIO93 = (0x0c20, 0b111)


def config_flex_connect_pin_control(bus: SMBus, 
                                    logical_port: FlexPort, 
                                    gpio_pin: FlexPin,
                                    flex_usb2: bool = True, 
                                    flex_usb3: bool = True):

    # AN4550 page 21 example 3
    gpio_offset = gpio_pin.value[0]
    port_offset = logical_port.value
    flex_value = gpio_pin.value[1]
    flex_value |= ((1 if flex_usb2 else 0) << 7)
    flex_value |= ((1 if flex_usb3 else 0) << 3)
    
    # config gpio
    write_config_register(bus, gpio_offset, [0x00]) # zero means "use as gpio"

    # tell we can flex the port w/ this gpio
    write_config_register(bus, port_offset, [flex_value], 0xbfd2_0000)
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
with SMBus(BUS_ADDR) as bus:
    
    # follow the steps in AN4550 / page 21 / example 3,
    # except that I'll be flexing PORT2
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RPI_GPIO_FLEX, GPIO.OUT)
    GPIO.output(RPI_GPIO_FLEX, 0)

    config_flex_connect_pin_control(bus, FlexPort.PORT2, FlexPin.PF29_GPIO93)
    usb_set_vbus_pass_thru_pio(bus)

    # *** now pull PF7 HIGH ***
    GPIO.output(RPI_GPIO_FLEX, 1)
    
    usb_attach(bus)

