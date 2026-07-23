"""
Application development testbench for main_controller.

Usage:
  - Generate a ROM hex file (18-bit words, 1 per line). By default, the ROM
    module reads `rtl/rom.mem` at time 0.
  - Optionally set `ROM_PATH` to load a different hex file into the ROM
    during simulation.
  - Optional tracing:
      INSTR_TRACE=1   Enable instruction trace logging
      TRACE_RAM=1     Include RAM[arg1]/RAM[arg2] values in trace
  - Runtime controls:
      MAX_CYCLES=200000  Maximum cycles to run
      STOP_PC=0x000      Stop when PC reaches this value (unset to disable)
"""

import os
import logging
import secrets
from random import getrandbits
from typing import Dict, List, Optional, Tuple

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, First, with_timeout
from Crypto.Cipher import AES

from abc import ABC, abstractmethod

# CPU state encoding (from rtl/main_controller.v)
FETCH = 0
EXECUTE = 1
WRITEBACK = 2
WAIT_CRC = 3

STATE_NAMES = {
    FETCH: "FETCH",
    EXECUTE: "EXECUTE",
    WRITEBACK: "WRITEBACK",
    WAIT_CRC: "WAIT_CRC",
}

# Opcode encoding (from rtl/main_controller.v)
OPCODE_NAMES = {
    0: "CRCRST",
    1: "CRCLD",
    2: "CRCH",
    3: "CRCL",
    4: "ROMRST",
    5: "ROMRD",
    6: "RC522RST",
    7: "RC522PUSH",
    8: "RC522POP",
    9: "RC522BLEN",
    10: "RC522TRCVE",
    11: "RC522BUFRST",
    12: "RC522WAIT",
    13: "RNDRST",
    14: "RNDGET",
    15: "CMPEQ",
    16: "CMPLT",
    17: "JMPC",
    18: "JUMPE",
    19: "CALL",
    20: "RET",
    21: "ADD",
    22: "XOR",
    23: "AND",
    60: "IMMLD00",
    61: "IMMLD01",
    62: "IMMLD10",
    63: "IMMLD11",
}

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
        self.mask = bytearray(16)
        self.memory = bytearray(128)  # 0x00 to 0x7F
        for i in range(16):
            self.mask[i] = getrandbits(8)
            self.memory[i] = (0x11 * i) ^ self.mask[i]
        
        for i in range(16,32):
            self.memory[i] = self.mask[i-16]

        for i in range(32,48):
            self.memory[i] = (i-32) + 1


        # HERE YOU CAN CHANGE THE MEMORY CONTENTS
        
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


# ============================================================================
# RC522 Model Classes (JavaCard Applet Simulation)
# ============================================================================

class JavaCardApplet(ABC):
    """Base class for JavaCard applet simulation"""

    def __init__(self):
        self.selected = False
        self.log = logging.getLogger(f"cocotb.applet.{self.__class__.__name__}")

    def on_select(self) -> Tuple[int, int]:
        """Called when applet is selected"""
        self.selected = True
        self.log.info(f"Applet {self.__class__.__name__} selected")
        return 0x90, 0x00  # Success

    def on_deselect(self):
        """Called when applet is deselected"""
        self.selected = False
        self.log.info(f"Applet {self.__class__.__name__} deselected")

    @abstractmethod
    def process_apdu(self, cla: int, ins: int, p1: int, p2: int,
                    data: Optional[List[int]], le: Optional[int]) -> Tuple[List[int], int, int]:
        """Process APDU command and return (response_data, SW1, SW2)"""
        pass


class AuthenticatedIdentificationApplet(JavaCardApplet):
    """Implementation of the AuthenticatedIdentificationApplet"""

    def __init__(self):
        super().__init__()
        self.pre_shared_key = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
                                   0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
        self.card_id = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                            0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10])

        # Session state
        self.rc = None          # Card nonce (64-bit)
        self.rt = None          # Terminal nonce (64-bit)
        self.ephemeral_key = None   # Session key (128-bit)
        self.auth_success = False   # Authentication status

        # WTX configuration
        self.wtx_enabled = True     # Default: emit WTX for AUTH command
        self.wtx_delay_cycles = 50  # Processing delay simulation

    def on_select(self) -> Tuple[int, int]:
        """Reset session state on applet selection"""
        self._reset_session()
        return super().on_select()

    def on_deselect(self):
        """Clear session state on deselection"""
        self._reset_session()
        super().on_deselect()

    def _reset_session(self):
        """Reset authentication session state"""
        self.rc = None
        self.rt = None
        self.ephemeral_key = None
        self.auth_success = False
        self.log.debug("Session state reset")

    def process_apdu(self, cla: int, ins: int, p1: int, p2: int,
                    data: Optional[List[int]], le: Optional[int]) -> Tuple[List[int], int, int]:
        """Process proprietary APDU commands (CLA=0x80)"""

        if cla != 0x80:
            return [], 0x6E, 0x00  # Class not supported

        if ins == 0x10:  # AUTH_INIT
            return self._handle_auth_init(le)
        elif ins == 0x11:  # AUTH
            return self._handle_auth(data, le)
        elif ins == 0x12:  # GET_ID
            return self._handle_get_id(le)
        else:
            return [], 0x6D, 0x00  # Instruction not supported

    def _handle_auth_init(self, le: Optional[int]) -> Tuple[List[int], int, int]:
        """Handle AUTH_INIT command (INS=0x10)"""
        if le != 16:
            return [], 0x67, 0x00  # Wrong length

        # Generate random 64-bit nonce
        self.rc = secrets.token_bytes(8)
        self.log.info(f"AUTH_INIT: Generated card nonce rc: {self.rc.hex().upper()}")

        # Create plaintext: rc || 0x00...00 (rc + 8 zero bytes)
        plaintext = self.rc + b'\x00' * 8
        self.log.info(f"AUTH_INIT: Plaintext (rc||zeros): {plaintext.hex().upper()}")

        # Encrypt with pre-shared key
        cipher = AES.new(self.pre_shared_key, AES.MODE_ECB)
        ciphertext = cipher.encrypt(plaintext)
        self.log.info(f"AUTH_INIT: Ciphertext response: {ciphertext.hex().upper()}")

        return list(ciphertext), 0x90, 0x00

    def _handle_auth(self, data: Optional[List[int]], le: Optional[int]) -> Tuple[List[int], int, int, bool]:
        """Handle AUTH command (INS=0x11) - Returns (data, sw1, sw2, needs_wtx)"""
        if not data or len(data) != 16:
            return [], 0x67, 0x00, False  # Wrong length
        if le != 16:
            return [], 0x67, 0x00, False  # Wrong length
        if self.rc is None:
            return [], 0x69, 0x85, False  # Conditions not satisfied (AUTH_INIT not called)

        self.log.info(f"AUTH: Received encrypted data: {bytes(data).hex().upper()}")
        self.log.info(f"AUTH: Expected card nonce rc: {self.rc.hex().upper()}")

        # Decrypt received ciphertext
        cipher = AES.new(self.pre_shared_key, AES.MODE_ECB)
        try:
            plaintext = cipher.decrypt(bytes(data))
            self.log.info(f"AUTH: Decrypted plaintext (rt||rc'): {plaintext.hex().upper()}")
        except Exception:
            self.log.info("AUTH: AES decryption failed")
            return [], 0x6F, 0x00, False  # Unknown error

        # Extract terminal nonce and card nonce echo
        self.rt = plaintext[0:8]  # Terminal nonce
        rc_echo = plaintext[8:16]  # Card nonce echo

        self.log.info(f"AUTH: Terminal nonce rt: {self.rt.hex().upper()}")
        self.log.info(f"AUTH: Card nonce echo rc': {rc_echo.hex().upper()}")

        # Verify authentication
        self.auth_success = (rc_echo == self.rc)

        if self.auth_success:
            self.log.info("AUTH: ✓ Nonce verification successful - rc' matches rc")
        else:
            self.log.info(f"AUTH: ✗ Nonce verification failed - rc' ({rc_echo.hex().upper()}) != rc ({self.rc.hex().upper()})")

        # Derive ephemeral key
        self.ephemeral_key = self.rc + self.rt
        self.log.info(f"AUTH: Derived ephemeral key (rc||rt): {self.ephemeral_key.hex().upper()}")

        # Prepare response message
        if self.auth_success:
            response_msg = b"AUTH_SUCCESS\x00\x00\x00\x00"
            self.log.info("AUTH: Authentication successful")
        else:
            response_msg = b"AUTH_FAILURE\x00\x00\x00\x00"
            self.log.info("AUTH: Authentication failed")

        # Encrypt response with ephemeral key
        eph_cipher = AES.new(self.ephemeral_key, AES.MODE_ECB)
        encrypted_response = eph_cipher.encrypt(response_msg)
        self.log.info(f"AUTH: Encrypted response: {encrypted_response.hex().upper()}")

        return list(encrypted_response), 0x90, 0x00, self.wtx_enabled and self.auth_success

    def _handle_get_id(self, le: Optional[int]) -> Tuple[List[int], int, int]:
        """Handle GET_ID command (INS=0x12)"""
        if le != 16:
            return [], 0x67, 0x00  # Wrong length
        if not self.auth_success or self.ephemeral_key is None:
            return [], 0x69, 0x85  # Conditions not satisfied (not authenticated)

        # Encrypt card ID with ephemeral key
        cipher = AES.new(self.ephemeral_key, AES.MODE_ECB)
        encrypted_id = cipher.encrypt(self.card_id)

        self.log.info(f"GET_ID: Returning encrypted card ID ({len(encrypted_id)} bytes)")
        return list(encrypted_id), 0x90, 0x00

    def get_current_nonce(self):
        """Get the current card nonce (rc) generated during AUTH_INIT"""
        return self.rc


