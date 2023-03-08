from smbus2 import SMBus, i2c_msg
import RPi.GPIO as GPIO

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
FLEX_PORT_OFFSETS = {
    "PORT2": 0x3443,
    "PORT3": 0x3444,
    "PORT4": 0x3445,   
}

FLEX_PIN_CONTROL_GPIO_VALUES = {
    # gpio name: (mem offset, payload_value)
    # we flex usb2 + usb3, always
    "PF6/GPIO70":  (0x0c09, 0b000),
    "PF7/GPIO71":  (0x0c0a, 0b001),
    "PF14/GPIO78": (0x0c11, 0b010), 
    "PF19/GPIO83": (0x0c16, 0b011),
    "PF26/GPIO90": (0x0c1d, 0b100),
    "PF27/GPIO91": (0x0c1e, 0b101),
    "PF28/GPIO92": (0x0c1f, 0b110),
    "PF29/GPIO93": (0x0c20, 0b111)
}

def config_flex_connect_pin_control(bus: SMBus, 
                                    logical_port: str, 
                                    gpio_pin: str,
                                    flex_usb2: bool = True, 
                                    flex_usb3: bool = True):

    # AN4550 page 21 example 3
    if logical_port in FLEX_PORT_OFFSETS and gpio_pin in FLEX_PIN_CONTROL_GPIO_VALUES:
        
        gpio_offset = FLEX_PIN_CONTROL_GPIO_VALUES[gpio_pin][0]
        port_offset = FLEX_PORT_OFFSETS[logical_port]
        flex_value = FLEX_PIN_CONTROL_GPIO_VALUES[gpio_pin][1]
        flex_value |= ((1 if flex_usb2 else 0) << 7)
        flex_value |= ((1 if flex_usb3 else 0) << 3)
        
        # config gpio
        write_config_register(bus, gpio_offset, [0x00]) # zero means "use as gpio"

        # tell we can flex the port w/ this gpio
        write_config_register(bus, port_offset, [flex_value], 0xbfd2_0000)
    else:
        print("ERR: config_flex_connect_pin_control got invalid values.")

# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
with SMBus(BUS_ADDR) as bus:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(RPI_GPIO_FLEX, GPIO.OUT)
    GPIO.output(RPI_GPIO_FLEX, 0)

    # enable port 2 flexing via pin PF7
    config_flex_connect_pin_control(bus, "PORT4", "PF29/GPIO93", flex_usb2=True, flex_usb3=False)
    usb_set_vbus_pass_thru_pio(bus)

    # *** now pull PF7 HIGH ***
    GPIO.output(RPI_GPIO_FLEX, 1)

    usb_attach(bus)


    # # # from AN4550 / page 10 / example 1:

    # # # flex port 3
    # # # write_config_register(bus, 0x0808, [0x3])
    # # # write_config_register(bus, 0x0828, [0x3])
    # # # usb_attach(bus)
    # # # usb_set_vbus_pass_thru_pio(bus)

    # # # flex port 1
    # write_config_register(bus, 0x0808, [0x1])
    # write_config_register(bus, 0x0828, [0x1])
    # usb_set_vbus_pass_thru_pio(bus)
    # usb_attach(bus)
    

    # # # attach hub and keep i2c alive
    # # usb_attach(bus)  

    # # # config VBUS_PASS_THRU register to use PIO24/32, 
    # # # that avoids sending 2.7v on the VBUS_DET pin (on the EVB),
    # # # or routing some wires and a voltage divider on the final board.
    # # usb_set_vbus_pass_thru_pio(bus)

    # # # should be: bytearray(b'\x05\xa2\x00\xc1')
    # # # device_revision_register = read_config_register(bus, 0x0000, 4)
    # # # debug_bytearray("device_revision_register: ", device_revision_register)

    # # # usb2_sys_config_reg = read_config_register(bus, 0x0808, 4)
    # # # debug_bytearray("usb2_sys_config_reg: ", usb2_sys_config_reg)

    # # # vendor_id_reg = read_config_register(bus, 0x3000, 2)
    # # # debug_bytearray("vendor_id_reg: ", vendor_id_reg)

    # # # # will not persist a reset !!!
    # # # write_config_register(bus, 0x3000, [0xad, 0xde])

    # # # vendor_id_reg = read_config_register(bus, 0x3000, 2)
    # # # debug_bytearray("vendor_id_reg: ", vendor_id_reg)

    # # # The follwing code doesnt work, these commands are for the Hub Feature Controller only
    # # # (accessed thru USB directly)
    # # #
    # # # flexconnect port1 usb2+3
    # # # word = 0
    # # # word |= ((1 << 12) # port 1
    # # #     | (1 << 11) # usb3 enable
    # # #     | (0 << 8) # no timeout
    # # #     | (0 << 7) # usb3 attach and reattach
    # # #     | (0 << 6) # usb2 attach and reattach
    # # #     | (1 << 5) # enable flexconnect
    # # #     | (1 << 4) # usb2 enable
    # # #     | 1) # port 1
    # # # write_config_register(bus, 0x3440, [word >> 8, word & 0xff])


    # # usb_flex(bus, 1)
    # # usb_set_vbus_pass_thru_pio(bus)
    # # usb_attach(bus)
    # # write_config_register(bus, 0x5400, [0x01])

    # # # port2
    # # usb_flex(bus, 1)
    # # write_config_register(bus, 0x5800, [0x01])
