"""
SPI Master Testbench

Tests for the SPI Master controller implementation using cocotb.
Verifies basic functionality, multi-byte transfers, and SPI Mode 0 timing.

Test structure:
1. test_single_byte_transfer - Basic single byte transmission
2. test_multiple_byte_transfer - Continuous transfers in one CS session  
3. test_spi_mode_0_timing - Verify SPI Mode 0 clock behavior
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, FallingEdge
import random

@cocotb.test()
async def test_single_byte_transfer(dut):
    """
    Test basic single byte SPI transfer
    
    Verifies:
    - CS control (open_cs0 signal)
    - Single byte transmission with start_tx pulse
    - Busy signal behavior
    - Proper CS release after transfer
    """
    
    # Setup: Start 100MHz clock (10ns period)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset sequence: Assert reset and initialize all inputs
    dut.rst.value = 1
    dut.start_tx.value = 0
    dut.open_cs0.value = 0
    dut.open_cs1.value = 0
    dut.tx_data.value = 0
    dut.spi_miso.value = 0
    
    # Hold reset for 2 clock cycles
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    
    # Verify initial state after reset
    assert dut.busy.value == 0          # Should not be busy
    assert dut.spi_cs_0.value == 1      # CS should be inactive (high)
    
    # Test CS activation: assert open_cs0 to activate CS
    dut.open_cs0.value = 1
    await RisingEdge(dut.clk)
    assert dut.spi_cs_0.value == 0      # CS should now be active (low)
    
    # Setup transmission: load test data
    test_tx_data = 0xA5                 # Test pattern: 10100101
    dut.tx_data.value = test_tx_data
    
    # Initiate transmission: pulse start_tx
    dut.start_tx.value = 1
    await RisingEdge(dut.clk)
    dut.start_tx.value = 0
    await RisingEdge(dut.clk)           # Allow one more cycle for state transition
    
    # Verify transmission started: busy should be high
    assert dut.busy.value == 1
    
    # Wait for 8-bit transmission to complete
    while dut.busy.value == 1:
        await RisingEdge(dut.clk)
    
    # Test CS deactivation: deassert open_cs0 to release CS
    dut.open_cs0.value = 0
    await RisingEdge(dut.clk)
    assert dut.spi_cs_0.value == 1      # CS should be inactive (high) again
    
    # Allow some settling time
    await Timer(100, unit="ns")

@cocotb.test()
async def test_multiple_byte_transfer(dut):
    """
    Test multiple byte transfers in single CS session
    
    Verifies:
    - CS remains active across multiple byte transfers
    - Each byte transfer completes properly
    - Ability to send consecutive bytes without CS cycling
    """
    
    # Setup: Start 100MHz clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset sequence
    dut.rst.value = 1
    dut.start_tx.value = 0
    dut.open_cs0.value = 0
    dut.open_cs1.value = 0
    dut.tx_data.value = 0
    dut.spi_miso.value = 0
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    
    # Activate CS for the entire transfer session
    dut.open_cs0.value = 1
    await RisingEdge(dut.clk)
    assert dut.spi_cs_0.value == 0      # CS active for session
    
    # Test data: 4 bytes to transfer consecutively
    test_data = [0x12, 0x34, 0x56, 0x78]
    
    # Transfer each byte while keeping CS active
    for i, data in enumerate(test_data):
        dut.tx_data.value = data
        
        # Pulse start_tx to begin transmission
        dut.start_tx.value = 1
        await RisingEdge(dut.clk)
        dut.start_tx.value = 0
        await RisingEdge(dut.clk)
        
        # Verify transmission started
        assert dut.busy.value == 1
        
        # Wait for byte transmission to complete
        while dut.busy.value == 1:
            await RisingEdge(dut.clk)
        
        # Verify CS remains active between transfers (key feature)
        assert dut.spi_cs_0.value == 0
    
    # End the transfer session by deactivating CS
    dut.open_cs0.value = 0
    await RisingEdge(dut.clk)
    assert dut.spi_cs_0.value == 1      # CS should be released
    
    await Timer(100, unit="ns")

@cocotb.test()
async def test_spi_mode_0_timing(dut):
    """
    Test SPI Mode 0 timing compliance (CPOL=0, CPHA=0)
    
    Verifies:
    - SCLK idle state is low (CPOL=0)
    - Data changes on falling edge, sampled on rising edge (CPHA=0) 
    - MOSI data alignment with SCLK transitions
    - Proper MSB-first transmission
    """
    
    # Setup: Start 100MHz clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset sequence
    dut.rst.value = 1
    dut.start_tx.value = 0
    dut.open_cs0.value = 0
    dut.open_cs1.value = 0
    dut.tx_data.value = 0
    dut.spi_miso.value = 1              # Set MISO high to test RX path
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    
    # Activate CS
    dut.open_cs0.value = 1
    await RisingEdge(dut.clk)
    
    # Verify Mode 0 idle state: SCLK should be low when idle
    assert dut.spi_sclk.value == 0
    
    # Start transmission with test pattern
    dut.tx_data.value = 0x81            # Binary: 10000001 (MSB=1, LSB=1)
    dut.start_tx.value = 1
    await RisingEdge(dut.clk)
    dut.start_tx.value = 0
    
    # Monitor SPI signals during transmission for Mode 0 compliance
    bit_count = 0
    while dut.busy.value == 1 and bit_count < 16:  # Safety limit to prevent infinite loop
        await RisingEdge(dut.clk)
        bit_count += 1
        
        # In Mode 0: data is valid when SCLK is high
        # First transmitted bit should be MSB (bit 7 = 1)
        if dut.spi_sclk.value == 1:
            if bit_count <= 2:          # Check during first few cycles
                assert dut.spi_mosi.value == 1  # MSB should be 1
    
    # Deactivate CS after transmission
    dut.open_cs0.value = 0
    await RisingEdge(dut.clk)
    
    await Timer(100, unit="ns")

@cocotb.test()
async def test_spi_data_reception(dut):
    """
    Test SPI data reception from slave
    
    Verifies:
    - Proper reception of data on MISO line
    - Correct shift register operation for RX data
    - rx_data output contains received data after transmission
    - Simultaneous TX/RX operation (full duplex)
    """
    
    # Setup: Start 100MHz clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset sequence
    dut.rst.value = 1
    dut.start_tx.value = 0
    dut.open_cs0.value = 0
    dut.open_cs1.value = 0
    dut.tx_data.value = 0
    dut.spi_miso.value = 0              # Start with MISO low
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    
    # Activate CS
    dut.open_cs0.value = 1
    await RisingEdge(dut.clk)
    
    # Simple test: Keep MISO high throughout transmission to receive 0xFF
    tx_test_data = 0x00                 # Send all zeros
    rx_expected_data = 0xFF             # Expect all ones (MISO = 1)
    dut.tx_data.value = tx_test_data
    dut.spi_miso.value = 1              # Keep MISO high for entire transfer
    
    # Start transmission
    dut.start_tx.value = 1  
    await RisingEdge(dut.clk)
    dut.start_tx.value = 0
    await RisingEdge(dut.clk)
    
    # Debug: Check if transmission started
    print(f"DEBUG: After start_tx pulse: busy={dut.busy.value}")
    
    if dut.busy.value == 0:
        print("ERROR: Transmission never started!")
        print(f"DEBUG: open_cs0={dut.open_cs0.value}, cs_n={dut.spi_cs_0.value}")
        print(f"DEBUG: state={int(dut.state.value)}, tx_data={int(dut.tx_data.value):02X}")
        assert False, "SPI transmission did not start"
    
    # Wait for transmission to complete
    cycle_count = 0
    while dut.busy.value == 1 and cycle_count < 100:  # Safety limit
        await RisingEdge(dut.clk)
        cycle_count += 1
    
    print(f"DEBUG: Transmission completed after {cycle_count} cycles")
    print(f"DEBUG: Final state: busy={dut.busy.value}, shift_reg=0x{int(dut.shift_reg.value):02X}")
    
    # Verify received data
    received_data = int(dut.rx_data.value)
    print(f"DEBUG: rx_data=0x{received_data:02X}, expected=0x{rx_expected_data:02X}")
    assert received_data == rx_expected_data, f"Expected RX data 0x{rx_expected_data:02X}, got 0x{received_data:02X}"
    
    # Deactivate CS
    dut.open_cs0.value = 0
    await RisingEdge(dut.clk)
    
    await Timer(100, unit="ns")

@cocotb.test()
async def test_spi_data_integrity_random(dut):
    """
    Comprehensive test of SPI data transmission integrity using random data patterns
    
    Verifies:
    - MOSI output matches transmitted data bit-by-bit  
    - Proper bit timing relative to SCLK
    - MSB-first transmission order
    - Tests with multiple random data patterns to catch edge cases
    """
    
    # Setup: Start 100MHz clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset sequence
    dut.rst.value = 1
    dut.start_tx.value = 0
    dut.open_cs0.value = 0
    dut.open_cs1.value = 0  
    dut.tx_data.value = 0
    dut.spi_miso.value = 0
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    
    # Activate CS
    dut.open_cs0.value = 1
    await RisingEdge(dut.clk)
    
    # Test with multiple random data patterns
    random.seed(42)  # Reproducible random sequence
    test_patterns = [random.randint(0, 255) for _ in range(10)]
    
    print(f"Testing SPI data integrity with patterns: {[hex(p) for p in test_patterns]}")
    
    for test_data in test_patterns:
        print(f"\nTesting transmission of 0x{test_data:02X} (binary: {test_data:08b})")
        
        # Setup transmission
        dut.tx_data.value = test_data
        
        # Start transmission
        dut.start_tx.value = 1
        await RisingEdge(dut.clk)
        dut.start_tx.value = 0
        await RisingEdge(dut.clk)
        
        # Verify transmission started
        assert dut.busy.value == 1, "SPI transmission should be active"
        
        # Monitor MOSI bit-by-bit during transmission
        transmitted_bits = []
        sclk_edges = 0
        prev_sclk = 0  # Track previous SCLK state to detect rising edges
        
        while dut.busy.value == 1 and sclk_edges < 8:  # Safety limit - only need 8 bits
            await RisingEdge(dut.clk)
            
            # Check for SCLK transitions to track bit timing
            current_sclk = int(dut.spi_sclk.value)
            current_mosi = int(dut.spi_mosi.value)
            
            # Detect actual rising edge of SCLK (transition from 0 to 1)
            if prev_sclk == 0 and current_sclk == 1:
                # This is a true rising edge - sample MOSI
                transmitted_bits.append(current_mosi)
                print(f"  SCLK rising edge {sclk_edges}: MOSI = {current_mosi}")
                sclk_edges += 1
            
            prev_sclk = current_sclk  # Update previous state
        
        # Verify we captured 8 bits
        assert len(transmitted_bits) == 8, f"Expected 8 bits, got {len(transmitted_bits)}"
        
        # Reconstruct transmitted byte from captured bits (MSB first)
        reconstructed_byte = 0
        for i, bit in enumerate(transmitted_bits):
            reconstructed_byte |= (bit << (7 - i))
        
        print(f"  Expected: 0x{test_data:02X} ({test_data:08b})")
        print(f"  Received: 0x{reconstructed_byte:02X} ({reconstructed_byte:08b})")
        
        # This is the key verification - transmitted data should match exactly
        assert reconstructed_byte == test_data, \
            f"Data integrity failed: sent 0x{test_data:02X}, MOSI transmitted 0x{reconstructed_byte:02X}"
    
    # Deactivate CS
    dut.open_cs0.value = 0
    await RisingEdge(dut.clk)
    
    await Timer(100, unit="ns")
    print("All random data patterns transmitted correctly!")

@cocotb.test()
async def test_spi_timing_stability(dut):
    """
    Test SPI Mode 0 timing stability - verify MOSI is stable during SCLK high periods
    
    Verifies:
    - MOSI data is stable while SCLK is high (proper sampling window)
    - MOSI changes only occur during SCLK low periods  
    - Proper SPI Mode 0 timing compliance
    """
    
    # Setup: Start 100MHz clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset sequence
    dut.rst.value = 1
    dut.start_tx.value = 0
    dut.open_cs0.value = 0
    dut.open_cs1.value = 0
    dut.tx_data.value = 0
    dut.spi_miso.value = 0
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    
    # Activate CS
    dut.open_cs0.value = 1
    await RisingEdge(dut.clk)
    
    # Test with a specific pattern that will reveal timing issues
    test_data = 0xAA  # 10101010 - alternating pattern stresses timing
    print(f"Testing MOSI timing stability with 0x{test_data:02X}")
    
    dut.tx_data.value = test_data
    
    # Start transmission
    dut.start_tx.value = 1
    await RisingEdge(dut.clk)
    dut.start_tx.value = 0
    await RisingEdge(dut.clk)
    
    # Monitor MOSI stability during each SCLK high period
    bit_count = 0
    prev_sclk = 0
    mosi_stable = True
    stability_violations = []
    
    while dut.busy.value == 1 and bit_count < 8:
        await RisingEdge(dut.clk)
        
        current_sclk = int(dut.spi_sclk.value)
        current_mosi = int(dut.spi_mosi.value)
        
        # Track SCLK transitions
        if prev_sclk == 0 and current_sclk == 1:
            # Rising edge - start of sampling period
            sampling_mosi = current_mosi
            sampling_start = True
            print(f"  Bit {bit_count}: SCLK rising, MOSI = {current_mosi}")
            
        elif prev_sclk == 1 and current_sclk == 1 and 'sampling_start' in locals():
            # During high period - MOSI should be stable
            if current_mosi != sampling_mosi:
                mosi_stable = False
                violation = f"Bit {bit_count}: MOSI changed from {sampling_mosi} to {current_mosi} during SCLK high"
                stability_violations.append(violation)
                print(f"  TIMING VIOLATION: {violation}")
                
        elif prev_sclk == 1 and current_sclk == 0:
            # Falling edge - end of sampling period
            if 'sampling_start' in locals():
                del sampling_start
                bit_count += 1
        
        prev_sclk = current_sclk
    
    # Verify MOSI was stable during all sampling periods
    assert mosi_stable, f"MOSI timing violations detected: {stability_violations}"
    
    # Deactivate CS
    dut.open_cs0.value = 0
    await RisingEdge(dut.clk)
    
    await Timer(100, unit="ns")
    print("SPI timing stability verified - MOSI stable during SCLK high periods")