class RC522Model:
    """
    RC522 RFID Reader Model

    Emulates the RC522 chip with:
    - Complete SPI register interface
    - FIFO buffer management
    - Command execution simulation
    - JavaCard simulation for NFC responses

    Key registers implemented based on MFRC522 datasheet:
    - 0x02: CommandReg - Command execution
    - 0x08: ComIrqReg - Communication interrupt requests
    - 0x0C: ErrorReg - Error flags
    - 0x12: FIFODataReg - FIFO buffer access
    - 0x14: FIFOLevelReg - FIFO level indicator
    - 0x1A: BitFramingReg - Bit framing control
    - 0x22: ModeReg - General modes and CRC settings
    - 0x6E: VersionReg - IC version (0x92 for v2.0)
    """

    def __init__(self, sclk, cs_n, mosi, miso):
        # RC522 registers (64 registers, 0x00-0x3F)
        self.registers = {}
        self._init_registers()

        # FIFO buffer (64 bytes)
        self.fifo_buffer = bytearray(64)
        self.fifo_level = 0
        self.fifo_read_ptr = 0
        self.fifo_write_ptr = 0

        # Simulated JavaCard state
        self.card_present = True
        self.card_uid = [0x2F, 0xFB, 0xBC, 0x4A]  # From streamlined.log
        self.card_selected = False
        self.card_ats = [0x0A, 0x78, 0x80, 0x91, 0x02, 0x80, 0x73, 0xC8, 0x21, 0x10, 0xC3, 0x92]

        # Applet registry - maps AID bytes to applet instances
        self.registered_applets = {
            bytes([0xF0, 0x00, 0x00, 0x0C, 0xDC, 0x01]): AuthenticatedIdentificationApplet(),
            # Future applets can be added here
        }
        self.selected_applet = None  # Currently selected applet instance

        # WTX (Waiting Time Extension) protocol state
        self._pending_wtx_response = None  # Pending response after WTX acknowledgment

        # Register name mapping for debugging (using actual RC522 register addresses)
        self.reg_names = {
            0x01: "CommandReg", 0x04: "ComIrqReg", 0x06: "ErrorReg",
            0x09: "FIFODataReg", 0x0A: "FIFOLevelReg", 0x0D: "BitFramingReg",
            0x11: "ModeReg", 0x12: "TxModeReg", 0x13: "RxModeReg", 0x14: "TxControlReg",
            0x15: "TxASKReg", 0x16: "TxSelReg", 0x17: "RxSelReg", 0x18: "RxThresholdReg",
            0x19: "DemodReg", 0x24: "ModWidthReg", 0x26: "RFCfgReg", 0x2A: "TModeReg",
            0x2B: "TPrescalerReg", 0x2C: "TReloadRegH", 0x2D: "TReloadRegL", 0x37: "VersionReg"
        }

        # Transaction counter for correlation
        self.transaction_id = 0

        # Transaction history for testbench validation
        self._spi_transactions = []

        # Use manual implementation for this testbench
        # Manual implementation
        self.sclk = sclk
        self.cs_n = cs_n
        self.mosi = mosi
        self.miso = miso

        # SPI transaction state
        self.is_read = False
        self.current_address = 0

        # Initialize MISO to high (idle)
        self.miso.value = 1

        # Start the manual SPI slave process
        cocotb.start_soon(self._manual_spi_slave_process())

        self.log = logging.getLogger("cocotb.rc522_model")

    def _get_reg_name(self, address):
        """Get human-readable register name"""
        return self.reg_names.get(address, f"Reg{address:02X}")

    def _format_bytes(self, data, prefix=""):
        """Format byte array for logging"""
        if isinstance(data, (list, tuple)):
            return f"{prefix}{' '.join(f'{b:02X}' for b in data)}"
        elif isinstance(data, int):
            return f"{prefix}{data:02X}"
        return f"{prefix}{data}"

    def _log_transaction_start(self, is_read, address):
        """Log start of SPI transaction"""
        self.transaction_id += 1
        reg_name = self._get_reg_name(address)
        self.log.info(f"[TXN#{self.transaction_id:03d}] SPI {'READ' if is_read else 'WRITE'} {reg_name} (0x{address:02X})")
        return self.transaction_id

    def _calculate_iso14443a_crc(self, data: List[int]) -> List[int]:
        """
        Calculate ISO14443-A CRC for given data
        Polynomial: 0x8408, Initial value: 0x6363
        Returns CRC as [low_byte, high_byte]
        """
        crc = 0x6363  # Initial value for ISO14443-A

        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0x8408
                else:
                    crc >>= 1

        # Return as [low_byte, high_byte]
        return [crc & 0xFF, (crc >> 8) & 0xFF]

    def _init_registers(self):
        """Initialize RC522 registers to power-on defaults"""
        # Key registers with their default values (using actual RC522 register addresses)
        self.registers[0x01] = 0x20  # CommandReg - Idle command
        self.registers[0x04] = 0x04  # ComIrqReg - Initial interrupt state
        self.registers[0x06] = 0x00  # ErrorReg - No errors
        self.registers[0x09] = 0x00  # FIFODataReg - FIFO access
        self.registers[0x0A] = 0x00  # FIFOLevelReg - FIFO empty
        self.registers[0x0D] = 0x00  # BitFramingReg - No framing
        self.registers[0x11] = 0x3D  # ModeReg - CRC enabled, preset 6363h
        self.registers[0x12] = 0x00  # TxModeReg - Tx configuration
        self.registers[0x13] = 0x00  # RxModeReg - Rx configuration
        self.registers[0x14] = 0x80  # TxControlReg - Antenna off
        self.registers[0x15] = 0x40  # TxASKReg - ASK modulation
        self.registers[0x16] = 0x10  # TxSelReg - Tx selection
        self.registers[0x17] = 0x84  # RxSelReg - Rx selection
        self.registers[0x18] = 0x86  # RxThresholdReg - Rx threshold
        self.registers[0x19] = 0x4D  # DemodReg - Demodulator settings
        self.registers[0x24] = 0x26  # ModWidthReg - Modulation width
        self.registers[0x26] = 0x48  # RFCfgReg - RF configuration
        self.registers[0x2A] = 0x80  # TModeReg - Timer mode
        self.registers[0x2B] = 0xA9  # TPrescalerReg - Timer prescaler
        self.registers[0x2C] = 0x03  # TReloadRegH - Timer reload high
        self.registers[0x2D] = 0xE8  # TReloadRegL - Timer reload low
        self.registers[0x37] = 0x92  # VersionReg - RC522 v2.0

        # Initialize all other registers to 0x00
        for addr in range(0x64):
            if addr not in self.registers:
                self.registers[addr] = 0x00

    async def _manual_spi_slave_process(self):
        """Manual SPI slave implementation (fallback when cocotbext-spi unavailable)"""
        self.log.info("[SPI_SLAVE] RC522 SPI slave process started")
        self.log.info(f"[SPI_SLAVE] Monitoring CS signal: {self.cs_n.value}")

        # Add periodic CS monitoring to detect if it ever changes
        monitor_count = 0
        while True:
            try:
                # Wait for CS to go low (start of transaction) with timeout
                self.log.debug(f"[SPI_SLAVE] Waiting for CS assertion... (check #{monitor_count})")
                await with_timeout(FallingEdge(self.cs_n), 10, "ms")
                self.log.info("[SPI_SLAVE] === CS ASSERTED - Transaction Start ===")

                # Process SPI transaction
                await self._handle_spi_transaction()

                # Set MISO back to idle
                self.miso.value = 1
                self.log.info("[SPI_SLAVE] === CS RELEASED - Transaction End ===")
                self.log.debug("[SPI_SLAVE] MISO set to idle (high)")

            except Exception as e:
                monitor_count += 1
                current_cs = int(self.cs_n.value)  # FIX: Use int() for cocotb compatibility
                self.log.debug(f"[SPI_SLAVE] CS monitor timeout #{monitor_count}, CS={current_cs} (expecting 0 for active)")

                # Log every 100 checks (1 second) to show we're alive
                if monitor_count % 100 == 0:
                    self.log.info(f"[SPI_SLAVE] Still waiting for CS assertion after {monitor_count} checks (CS={current_cs})")

                # Don't flood the log, but continue monitoring
                continue

    async def _handle_spi_transaction(self):
        """Handle a complete SPI transaction"""
        byte_count = 0
        txn_id = None
        tx_bytes = []
        rx_bytes = []

        self.log.debug("[SPI_TXN] Starting SPI transaction handling")

        # Continue processing bytes until CS goes high or transaction complete
        while True:
            # Check CS before processing each byte
            if int(self.cs_n.value) != 0:  # FIX: Use int() for cocotb compatibility
                self.log.debug(f"[SPI_TXN] CS deasserted before byte #{byte_count}")
                break

            self.log.debug(f"[SPI_TXN] Processing byte #{byte_count}")

            # Set the byte index for bit-level processing (needed by _get_read_bit)
            self._current_tx_byte_index = byte_count

            # Receive one byte with CS monitoring
            try:
                rx_byte = await self._receive_spi_byte()
            except Exception as e:
                self.log.debug(f"[SPI_TXN] Exception during byte receive: {e}")
                break

            # Check if CS went high during byte reception
            if int(self.cs_n.value) != 0:  # FIX: Use int() for cocotb compatibility
                self.log.debug("[SPI_TXN] CS went high during byte receive - aborting")
                break

            rx_bytes.append(rx_byte)

            # Track transmitted byte for this transaction
            if hasattr(self, '_last_tx_byte'):
                tx_bytes.append(self._last_tx_byte)
                self.log.debug(f"[SPI_TXN] Byte #{byte_count}: RX=0x{rx_byte:02X}, TX=0x{self._last_tx_byte:02X}")
            else:
                self.log.debug(f"[SPI_TXN] Byte #{byte_count}: RX=0x{rx_byte:02X}, TX=N/A")

            if byte_count == 0:
                # First byte is address/command
                self.current_address = (rx_byte >> 1) & 0x3F  # Address in bits 6-1
                self.is_read = (rx_byte & 0x80) != 0   # MSB indicates read/write
                txn_id = self._log_transaction_start(self.is_read, self.current_address)
                self.log.debug(f"[TXN#{txn_id:03d}] Command byte: 0x{rx_byte:02X}")
            else:
                # Subsequent bytes are data
                if not self.is_read:
                    # Write operation - log the data being written
                    old_value = self.registers.get(self.current_address, 0x00)
                    self.log.info(f"[TXN#{txn_id:03d}] Write data: 0x{rx_byte:02X} (was 0x{old_value:02X})")
                    self._write_register(self.current_address, rx_byte)
                else:
                    # Read operation - log what we're sending back
                    if hasattr(self, '_last_tx_byte'):
                        self.log.info(f"[TXN#{txn_id:03d}] Read data: sent 0x{self._last_tx_byte:02X}")

            byte_count += 1

            # For read operations, typically only 2 bytes (address + data)
            # For write operations, typically only 2 bytes (address + data)
            # Break after processing expected number of bytes for the operation
            if (self.is_read and byte_count >= 2) or (not self.is_read and byte_count >= 2):
                self.log.debug(f"[SPI_TXN] Transaction complete after {byte_count} bytes")
                break

        # Transaction cleanup
        self._cleanup_transaction()

        # Log transaction summary and track for testbench validation
        if txn_id:
            summary = f"Complete - RX: {self._format_bytes(rx_bytes)} | TX: {self._format_bytes(tx_bytes)} ({byte_count} bytes)"
            self.log.info(f"[TXN#{txn_id:03d}] {summary}")

            # Add to transaction history for testbench validation
            if len(rx_bytes) >= 1:
                cmd_byte = rx_bytes[0]
                is_read = (cmd_byte & 0x80) != 0
                address = (cmd_byte >> 1) & 0x3F  # Correct address extraction
                reg_name = self._get_reg_name(address)
                if is_read:
                    result = tx_bytes[1] if len(tx_bytes) > 1 else 0
                    txn_desc = f"READ {reg_name} -> 0x{result:02X}"
                else:
                    data = rx_bytes[1] if len(rx_bytes) > 1 else 0
                    txn_desc = f"WRITE {reg_name} <- 0x{data:02X}"
                self._spi_transactions.append(f"TXN#{txn_id:03d}: {txn_desc}")
        else:
            self.log.warning(f"[SPI_TXN] Transaction completed with no TXN ID - {byte_count} bytes")

    def _cleanup_transaction(self):
        """Clean up transaction state and ensure proper idle conditions"""
        # Reset transaction state variables
        if hasattr(self, '_current_tx_byte_index'):
            delattr(self, '_current_tx_byte_index')
        if hasattr(self, '_current_read_byte'):
            delattr(self, '_current_read_byte')
        if hasattr(self, '_last_tx_byte'):
            delattr(self, '_last_tx_byte')

        # Ensure MISO is set to idle state
        self.miso.value = 1
        self.log.debug("[SPI_TXN] Transaction state cleaned up, MISO set to idle")

    async def _receive_spi_byte(self) -> int:
        """Receive one byte via SPI (Mode 0: CPOL=0, CPHA=0)"""
        rx_byte = 0
        tx_byte = 0

        self.log.debug("[SPI_BITS] Starting byte reception")

        for bit_index in range(8):
            # Check CS before each bit
            if int(self.cs_n.value) != 0:  # FIX: Use int() for cocotb compatibility
                self.log.debug(f"[SPI_BITS] CS deasserted before bit {bit_index}")
                raise Exception("CS deasserted during byte")

            # For read operations, set MISO before the rising edge
            if self.is_read and hasattr(self, 'current_address'):
                tx_bit = self._get_read_bit(self.current_address, bit_index)
                self.miso.value = tx_bit
                old_tx_byte = tx_byte
                tx_byte = (tx_byte << 1) | tx_bit
                self.log.debug(f"[SPI_BITS] Bit {bit_index}: TX={tx_bit}, tx_byte: 0x{old_tx_byte:02X}->0x{tx_byte:02X} (read mode, addr=0x{self.current_address:02X})")
            else:
                self.miso.value = 1  # Idle high for writes
                tx_byte = (tx_byte << 1) | 1
                self.log.debug(f"[SPI_BITS] Bit {bit_index}: TX=1 (write mode/idle)")

            # Wait for rising edge to sample MOSI
            await RisingEdge(self.sclk)
            if int(self.cs_n.value) != 0:  # FIX: Use int() for cocotb compatibility
                self.log.debug("[SPI_BITS] CS deasserted during clock edge - aborting")
                raise Exception("CS deasserted during clock edge")

            # Sample MOSI (MSB first)
            mosi_bit = int(self.mosi.value)  # FIX: Use int() for cocotb compatibility
            rx_byte = (rx_byte << 1) | mosi_bit
            self.log.debug(f"[SPI_BITS] Bit {bit_index}: RX={mosi_bit} (sampled on rising edge)")

            # Wait for falling edge (end of bit period)
            await FallingEdge(self.sclk)
            if int(self.cs_n.value) != 0:  # FIX: Use int() for cocotb compatibility
                self.log.debug("[SPI_BITS] CS deasserted during clock falling edge - returning partial")
                # Store partial transmitted byte for logging
                self._last_tx_byte = tx_byte
                raise Exception("CS deasserted during clock falling edge")

        # Store transmitted byte for logging
        self._last_tx_byte = tx_byte
        self.log.debug(f"[SPI_BITS] Byte complete: RX=0x{rx_byte:02X}, TX=0x{tx_byte:02X}")
        return rx_byte

    def _get_read_bit(self, address: int, bit_index: int) -> int:
        """Get transmit bit for register read operations"""
        # For SPI register reads in RC522:
        # - First byte (command/address): return don't care (all 1s)
        # - Second byte (data): return actual register data

        # Check if we're in the first or second byte of the transaction
        # We can determine this by checking if we've stored the tx byte yet
        if not hasattr(self, '_current_tx_byte_index'):
            self._current_tx_byte_index = 0

        # During first byte (address), always return 1 (don't care)
        if self._current_tx_byte_index == 0:
            return 1
        else:
            # During second byte, return actual register data
            if address == 0x09:  # FIFODataReg - special handling (raw address, not SPI address)
                if bit_index == 0:  # First bit - read the byte once per transaction
                    self._current_read_byte = self._read_fifo_byte()
                    reg_name = self._get_reg_name(address)
                    self.log.info(f"[READ] {reg_name} FIFO read: 0x{self._current_read_byte:02X}")
                data_byte = self._current_read_byte
            else:
                # Regular register - read current value
                data_byte = self.registers.get(address, 0x00)
                if bit_index == 0:  # Log once per byte
                    reg_name = self._get_reg_name(address)
                    self.log.info(f"[READ] {reg_name} (0x{address:02X}) value: 0x{data_byte:02X}")

            # Return bit (MSB first)
            return (data_byte >> (7 - bit_index)) & 1

    def _write_register(self, address: int, value: int):
        """Write to RC522 register with side effects"""
        old_value = self.registers.get(address, 0x00)
        reg_name = self._get_reg_name(address)

        if address == 0x09:  # FIFODataReg
            self.log.info(f"[WRITE] {reg_name} FIFO write: 0x{value:02X}")
            self._write_fifo_byte(value)
        elif address == 0x0A and (value & 0x80):  # FIFOLevelReg flush
            self.log.info(f"[WRITE] {reg_name} FIFO flush triggered (0x{value:02X})")
            self._flush_fifo()
        elif address == 0x01:  # CommandReg - execute command
            cmd_names = {0x00: "Idle", 0x0C: "Transceive", 0x0F: "SoftReset"}
            cmd_name = cmd_names.get(value, f"Cmd{value:02X}")
            self.log.info(f"[WRITE] {reg_name} execute {cmd_name} (0x{value:02X})")
            self._execute_command(value)
        else:
            # Regular register write
            self.registers[address] = value
            change_str = f"0x{old_value:02X} → 0x{value:02X}" if old_value != value else f"0x{value:02X} (unchanged)"
            self.log.info(f"[WRITE] {reg_name} = {change_str}")

    def _read_fifo_byte(self) -> int:
        """Read one byte from FIFO buffer"""
        if self.fifo_level == 0:
            self.log.warning("[FIFO] Read from empty FIFO, returning 0x00 - NO ATQA DATA!")
            return 0x00

        data = self.fifo_buffer[self.fifo_read_ptr]
        old_read_ptr = self.fifo_read_ptr
        self.fifo_read_ptr = (self.fifo_read_ptr + 1) % 64
        self.fifo_level -= 1
        self.registers[0x0A] = self.fifo_level  # Update FIFOLevelReg

        self.log.info(f"[FIFO] *** FIFO BYTE READ *** 0x{data:02X} from pos {old_read_ptr}, level now {self.fifo_level}")
        return data

    def _write_fifo_byte(self, value: int):
        """Write one byte to FIFO buffer"""
        if self.fifo_level < 64:
            old_write_ptr = self.fifo_write_ptr
            self.fifo_buffer[self.fifo_write_ptr] = value
            self.fifo_write_ptr = (self.fifo_write_ptr + 1) % 64
            self.fifo_level += 1
            self.registers[0x0A] = self.fifo_level  # Update FIFOLevelReg
            self.log.debug(f"[FIFO] Write byte 0x{value:02X} to pos {old_write_ptr}, level now {self.fifo_level}")
        else:
            self.log.warning(f"[FIFO] Buffer full, discarded byte 0x{value:02X}")

    def _flush_fifo(self):
        """Flush FIFO buffer"""
        old_level = self.fifo_level
        self.fifo_level = 0
        self.fifo_read_ptr = 0
        self.fifo_write_ptr = 0
        self.registers[0x0A] = 0x00
        self.log.info(f"[FIFO] Flushed buffer (was {old_level} bytes)")

    def _execute_command(self, command: int):
        """Execute RC522 command"""
        self.registers[0x01] = command

        cmd_names = {0x00: "Idle", 0x0C: "Transceive", 0x0F: "SoftReset"}
        cmd_name = cmd_names.get(command, f"Unknown(0x{command:02X})")

        if command == 0x00:  # Idle
            self.log.debug(f"[CMD] {cmd_name} - stopping active operations")
            # Idle command immediately sets CommandReg to idle state
            self.registers[0x01] = 0x00
        elif command == 0x0C:  # Transceive
            self.log.info(f"[CMD] {cmd_name} - starting RF communication")
            self._execute_transceive()
        elif command == 0x0F:  # SoftReset
            self.log.info(f"[CMD] {cmd_name} - resetting RC522 state")
            self._execute_soft_reset()
        else:
            self.log.warning(f"[CMD] {cmd_name} - unsupported command")

    def _execute_transceive(self):
        """Execute Transceive command - communicate with simulated card"""
        # Read command from FIFO
        if self.fifo_level == 0:
            self.log.warning("[TRANSCEIVE] No data in FIFO for transmission")
            return

        # Get the command bytes from FIFO (non-destructive read)
        cmd_bytes = []
        temp_level = self.fifo_level
        temp_read_ptr = self.fifo_read_ptr

        for i in range(temp_level):
            cmd_bytes.append(self.fifo_buffer[temp_read_ptr])
            temp_read_ptr = (temp_read_ptr + 1) % 64

        self.log.info(f"[TRANSCEIVE] TX to card: {self._format_bytes(cmd_bytes)} ({temp_level} bytes)")

        # Simulate card response based on command
        response = self._simulate_card_response(cmd_bytes)

        if response:
            self.log.info(f"[TRANSCEIVE] RX from card: {self._format_bytes(response)} ({len(response)} bytes)")
            # Clear FIFO and write response
            self._flush_fifo()
            self.log.info(f"[TRANSCEIVE] Writing card response to FIFO: {self._format_bytes(response)}")
            for i, byte_val in enumerate(response):
                self.log.info(f"[TRANSCEIVE] Writing card byte {i+1}/{len(response)}: 0x{byte_val:02X}")
                self._write_fifo_byte(byte_val)
        else:
            self.log.warning("[TRANSCEIVE] No card response generated")

        # Set interrupt flags to indicate completion
        old_irq = self.registers[0x04]
        self.registers[0x04] |= 0x60  # RxIRq and TxIRq
        self.log.debug(f"[TRANSCEIVE] IRQ flags: 0x{old_irq:02X} → 0x{self.registers[0x04]:02X}")

        # Clear ErrorReg after successful transceive (like real RC522)
        self.registers[0x06] = 0x00  # Clear ErrorReg to indicate no communication errors
        self.log.debug("[TRANSCEIVE] ErrorReg cleared (0x00) after successful operation")

        # After transceive completes, set CommandReg back to idle
        self.registers[0x01] = 0x00  # Idle command
        self.log.debug("[TRANSCEIVE] Command completed, CommandReg set to idle (0x00)")

    def _simulate_card_response(self, command: List[int]) -> Optional[List[int]]:
        """Simulate JavaCard responses to NFC commands"""
        if not command:
            self.log.warning("[CARD] Empty command received")
            return None

        cmd_str = self._format_bytes(command)

        if len(command) == 1 and command[0] == 0x26:
            # REQA command - return ATQA
            response = [0x08, 0x00]
            self.log.info(f"[CARD] REQA command ({cmd_str}) → ATQA ({self._format_bytes(response)})")
            return response

        elif len(command) == 2 and command == [0x93, 0x20]:
            # Anti-collision CL1 - return UID + BCC
            response = self.card_uid + [0x22]  # UID + BCC from log
            self.log.info(f"[CARD] Anti-collision CL1 ({cmd_str}) → UID+BCC ({self._format_bytes(response)})")
            return response

        elif len(command) >= 7 and command[0:2] == [0x93, 0x70]:
            # SELECT CL1 - verify CRC and return SAK
            if len(command) == 9:
                # Command format: [0x93, 0x70, UID[4], BCC, CRC[2]]
                command_data = command[0:7]  # Command + UID + BCC
                received_crc = command[7:9]   # Received CRC
                expected_crc = self._calculate_iso14443a_crc(command_data)

                uid_in_cmd = self._format_bytes(command[2:6])
                crc_str = self._format_bytes(received_crc)
                expected_crc_str = self._format_bytes(expected_crc)

                if received_crc == expected_crc:
                    self.log.info(f"[CARD] SELECT CL1 UID={uid_in_cmd} CRC={crc_str} ✓ ({cmd_str}) → SAK")
                    response = [0x20, 0xFC, 0x70]  # SAK + CRC from log
                    self.card_selected = True
                    return response
                else:
                    self.log.error(f"[CARD] SELECT CL1 CRC mismatch: received {crc_str}, expected {expected_crc_str}")
                    return None  # CRC error - no response
            else:
                # Invalid command length
                self.log.error(f"[CARD] SELECT CL1 invalid length: {len(command)} bytes, expected 9")
                return None

        elif len(command) == 4 and command[0:2] == [0xE0, 0x40]:
            # RATS command - validate CRC first
            command_data = command[0:2]  # [0xE0, 0x80]
            received_crc = command[2:4]   # Received CRC
            expected_crc = self._calculate_iso14443a_crc(command_data)

            crc_str = self._format_bytes(received_crc)
            expected_crc_str = self._format_bytes(expected_crc)

            if received_crc == expected_crc:
                self.log.info(f"[CARD] RATS CRC valid {crc_str} ✓ ({cmd_str}) → ATS ({self._format_bytes(self.card_ats)}) [{len(self.card_ats)} bytes]")
                response = self.card_ats
                return response
            else:
                self.log.error(f"[CARD] RATS CRC mismatch: received {crc_str}, expected {expected_crc_str}")
                return None  # CRC error - no response

        elif len(command) == 4 and command[0] == 0xF2:  # WTX S-block acknowledgment
            # WTX acknowledgment from host - send pending I-block response
            command_data = command[0:-2]  # S-block data (all but last 2 CRC bytes)
            received_crc = command[-2:]   # Last 2 bytes are CRC
            expected_crc = self._calculate_iso14443a_crc(command_data)

            crc_str = self._format_bytes(received_crc)
            expected_crc_str = self._format_bytes(expected_crc)

            if received_crc == expected_crc:
                wtxm = command[1]  # WTX multiplier
                self.log.info(f"[WTX] Received WTX acknowledgment: WTXM={wtxm}")

                if self._pending_wtx_response is not None:
                    # Send the pending I-block response
                    pending = self._pending_wtx_response
                    if pending['response_data']:
                        response_bytes = [pending['pcb']] + pending['response_data'] + [pending['sw1'], pending['sw2']]
                    else:
                        response_bytes = [pending['pcb'], pending['sw1'], pending['sw2']]

                    response_crc = self._calculate_iso14443a_crc(response_bytes)
                    complete_response = response_bytes + response_crc

                    self.log.info(f"[WTX] Sending pending I-block response: SW={pending['sw1']:02X}{pending['sw2']:02X} Data({len(pending['response_data'])})")

                    # Clear pending response
                    self._pending_wtx_response = None

                    return complete_response
                else:
                    self.log.error("[WTX] No pending response for WTX acknowledgment")
                    return None
            else:
                self.log.error(f"[WTX] S-block CRC mismatch: received {crc_str}, expected {expected_crc_str}")
                return None  # CRC error - no response

        elif len(command) >= 5 and command[0] in [0x02, 0x03]:  # I-block (PCB = 0x02 or 0x03)
            # I-block APDU - validate CRC and parse command
            command_data = command[0:-2]  # PCB + APDU (all but last 2 CRC bytes)
            received_crc = command[-2:]   # Last 2 bytes are CRC
            expected_crc = self._calculate_iso14443a_crc(command_data)

            crc_str = self._format_bytes(received_crc)
            expected_crc_str = self._format_bytes(expected_crc)

            if received_crc == expected_crc:
                # Extract APDU from I-block (skip PCB byte)
                apdu = command_data[1:]  # Skip PCB, extract APDU
                if len(apdu) >= 4:
                    cla, ins, p1, p2 = apdu[0], apdu[1], apdu[2], apdu[3]

                    # Check if this is SELECT by AID command: 00 A4 04 00 06
                    if (cla == 0x00 and ins == 0xA4 and p1 == 0x04 and p2 == 0x00 and
                        len(apdu) >= 11 and apdu[4] == 0x06):  # Lc = 6
                        aid = list(apdu[5:11])
                        # Check applet registry for requested AID
                        aid_bytes = bytes(aid)
                        aid_str = self._format_bytes(aid)

                        if aid_bytes in self.registered_applets:
                            # Deselect current applet if any
                            if self.selected_applet is not None:
                                self.selected_applet.on_deselect()

                            # Select new applet
                            applet = self.registered_applets[aid_bytes]
                            sw1, sw2 = applet.on_select()
                            self.selected_applet = applet

                            # Build response with status words
                            response_data = [0x02, sw1, sw2]  # PCB + SW1 + SW2
                            response_crc = self._calculate_iso14443a_crc(response_data)
                            response = response_data + response_crc
                            self.log.info(f"[CARD] SELECT applet AID={aid_str} CRC={crc_str} ✓ → SUCCESS SW={sw1:02X}{sw2:02X}")
                            return response
                        else:
                            # Applet not found - return SW=6A82 (File not found)
                            response_data = [0x02, 0x6A, 0x82]  # PCB + SW1 + SW2
                            response_crc = self._calculate_iso14443a_crc(response_data)
                            response = response_data + response_crc
                            available_aids = [self._format_bytes(list(aid_key)) for aid_key in self.registered_applets.keys()]
                            self.log.info(f"[CARD] SELECT applet AID={aid_str} → NOT FOUND SW=6A82 (available: {', '.join(available_aids)})")
                            return response
                    else:
                        # Not a SELECT command - route to selected applet if available
                        if self.selected_applet is not None:
                            return self._handle_applet_apdu(apdu, command[0])  # Pass APDU and PCB
                        else:
                            # No applet selected - return SW=6E00 (Class not supported)
                            response_data = [0x02, 0x6E, 0x00]  # PCB + SW1 + SW2
                            response_crc = self._calculate_iso14443a_crc(response_data)
                            response = response_data + response_crc
                            apdu_str = self._format_bytes(apdu)
                            self.log.info(f"[CARD] I-block APDU={apdu_str} → No applet selected SW=6E00")
                            return response
                else:
                    # Invalid APDU length
                    response_data = [0x02, 0x67, 0x00]  # PCB + SW=6700 (Wrong length)
                    response_crc = self._calculate_iso14443a_crc(response_data)
                    response = response_data + response_crc
                    self.log.error(f"[CARD] I-block APDU too short: {len(apdu)} bytes → SW=6700")
                    return response
            else:
                self.log.error(f"[CARD] I-block CRC mismatch: received {crc_str}, expected {expected_crc_str}")
                return None  # CRC error - no response

        else:
            self.log.error(f"[CARD] UNKNOWN/UNSUPPORTED command: {cmd_str} ({len(command)} bytes)")
            return None

    def _handle_applet_apdu(self, apdu: List[int], pcb: int) -> Optional[List[int]]:
        """Route APDU to selected applet and handle response"""
        if self.selected_applet is None:
            self.log.error("[APPLET] No applet selected for APDU processing")
            return None

        # Parse APDU components
        apdu_str = self._format_bytes(apdu)
        if len(apdu) < 4:
            self.log.error(f"[APPLET] APDU too short: {apdu_str} ({len(apdu)} bytes)")
            response_data = [pcb, 0x67, 0x00]  # PCB + SW=6700 (Wrong length)
            response_crc = self._calculate_iso14443a_crc(response_data)
            return response_data + response_crc

        cla, ins, p1, p2 = apdu[0], apdu[1], apdu[2], apdu[3]

        # Extract data and Le based on APDU case
        data = None
        le = None

        if len(apdu) == 4:  # Case 1: no data, no response expected
            pass
        elif len(apdu) == 5:  # Case 2: no data, response expected (Le)
            le = apdu[4] if apdu[4] != 0 else 256
        elif len(apdu) >= 5:  # Case 3/4: with data
            lc = apdu[4]
            if len(apdu) >= 5 + lc:
                data = apdu[5:5+lc]
                if len(apdu) == 5 + lc + 1:  # Case 4: data + Le
                    le = apdu[5+lc] if apdu[5+lc] != 0 else 256

        self.log.debug(f"[APPLET] Processing APDU: CLA={cla:02X} INS={ins:02X} P1={p1:02X} P2={p2:02X} Lc={len(data) if data else 0} Le={le}")

        # Route to applet - special handling for AUTH command (INS=0x11) with WTX support
        try:
            if ins == 0x11:  # AUTH command - special handling for WTX
                response_data, sw1, sw2, needs_wtx = self.selected_applet._handle_auth(data, le)
            else:
                response_data, sw1, sw2 = self.selected_applet.process_apdu(cla, ins, p1, p2, data, le)
                needs_wtx = False  # Other commands don't need WTX
        except Exception as e:
            self.log.error(f"[APPLET] Exception processing APDU {apdu_str}: {e}")
            response_data, sw1, sw2 = [], 0x6F, 0x00  # Unknown error
            needs_wtx = False

        # Handle WTX protocol for AUTH command
        if needs_wtx and ins == 0x11:
            return self._handle_wtx_protocol(apdu, pcb, response_data, sw1, sw2)

        # Build normal I-block response
        if response_data:
            response_bytes = [pcb] + response_data + [sw1, sw2]
        else:
            response_bytes = [pcb, sw1, sw2]

        response_crc = self._calculate_iso14443a_crc(response_bytes)
        complete_response = response_bytes + response_crc

        self.log.info(f"[APPLET] APDU {apdu_str} → SW={sw1:02X}{sw2:02X} Data({len(response_data)}) Total({len(complete_response)})")
        return complete_response

    def _handle_wtx_protocol(self, apdu: List[int], pcb: int, response_data: List[int], sw1: int, sw2: int) -> Optional[List[int]]:
        """
        Handle WTX (Waiting Time Extension) protocol for AUTH command

        WTX Protocol Flow (based on encrypted.log):
        1. Send WTX S-block: F2 01 [CRC] (WTXM=1)
        2. Wait for WTX acknowledgment: F2 01 [CRC] (echo)
        3. Send final I-block response: [PCB] [response_data] [SW1] [SW2] [CRC]

        Returns the WTX S-block to be sent first. The actual I-block will be sent later.
        """
        apdu_str = self._format_bytes(apdu)

        # Create WTX S-block: PCB=0xF2, WTXM=1
        wtx_s_block = [0xF2, 0x01]
        wtx_crc = self._calculate_iso14443a_crc(wtx_s_block)
        wtx_complete = wtx_s_block + wtx_crc

        self.log.info(f"[WTX] AUTH command {apdu_str} → Sending WTX S-block: WTXM=1")

        # Store the final response for later (this is a simulation)
        # In a real implementation, this would be handled asynchronously
        self._pending_wtx_response = {
            'pcb': pcb,
            'response_data': response_data,
            'sw1': sw1,
            'sw2': sw2
        }

        return wtx_complete

    def _execute_soft_reset(self):
        """Execute soft reset command"""
        self.log.info("[RESET] Starting soft reset - immediately setting registers to post-reset state")

        # For testbench simplicity, immediately set the expected post-reset state
        # The hardware will wait 50ms anyway, so this eliminates race conditions
        self._init_registers()
        self._flush_fifo()
        # Reset card state
        self.card_selected = False
        # Deselect any selected applet
        if self.selected_applet is not None:
            self.selected_applet.on_deselect()
            self.selected_applet = None

        # Set CommandReg to idle state immediately (what hardware expects after reset)
        self.registers[0x01] = 0x20  # Idle state after reset
        self.log.info("[RESET] Soft reset completed immediately - CommandReg=0x20, all registers reinitialized")

    async def _transaction(self, frame_start, frame_end):
        """
        cocotbext-spi transaction implementation

        This method is called by the SpiSlaveBase framework for each SPI transaction.
        """
        if not USE_COCOTBEXT_SPI:
            return

        await frame_start
        self.idle.clear()

        byte_count = 0
        current_address = None
        is_read = False

        try:
            while True:
                # Shift in/out one byte
                if byte_count == 0:
                    # First byte is address/command
                    rx_byte = int(await self._shift(8, tx_word=0xFF))  # Send 0xFF during address
                    current_address = rx_byte & 0x3F  # Lower 6 bits
                    is_read = (rx_byte & 0x80) != 0   # MSB indicates read/write
                    self.log.debug(f"SPI {'READ' if is_read else 'WRITE'} addr=0x{current_address:02X}")
                else:
                    # Subsequent bytes are data
                    if is_read:
                        # Read operation - send register data
                        if current_address == 0x12:  # FIFODataReg
                            tx_data = self._read_fifo_byte()
                        else:
                            tx_data = self.registers.get(current_address, 0x00)
                        rx_byte = int(await self._shift(8, tx_word=tx_data))
                    else:
                        # Write operation - receive data
                        rx_byte = int(await self._shift(8, tx_word=0xFF))
                        self._write_register(current_address, rx_byte)

                byte_count += 1

        except Exception as e:
            self.log.debug(f"Transaction ended: {e}")

        await frame_end

    def get_selected_applet(self):
        """Get the currently selected applet instance"""
        return self.selected_applet

