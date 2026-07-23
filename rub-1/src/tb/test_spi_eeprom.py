"""
SPI EEPROM (AT25010B) Testbench

Tests the UART-SPI interface with a simulated AT25010B 1K SPI EEPROM.
The AT25010B supports standard SPI EEPROM commands with Write Enable Latch,
status register, and 8-byte page write boundaries.

Test commands via UART:
- Write Enable/Disable (WREN/WRDI) operations
- Status register read/write operations
- Single byte and page write/read operations
- Page boundary behavior and wraparound
- Sequential addressing verification
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout, First
from cocotbext.uart import UartSource, UartSink
import logging

class SpiEeprom25010B:
    """
    AT25010B 1K SPI EEPROM Model
    
    Supports:
    - WREN (0x06): Write Enable - sets WEL bit
    - WRDI (0x04): Write Disable - clears WEL bit  
    - RDSR (0x05): Read Status Register
    - WRSR (0x01): Write Status Register
    - READ (0x03): Read Data from Memory Array [cmd][addr][data_bytes...]
    - WRITE (0x02): Write Data to Memory Array [cmd][addr][data_bytes...]
    - 8-byte page write boundaries with wraparound
    - 7-bit addressing (128 bytes, 0x00-0x7F)
    """
    
    def __init__(self, sclk, cs_n, mosi, miso):
        self.sclk = sclk
        self.cs_n = cs_n
        self.mosi = mosi
        self.miso = miso
        
        # 128 bytes memory array (7-bit addressing)
        self.memory = bytearray(128)  # 0x00 to 0x7F
        
        # Status register: [X X X X BP1 BP0 WEL RDY]
        # WEL (bit 1): Write Enable Latch
        # RDY (bit 0): Ready (0=ready, 1=busy - always ready in simulation)
        self.status_register = 0x00  # Start with WEL=0, RDY=0
        
        # Initialize MISO to high (idle)
        self.miso.value = 1
        
        # Track if any writes occurred during current CS transaction
        self._wrote_anything_this_cs = False
        
        # Start the SPI slave coroutine
        cocotb.start_soon(self._spi_slave_process())
        
        self.log = logging.getLogger("cocotb.spi_eeprom")
        
    async def _spi_slave_process(self):
        """Main SPI slave process - handles discontinuous SCLK bursts"""
        
        while True:
            # Wait for CS to go low (start of new EEPROM command)
            self.log.debug("Waiting for CS falling edge...")
            await FallingEdge(self.cs_n)
            self.log.debug("CS went low - starting new EEPROM command")
            
            # Reset state for new EEPROM command
            self.state = "IDLE"
            self.command = None
            self.address = 0
            self.byte_count = 0
            self._wrote_anything_this_cs = False
            
            # Process individual SPI byte transmissions with edge-driven CS detection
            while True:
                # Check CS state before starting new byte
                if self.cs_n.value == 1:
                    break
                    
                try:
                    byte_completed = await self._process_single_spi_byte()
                    if not byte_completed:  # CS went high during byte processing
                        break
                except Exception as e:
                    self.log.error(f"SPI byte processing error: {e}")
                    break
            
            # Clear WEL after any write transaction (when CS goes high)
            if self._wrote_anything_this_cs and (self.status_register & 0x02):
                self.status_register &= ~0x02  # Clear WEL bit
                self.log.info("Write transaction completed - WEL cleared automatically")
            self._wrote_anything_this_cs = False
            
            # Set MISO back to idle
            self.miso.value = 1
            self.log.debug("CS went high - EEPROM command complete")
            
    async def _process_single_spi_byte(self):
        """Process one SPI byte transmission (8 SCLK cycles) with edge-driven CS detection"""
        
        # Determine what byte to transmit during this 8-bit exchange
        if self.state == "READ_STATUS" and self.command == 0x05:
            current_tx_byte = self.status_register
            self.log.info(f"MISO TX: Status register 0x{current_tx_byte:02X}")
        elif self.state == "READ_DATA" and self.command == 0x03:
            current_tx_byte = self.memory[self.address]
            self.log.info(f"MISO TX: Memory data 0x{current_tx_byte:02X} from addr 0x{self.address:02X}")
        else:
            current_tx_byte = 0xFF  # Idle/don't care value
        
        # Set first bit immediately (before any SCLK activity)
        first_bit = (current_tx_byte >> 7) & 1
        self.miso.value = first_bit
        
        # Process 8 bits with edge-driven CS detection
        rx_byte = 0
        
        for bit_idx in range(8):
            # Wait for rising edge, but allow CS to abort
            trigger = await First(RisingEdge(self.cs_n), RisingEdge(self.sclk))
            if trigger is RisingEdge(self.cs_n):  # CS went high, abort transaction
                self.log.debug(f"CS rose during bit {bit_idx}, aborting byte")
                return False  # Indicate CS abort
                
            # Sample MOSI on this rising edge
            mosi_bit = int(self.mosi.value)
            rx_byte = (rx_byte << 1) | mosi_bit
            
            # Wait for falling edge, then prepare next MISO bit
            if bit_idx < 7:  # Not the last bit
                trigger = await First(RisingEdge(self.cs_n), FallingEdge(self.sclk))
                if trigger is RisingEdge(self.cs_n):  # CS went high
                    self.log.debug(f"CS rose after bit {bit_idx}, aborting byte")
                    return False  # Indicate CS abort
                    
                # Set next bit on falling edge (ready for next rising edge sample)
                next_bit = (current_tx_byte >> (6 - bit_idx)) & 1
                self.miso.value = next_bit
        
        # Process the received byte and update state
        old_state = self.state
        self.log.info(f"SPI RX: 0x{rx_byte:02X} in state {self.state}")
        
        self.state, self.command, self.address, self.byte_count = self._process_rx_byte(
            rx_byte, self.state, self.command, self.address, self.byte_count)
        
        cmd_str = f"0x{self.command:02X}" if self.command is not None else "None"
        self.log.info(f"New state: {self.state}, cmd: {cmd_str}, addr: 0x{self.address:02X}")
        
        return True  # Indicate successful byte completion
            
    def _process_rx_byte(self, rx_byte, state, command, address, byte_count):
        """Process received byte and update state"""
        
        if state == "IDLE":
            # Only process commands in IDLE state (start of CS transaction)
            command = rx_byte
            self.log.info(f"Processing command: 0x{command:02X}")
            if command == 0x06:  # WREN
                self.status_register |= 0x02  # Set WEL bit (bit 1)
                self.log.info(f"WREN: Write Enable Latch set, status=0x{self.status_register:02X}")
                return "IDLE", command, address, 0
            elif command == 0x04:  # WRDI
                self.status_register &= ~0x02  # Clear WEL bit (bit 1)
                self.log.info(f"WRDI: Write Enable Latch cleared, status=0x{self.status_register:02X}")
                return "IDLE", command, address, 0
            elif command == 0x05:  # RDSR
                return "READ_STATUS", command, address, 0
            elif command == 0x01:  # WRSR
                return "WRITE_STATUS", command, address, 0
            elif command == 0x03:  # READ
                return "READ_ADDR", command, address, 0
            elif command == 0x02:  # WRITE
                return "WRITE_ADDR", command, address, 0
            else:
                self.log.warning(f"Unsupported command: 0x{command:02X}")
                return "IDLE", command, address, 0
        
        # Process based on current state (multi-byte command sequences)
        # In all non-IDLE states, treat bytes as address/data, NOT commands
                
        elif state == "READ_STATUS":
            # Status register read - ignore incoming data (dummy bytes)
            return "READ_STATUS", command, address, byte_count
            
        elif state == "WRITE_STATUS":
            # Write to status register (only BP1, BP0 bits writable)
            self.status_register = (self.status_register & 0x03) | (rx_byte & 0x0C)
            self.log.debug(f"WRSR: Status register written: 0x{self.status_register:02X}")
            return "IDLE", command, address, 0
            
        elif state == "READ_ADDR":
            # Second byte: address (7 bits) - treat as address, NOT command
            address = rx_byte & 0x7F  # Mask to 7 bits
            self.log.debug(f"READ from address 0x{address:02X}")
            return "READ_DATA", command, address, 0
            
        elif state == "READ_DATA":
            # Data bytes: read from memory with auto-increment
            # Note: This is called AFTER we've already transmitted the byte for this address
            self.log.debug(f"READ_DATA: data 0x{self.memory[address]:02X} from address 0x{address:02X}")
            address = (address + 1) & 0x7F  # Auto-increment with 7-bit wrap for next read
            return "READ_DATA", command, address, byte_count
            
        elif state == "WRITE_ADDR":
            # Second byte: address (7 bits) - treat as address, NOT command
            address = rx_byte & 0x7F  # Mask to 7 bits
            # Check if Write Enable Latch is set
            if not (self.status_register & 0x02):
                self.log.warning("WRITE attempted without Write Enable Latch set")
                return "IDLE", command, address, 0
            self.log.debug(f"WRITE to address 0x{address:02X}")
            return "WRITE_DATA", command, address, 0
            
        elif state == "WRITE_DATA":
            # Check if Write Enable Latch is still set
            if not (self.status_register & 0x02):
                self.log.warning("WRITE data ignored - WEL not set")
                return "WRITE_DATA", command, address, byte_count
                
            # Data bytes: write to memory with 8-byte page boundary
            self.memory[address] = rx_byte
            self._wrote_anything_this_cs = True  # Mark that we wrote to memory
            self.log.debug(f"Wrote 0x{rx_byte:02X} to address 0x{address:02X}")
            
            # 8-byte page write: only A2-A0 increment, A7-A3 stay constant
            # Calculate next address within same page
            page_base = address & 0xF8  # A7-A3 (page number) - fixed mask
            current_offset = address & 0x07  # A2-A0 (current position in page)
            next_offset = (current_offset + 1) & 0x07  # Increment with 3-bit wrap
            address = page_base | next_offset
            
            byte_count += 1
            self.log.debug(f"Next write address: 0x{address:02X} (page_base=0x{page_base:02X}, offset={next_offset})")
            return "WRITE_DATA", command, address, byte_count
        
        # Default fallback
        self.log.warning(f"Unhandled state {state} with byte 0x{rx_byte:02X}")
        return state, command, address, byte_count

'''
#@cocotb.test()
async def test_write_enable_disable(dut):
    """Test WREN/WRDI commands and WEL bit behavior"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Test WREN command
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    assert response[0] == 0x01
    
    # Send WREN command (0x06)
    await uart_source.write([0x05, 0x06])
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    assert response[0] == 0x02
    
    # Read status register to check WEL bit
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x05])  # RDSR command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, 0x00])  # Clock out status register
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Check WEL bit is set (bit 1 = 1)
    assert (response[0] & 0x02) != 0, f"WEL bit not set: 0x{response[0]:02X}"
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Test WRDI command
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Send WRDI command (0x04)
    await uart_source.write([0x05, 0x04])
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Read status register to check WEL bit cleared
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x05])  # RDSR command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, 0x00])  # Clock out status register
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Check WEL bit is cleared (bit 1 = 0)
    assert (response[0] & 0x02) == 0, f"WEL bit not cleared: 0x{response[0]:02X}"
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_status_register(dut):
    """Test RDSR command and status register functionality"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Read initial status register (should be 0x00)
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x05])  # RDSR command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, 0x00])  # Clock out status register
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Should be 0x00 initially (WEL=0, RDY=0)
    assert response[0] == 0x00, f"Initial status register should be 0x00, got 0x{response[0]:02X}"
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_single_byte_write_read(dut):
    """Test single byte write/read with proper WREN sequence"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Test data and address
    test_address = 0x10
    test_data = 0xA5
    
    # Write operation with proper WREN sequence
    
    # 1. Write Enable (WREN)
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x06])  # WREN command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # 2. Write Data
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_data])  # Data
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS (completes write cycle)
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(1000, units="us")
    
    # Read operation
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x03])  # READ command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, 0x00])  # Clock out data byte
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Verify read data matches written data
    assert response[0] == test_data, f"Read data 0x{response[0]:02X} != written data 0x{test_data:02X}"
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_write_without_wren(dut):
    """Test write protection when WEL=0"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Test data and address
    test_address = 0x20
    test_data = 0x33
    
    # Try to write without WREN (should be ignored)
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_data])  # Data (should be ignored)
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(1000, units="us")
    
    # Read back to verify data was not written (should be 0x00)
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x03])  # READ command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, 0x00])  # Clock out data byte
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Verify data was not written (should still be 0x00)
    assert response[0] == 0x00, f"Data should not be written without WREN, got 0x{response[0]:02X}"
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_8_byte_page_write(dut):
    """Test 8-byte page write within page boundary"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Test data and address (start of a page)
    test_address = 0x08  # Page 1 start (0x08-0x0F)
    test_data = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]
    
    # Write Enable
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x06])  # WREN command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Write 8 bytes to page
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Write all 8 bytes
    for data_byte in test_data:
        await uart_source.write([0x05, data_byte])
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    
    await Timer(1000, units="us")
    
    # Read back all 8 bytes
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x03])  # READ command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Read all 8 bytes
    read_data = []
    for i in range(8):
        await uart_source.write([0x05, 0x00])  # Clock out data
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        read_data.append(response[0])
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Verify all data matches
    for i, (written, read) in enumerate(zip(test_data, read_data)):
        assert read == written, f"Byte {i}: read 0x{read:02X} != written 0x{written:02X}"
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_page_boundary_wrap(dut):
    """Test wraparound when writing across page boundary"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Test address near page boundary (page 0: 0x00-0x07)
    test_address = 0x06  # 2 bytes from end of page 0
    test_data = [0xAA, 0xBB, 0xCC, 0xDD]  # 4 bytes - should wrap to beginning of page
    
    # Write Enable
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x06])  # WREN command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Write 4 bytes starting at 0x06 (should wrap within page 0)
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Write 4 bytes
    for data_byte in test_data:
        await uart_source.write([0x05, data_byte])
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    
    await Timer(1000, units="us")
    
    # Expected result: 0xCC, 0xDD, 0x00, 0x00, 0x00, 0x00, 0xAA, 0xBB
    # (bytes 0-1 overwritten by wraparound, bytes 2-5 unchanged, bytes 6-7 written normally)
    expected_page = [0xCC, 0xDD, 0x00, 0x00, 0x00, 0x00, 0xAA, 0xBB]
    
    # Read entire page 0
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x03])  # READ command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, 0x00])  # Address 0x00 (start of page)
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Read entire page
    read_data = []
    for i in range(8):
        await uart_source.write([0x05, 0x00])  # Clock out data
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        read_data.append(response[0])
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Verify wraparound behavior
    for i, (expected, read) in enumerate(zip(expected_page, read_data)):
        assert read == expected, f"Address 0x{i:02X}: read 0x{read:02X} != expected 0x{expected:02X}"
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_multi_page_operations(dut):
    """Test write to different pages sequentially"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Write to multiple pages
    pages_data = [
        (0x00, [0x01, 0x02]),  # Page 0, first 2 bytes
        (0x10, [0x11, 0x12]),  # Page 2, first 2 bytes  
        (0x20, [0x21, 0x22]),  # Page 4, first 2 bytes
    ]
    
    for page_addr, page_data in pages_data:
        # Write Enable
        await uart_source.write([0x01])  # Assert CS
        response = await with_timeout(uart_sink.read(count=1), 10000, "us")
        
        await uart_source.write([0x05, 0x06])  # WREN command
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        
        await uart_source.write([0x02])  # Deassert CS
        response = await with_timeout(uart_sink.read(count=1), 10000, "us")
        
        # Write to page
        await uart_source.write([0x01])  # Assert CS
        response = await with_timeout(uart_sink.read(count=1), 10000, "us")
        
        await uart_source.write([0x05, 0x02])  # WRITE command
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        
        await uart_source.write([0x05, page_addr])  # Address
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        
        # Write data bytes
        for data_byte in page_data:
            await uart_source.write([0x05, data_byte])
            response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        
        await uart_source.write([0x02])  # Deassert CS
        response = await with_timeout(uart_sink.read(count=1), 10000, "us")
        
        # Simulate write cycle completion
            
        await Timer(500, units="us")
    
    # Verify all pages
    for page_addr, expected_data in pages_data:
        await uart_source.write([0x01])  # Assert CS
        response = await with_timeout(uart_sink.read(count=1), 10000, "us")
        
        await uart_source.write([0x05, 0x03])  # READ command
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        
        await uart_source.write([0x05, page_addr])  # Address
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        
        # Read data bytes
        read_data = []
        for i in range(len(expected_data)):
            await uart_source.write([0x05, 0x00])  # Clock out data
            response = await with_timeout(uart_sink.read(count=1), 20000, "us")
            read_data.append(response[0])
        
        await uart_source.write([0x02])  # Deassert CS
        response = await with_timeout(uart_sink.read(count=1), 10000, "us")
        
        # Verify data
        for i, (expected, read) in enumerate(zip(expected_data, read_data)):
            addr = page_addr + i
            assert read == expected, f"Address 0x{addr:02X}: read 0x{read:02X} != expected 0x{expected:02X}"
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_sequential_read_within_page(dut):
    """Test sequential read multiple bytes within single page"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Pre-populate memory with test pattern
    test_data = [0x10, 0x11, 0x12, 0x13, 0x14, 0x15]
    test_address = 0x30  # Page 6
    
    # Write test data
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x06])  # WREN command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    for data_byte in test_data:
        await uart_source.write([0x05, data_byte])
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(500, units="us")
    
    # Sequential read starting from middle of test data
    read_start = test_address + 2  # Start at 0x32
    
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x03])  # READ command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, read_start])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Read 4 sequential bytes
    read_data = []
    for i in range(4):
        await uart_source.write([0x05, 0x00])  # Clock out data
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        read_data.append(response[0])
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Verify sequential read
    expected_data = test_data[2:6]  # 0x12, 0x13, 0x14, 0x15
    for i, (expected, read) in enumerate(zip(expected_data, read_data)):
        assert read == expected, f"Sequential read byte {i}: read 0x{read:02X} != expected 0x{expected:02X}"
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_sequential_read_across_pages(dut):
    """Test sequential read across page boundaries"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Write data to end of page 1 and beginning of page 2
    page1_data = [0xA1, 0xA2]  # Last 2 bytes of page 1 (0x0E, 0x0F)
    page2_data = [0xB1, 0xB2]  # First 2 bytes of page 2 (0x10, 0x11)
    
    # Write to page 1
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x06])  # WREN
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, 0x0E])  # Address page 1 end
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    for data_byte in page1_data:
        await uart_source.write([0x05, data_byte])
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Write to page 2
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x06])  # WREN
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, 0x10])  # Address page 2 start
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    for data_byte in page2_data:
        await uart_source.write([0x05, data_byte])
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(500, units="us")
    
    # Sequential read across page boundary
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x03])  # READ command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, 0x0E])  # Start at page boundary
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Read 4 bytes across page boundary
    read_data = []
    for i in range(4):
        await uart_source.write([0x05, 0x00])  # Clock out data
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        read_data.append(response[0])
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Verify cross-page read
    expected_data = page1_data + page2_data  # [0xA1, 0xA2, 0xB1, 0xB2]
    for i, (expected, read) in enumerate(zip(expected_data, read_data)):
        addr = 0x0E + i
        assert read == expected, f"Cross-page read addr 0x{addr:02X}: read 0x{read:02X} != expected 0x{expected:02X}"
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_address_rollover(dut):
    """Test 128-byte address space rollover (0x7F → 0x00)"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Write data to last bytes of memory and first bytes
    end_data = [0xFE, 0xFF]  # Last 2 bytes (0x7E, 0x7F)
    start_data = [0x00, 0x01]  # First 2 bytes (0x00, 0x01)
    
    # Write to end of memory
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x06])  # WREN
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, 0x7E])  # Near end address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    for data_byte in end_data:
        await uart_source.write([0x05, data_byte])
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Write to beginning of memory
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x06])  # WREN
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, 0x00])  # Start address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    for data_byte in start_data:
        await uart_source.write([0x05, data_byte])
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(500, units="us")
    
    # Sequential read across memory boundary (rollover test)
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await uart_source.write([0x05, 0x03])  # READ command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x05, 0x7E])  # Start near end
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Read 4 bytes across memory boundary
    read_data = []
    for i in range(4):
        await uart_source.write([0x05, 0x00])  # Clock out data
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        read_data.append(response[0])
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Verify rollover behavior
    expected_data = end_data + start_data  # [0xFE, 0xFF, 0x00, 0x01]
    for i, (expected, read) in enumerate(zip(expected_data, read_data)):
        addr = (0x7E + i) & 0x7F
        assert read == expected, f"Rollover read addr 0x{addr:02X}: read 0x{read:02X} != expected 0x{expected:02X}"
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_wel_cleared_after_write(dut):
    """Test that WEL bit is auto-cleared after write cycle completion"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable writes
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x06])  # WREN command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Verify WEL is set
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x05])  # RDSR command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, 0x00])  # Clock out status
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    assert (response[0] & 0x02) != 0, "WEL bit should be set before write"
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Perform write operation
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, 0x40])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, 0x55])  # Data
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x02])  # Deassert CS (completes write cycle)
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Verify WEL is cleared after write
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x05])  # RDSR command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, 0x00])  # Clock out status
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    assert (response[0] & 0x02) == 0, f"WEL bit should be cleared after write, got 0x{response[0]:02X}"
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(1000, units="us")

