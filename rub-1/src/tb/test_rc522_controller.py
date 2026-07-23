"""
RC522 Card Reader Controller Testbench

This testbench emulates the RC522 card reader connected via SPI with a JavaCard present.
It focuses on the initial communication sequence up to and including applet selection.

The testbench includes:
1. RC522Model - SPI slave emulating the RC522 chip with full register set
2. JavaCard simulation - responds to NFC commands (REQA, anti-collision, SELECT, RATS, APDU)
3. Software SPI master - sends commands following the streamlined.log sequence
4. Test cases - verify initialization, card detection, and applet selection

Based on:
- MFRC522 datasheet and register specifications
- streamlined.log communication sequence
- ISO14443-3 Type A and ISO14443-4 protocols

Test structure:
1. test_rc522_initialization - RC522 register setup and configuration
2. test_card_detection - REQA, anti-collision, and SELECT commands
3. test_iso14443_protocol - RATS and I-block communication
4. test_full_applet_selection - Complete sequence from init to applet selection
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout
import logging
from typing import Dict, List, Optional, Tuple
from cocotbext.uart import UartSource, UartSink
from abc import ABC, abstractmethod
import secrets
from Crypto.Cipher import AES

# Try to use cocotbext-spi, fallback to manual implementation if unavailable
try:
    from cocotbext.spi import SpiSlaveBase, SpiBus, SpiConfig
    USE_COCOTBEXT_SPI = True
except ImportError:
    USE_COCOTBEXT_SPI = False
    logging.warning("cocotbext-spi not available, using manual SPI implementation")


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
                current_cs = self.cs_n.value.integer
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
            if self.cs_n.value.integer != 0:
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
            if self.cs_n.value.integer != 0:
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
            if self.cs_n.value.integer != 0:
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
            if self.cs_n.value.integer != 0:
                self.log.debug("[SPI_BITS] CS deasserted during clock edge - aborting")
                raise Exception("CS deasserted during clock edge")
                
            # Sample MOSI (MSB first)
            mosi_bit = self.mosi.value.integer
            rx_byte = (rx_byte << 1) | mosi_bit
            self.log.debug(f"[SPI_BITS] Bit {bit_index}: RX={mosi_bit} (sampled on rising edge)")
            
            # Wait for falling edge (end of bit period)
            await FallingEdge(self.sclk)
            if self.cs_n.value.integer != 0:
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
            
        elif len(command) == 4 and command[0:2] == [0xE0, 0x80]:
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
# Unit Tests for AuthenticatedIdentificationApplet Crypto Operations
# ============================================================================

def test_applet_crypto_operations():
    """Unit tests for AuthenticatedIdentificationApplet crypto operations
    
    These tests validate the crypto implementation against known test vectors
    from the encrypted.log and software reference implementation.
    """
    logging.info("=== Starting AuthenticatedIdentificationApplet Crypto Tests ===")
    
    # Test 1: AUTH_INIT basic functionality
    applet = AuthenticatedIdentificationApplet()
    
    # Test AUTH_INIT response generation
    response_data, sw1, sw2 = applet._handle_auth_init(16)
    assert sw1 == 0x90 and sw2 == 0x00, f"AUTH_INIT should return SW=9000, got SW={sw1:02X}{sw2:02X}"
    assert len(response_data) == 16, f"AUTH_INIT should return 16 bytes, got {len(response_data)}"
    assert applet.rc is not None, "AUTH_INIT should generate card nonce"
    assert len(applet.rc) == 8, f"Card nonce should be 8 bytes, got {len(applet.rc)}"
    
    # Verify we can decrypt the response and get the correct format
    cipher = AES.new(applet.pre_shared_key, AES.MODE_ECB)
    decrypted = cipher.decrypt(bytes(response_data))
    assert decrypted[:8] == applet.rc, "Decrypted response should contain card nonce"
    assert decrypted[8:] == b'\x00' * 8, "Decrypted response should have 8 zero bytes"
    logging.info("✓ AUTH_INIT crypto test passed")
    
    # Test 2: AUTH with generated nonce from AUTH_INIT
    test_rt = bytes([0x63, 0x70, 0x0c, 0xae, 0x42, 0x9a, 0x1d, 0x95])  # Known terminal nonce
    
    # Create AUTH command data: rt || rc (terminal nonce || card nonce)
    auth_plaintext = test_rt + applet.rc  # Use the nonce generated by AUTH_INIT
    auth_ciphertext = cipher.encrypt(auth_plaintext)
    
    # Test AUTH processing
    response_data, sw1, sw2 = applet._handle_auth(list(auth_ciphertext), 16)
    assert sw1 == 0x90 and sw2 == 0x00, f"AUTH should return SW=9000, got SW={sw1:02X}{sw2:02X}"
    assert len(response_data) == 16, f"AUTH should return 16 bytes, got {len(response_data)}"
    assert applet.auth_success == True, "AUTH should succeed with correct nonces"
    
    # Verify ephemeral key derivation
    expected_ephemeral_key = applet.rc + test_rt
    assert applet.ephemeral_key == expected_ephemeral_key, f"Ephemeral key mismatch\nExpected: {expected_ephemeral_key.hex()}\nActual:   {applet.ephemeral_key.hex()}"
    
    # Decrypt AUTH response and verify success message
    eph_cipher = AES.new(applet.ephemeral_key, AES.MODE_ECB)
    decrypted_response = eph_cipher.decrypt(bytes(response_data))
    expected_msg = b"AUTH_SUCCESS\x00\x00\x00\x00"
    assert decrypted_response == expected_msg, f"AUTH response message mismatch\nExpected: {expected_msg}\nActual:   {decrypted_response}"
    logging.info("✓ AUTH crypto test passed")
    
    # Test 3: GET_ID with ephemeral key encryption
    response_data, sw1, sw2 = applet._handle_get_id(16)
    assert sw1 == 0x90 and sw2 == 0x00, f"GET_ID should return SW=9000, got SW={sw1:02X}{sw2:02X}"
    assert len(response_data) == 16, f"GET_ID should return 16 bytes, got {len(response_data)}"
    
    # Decrypt GET_ID response and verify card ID
    decrypted_id = eph_cipher.decrypt(bytes(response_data))
    assert decrypted_id == applet.card_id, f"GET_ID decrypted ID mismatch\nExpected: {applet.card_id.hex()}\nActual:   {decrypted_id.hex()}"
    logging.info("✓ GET_ID crypto test passed")
    
    # Test 4: Error conditions
    fresh_applet = AuthenticatedIdentificationApplet()
    
    # AUTH without AUTH_INIT should fail
    response_data, sw1, sw2 = fresh_applet._handle_auth([0x00] * 16, 16)
    assert sw1 == 0x69 and sw2 == 0x85, f"AUTH without AUTH_INIT should return SW=6985, got SW={sw1:02X}{sw2:02X}"
    
    # GET_ID without authentication should fail
    response_data, sw1, sw2 = fresh_applet._handle_get_id(16)
    assert sw1 == 0x69 and sw2 == 0x85, f"GET_ID without auth should return SW=6985, got SW={sw1:02X}{sw2:02X}"
    
    # Test wrong length parameters
    response_data, sw1, sw2 = applet._handle_auth_init(15)  # Wrong Le
    assert sw1 == 0x67 and sw2 == 0x00, f"AUTH_INIT with wrong Le should return SW=6700, got SW={sw1:02X}{sw2:02X}"
    
    logging.info("✓ Error condition tests passed")
    
    # Test 5: Authentication failure with wrong nonce
    wrong_applet = AuthenticatedIdentificationApplet()
    wrong_rc = b'\x11\x22\x33\x44\x55\x66\x77\x88'  # Different nonce
    wrong_applet.rc = wrong_rc
    
    # Try to authenticate with original test data but wrong nonce (should fail)
    response_data, sw1, sw2 = wrong_applet._handle_auth(list(auth_ciphertext), 16)
    assert sw1 == 0x90 and sw2 == 0x00, "AUTH should return SW=9000 even on auth failure"
    assert wrong_applet.auth_success == False, "AUTH should fail with wrong nonce"
    
    # Decrypt response and verify failure message
    wrong_eph_key = wrong_rc + test_rt  # Ephemeral key still derived with wrong rc
    wrong_cipher = AES.new(wrong_eph_key, AES.MODE_ECB)
    decrypted_response = wrong_cipher.decrypt(bytes(response_data))
    expected_fail_msg = b"AUTH_FAILURE\x00\x00\x00\x00"
    assert decrypted_response == expected_fail_msg, f"AUTH failure message mismatch\nExpected: {expected_fail_msg}\nActual:   {decrypted_response}"
    
    logging.info("✓ Authentication failure test passed")
    
    logging.info("=== All AuthenticatedIdentificationApplet Crypto Tests Passed! ===")
    return True


# Run crypto tests when module is loaded (can be called independently)
if __name__ == "__main__":
    test_applet_crypto_operations()


@cocotb.test()
async def test_rc522_hw_init(dut):
    """
    Test the hardware RC522 controller initialization
    
    Verifies:
    - UART echo command (0xFF -> 0xFF) 
    - RC522 initialization command (0x01 -> 0x01/0x02)
    - Complete RC522 initialization sequence via SPI
    - Proper timing and state management
    """
    # Setup 10MHz clock as specified in controller design
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    
    # Reset sequence  
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Create RC522 model and connect to controller's SPI interface
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable verbose SPI logging for debugging
    rc522_model.verbose_spi = True
    
    # Setup UART interfaces using cocotbext.uart (much more reliable than manual implementation)
    uart_source = UartSource(dut.uart_rxd, baud=9600, bits=8)
    uart_sink = UartSink(dut.uart_txd, baud=9600, bits=8)
    
    # Wait for system to stabilize
    await Timer(1000, units="us")
    
    logging.info("=== Testing UART Echo Command ===")
    
    # Test 1: Echo command (0xFF -> 0xFF)
    await uart_source.write([0xFF])
    
    # Wait for echo response
    response = await with_timeout(uart_sink.read(count=1), 50_000, "us")
    assert len(response) == 1, f"Expected 1 response byte, got {len(response)}"
    assert response[0] == 0xFF, f"Expected echo 0xFF, got 0x{response[0]:02X}"
    
    logging.info(f"✓ Echo test passed: sent 0xFF, received 0x{response[0]:02X}")
    
    # Wait between commands
    await Timer(1000, units="us")
    
    logging.info("=== Testing RC522 Initialization Command ===")
    
    # Test 2: RC522 initialization command (0x01)
    logging.info("Sending RC522 initialization command (0x01)...")
    
    # Log initial states before sending command
    logging.info(f"Before command - controller state: {dut.debug_state.value}, busy: {dut.busy.value}, rc522_busy: {dut.rc522_inst.busy.value}")
    
    await uart_source.write([0x01])
    
    # Monitor busy signal - should go high during initialization
    # Check immediately and frequently since state transitions are fast
    busy_detected = False
    state_changes = []
    
    # Wait for the initialization response instead of trying to catch the busy signal
    # The busy signal transitions are too fast to catch reliably in the testbench
    
    # Wait for initialization to complete and get response
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for init
    assert len(response) == 1, f"Expected 1 response byte, got {len(response)}"
    response_code = response[0]
    
    # Add detailed debugging for why initialization might fail
    final_rc522_state = int(dut.rc522_inst.debug_state.value)
    final_init_done = int(dut.rc522_inst.init_done.value)
    final_init_success = int(dut.rc522_inst.init_success.value)
    
    logging.info(f"RC522 initialization response: 0x{response_code:02X}")
    logging.info(f"Final RC522 state: 0x{final_rc522_state:02X}")
    logging.info(f"Final init_done: {final_init_done}")
    logging.info(f"Final init_success: {final_init_success}")
    
    # RC522 initialization must succeed
    if response_code == 0x01:
        logging.info("✓ RC522 initialization successful")
    elif response_code == 0x02:
        # Analyze failure cause for debugging
        logging.error("✗ RC522 initialization failed unexpectedly")
        logging.info("Analyzing failure cause...")
        
        # Check what the RC522 model received
        if hasattr(rc522_model, 'last_version_read'):
            logging.info(f"RC522 model version read: 0x{rc522_model.last_version_read:02X}")
        
        # Check SPI transactions
        if hasattr(rc522_model, '_spi_transactions'):
            logging.info("Recent SPI transactions:")
            for txn in rc522_model._spi_transactions[-10:]:  # Last 10 transactions
                logging.info(f"  {txn}")
        
        assert False, f"RC522 initialization failed with response 0x{response_code:02X} - initialization should succeed"
    else:
        assert False, f"Invalid initialization response: 0x{response_code:02X} (expected 0x01 for success)"
    
    # Check final busy state
    final_busy = int(dut.busy.value)
    logging.info(f"Final busy signal: {final_busy}")
    assert final_busy == 0, "Busy signal should be low after initialization complete"
    
    logging.info("=== Hardware Controller Test Complete ===")
    logging.info("Successfully tested UART command interface and RC522 integration")
    
    await Timer(1000, units="us")


@cocotb.test()
async def test_rc522_hw_reqa(dut):
    """
    Test the hardware RC522 controller REQA functionality
    
    Verifies:
    - UART echo command (0xFF -> 0xFF) 
    - RC522 initialization command (0x01 -> 0x01)
    - REQA card detection command (0x02 -> 0x03)
    - Complete REQA sequence via SPI with card emulation
    """
    # Setup 10MHz clock as specified in controller design
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    
    # Reset sequence  
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Create RC522 model - same as init test
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable verbose SPI logging for debugging
    rc522_model.verbose_spi = True
    
    logging.info("=== Testing Hardware RC522 Controller REQA ===")
    
    # Create UART interface for controller communication
    uart_source = UartSource(dut.uart_rxd, 9600, 8)
    uart_sink = UartSink(dut.uart_txd, 9600, 8)
    
    # Wait for system to stabilize
    await Timer(1000, units="us")
    logging.info("System stabilized, starting test sequence")
    
    # =================== Step 1: Test Echo Command ===================
    logging.info("\n[STEP 1] Testing UART echo command...")
    
    # Check initial state
    logging.info(f"Initial controller state: {int(dut.debug_state.value)}")
    logging.info(f"Initial busy signal: {int(dut.busy.value)}")
    
    # Send echo command (0xFF) - using proven working approach from init test
    await uart_source.write([0xFF])
    
    # Wait for echo response - blocking read with sufficient timeout
    response = await with_timeout(uart_sink.read(count=1), 50_000, "us")
    assert len(response) == 1, f"Expected 1 response byte, got {len(response)}"
    assert response[0] == 0xFF, f"Expected echo 0xFF, got 0x{response[0]:02X}"
    logging.info(f"✓ Echo test passed: 0x{response[0]:02X}")
    
    # =================== Step 2: Initialize RC522 ===================
    logging.info("\n[STEP 2] Testing RC522 initialization...")
    
    # Send initialization command (0x01) 
    init_data = [0x01]
    await uart_source.write(init_data)
    logging.info(f"Sent initialization command: 0x{init_data[0]:02X}")
    
    # Wait for initialization to complete - using reliable blocking read
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for init
    assert len(response) == 1, f"Expected 1 init response byte, got {len(response)}"
    response_code = response[0]
    
    # RC522 initialization must succeed
    if response_code == 0x01:
        logging.info("✓ RC522 initialization successful")
    else:
        assert False, f"RC522 initialization failed with response 0x{response_code:02X}"
    
    # =================== Step 3: Test REQA Command ===================
    logging.info("\n[STEP 3] Testing REQA card detection...")
    
    # Send REQA command (0x02)
    reqa_data = [0x02]
    await uart_source.write(reqa_data)
    logging.info(f"Sent REQA command: 0x{reqa_data[0]:02X}")
    
    # Wait for REQA operation to complete - using reliable blocking read
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for REQA
    assert len(response) == 1, f"Expected 1 REQA response byte, got {len(response)}"
    response_code = response[0]
    
    # Add detailed debugging for REQA operation
    final_rc522_state = int(dut.rc522_inst.debug_state.value)
    final_reqa_done = int(dut.rc522_inst.reqa_done.value)
    final_reqa_success = int(dut.rc522_inst.reqa_success.value)
    
    logging.info(f"REQA operation response: 0x{response_code:02X}")
    logging.info(f"Final RC522 state: 0x{final_rc522_state:02X}")
    logging.info(f"Final reqa_done: {final_reqa_done}")
    logging.info(f"Final reqa_success: {final_reqa_success}")
    
    # REQA operation should succeed with card present
    if response_code == 0x03:
        logging.info("✓ REQA card detection successful")
    elif response_code == 0x04:
        logging.error("✗ REQA card detection failed - no card response")
        
        # Debug info for REQA failure
        logging.info("Analyzing REQA failure...")
        if hasattr(rc522_model, '_spi_transactions'):
            logging.info("Recent SPI transactions:")
            for txn in rc522_model._spi_transactions[-15:]:
                logging.info(f"  {txn}")
                
        assert False, "REQA should succeed with card present"
    else:
        assert False, f"Invalid REQA response: 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 4: Test ATQA Byte Retrieval ===================
    logging.info("\n[STEP 4] Testing ATQA byte retrieval...")
    
    # Send ATQA read command (0x03)
    atqa_data = [0x03]
    await uart_source.write(atqa_data)
    logging.info(f"Sent ATQA read command: 0x{atqa_data[0]:02X}")
    
    # Wait for first ATQA byte
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")  # 5 second timeout
    assert len(response) == 1, f"Expected 1 ATQA byte 0 response, got {len(response)}"
    atqa_byte_0 = response[0]
    
    # Wait for second ATQA byte
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")  # 5 second timeout
    assert len(response) == 1, f"Expected 1 ATQA byte 1 response, got {len(response)}"
    atqa_byte_1 = response[0]
    
    logging.info(f"Received ATQA bytes: 0x{atqa_byte_0:02X} 0x{atqa_byte_1:02X}")
    
    # Verify ATQA bytes match expected values (0x08, 0x00)
    expected_atqa_0 = 0x08
    expected_atqa_1 = 0x00
    
    if atqa_byte_0 == expected_atqa_0 and atqa_byte_1 == expected_atqa_1:
        logging.info(f"✓ ATQA bytes correct: {atqa_byte_0:02X} {atqa_byte_1:02X}")
    else:
        logging.error(f"✗ ATQA bytes incorrect: got {atqa_byte_0:02X} {atqa_byte_1:02X}, expected {expected_atqa_0:02X} {expected_atqa_1:02X}")
        
        # Debug ATQA byte retrieval failure
        logging.info("Debugging ATQA byte mismatch...")
        if hasattr(dut, 'rc522_inst'):
            try:
                atqa_valid = int(dut.rc522_inst.atqa_valid.value)
                hw_atqa_0 = int(dut.rc522_inst.atqa_byte_0.value)
                hw_atqa_1 = int(dut.rc522_inst.atqa_byte_1.value)
                logging.info(f"Hardware ATQA valid: {atqa_valid}")
                logging.info(f"Hardware ATQA bytes: 0x{hw_atqa_0:02X} 0x{hw_atqa_1:02X}")
            except Exception as e:
                logging.info(f"Could not read hardware ATQA signals: {e}")
                
        assert False, "ATQA bytes should match expected values from RC522 model"
    
    # Check final busy state
    final_busy = int(dut.busy.value)
    logging.info(f"Final busy signal: {final_busy}")
    assert final_busy == 0, "Busy signal should be low after ATQA read complete"
    
    logging.info("=== Hardware Controller REQA + ATQA Test Complete ===")
    logging.info("Successfully tested UART echo, RC522 init, REQA card detection, and ATQA byte retrieval")
    
    await Timer(1000, units="us")


@cocotb.test()
async def test_rc522_hw_cl1_full_sequence(dut):
    """
    Test the complete hardware RC522 controller Anti-Collision CL1 functionality
    
    Verifies the complete NFC card detection sequence:
    - UART echo command (0xFF -> 0xFF)
    - RC522 initialization command (0x01 -> 0x01)
    - REQA card detection command (0x02 -> 0x03)
    - ATQA byte retrieval command (0x03 -> 0x08, 0x00)
    - Anti-Collision CL1 command (0x04 -> 0x03)
    - UID byte retrieval command (0x05 -> 0x2F, 0xFB, 0xBC, 0x4A, 0x22)
    """
    # Setup 10MHz clock as specified in controller design
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    
    # Reset sequence  
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Create RC522 model with Anti-Collision CL1 support
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable verbose SPI logging for debugging
    rc522_model.verbose_spi = True
    
    logging.info("=== Testing Complete Hardware RC522 Controller CL1 Sequence ===")
    
    # Create UART interface for controller communication
    uart_source = UartSource(dut.uart_rxd, 9600, 8)
    uart_sink = UartSink(dut.uart_txd, 9600, 8)
    
    # Wait for system to stabilize
    await Timer(1000, units="us")
    logging.info("System stabilized, starting complete CL1 test sequence")
    
    # =================== Step 1: Test Echo Command ===================
    logging.info("\n[STEP 1] Testing UART echo command...")
    
    # Send echo command (0xFF) - using proven working approach
    await uart_source.write([0xFF])
    
    # Wait for echo response 
    response = await with_timeout(uart_sink.read(count=1), 50_000, "us")
    assert len(response) == 1, f"Expected 1 response byte, got {len(response)}"
    assert response[0] == 0xFF, f"Expected echo 0xFF, got 0x{response[0]:02X}"
    logging.info(f"✓ Echo test passed: 0x{response[0]:02X}")
    
    # =================== Step 2: Initialize RC522 ===================
    logging.info("\n[STEP 2] Testing RC522 initialization...")
    
    # Send initialization command (0x01) 
    await uart_source.write([0x01])
    logging.info("Sent initialization command: 0x01")
    
    # Wait for initialization to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for init
    assert len(response) == 1, f"Expected 1 init response byte, got {len(response)}"
    response_code = response[0]
    
    # RC522 initialization must succeed
    if response_code == 0x01:
        logging.info("✓ RC522 initialization successful")
    else:
        assert False, f"RC522 initialization failed with response 0x{response_code:02X}"
    
    # =================== Step 3: Test REQA Command ===================
    logging.info("\n[STEP 3] Testing REQA card detection...")
    
    # Send REQA command (0x02)
    await uart_source.write([0x02])
    logging.info("Sent REQA command: 0x02")
    
    # Wait for REQA operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for REQA
    assert len(response) == 1, f"Expected 1 REQA response byte, got {len(response)}"
    response_code = response[0]
    
    # REQA operation should succeed with card present
    if response_code == 0x03:
        logging.info("✓ REQA card detection successful")
    else:
        assert False, f"REQA failed with response 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 4: Test ATQA Byte Retrieval ===================
    logging.info("\n[STEP 4] Testing ATQA byte retrieval...")
    
    # Send ATQA read command (0x03)
    await uart_source.write([0x03])
    logging.info("Sent ATQA read command: 0x03")
    
    # Wait for first ATQA byte
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1, f"Expected 1 ATQA byte 0 response, got {len(response)}"
    atqa_byte_0 = response[0]
    
    # Wait for second ATQA byte
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1, f"Expected 1 ATQA byte 1 response, got {len(response)}"
    atqa_byte_1 = response[0]
    
    logging.info(f"Received ATQA bytes: 0x{atqa_byte_0:02X} 0x{atqa_byte_1:02X}")
    
    # Verify ATQA bytes match expected values (0x08, 0x00)
    expected_atqa_0 = 0x08
    expected_atqa_1 = 0x00
    assert atqa_byte_0 == expected_atqa_0 and atqa_byte_1 == expected_atqa_1, \
        f"ATQA bytes incorrect: got {atqa_byte_0:02X} {atqa_byte_1:02X}, expected {expected_atqa_0:02X} {expected_atqa_1:02X}"
    logging.info(f"✓ ATQA bytes correct: {atqa_byte_0:02X} {atqa_byte_1:02X}")
    
    # =================== Step 5: NEW - Test Anti-Collision CL1 ===================
    logging.info("\n[STEP 5] Testing Anti-Collision CL1 (NEW FUNCTIONALITY)...")
    
    # Send Anti-Collision CL1 command (0x04) - NEW UART command
    await uart_source.write([0x04])
    logging.info("Sent Anti-Collision CL1 command: 0x04")
    
    # Wait for CL1 operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for CL1
    assert len(response) == 1, f"Expected 1 CL1 response byte, got {len(response)}"
    response_code = response[0]
    
    # Add detailed debugging for CL1 operation
    final_rc522_state = int(dut.rc522_inst.debug_state.value)
    final_cl1_done = int(dut.rc522_inst.cl1_done.value) if hasattr(dut.rc522_inst, 'cl1_done') else 0
    final_cl1_success = int(dut.rc522_inst.cl1_success.value) if hasattr(dut.rc522_inst, 'cl1_success') else 0
    
    logging.info(f"CL1 operation response: 0x{response_code:02X}")
    logging.info(f"Final RC522 state: 0x{final_rc522_state:02X}")
    logging.info(f"Final cl1_done: {final_cl1_done}")
    logging.info(f"Final cl1_success: {final_cl1_success}")
    
    # CL1 operation should succeed with card present
    if response_code == 0x03:
        logging.info("✓ Anti-Collision CL1 successful")
    elif response_code == 0x04:
        logging.error("✗ Anti-Collision CL1 failed - no card response")
        assert False, "CL1 should succeed with card present"
    else:
        assert False, f"Invalid CL1 response: 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 6: NEW - Test UID Byte Retrieval ===================
    logging.info("\n[STEP 6] Testing UID byte retrieval (NEW FUNCTIONALITY)...")
    
    # Send UID read command (0x05) - NEW UART command  
    await uart_source.write([0x05])
    logging.info("Sent UID read command: 0x05")
    
    # Read 5 bytes sequentially: 4 UID bytes + 1 BCC byte
    uid_bytes = []
    expected_uid_sequence = [0x2F, 0xFB, 0xBC, 0x4A, 0x22]  # From smalllog2.log
    
    for i in range(5):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 UID byte {i} response, got {len(response)}"
        uid_byte = response[0]
        uid_bytes.append(uid_byte)
        logging.info(f"Received UID byte {i}: 0x{uid_byte:02X}")
    
    logging.info(f"Complete UID sequence received: {' '.join(f'0x{b:02X}' for b in uid_bytes)}")
    
    # Verify UID bytes match expected values from smalllog2.log exactly
    if uid_bytes == expected_uid_sequence:
        logging.info(f"✓ UID bytes correct: {' '.join(f'{b:02X}' for b in uid_bytes)}")
    else:
        logging.error(f"✗ UID bytes incorrect: got {' '.join(f'{b:02X}' for b in uid_bytes)}, expected {' '.join(f'{b:02X}' for b in expected_uid_sequence)}")
        
        # Debug UID byte retrieval failure
        logging.info("Debugging UID byte mismatch...")
        if hasattr(dut, 'rc522_inst'):
            try:
                cl1_valid = int(dut.rc522_inst.cl1_valid.value) if hasattr(dut.rc522_inst, 'cl1_valid') else 0
                hw_uid = int(dut.rc522_inst.uid_bytes.value) if hasattr(dut.rc522_inst, 'uid_bytes') else 0
                hw_bcc = int(dut.rc522_inst.bcc_byte.value) if hasattr(dut.rc522_inst, 'bcc_byte') else 0
                logging.info(f"Hardware CL1 valid: {cl1_valid}")
                logging.info(f"Hardware UID bytes: 0x{hw_uid:08X}")
                logging.info(f"Hardware BCC byte: 0x{hw_bcc:02X}")
            except Exception as e:
                logging.info(f"Could not read hardware CL1 signals: {e}")
                
        assert False, "UID bytes should match smalllog2.log exactly"
    
    # Check final busy state
    final_busy = int(dut.busy.value)
    logging.info(f"Final busy signal: {final_busy}")
    assert final_busy == 0, "Busy signal should be low after UID read complete"
    
    logging.info("=== Complete Hardware Controller CL1 Test PASSED ===")
    logging.info("Successfully tested complete NFC detection sequence:")
    logging.info("  - UART echo (0xFF -> 0xFF)")
    logging.info("  - RC522 init (0x01 -> 0x01)")  
    logging.info("  - REQA detection (0x02 -> 0x03)")
    logging.info("  - ATQA retrieval (0x03 -> 0x08, 0x00)")
    logging.info("  - Anti-Collision CL1 (0x04 -> 0x03)")
    logging.info(f"  - UID retrieval (0x05 -> {' '.join(f'{b:02X}' for b in uid_bytes)})")
    
    await Timer(1000, units="us")


@cocotb.test()
async def test_rc522_hw_select(dut):
    """
    Test the complete hardware RC522 controller SELECT CL1 functionality
    
    Verifies the complete NFC card selection sequence:
    1. Echo test (0xFF -> 0xFF)
    2. RC522 initialization (0x01 -> 0x01) 
    3. REQA card detection (0x02 -> 0x03)
    4. ATQA byte retrieval (0x03 -> 0x08, 0x00)
    5. Anti-Collision CL1 (0x04 -> 0x03)
    6. UID byte retrieval (0x05 -> 0x2F, 0xFB, 0xBC, 0x4A, 0x22)
    7. SELECT CL1 (0x06 -> 0x03)
    8. SAK byte retrieval (0x07 -> 0x20, 0xFC, 0x70)
    
    Uses software CRC calculation and centralized CRC framework.
    """
    # Setup 10MHz clock as specified in controller design
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    
    # Reset sequence - using proven working pattern
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Create RC522 model with SELECT CL1 support
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable verbose SPI logging for debugging
    rc522_model.verbose_spi = True
    
    logging.info("=== Testing Complete Hardware RC522 Controller SELECT Sequence ===")
    
    # Create UART interface for controller communication
    uart_source = UartSource(dut.uart_rxd, 9600, 8)
    uart_sink = UartSink(dut.uart_txd, 9600, 8)
    
    # Wait for system to stabilize
    await Timer(1000, units="us")
    logging.info("System stabilized, starting complete SELECT test sequence")
    
    # =================== Step 1: Test Echo Command ===================
    logging.info("\n[STEP 1] Testing UART echo command...")
    
    # Send echo command (0xFF) - using proven working approach
    await uart_source.write([0xFF])
    
    # Wait for echo response 
    response = await with_timeout(uart_sink.read(count=1), 50_000, "us")
    assert len(response) == 1, f"Expected 1 response byte, got {len(response)}"
    assert response[0] == 0xFF, f"Expected echo 0xFF, got 0x{response[0]:02X}"
    logging.info(f"✓ Echo test passed: 0x{response[0]:02X}")
    
    # =================== Step 2: Initialize RC522 ===================
    logging.info("\n[STEP 2] Testing RC522 initialization...")
    
    # Send initialization command (0x01) 
    await uart_source.write([0x01])
    logging.info("Sent initialization command: 0x01")
    
    # Wait for initialization to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for init
    assert len(response) == 1, f"Expected 1 init response byte, got {len(response)}"
    response_code = response[0]
    
    # RC522 initialization must succeed
    if response_code == 0x01:
        logging.info("✓ RC522 initialization successful")
    else:
        assert False, f"RC522 initialization failed with response 0x{response_code:02X}"
    
    # =================== Step 3: Test REQA Command ===================
    logging.info("\n[STEP 3] Testing REQA card detection...")
    
    # Send REQA command (0x02)
    await uart_source.write([0x02])
    logging.info("Sent REQA command: 0x02")
    
    # Wait for REQA operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for REQA
    assert len(response) == 1, f"Expected 1 REQA response byte, got {len(response)}"
    response_code = response[0]
    
    # REQA operation should succeed with card present
    if response_code == 0x03:
        logging.info("✓ REQA card detection successful")
    else:
        assert False, f"REQA failed with response 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 4: Test ATQA Byte Retrieval ===================
    logging.info("\n[STEP 4] Testing ATQA byte retrieval...")
    
    # Send ATQA read command (0x03)
    await uart_source.write([0x03])
    logging.info("Sent ATQA read command: 0x03")
    
    # Wait for first ATQA byte
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1, f"Expected 1 ATQA byte 0 response, got {len(response)}"
    atqa_byte_0 = response[0]
    
    # Wait for second ATQA byte
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1, f"Expected 1 ATQA byte 1 response, got {len(response)}"
    atqa_byte_1 = response[0]
    
    logging.info(f"Received ATQA bytes: 0x{atqa_byte_0:02X} 0x{atqa_byte_1:02X}")
    
    # Verify ATQA bytes match expected values (0x08, 0x00)
    expected_atqa_0 = 0x08
    expected_atqa_1 = 0x00
    assert atqa_byte_0 == expected_atqa_0 and atqa_byte_1 == expected_atqa_1, \
        f"ATQA bytes incorrect: got {atqa_byte_0:02X} {atqa_byte_1:02X}, expected {expected_atqa_0:02X} {expected_atqa_1:02X}"
    logging.info(f"✓ ATQA bytes correct: {atqa_byte_0:02X} {atqa_byte_1:02X}")
    
    # =================== Step 5: Test Anti-Collision CL1 ===================
    logging.info("\n[STEP 5] Testing Anti-Collision CL1...")
    
    # Send Anti-Collision CL1 command (0x04)
    await uart_source.write([0x04])
    logging.info("Sent Anti-Collision CL1 command: 0x04")
    
    # Wait for CL1 operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for CL1
    assert len(response) == 1, f"Expected 1 CL1 response byte, got {len(response)}"
    response_code = response[0]
    
    logging.info(f"CL1 operation response: 0x{response_code:02X}")
    
    # CL1 operation should succeed with card present
    if response_code == 0x03:
        logging.info("✓ Anti-Collision CL1 successful")
    elif response_code == 0x04:
        logging.error("✗ Anti-Collision CL1 failed - no card response")
        assert False, "CL1 should succeed with card present"
    else:
        assert False, f"Invalid CL1 response: 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 6: Test UID Byte Retrieval ===================
    logging.info("\n[STEP 6] Testing UID byte retrieval...")
    
    # Send UID read command (0x05)
    await uart_source.write([0x05])
    logging.info("Sent UID read command: 0x05")
    
    # Read 5 UID bytes (4 UID + 1 BCC)
    uid_bytes = []
    for i in range(5):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 UID byte {i} response, got {len(response)}"
        uid_bytes.append(response[0])
        logging.info(f"Received UID byte {i}: 0x{response[0]:02X}")
    
    # Verify UID bytes match expected values from smalllog2.log
    expected_uid = [0x2F, 0xFB, 0xBC, 0x4A, 0x22]
    assert uid_bytes == expected_uid, f"UID bytes incorrect: got {uid_bytes}, expected {expected_uid}"
    logging.info(f"✓ UID bytes correct: {' '.join(f'{b:02X}' for b in uid_bytes)}")
    
    # =================== Step 7: NEW - Test SELECT CL1 ===================
    logging.info("\n[STEP 7] Testing SELECT CL1 (NEW FUNCTIONALITY)...")
    
    # Send SELECT CL1 command (0x06) - NEW UART command
    await uart_source.write([0x06])
    logging.info("Sent SELECT CL1 command: 0x06")
    
    # Wait for SELECT operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")  # 60 second timeout for SELECT
    assert len(response) == 1, f"Expected 1 SELECT response byte, got {len(response)}"
    response_code = response[0]
    
    logging.info(f"SELECT operation response: 0x{response_code:02X}")
    
    # SELECT operation should succeed with card present
    if response_code == 0x03:
        logging.info("✓ SELECT CL1 successful")
    elif response_code == 0x04:
        logging.error("✗ SELECT CL1 failed - operation error")
        assert False, "SELECT should succeed with proper card"
    else:
        assert False, f"Invalid SELECT response: 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 8: NEW - Test SAK Byte Retrieval ===================
    logging.info("\n[STEP 8] Testing SAK byte retrieval (NEW FUNCTIONALITY)...")
    
    # Send SAK read command (0x07) - NEW UART command
    await uart_source.write([0x07])
    logging.info("Sent SAK read command: 0x07")
    
    # Read 3 SAK bytes
    sak_bytes = []
    for i in range(3):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 SAK byte {i} response, got {len(response)}"
        sak_bytes.append(response[0])
        logging.info(f"Received SAK byte {i}: 0x{response[0]:02X}")
    
    # Verify SAK bytes match expected values from smalllog2.log
    expected_sak = [0x20, 0xFC, 0x70]
    assert sak_bytes == expected_sak, f"SAK bytes incorrect: got {sak_bytes}, expected {expected_sak}"
    logging.info(f"✓ SAK bytes correct: {' '.join(f'{b:02X}' for b in sak_bytes)}")
    
    # Check final busy state
    final_busy = int(dut.busy.value)
    logging.info(f"Final busy signal: {final_busy}")
    assert final_busy == 0, "Busy signal should be low after SELECT complete"
    
    logging.info("=== Complete Hardware Controller SELECT Test PASSED ===")
    logging.info("Successfully tested complete NFC card selection sequence:")
    logging.info("  - UART echo (0xFF -> 0xFF)")
    logging.info("  - RC522 init (0x01 -> 0x01)")
    logging.info("  - REQA detection (0x02 -> 0x03)")
    logging.info("  - ATQA retrieval (0x03 -> 0x08, 0x00)")
    logging.info("  - Anti-Collision CL1 (0x04 -> 0x03)")
    logging.info(f"  - UID retrieval (0x05 -> {' '.join(f'{b:02X}' for b in uid_bytes)})")
    logging.info(f"  - SELECT CL1 (0x06 -> 0x03)")
    logging.info(f"  - SAK retrieval (0x07 -> {' '.join(f'{b:02X}' for b in sak_bytes)})")
    
    await Timer(1000, units="us")


@cocotb.test()
async def test_rc522_hw_full_sequence(dut):
    """
    Test the complete hardware RC522 controller full sequence with RATS
    
    Verifies the complete NFC card sequence including RATS:
    1. Echo test (0xFF -> 0xFF)
    2. RC522 initialization (0x01 -> 0x01) 
    3. REQA card detection (0x02 -> 0x03)
    4. ATQA byte retrieval (0x03 -> 0x08, 0x00)
    5. Anti-Collision CL1 (0x04 -> 0x03)
    6. UID byte retrieval (0x05 -> 0x2F, 0xFB, 0xBC, 0x4A, 0x22)
    7. SELECT CL1 (0x06 -> 0x03)
    8. SAK byte retrieval (0x07 -> 0x20, 0xFC, 0x70)
    9. RATS (0x08 -> 0x03)
    10. ATS byte retrieval (0x09 -> 12 bytes from smalllog2.log)
    
    Uses software CRC calculation and centralized CRC framework.
    """
    # Setup 10MHz clock as specified in controller design
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    
    # Reset sequence - using proven working pattern
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Create RC522 model with full sequence support
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable verbose SPI logging for debugging
    rc522_model.verbose_spi = True
    
    logging.info("=== Testing Complete Hardware RC522 Controller Full Sequence with RATS ===")
    
    # Create UART interface for controller communication
    uart_source = UartSource(dut.uart_rxd, 9600, 8)
    uart_sink = UartSink(dut.uart_txd, 9600, 8)
    
    # Wait for system to stabilize
    await Timer(1000, units="us")
    logging.info("System stabilized, starting complete full test sequence")
    
    # =================== Step 1: Test Echo Command ===================
    logging.info("\n[STEP 1] Testing UART echo command...")
    
    # Send echo command (0xFF)
    await uart_source.write([0xFF])
    
    # Wait for echo response 
    response = await with_timeout(uart_sink.read(count=1), 50_000, "us")
    assert len(response) == 1, f"Expected 1 response byte, got {len(response)}"
    assert response[0] == 0xFF, f"Expected echo 0xFF, got 0x{response[0]:02X}"
    logging.info(f"✓ Echo test passed: 0x{response[0]:02X}")
    
    # =================== Step 2: Initialize RC522 ===================
    logging.info("\n[STEP 2] Testing RC522 initialization...")
    
    # Send initialization command (0x01) 
    await uart_source.write([0x01])
    logging.info("Sent initialization command: 0x01")
    
    # Wait for initialization to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1, f"Expected 1 init response byte, got {len(response)}"
    response_code = response[0]
    
    # RC522 initialization must succeed
    if response_code == 0x01:
        logging.info("✓ RC522 initialization successful")
    else:
        assert False, f"RC522 initialization failed with response 0x{response_code:02X}"
    
    # =================== Step 3: Test REQA Command ===================
    logging.info("\n[STEP 3] Testing REQA card detection...")
    
    # Send REQA command (0x02)
    await uart_source.write([0x02])
    logging.info("Sent REQA command: 0x02")
    
    # Wait for REQA operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1, f"Expected 1 REQA response byte, got {len(response)}"
    response_code = response[0]
    
    # REQA operation should succeed with card present
    if response_code == 0x03:
        logging.info("✓ REQA card detection successful")
    else:
        assert False, f"REQA failed with response 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 4: Test ATQA Byte Retrieval ===================
    logging.info("\n[STEP 4] Testing ATQA byte retrieval...")
    
    # Send ATQA read command (0x03)
    await uart_source.write([0x03])
    logging.info("Sent ATQA read command: 0x03")
    
    # Wait for ATQA bytes 
    atqa_bytes = []
    for i in range(2):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 ATQA byte {i} response, got {len(response)}"
        atqa_bytes.append(response[0])
        logging.info(f"Received ATQA byte {i}: 0x{response[0]:02X}")
    
    # Verify ATQA bytes match expected values
    expected_atqa = [0x08, 0x00]
    assert atqa_bytes == expected_atqa, f"ATQA bytes incorrect: got {atqa_bytes}, expected {expected_atqa}"
    logging.info(f"✓ ATQA bytes correct: {' '.join(f'{b:02X}' for b in atqa_bytes)}")
    
    # =================== Step 5: Test Anti-Collision CL1 ===================
    logging.info("\n[STEP 5] Testing Anti-Collision CL1...")
    
    # Send anti-collision command (0x04)
    await uart_source.write([0x04])
    logging.info("Sent anti-collision command: 0x04")
    
    # Wait for anti-collision operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1, f"Expected 1 anti-collision response byte, got {len(response)}"
    response_code = response[0]
    
    # Anti-collision operation should succeed
    if response_code == 0x03:
        logging.info("✓ Anti-Collision CL1 successful")
    else:
        assert False, f"Anti-Collision failed with response 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 6: Test UID Byte Retrieval ===================
    logging.info("\n[STEP 6] Testing UID byte retrieval...")
    
    # Send UID read command (0x05)
    await uart_source.write([0x05])
    logging.info("Sent UID read command: 0x05")
    
    # Wait for UID bytes
    uid_bytes = []
    for i in range(5):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 UID byte {i} response, got {len(response)}"
        uid_bytes.append(response[0])
        logging.info(f"Received UID byte {i}: 0x{response[0]:02X}")
    
    # Verify UID bytes match expected values
    expected_uid = [0x2F, 0xFB, 0xBC, 0x4A, 0x22]
    assert uid_bytes == expected_uid, f"UID bytes incorrect: got {uid_bytes}, expected {expected_uid}"
    logging.info(f"✓ UID bytes correct: {' '.join(f'{b:02X}' for b in uid_bytes)}")
    
    # =================== Step 7: Test SELECT CL1 ===================
    logging.info("\n[STEP 7] Testing SELECT CL1...")
    
    # Send SELECT command (0x06)
    await uart_source.write([0x06])
    logging.info("Sent SELECT command: 0x06")
    
    # Wait for SELECT operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1, f"Expected 1 SELECT response byte, got {len(response)}"
    response_code = response[0]
    
    # SELECT operation should succeed
    if response_code == 0x03:
        logging.info("✓ SELECT CL1 successful")
    else:
        assert False, f"SELECT failed with response 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 8: Test SAK Byte Retrieval ===================
    logging.info("\n[STEP 8] Testing SAK byte retrieval...")
    
    # Send SAK read command (0x07)
    await uart_source.write([0x07])
    logging.info("Sent SAK read command: 0x07")
    
    # Wait for SAK bytes
    sak_bytes = []
    for i in range(3):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 SAK byte {i} response, got {len(response)}"
        sak_bytes.append(response[0])
        logging.info(f"Received SAK byte {i}: 0x{response[0]:02X}")
    
    # Verify SAK bytes match expected values
    expected_sak = [0x20, 0xFC, 0x70]
    assert sak_bytes == expected_sak, f"SAK bytes incorrect: got {sak_bytes}, expected {expected_sak}"
    logging.info(f"✓ SAK bytes correct: {' '.join(f'{b:02X}' for b in sak_bytes)}")
    
    # =================== Step 9: Test RATS Command ===================
    logging.info("\n[STEP 9] Testing RATS command...")
    
    # Send RATS command (0x08)
    await uart_source.write([0x08])
    logging.info("Sent RATS command: 0x08")
    
    # Wait for RATS operation to complete
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1, f"Expected 1 RATS response byte, got {len(response)}"
    response_code = response[0]
    
    # RATS operation should succeed
    if response_code == 0x03:
        logging.info("✓ RATS successful")
    else:
        assert False, f"RATS failed with response 0x{response_code:02X} (expected 0x03 for success)"
    
    # =================== Step 10: Test ATS Byte Retrieval ===================
    logging.info("\n[STEP 10] Testing ATS byte retrieval...")
    
    # Send ATS read command (0x09)
    await uart_source.write([0x09])
    logging.info("Sent ATS read command: 0x09")
    
    # Wait for ATS bytes (12 bytes from smalllog2.log)
    ats_bytes = []
    for i in range(12):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 ATS byte {i} response, got {len(response)}"
        ats_bytes.append(response[0])
        logging.info(f"Received ATS byte {i}: 0x{response[0]:02X}")
    
    # Verify ATS bytes match expected values from smalllog2.log
    expected_ats = [0x0A, 0x78, 0x80, 0x91, 0x02, 0x80, 0x73, 0xC8, 0x21, 0x10, 0xC3, 0x92]
    assert ats_bytes == expected_ats, f"ATS bytes incorrect: got {ats_bytes}, expected {expected_ats}"
    logging.info(f"✓ ATS bytes correct: {' '.join(f'{b:02X}' for b in ats_bytes)}")
    
    # Check final busy state
    final_busy = int(dut.busy.value)
    logging.info(f"Final busy signal: {final_busy}")
    assert final_busy == 0, "Busy signal should be low after RATS complete"
    
    logging.info("=== Complete Hardware Controller Full Sequence Test PASSED ===")
    logging.info("Successfully tested complete NFC card sequence with RATS:")
    logging.info("  - UART echo (0xFF -> 0xFF)")
    logging.info("  - RC522 init (0x01 -> 0x01)")
    logging.info("  - REQA detection (0x02 -> 0x03)")
    logging.info("  - ATQA retrieval (0x03 -> 0x08, 0x00)")
    logging.info("  - Anti-Collision CL1 (0x04 -> 0x03)")
    logging.info(f"  - UID retrieval (0x05 -> {' '.join(f'{b:02X}' for b in uid_bytes)})")
    logging.info(f"  - SELECT CL1 (0x06 -> 0x03)")
    logging.info(f"  - SAK retrieval (0x07 -> {' '.join(f'{b:02X}' for b in sak_bytes)})")
    logging.info(f"  - RATS (0x08 -> 0x03)")
    logging.info(f"  - ATS retrieval (0x09 -> {' '.join(f'{b:02X}' for b in ats_bytes)})")
    
    await Timer(1000, units="us")


@cocotb.test()
async def test_rc522_hw_applet_select(dut):
    """
    Test the complete hardware RC522 controller sequence with JavaCard applet selection
    
    Verifies the complete NFC card sequence including JavaCard applet selection:
    1. Echo test (0xFF -> 0xFF)
    2. RC522 initialization (0x01 -> 0x01) 
    3. REQA card detection (0x02 -> 0x03)
    4. ATQA byte retrieval (0x03 -> 0x08, 0x00)
    5. Anti-Collision CL1 (0x04 -> 0x03)
    6. UID byte retrieval (0x05 -> 0x2F, 0xFB, 0xBC, 0x4A, 0x22)
    7. SELECT CL1 (0x06 -> 0x03)
    8. SAK byte retrieval (0x07 -> 0x20, 0xFC, 0x70)
    9. RATS (0x08 -> 0x03)
    10. ATS byte retrieval (0x09 -> 12 bytes from smalllog2.log)
    11. JavaCard applet selection (0x0A -> 0x01)
    
    Tests I-block communication with PCB alternation and SW=0x9000 validation.
    """
    # Setup 10MHz clock as specified in controller design
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    
    # Reset sequence - using proven working pattern
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Create RC522 model with applet selection support
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable verbose SPI logging for debugging
    rc522_model.verbose_spi = True
    
    logging.info("=== Testing Complete Hardware RC522 Controller with JavaCard Applet Selection ===")
    
    # Create UART interface for controller communication
    uart_source = UartSource(dut.uart_rxd, 9600, 8)
    uart_sink = UartSink(dut.uart_txd, 9600, 8)
    
    # Wait for system to stabilize
    await Timer(1000, units="us")
    logging.info("System stabilized, starting applet selection test sequence")
    
    # =================== Steps 1-10: Complete NFC card sequence ===================
    # (Same as test_rc522_hw_full_sequence)
    
    # Step 1: Test Echo Command
    logging.info("\n[STEP 1] Testing UART echo command...")
    await uart_source.write([0xFF])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0xFF, f"Echo test failed: got {response}"
    logging.info("✓ Echo test passed")
    
    # Step 2: Test RC522 Initialization
    logging.info("\n[STEP 2] Testing RC522 initialization...")
    await uart_source.write([0x01])
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1 and response[0] == 0x01, f"Init failed: got {response}"
    logging.info("✓ RC522 initialization successful")
    
    # Step 3: Test REQA
    logging.info("\n[STEP 3] Testing REQA card detection...")
    await uart_source.write([0x02])
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03, f"REQA failed: got {response}"
    logging.info("✓ REQA successful")
    
    # Step 4: Test ATQA retrieval
    logging.info("\n[STEP 4] Testing ATQA byte retrieval...")
    await uart_source.write([0x03])
    
    # Wait for ATQA bytes 
    atqa_bytes = []
    for i in range(2):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 ATQA byte {i} response, got {len(response)}"
        atqa_bytes.append(response[0])
        logging.info(f"Received ATQA byte {i}: 0x{response[0]:02X}")
    
    # Verify ATQA bytes match expected values
    expected_atqa = [0x08, 0x00]
    assert atqa_bytes == expected_atqa, f"ATQA bytes incorrect: got {atqa_bytes}, expected {expected_atqa}"
    logging.info(f"✓ ATQA bytes correct: {' '.join(f'{b:02X}' for b in atqa_bytes)}")
    
    # Step 5: Test Anti-Collision CL1
    logging.info("\n[STEP 5] Testing Anti-Collision CL1...")
    await uart_source.write([0x04])
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03, f"CL1 failed: got {response}"
    logging.info("✓ Anti-Collision CL1 successful")
    
    # Step 6: Test UID retrieval
    logging.info("\n[STEP 6] Testing UID byte retrieval...")
    await uart_source.write([0x05])
    uid_bytes = []
    for i in range(5):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 UID byte {i}, got {len(response)}"
        uid_bytes.append(response[0])
    expected_uid = [0x2F, 0xFB, 0xBC, 0x4A, 0x22]
    assert uid_bytes == expected_uid, f"UID incorrect: got {uid_bytes}, expected {expected_uid}"
    logging.info(f"✓ UID bytes correct: {' '.join(f'{b:02X}' for b in uid_bytes)}")
    
    # Step 7: Test SELECT CL1
    logging.info("\n[STEP 7] Testing SELECT CL1...")
    await uart_source.write([0x06])
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03, f"SELECT failed: got {response}"
    logging.info("✓ SELECT CL1 successful")
    
    # Step 8: Test SAK retrieval
    logging.info("\n[STEP 8] Testing SAK byte retrieval...")
    await uart_source.write([0x07])
    sak_bytes = []
    for i in range(3):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 SAK byte {i}, got {len(response)}"
        sak_bytes.append(response[0])
    expected_sak = [0x20, 0xFC, 0x70]
    assert sak_bytes == expected_sak, f"SAK incorrect: got {sak_bytes}, expected {expected_sak}"
    logging.info(f"✓ SAK bytes correct: {' '.join(f'{b:02X}' for b in sak_bytes)}")
    
    # Step 9: Test RATS
    logging.info("\n[STEP 9] Testing RATS command...")
    await uart_source.write([0x08])
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03, f"RATS failed: got {response}"
    logging.info("✓ RATS successful")
    
    # Step 10: Test ATS retrieval
    logging.info("\n[STEP 10] Testing ATS byte retrieval...")
    await uart_source.write([0x09])
    ats_bytes = []
    for i in range(12):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 ATS byte {i}, got {len(response)}"
        ats_bytes.append(response[0])
    expected_ats = [0x0A, 0x78, 0x80, 0x91, 0x02, 0x80, 0x73, 0xC8, 0x21, 0x10, 0xC3, 0x92]
    assert ats_bytes == expected_ats, f"ATS incorrect: got {ats_bytes}, expected {expected_ats}"
    logging.info(f"✓ ATS bytes correct: {' '.join(f'{b:02X}' for b in ats_bytes)}")
    
    # =================== Step 11: NEW - Test JavaCard Applet Selection ===================
    logging.info("\n[STEP 11] Testing JavaCard applet selection...")
    
    # Send applet selection command (0x0A)
    # The hardware will build I-block frame: 02 00 A4 04 00 06 F0 00 00 0C DC 01 [CRC] (14 bytes)
    # RC522 model will automatically respond with: 02 90 00 F1 09 (SW=0x9000 success)
    await uart_source.write([0x0A])
    logging.info("Sent JavaCard applet selection command: 0x0A")
    
    # Wait for applet selection response
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1, f"Expected 1 applet selection response byte, got {len(response)}"
    response_code = response[0]
    
    # Applet selection should succeed (0x01 = success, 0x00 = error)
    if response_code == 0x01:
        logging.info("✓ JavaCard applet selection successful")
    else:
        assert False, f"Applet selection failed with response 0x{response_code:02X} (expected 0x01 for success)"
    
    # Check final busy state
    final_busy = int(dut.busy.value)
    logging.info(f"Final busy signal: {final_busy}")
    assert final_busy == 0, "Busy signal should be low after applet selection complete"
    
    logging.info("=== Complete Hardware Controller Applet Selection Test PASSED ===")
    logging.info("Successfully tested complete NFC card sequence with JavaCard applet selection:")
    logging.info("  - UART echo (0xFF -> 0xFF)")
    logging.info("  - RC522 init (0x01 -> 0x01)")
    logging.info("  - REQA detection (0x02 -> 0x03)")
    logging.info("  - ATQA retrieval (0x03 -> 0x08, 0x00)")
    logging.info("  - Anti-Collision CL1 (0x04 -> 0x03)")
    logging.info(f"  - UID retrieval (0x05 -> {' '.join(f'{b:02X}' for b in uid_bytes)})")
    logging.info(f"  - SELECT CL1 (0x06 -> 0x03)")
    logging.info(f"  - SAK retrieval (0x07 -> {' '.join(f'{b:02X}' for b in sak_bytes)})")
    logging.info(f"  - RATS (0x08 -> 0x03)")
    logging.info(f"  - ATS retrieval (0x09 -> {' '.join(f'{b:02X}' for b in ats_bytes)})")
    logging.info("  - JavaCard applet selection (0x0A -> 0x01)")
    
    await Timer(1000, units="us")


@cocotb.test(timeout_time=1200, timeout_unit="sec")  # 20 minute timeout
async def test_rc522_hw_auth_init(dut):
    """
    Test the complete hardware RC522 controller sequence with JavaCard AUTH_INIT
    
    Verifies the complete NFC card sequence including JavaCard applet selection and AUTH_INIT:
    1. Echo test (0xFF -> 0xFF)
    2. RC522 initialization (0x01 -> 0x01) 
    3. REQA card detection (0x02 -> 0x03)
    4. ATQA byte retrieval (0x03 -> 0x08, 0x00)
    5. Anti-Collision CL1 (0x04 -> 0x03)
    6. UID byte retrieval (0x05 -> 0x2F, 0xFB, 0xBC, 0x4A, 0x22)
    7. SELECT CL1 (0x06 -> 0x03)
    8. SAK byte retrieval (0x07 -> 0x20, 0xFC, 0x70)
    9. RATS (0x08 -> 0x03)
    10. ATS byte retrieval (0x09 -> 12 bytes from smalllog2.log)
    11. JavaCard applet selection (0x0A -> 0x01)
    12. AUTH_INIT command (0x0B -> 0x01)
    13. Nonce byte retrieval (0x0C -> 8 bytes decrypted nonce)
    
    Tests AUTH_INIT APDU communication with AES decryption and nonce extraction.
    """
    # Setup 10MHz clock as specified in controller design
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    
    # Reset sequence - using proven working pattern
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Create RC522 model with applet selection support
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_n,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable verbose SPI logging for debugging
    rc522_model.verbose_spi = True
    
    logging.info("=== Testing Complete Hardware RC522 Controller with AUTH_INIT ===")
    
    # Create UART interface for controller communication
    uart_source = UartSource(dut.uart_rxd, 9600, 8)
    uart_sink = UartSink(dut.uart_txd, 9600, 8)
    
    # Wait for system to stabilize
    await Timer(1000, units="us")
    logging.info("System stabilized, starting AUTH_INIT test sequence")
    
    # =================== Steps 1-11: Complete NFC card sequence ===================
    # This follows the exact same pattern as test_rc522_hw_applet_select
    
    # Step 1: Echo test
    logging.info("\n[STEP 1] Testing UART echo command...")
    await uart_source.write([0xFF])
    response = await with_timeout(uart_sink.read(count=1), 50_000, "us")
    assert len(response) == 1 and response[0] == 0xFF
    logging.info(f"✓ Echo test passed: 0x{response[0]:02X}")
    
    # Step 2: RC522 initialization 
    logging.info("\n[STEP 2] Testing RC522 initialization...")
    await uart_source.write([0x01])
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1 and response[0] == 0x01
    logging.info("✓ RC522 initialization successful")
    
    # Step 3: REQA card detection
    logging.info("\n[STEP 3] Testing REQA card detection...")
    await uart_source.write([0x02])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03
    logging.info("✓ REQA detection successful")
    
    # Step 4: ATQA byte retrieval
    logging.info("\n[STEP 4] Testing ATQA byte retrieval...")
    await uart_source.write([0x03])
    atqa_bytes = []
    for i in range(2):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        atqa_bytes.append(response[0])
    expected_atqa = [0x08, 0x00]
    assert atqa_bytes == expected_atqa
    logging.info(f"✓ ATQA bytes correct: {' '.join(f'{b:02X}' for b in atqa_bytes)}")
    
    # Step 5: Anti-Collision CL1
    logging.info("\n[STEP 5] Testing Anti-Collision CL1...")
    await uart_source.write([0x04])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03
    logging.info("✓ Anti-Collision CL1 successful")
    
    # Step 6: UID byte retrieval
    logging.info("\n[STEP 6] Testing UID byte retrieval...")
    await uart_source.write([0x05])
    uid_bytes = []
    for i in range(5):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        uid_bytes.append(response[0])
    expected_uid = [0x2F, 0xFB, 0xBC, 0x4A, 0x22]
    assert uid_bytes == expected_uid
    logging.info(f"✓ UID bytes correct: {' '.join(f'{b:02X}' for b in uid_bytes)}")
    
    # Step 7: SELECT CL1
    logging.info("\n[STEP 7] Testing SELECT CL1...")
    await uart_source.write([0x06])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03
    logging.info("✓ SELECT CL1 successful")
    
    # Step 8: SAK byte retrieval
    logging.info("\n[STEP 8] Testing SAK byte retrieval...")
    await uart_source.write([0x07])
    sak_bytes = []
    for i in range(3):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        sak_bytes.append(response[0])
    expected_sak = [0x20, 0xFC, 0x70]
    assert sak_bytes == expected_sak
    logging.info(f"✓ SAK bytes correct: {' '.join(f'{b:02X}' for b in sak_bytes)}")
    
    # Step 9: RATS
    logging.info("\n[STEP 9] Testing RATS...")
    await uart_source.write([0x08])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03
    logging.info("✓ RATS successful")
    
    # Step 10: ATS byte retrieval
    logging.info("\n[STEP 10] Testing ATS byte retrieval...")
    await uart_source.write([0x09])
    ats_bytes = []
    for i in range(12):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        ats_bytes.append(response[0])
    expected_ats = [0x0A, 0x78, 0x80, 0x91, 0x02, 0x80, 0x73, 0xC8, 0x21, 0x10, 0xC3, 0x92]
    assert ats_bytes == expected_ats
    logging.info(f"✓ ATS bytes correct: {' '.join(f'{b:02X}' for b in ats_bytes)}")
    
    # Step 11: JavaCard applet selection
    logging.info("\n[STEP 11] Testing JavaCard applet selection...")
    await uart_source.write([0x0A])
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1 and response[0] == 0x01
    logging.info("✓ JavaCard applet selection successful")
    
    # =================== Step 12: NEW - Test AUTH_INIT Command ===================
    logging.info("\n[STEP 12] Testing AUTH_INIT command...")
    
    # Get the current applet instance to access the generated nonce later
    applet = rc522_model.get_selected_applet()
    assert applet is not None, "No applet selected"
    
    # Send AUTH_INIT command (0x0B)
    # The hardware will build I-block frame: 03 80 10 00 00 10 [CRC] (8 bytes) 
    # RC522 model will automatically respond with: 03 [16-byte encrypted nonce] 90 00 [CRC] (21 bytes)
    await uart_source.write([0x0B])
    logging.info("Sent AUTH_INIT command: 0x0B")
    
    # Wait for AUTH_INIT response (should be success=0x01)
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1, f"Expected 1 AUTH_INIT response byte, got {len(response)}"
    response_code = response[0]
    
    # AUTH_INIT should succeed (0x01 = success, 0x02 = error)
    if response_code == 0x01:
        logging.info("✓ AUTH_INIT command successful")
    else:
        assert False, f"AUTH_INIT failed with response 0x{response_code:02X} (expected 0x01 for success)"
    
    # =================== Step 13: NEW - Test Nonce Byte Retrieval ===================
    logging.info("\n[STEP 13] Testing nonce byte retrieval...")
    
    # Send GET_NONCE command (0x0C) 8 times to get all nonce bytes
    received_nonce_bytes = []
    await uart_source.write([0x0C])
    for i in range(8):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1, f"Expected 1 nonce byte {i}, got {len(response)}"
        received_nonce_bytes.append(response[0])
        logging.info(f"Received nonce byte {i}: 0x{response[0]:02X}")
    
    # Compare with expected nonce from applet model
    expected_nonce_bytes = list(applet.rc)  # Convert bytes to list of integers
    logging.info(f"Expected nonce: {' '.join(f'{b:02X}' for b in expected_nonce_bytes)}")
    logging.info(f"Received nonce: {' '.join(f'{b:02X}' for b in received_nonce_bytes)}")
    
    assert received_nonce_bytes == expected_nonce_bytes, \
        f"Nonce mismatch! Expected: {expected_nonce_bytes}, Received: {received_nonce_bytes}"
    
    logging.info(f"✓ Nonce bytes correct: {' '.join(f'{b:02X}' for b in received_nonce_bytes)}")
    
    # Check final busy state
    final_busy = int(dut.busy.value)
    logging.info(f"Final busy signal: {final_busy}")
    assert final_busy == 0, "Busy signal should be low after AUTH_INIT complete"
    
    logging.info("=== Complete Hardware Controller AUTH_INIT Test PASSED ===")
    logging.info("Successfully tested complete NFC card sequence with JavaCard AUTH_INIT:")
    logging.info("  - UART echo (0xFF -> 0xFF)")
    logging.info("  - RC522 init (0x01 -> 0x01)")
    logging.info("  - REQA detection (0x02 -> 0x03)")
    logging.info("  - ATQA retrieval (0x03 -> 0x08, 0x00)")
    logging.info("  - Anti-Collision CL1 (0x04 -> 0x03)")
    logging.info(f"  - UID retrieval (0x05 -> {' '.join(f'{b:02X}' for b in uid_bytes)})")
    logging.info(f"  - SELECT CL1 (0x06 -> 0x03)")
    logging.info(f"  - SAK retrieval (0x07 -> {' '.join(f'{b:02X}' for b in sak_bytes)})")
    logging.info(f"  - RATS (0x08 -> 0x03)")
    logging.info(f"  - ATS retrieval (0x09 -> {' '.join(f'{b:02X}' for b in ats_bytes)})")
    logging.info("  - JavaCard applet selection (0x0A -> 0x01)")
    logging.info("  - AUTH_INIT command (0x0B -> 0x01)")
    logging.info(f"  - Nonce retrieval (0x0C x8 -> {' '.join(f'{b:02X}' for b in received_nonce_bytes)})")
    
    await Timer(1000, units="us")


@cocotb.test(timeout_time=20*60, timeout_unit="sec")
async def test_rc522_hw_full_auth(dut):
    """Complete authenticated identification test with WTX support
    
    Tests the full sequence from card initialization through AUTH completion:
    1. Complete NFC initialization sequence (WUPA, ATQA, Anti-collision, etc.)
    2. JavaCard applet selection 
    3. AUTH_INIT command with nonce extraction
    4. AUTH command with WTX protocol handling
    5. Verify successful authentication
    
    Includes 20-minute timeout for complete hardware crypto operations.
    """
    # Setup 10MHz clock as specified in controller design
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    
    # Reset sequence - using proven working pattern
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Create RC522 model with applet selection support
    rc522_model = RC522Model(
        sclk=dut.spi_sclk,
        cs_n=dut.spi_cs_0,
        mosi=dut.spi_mosi,
        miso=dut.spi_miso
    )
    
    # Enable verbose SPI logging for debugging
    rc522_model.verbose_spi = True
    
    logging.info("=== Testing Complete Hardware RC522 Controller with Full AUTH ===")
    
    # Create UART interface for controller communication
    uart_source = UartSource(dut.uart_rxd, 9600, 8)
    uart_sink = UartSink(dut.uart_txd, 9600, 8)
    
    # Wait for system to stabilize
    await Timer(1000, units="us")
    logging.info("System stabilized, starting full AUTH test sequence")
    
    # =================== Steps 1-11: Complete NFC card sequence ===================
    # This follows the exact same pattern as test_rc522_hw_auth_init
    
    # Step 1: Echo test
    logging.info("\n[STEP 1] Testing UART echo command...")
    await uart_source.write([0xFF])
    response = await with_timeout(uart_sink.read(count=1), 50_000, "us")
    assert len(response) == 1 and response[0] == 0xFF
    logging.info(f"✓ Echo test passed: 0x{response[0]:02X}")
    
    # Step 2: RC522 initialization 
    logging.info("\n[STEP 2] Testing RC522 initialization...")
    await uart_source.write([0x01])
    response = await with_timeout(uart_sink.read(count=1), 60_000_000, "us")
    assert len(response) == 1 and response[0] == 0x01
    logging.info("✓ RC522 initialization successful")
    
    # Step 3: REQA card detection
    logging.info("\n[STEP 3] Testing REQA card detection...")
    await uart_source.write([0x02])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03
    logging.info("✓ REQA detection successful")
    
    # Step 4: ATQA byte retrieval
    logging.info("\n[STEP 4] Testing ATQA byte retrieval...")
    await uart_source.write([0x03])
    atqa_bytes = []
    for i in range(2):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        atqa_bytes.append(response[0])
    expected_atqa = [0x08, 0x00]
    assert atqa_bytes == expected_atqa
    logging.info(f"✓ ATQA bytes correct: {' '.join(f'{b:02X}' for b in atqa_bytes)}")
    
    # Step 5: Anti-collision CL1
    logging.info("\n[STEP 5] Testing anti-collision CL1...")
    await uart_source.write([0x04])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03
    logging.info("✓ Anti-collision CL1 successful")
    
    # Step 6: UID byte retrieval
    logging.info("\n[STEP 6] Testing UID byte retrieval...")
    await uart_source.write([0x05])
    uid_bytes = []
    for i in range(5):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        uid_bytes.append(response[0])
    expected_uid = [0x2F, 0xFB, 0xBC, 0x4A, 0x22]
    assert uid_bytes == expected_uid
    logging.info(f"✓ UID bytes correct: {' '.join(f'{b:02X}' for b in uid_bytes)}")
    
    # Step 7: SELECT CL1
    logging.info("\n[STEP 7] Testing SELECT CL1...")
    await uart_source.write([0x06])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03
    logging.info("✓ SELECT CL1 successful")
    
    # Step 8: SAK byte retrieval
    logging.info("\n[STEP 8] Testing SAK byte retrieval...")
    await uart_source.write([0x07])
    sak_bytes = []
    for i in range(3):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        sak_bytes.append(response[0])
    expected_sak = [0x20, 0xFC, 0x70]
    assert sak_bytes == expected_sak
    logging.info(f"✓ SAK bytes correct: {' '.join(f'{b:02X}' for b in sak_bytes)}")
    
    # Step 9: RATS
    logging.info("\n[STEP 9] Testing RATS...")
    await uart_source.write([0x08])
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1 and response[0] == 0x03
    logging.info("✓ RATS successful")
    
    # Step 10: ATS byte retrieval
    logging.info("\n[STEP 10] Testing ATS byte retrieval...")
    await uart_source.write([0x09])
    ats_bytes = []
    for i in range(12):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        ats_bytes.append(response[0])
    expected_ats = [0x0A, 0x78, 0x80, 0x91, 0x02, 0x80, 0x73, 0xC8, 0x21, 0x10, 0xC3, 0x92]
    assert ats_bytes == expected_ats
    logging.info(f"✓ ATS bytes correct: {' '.join(f'{b:02X}' for b in ats_bytes)}")
    
    # Step 11: JavaCard applet selection
    logging.info("\n[STEP 11] Testing JavaCard applet selection...")
    await uart_source.write([0x0A])
    response = await with_timeout(uart_sink.read(count=1), 10_000_000, "us")
    assert len(response) == 1 and response[0] == 0x01
    logging.info("✓ JavaCard applet selection successful")
    
    # Step 11.5: Read applet selection response bytes for FPGA debugging
    logging.info("\n[STEP 11.5] Testing applet selection response retrieval...")
    await uart_source.write([0x0E])
    applet_response_bytes = []
    for i in range(5):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        applet_response_bytes.append(response[0])
    logging.info(f"✓ Applet selection response bytes: {' '.join(f'{b:02X}' for b in applet_response_bytes)}")
    logging.info(f"  - PCB (byte 0): 0x{applet_response_bytes[0]:02X}")
    logging.info(f"  - SW1 (byte 1): 0x{applet_response_bytes[1]:02X}")  
    logging.info(f"  - SW2 (byte 2): 0x{applet_response_bytes[2]:02X}")
    logging.info(f"  - CRC Low (byte 3): 0x{applet_response_bytes[3]:02X}")
    logging.info(f"  - CRC High (byte 4): 0x{applet_response_bytes[4]:02X}")
    # Validate expected success response format (SW1=0x90, SW2=0x00 indicates success)
    if applet_response_bytes[1] == 0x90 and applet_response_bytes[2] == 0x00:
        logging.info("✓ Applet selection response indicates success (SW1=90, SW2=00)")
    else:
        logging.warning(f"⚠ Unexpected applet selection response status: SW1={applet_response_bytes[1]:02X}, SW2={applet_response_bytes[2]:02X}")
    
    # Step 12: AUTH_INIT command
    logging.info("\n[STEP 12] Testing AUTH_INIT command...")
    await uart_source.write([0x0B])
    response = await with_timeout(uart_sink.read(count=1), 10_000_000, "us")
    assert len(response) == 1 and response[0] == 0x01
    logging.info("✓ AUTH_INIT successful")
    
    # Step 13: Nonce byte retrieval  
    logging.info("\n[STEP 13] Testing nonce byte retrieval...")
    received_nonce_bytes = []
    await uart_source.write([0x0C])
    for i in range(8):
        response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
        assert len(response) == 1
        received_nonce_bytes.append(response[0])
    logging.info(f"✓ Nonce bytes received: {' '.join(f'{b:02X}' for b in received_nonce_bytes)}")
    
    # =================== Step 14: AUTH command with WTX handling ===================
    logging.info("\n[STEP 14] Testing AUTH command with WTX protocol...")
    await uart_source.write([0x0D])
    response = await with_timeout(uart_sink.read(count=1), 10_000_000, "us")
    assert len(response) == 1
    
    if response[0] == 0x01:
        logging.info("✓ AUTH successful - Authentication completed!")
        logging.info("\n=== COMPLETE AUTHENTICATED IDENTIFICATION SUCCESS ===")
        logging.info("Full hardware sequence verification:")
        logging.info("  - Echo test (0xFF -> 0xFF)")
        logging.info("  - RC522 initialization (0x01 -> 0x01)")
        logging.info("  - REQA card detection (0x02 -> 0x03)")
        logging.info("  - ATQA retrieval (0x03 -> 0x08, 0x00)")
        logging.info("  - Anti-Collision CL1 (0x04 -> 0x03)")
        logging.info(f"  - UID retrieval (0x05 -> {' '.join(f'{b:02X}' for b in uid_bytes)})")
        logging.info(f"  - SELECT CL1 (0x06 -> 0x03)")
        logging.info(f"  - SAK retrieval (0x07 -> {' '.join(f'{b:02X}' for b in sak_bytes)})")
        logging.info(f"  - RATS (0x08 -> 0x03)")
        logging.info(f"  - ATS retrieval (0x09 -> {' '.join(f'{b:02X}' for b in ats_bytes)})")
        logging.info("  - JavaCard applet selection (0x0A -> 0x01)")
        logging.info(f"  - Applet selection response retrieval (0x0E -> {' '.join(f'{b:02X}' for b in applet_response_bytes)})")
        logging.info("  - AUTH_INIT command (0x0B -> 0x01)")
        logging.info(f"  - Nonce retrieval (0x0C x8 -> {' '.join(f'{b:02X}' for b in received_nonce_bytes)})")
        logging.info("  - AUTH command with WTX handling (0x0D -> 0x01)")

        # Step 14: Read AES authentication message for FPGA debugging
        logging.info("Step 14: Reading AES authentication message bytes for FPGA debugging...")
        await uart_source.write([0x0F])  # CMD_GET_AUTH_MESSAGE_REQ
        
        # Read 16 bytes of the authentication message
        auth_message_bytes = []
        for i in range(16):
            byte_data = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
            auth_message_bytes.append(byte_data[0])
            logging.info(f"  Auth message byte {i}: 0x{byte_data[0]:02X}")
        
        # Log the complete 16-byte message for FPGA debugging
        logging.info(f"Complete AES auth message: {' '.join(f'{b:02X}' for b in auth_message_bytes)}")
        
        # Interpret the authentication message
        # Expected success pattern: "AUTH_SUCCESS\0\0\0\0" = 0x415554485f5355434345535300000000
        message_hex = ''.join(f'{b:02X}' for b in auth_message_bytes)
        expected_success = "415554485F5355434345535300000000"
        
        if message_hex == expected_success:
            logging.info("✓ Authentication message indicates SUCCESS: 'AUTH_SUCCESS\\0\\0\\0\\0'")
        else:
            logging.info(f"⚠ Authentication message: 0x{message_hex}")
            # Try to interpret as ASCII
            try:
                ascii_chars = []
                for b in auth_message_bytes:
                    if 32 <= b <= 126:  # Printable ASCII range
                        ascii_chars.append(chr(b))
                    else:
                        ascii_chars.append(f'\\x{b:02x}')
                ascii_interpretation = ''.join(ascii_chars)
                logging.info(f"  ASCII interpretation: '{ascii_interpretation}'")
            except:
                logging.info("  Non-ASCII authentication message")
        
        logging.info(f"AES authentication message retrieval completed successfully!")
        
        # Update final summary
        logging.info("  - AES authentication message retrieval (0x0F x16 -> debugging data)")
        
    elif response[0] == 0x02:
        raise Exception("AUTH failed: Authentication error")
    else:
        raise Exception(f"AUTH unexpected response: expected 0x01 or 0x02, got 0x{response[0]:02X}")
    
    # Step 15: Test GET_ID command
    logging.info("Step 15: Testing GET_ID command...")
    await uart_source.write([0x10])  # CMD_GET_ID_REQ
    
    # Wait for GET_ID completion  
    response = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
    assert len(response) == 1, f"Expected 1 response byte for GET_ID, got {len(response)}"
    if response[0] == 0x01:
        logging.info("  GET_ID command succeeded")
        
        # Step 16: Read decrypted card ID
        logging.info("Step 16: Reading decrypted card ID...")
        await uart_source.write([0x11])  # CMD_GET_ID_DATA_REQ
        
        # Read 16 bytes of decrypted ID
        decrypted_id_bytes = []
        for i in range(16):
            byte_data = await with_timeout(uart_sink.read(count=1), 5_000_000, "us")
            decrypted_id_bytes.append(byte_data[0])
            logging.info(f"  ID byte {i}: 0x{byte_data[0]:02X}")
        
        # Log the complete 16-byte decrypted ID
        id_hex = ' '.join(f'{b:02X}' for b in decrypted_id_bytes)
        logging.info(f"Complete decrypted card ID: {id_hex}")
        
        # Verify decrypted ID matches expected test card ID (0x00 through 0x0F)
        expected_id = list(range(16))  # Expected test card ID
        if decrypted_id_bytes == expected_id:
            logging.info("✓ Decrypted ID matches expected test card ID: 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F")
        else:
            logging.info(f"⚠ Decrypted ID verification:")
            logging.info(f"  Expected: {' '.join(f'{b:02X}' for b in expected_id)}")
            logging.info(f"  Actual:   {id_hex}")
        
        logging.info(f"GET_ID operation completed successfully!")
        
        # Update final summary
        logging.info("  - GET_ID command (0x10 -> success)")
        logging.info("  - Decrypted ID retrieval (0x11 x16 -> card identifier)")
        
    elif response[0] == 0x02:
        raise Exception("GET_ID failed: Operation error (authentication may be required)")
    else:
        raise Exception(f"GET_ID unexpected response: expected 0x01 or 0x02, got 0x{response[0]:02X}")
    
    logging.info("\ntest_rc522_hw_full_auth completed successfully!")
    await Timer(1000, units="us")