# ============================================================================
# Helper Functions - CRC Reference Implementation
# ============================================================================


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val, 0)
    except ValueError:
        return default


def decode_instruction(instruction_value: int) -> Tuple[int, int, int]:
    opcode = (instruction_value >> 12) & 0x3F
    arg1 = (instruction_value >> 6) & 0x3F
    arg2 = instruction_value & 0x3F
    return opcode, arg1, arg2


def read_ram_byte(dut, address: int) -> int:
    assert 0 <= address < 64, f"RAM address {address} out of range (0-63)"
    return int(dut.ram_data[address].value)


def write_ram_byte(dut, address: int, value: int) -> None:
    assert 0 <= address < 64, f"RAM address {address} out of range (0-63)"
    assert 0 <= value <= 0xFF, f"Value {value} out of range (0-255)"
    dut.ram_data[address].value = value


def read_ram_bytes(dut, start_address: int, count: int) -> List[int]:
    return [read_ram_byte(dut, start_address + i) for i in range(count)]

def dump_ram(dut, log: logging.Logger) -> None:
    values = [read_ram_byte(dut, i) for i in range(64)]
    for base in range(0, 64, 16):
        chunk = values[base:base + 16]
        hex_bytes = " ".join(f"{value:02X}" for value in chunk)
        log.info("RAM[%02d..%02d]: %s", base, base + 15, hex_bytes)


