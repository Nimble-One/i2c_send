from smbus2 import SMBus, i2c_msg
from enum import Enum

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
def write_config_register(bus: SMBus, offset: int, bytes: bytearray):
    
    count = len(bytes)

    # ---
    # write the command block to the buffer area
    payload = [0x00, 0x00, # memory addr (???)
               0x06 + count, # number of bytes to write to memory
               0x00, # write configuration register 
               count] # write count bytes to register

    offset += USB7216_BASE_ADDR
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
    w = i2c_msg.write(I2C_SLAVE_ADDR,
                      [0x99, 0x37, 0x00]) # command 9937h + 00h (command completion)
    bus.i2c_rdwr(w)
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def usb_attach(bus: SMBus, during_runtime: bool = True):
    w = i2c_msg.write(I2C_SLAVE_ADDR,
                      [0xaa, 0x55 + (1 if during_runtime else 0), 0x00])
    bus.i2c_rdwr(w)
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
class FlexPort(Enum):
    # PORT = (phy usb2, phy usb3)
    PORT0 = 0, 0,
    PORT1 = 1, 1,
    PORT2 = 3, 3,
    PORT3 = 4, 4,
    PORT4 = 5, 5,

def usb_flex(bus: SMBus, port: FlexPort, usb2_enable: bool = True, usb3_enable: bool = True):
    # AN2935 page 15
    # flex usb2
    if usb2_enable:
        write_config_register(bus, 0x0808, [port.value[0]])

    # flex usb3
    if usb3_enable:
        write_config_register(bus, 0x0828, [port.value[1]])

    # config port 1 cc ?
    if port == FlexPort.PORT1:
        write_config_register(bus, 0x5400, [0x01])
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
def debug_bytearray(msg: str, bytes: bytearray):
    print(msg)
    for b in bytes:
        print(hex(b) + " ", end="")
    print("")
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
with SMBus(BUS_ADDR) as bus:

    # attach hub and keep i2c alive
    usb_attach(bus)  

    # config VBUS_PASS_THRU register to use PIO24/32, 
    # that avoids sending 2.7v on the VBUS_DET pin (on the EVB),
    # or routing some wires and a voltage divider on the final board.
    usb_set_vbus_pass_thru_pio(bus)

    # should be: bytearray(b'\x05\xa2\x00\xc1')
    device_revision_register = read_config_register(bus, 0x0000, 4)
    debug_bytearray("device_revision_register: ", device_revision_register)
    
    usb_flex(bus, FlexPort.PORT4)