#@cocotb.test()
async def test_write_more_than_8_bytes(dut):
    """Test page wraparound with >8 byte writes"""
    
    # Setup clock
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    
    # Reset sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Setup UART interfaces
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Create SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Test writing 12 bytes starting at address 0x18 (page 3)
    test_address = 0x18
    test_data = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C]
    
    # Write Enable
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x06])  # WREN command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Write 12 bytes (should wrap after 8)
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x02])  # WRITE command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    for data_byte in test_data:
        await uart_source.write([0x05, data_byte])
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    await Timer(500, units="us")
    
    # Read entire page to verify wraparound
    await uart_source.write([0x01])  # Assert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    await uart_source.write([0x05, 0x03])  # READ command
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    await uart_source.write([0x05, test_address])  # Address
    response = await with_timeout(uart_sink.read(count=1), 20000, "us")
    
    # Read 8 bytes (full page)
    read_data = []
    for i in range(8):
        await uart_source.write([0x05, 0x00])  # Clock out data
        response = await with_timeout(uart_sink.read(count=1), 20000, "us")
        read_data.append(response[0])
    
    await uart_source.write([0x02])  # Deassert CS
    response = await with_timeout(uart_sink.read(count=1), 10000, "us")
    
    # Expected: first 8 bytes written normally, then last 4 bytes wrap to beginning of page
    # So page should have: [0x09, 0x0A, 0x0B, 0x0C, 0x05, 0x06, 0x07, 0x08]
    expected_page = [0x09, 0x0A, 0x0B, 0x0C, 0x05, 0x06, 0x07, 0x08]
    
    for i, (expected, read) in enumerate(zip(expected_page, read_data)):
        addr = test_address + i
        assert read == expected, f"Page wrap addr 0x{addr:02X}: read 0x{read:02X} != expected 0x{expected:02X}"
    
    await Timer(1000, units="us")