def load_rom_hex_into_dut(dut, rom_path: str) -> None:
    lines = []
    with open(rom_path, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#") or line.startswith("//"):
                continue
            lines.append(line.split()[0])

    for i in range(1024):
        value = 0
        if i < len(lines):
            value = int(lines[i], 16)
        dut.rom_inst.memory[i].value = value


def log_cpu_state(dut, log: logging.Logger, prefix: str = "") -> None:
    pc = int(dut.pc.value)
    state = int(dut.state.value)
    state_name = STATE_NAMES.get(state, f"STATE_{state}")

    try:
        opcode = int(dut.opcode.value)
        arg1 = int(dut.arg1.value)
        arg2 = int(dut.arg2.value)
        opcode_name = OPCODE_NAMES.get(opcode, f"OP{opcode}")
        instr_str = f"{opcode_name} a1={arg1} a2={arg2}"
    except Exception:
        instr_str = "N/A"

    log.info("%sPC=%d State=%s Instr=%s", prefix, pc, state_name, instr_str)


async def reset_dut(dut) -> None:
    dut.uart_clk_in.value = 0
    dut.mode.value = 0
    dut.uart_rxd.value = 1
    dut.spi_miso.value = 0

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def instruction_trace(dut, log: logging.Logger) -> None:
    last_pc = None
    trace_ram = _env_bool("TRACE_RAM", False)

    while True:
        await RisingEdge(dut.clk)
        state = int(dut.state.value)
        if state != EXECUTE:
            continue

        pc = int(dut.pc.value)
        if pc == last_pc:
            continue
        last_pc = pc

        opcode = int(dut.opcode.value)
        arg1 = int(dut.arg1.value)
        arg2 = int(dut.arg2.value)
        opcode_name = OPCODE_NAMES.get(opcode, f"OP{opcode}")
        ram_base = int(dut.ram_base_register.value)
        repeat_cnt = int(dut.repeat_cnt.value)
        repeat_pcn = int(dut.repeat_pcn.value)

        if trace_ram:
            ram1 = read_ram_byte(dut, arg1)
            ram2 = read_ram_byte(dut, arg2)
            log.info("PC=%d %s a1=%d(0x%02X) a2=%d(0x%02X)", pc, opcode_name, arg1, ram1, arg2, ram2)
        else:
            log.info("PC=%d %s a1=%d a2=%d ram_base=%d repeat_cnt=%d repeat_pcn=%d", pc, opcode_name, arg1, arg2, ram_base, repeat_cnt, repeat_pcn)



@cocotb.test()
async def test_main_controller_app(dut):
    """
    Application development testbench.

    This test loads a ROM program from `rtl/rom.mem` by default and runs the CPU
    for a bounded number of cycles with optional instruction tracing.
    """
    log = logging.getLogger("cocotb.app_tb")
    log.setLevel(logging.INFO)

    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())

    # Attach SPI EEPROM model
    spi_eeprom = SpiEeprom25010B(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_0,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso,
    )

    # Attach RC522 model (JavaCard emulation)
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_1,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso,
    )

    # Allow RC522Model coroutine to start before reset
    for _ in range(4):
        await RisingEdge(dut.clk)

    rom_path = os.getenv("ROM_PATH")
    if rom_path:
        log.info("Loading ROM from %s", rom_path)
        load_rom_hex_into_dut(dut, rom_path)
    else:
        log.info("Using default ROM from rtl/rom.mem")

    await reset_dut(dut)

    if _env_bool("INSTR_TRACE", False):
        cocotb.start_soon(instruction_trace(dut, log))

    max_cycles = _env_int("MAX_CYCLES", 200000)
    stop_pc = _env_int("STOP_PC", -1)
    #stop_on_unlock = _env_bool("STOP_ON_UNLOCK", True)
    #stop_on_hard_fault = _env_bool("STOP_ON_HARD_FAULT", True)

    for cycle in range(max_cycles):
        await RisingEdge(dut.clk)
        '''
        if stop_on_hard_fault and int(dut.hard_fault.value):
            log_cpu_state(dut, log, prefix="HARD_FAULT: ")
            raise AssertionError("hard_fault asserted")

        if stop_on_unlock and int(dut.unlock.value):
            log.info("Unlock asserted at cycle %d", cycle)
            break
        '''
        if stop_pc >= 0 and int(dut.pc.value) == stop_pc:
            log.info("PC reached stop value %d at cycle %d", stop_pc, cycle)
            break

    log.info("Finished after %d cycles", max_cycles)
    log_cpu_state(dut, log, prefix="Final: ")
    dump_ram(dut, log)
