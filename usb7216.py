from smbus2 import SMBus, i2c_msg


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
with SMBus(BUS_ADDR) as bus:

    # attach hub and keep i2c alive
    usb_attach(bus)

    # should be: bytearray(b'\x05\xa2\x00\xc1')
    device_revision_register = read_config_register(bus, 0x0000, 4)
    debug_bytearray("device_revision_register: ", device_revision_register)

    usb2_sys_config_reg = read_config_register(bus, 0x0808, 4)
    debug_bytearray("usb2_sys_config_reg: ", usb2_sys_config_reg)

    vendor_id_reg = read_config_register(bus, 0x3000, 2)
    debug_bytearray("vendor_id_reg: ", vendor_id_reg)

    # will not persist a reset !!!
    write_config_register(bus, 0x3000, [0xad, 0xde])

    vendor_id_reg = read_config_register(bus, 0x3000, 2)
    debug_bytearray("vendor_id_reg: ", vendor_id_reg)

    # TODO: doesnt work, ask MJ why
    # flexconnect port1 usb2+3
    # word = 0
    # word |= ((1 << 12) # port 1
    #     | (1 << 11) # usb3 enable
    #     | (0 << 8) # no timeout
    #     | (0 << 7) # usb3 attach and reattach
    #     | (0 << 6) # usb2 attach and reattach
    #     | (1 << 5) # enable flexconnect
    #     | (1 << 4) # usb2 enable
    #     | 1) # port 1
    # write_config_register(bus, 0x3440, [word >> 8, word & 0xff])

    # TODO: doesnt work with port != 1, ask MJ why
    usb_flex(bus, 1)

    # TODO: what is this, ask MJ
    write_config_register(bus, 0x5400, [0x01])