'''

def _install_eeprom(dut) -> SpiEeprom25010B:
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_0,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso,
    )
    return spi_eeprom

@cocotb.test()
async def eepmod_test_single_read(dut):
    """ Test a regular single-byte read from memory """
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    spi_eeprom = _install_eeprom(dut)

    spi_eeprom.memory[0] = 0xaa

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    

    dut.address.value = 0
    dut.enable.value = 1
    await RisingEdge(dut.clk)

    dut.enable.value = 0

    await RisingEdge(dut.finished)

    assert dut.data_out.value == 0xaa

@cocotb.test()
async def eepmod_test_reset_during_read(dut):
    """ Test whether the EEPROM module continues to operate as intended after a mid-transaction reset """

    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())  # 10MHz
    spi_eeprom = _install_eeprom(dut)
    
    spi_eeprom.memory[0] = 0xaa

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    dut.address.value = 0
    dut.enable.value = 1

    # we test for a reset occuring at different steps in the process
    for num_cycles in range(0,100):
        for _ in range(num_cycles): await RisingEdge(dut.clk)
        dut.rst.value = 1
        await RisingEdge(dut.clk)
        dut.rst.value = 0
        await RisingEdge(dut.clk)

        dut.address.value = 0
        dut.enable.value = 1
        await RisingEdge(dut.clk)
        dut.enable.value = 0
        await RisingEdge(dut.finished)

        assert dut.data_out.value == 0xaa, f'Bad read value if reset occurs {num_cycles} cycles into transaction' 

@cocotb.test()
async def test_continuous_read(dut):
    """ Test the "Continuous read" feature of the EEPROM module:
        In the finished state, enabled can be pulsed again to read the next byte starting from the given address
    """

    cocotb.start_soon(Clock(dut.clk, 100, unit='ns').start())

    spi_eeprom = _install_eeprom(dut)
    OFFSET=0x48
    # fill pattern 001122...eeff
    # 0x48 crosses a page boundary (which shouldn't matter for reads), good to test that anyways
    spi_eeprom.memory[OFFSET:OFFSET+16] = bytes(range(0,0x100,0x11))

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    dut.address.value = OFFSET

    result = bytearray(16)

    # Once we have put in the address, we dont really care whether we're in idle or finished state
    # the procedure for the module user is the same: pulse enable for 1 cycle, wait for finished to be raised again, and check the data value
    for i in range(16):
        dut.enable.value = 1

        await RisingEdge(dut.clk)
        dut.enable.value = 0
        await RisingEdge(dut.finished)
        result[i] = dut.data_out.value

    
    assert result == spi_eeprom.memory[OFFSET:OFFSET+16], f'Read error. Expected {spi_eeprom.memory[OFFSET:OFFSET+16].hex()}, got {result.hex()}'