"""
ISO14443-A CRC Calculator Testbench

Tests for the CRC ISO14443-A implementation using cocotb.
Validates CRC calculations against software reference implementation.

Test structure:
1. test_single_byte_crc - Single byte CRC calculations
2. test_multi_byte_crc - Multi-byte CRC calculations  
3. test_random_data - Random data CRC validation
4. test_reset_functionality - Reset and state management
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import random

def calculate_crc_a_reference(data):
    """
    Reference CRC calculation from software implementation.
    Uses polynomial 0x8408 and initial value 0x6363 as per ISO14443-A spec.
    
    Args:
        data: List of bytes to calculate CRC over
        
    Returns:
        Tuple of (crc_low, crc_high) - CRC bytes in LSB-first order
    """
    # ISO14443-A CRC parameters
    polynomial = 0x8408
    initial_value = 0x6363
    
    crc = initial_value
    
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ polynomial
            else:
                crc = crc >> 1
    
    # Return as LSB first (CRC_L, CRC_H)
    crc_low = crc & 0xFF
    crc_high = (crc >> 8) & 0xFF
    
    return crc_low, crc_high

async def load_byte_and_wait(dut, byte_value):
    """
    Helper function to load a byte and wait for completion
    """
    dut.data_in.value = byte_value
    dut.load_byte.value = 1
    await RisingEdge(dut.clk)
    dut.load_byte.value = 0
    
    # Wait for busy to go high
    while dut.busy.value == 0:
        await RisingEdge(dut.clk)
    
    # Wait for busy to go low (calculation complete)
    while dut.busy.value == 1:
        await RisingEdge(dut.clk)

async def reset_dut(dut):
    """
    Helper function to reset the DUT
    """
    dut.rst.value = 1
    dut.load_byte.value = 0
    dut.data_in.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

@cocotb.test()
async def test_single_byte_crc(dut):
    """
    Test single byte CRC calculations against reference implementation
    """
    
    # Start 100MHz clock (10ns period)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset DUT
    await reset_dut(dut)
    
    # Test various single byte values
    test_values = [0x00, 0x01, 0x7F, 0x80, 0xFF, 0x93, 0x70, 0xE0]
    
    for test_byte in test_values:
        # Reset for new calculation
        await reset_dut(dut)
        
        # Load byte and wait for completion
        await load_byte_and_wait(dut, test_byte)
        
        # Get hardware result
        hw_crc = int(dut.crc_out.value)
        hw_crc_low = hw_crc & 0xFF
        hw_crc_high = (hw_crc >> 8) & 0xFF
        
        # Calculate reference
        ref_crc_low, ref_crc_high = calculate_crc_a_reference([test_byte])
        
        # Verify results
        assert hw_crc_low == ref_crc_low, f"CRC low mismatch for 0x{test_byte:02X}: HW=0x{hw_crc_low:02X}, REF=0x{ref_crc_low:02X}"
        assert hw_crc_high == ref_crc_high, f"CRC high mismatch for 0x{test_byte:02X}: HW=0x{hw_crc_high:02X}, REF=0x{ref_crc_high:02X}"
        
        print(f"Single byte 0x{test_byte:02X}: CRC = 0x{hw_crc_high:02X}{hw_crc_low:02X} ✓")

@cocotb.test()
async def test_multi_byte_crc(dut):
    """
    Test multi-byte CRC calculations
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Test data sets for multi-byte CRC
    test_data_sets = [
        [0x93, 0x70],                          # SELECT command start
        [0x93, 0x70, 0x12, 0x34, 0x56, 0x78], # SELECT with UID
        [0xE0, 0x80],                          # RATS command
        [0x02, 0x00, 0xA4, 0x04, 0x00],       # APDU SELECT start
        [0x00, 0x01, 0x02, 0x03, 0x04],       # Simple test pattern
    ]
    
    for test_data in test_data_sets:
        # Reset for new calculation
        await reset_dut(dut)
        
        # Load bytes one by one
        for byte_val in test_data:
            await load_byte_and_wait(dut, byte_val)
        
        # Get hardware result
        hw_crc = int(dut.crc_out.value)
        hw_crc_low = hw_crc & 0xFF
        hw_crc_high = (hw_crc >> 8) & 0xFF
        
        # Calculate reference
        ref_crc_low, ref_crc_high = calculate_crc_a_reference(test_data)
        
        # Verify results
        data_str = " ".join([f"0x{b:02X}" for b in test_data])
        assert hw_crc_low == ref_crc_low, f"Multi-byte CRC low mismatch for [{data_str}]: HW=0x{hw_crc_low:02X}, REF=0x{ref_crc_low:02X}"
        assert hw_crc_high == ref_crc_high, f"Multi-byte CRC high mismatch for [{data_str}]: HW=0x{hw_crc_high:02X}, REF=0x{ref_crc_high:02X}"
        
        print(f"Multi-byte [{data_str}]: CRC = 0x{hw_crc_high:02X}{hw_crc_low:02X} ✓")

@cocotb.test()
async def test_random_data(dut):
    """
    Test with random data to catch edge cases
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Generate and test random data sets
    for test_num in range(10):
        # Generate random data (1 to 16 bytes)
        data_length = random.randint(1, 16)
        test_data = [random.randint(0, 255) for _ in range(data_length)]
        
        # Reset for new calculation
        await reset_dut(dut)
        
        # Load bytes one by one
        for byte_val in test_data:
            await load_byte_and_wait(dut, byte_val)
        
        # Get hardware result
        hw_crc = int(dut.crc_out.value)
        hw_crc_low = hw_crc & 0xFF
        hw_crc_high = (hw_crc >> 8) & 0xFF
        
        # Calculate reference
        ref_crc_low, ref_crc_high = calculate_crc_a_reference(test_data)
        
        # Verify results
        data_str = " ".join([f"0x{b:02X}" for b in test_data])
        assert hw_crc_low == ref_crc_low, f"Random CRC low mismatch for [{data_str}]: HW=0x{hw_crc_low:02X}, REF=0x{ref_crc_low:02X}"
        assert hw_crc_high == ref_crc_high, f"Random CRC high mismatch for [{data_str}]: HW=0x{hw_crc_high:02X}, REF=0x{ref_crc_high:02X}"
        
        print(f"Random test {test_num+1} ({data_length} bytes): CRC = 0x{hw_crc_high:02X}{hw_crc_low:02X} ✓")

@cocotb.test()
async def test_reset_functionality(dut):
    """
    Test reset functionality and state management
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Initial reset
    await reset_dut(dut)
    
    # Verify initial state
    assert dut.busy.value == 0, "DUT should not be busy after reset"
    initial_crc = int(dut.crc_out.value)
    assert initial_crc == 0x6363, f"Initial CRC should be 0x6363, got 0x{initial_crc:04X}"
    
    # Load a byte to change CRC
    await load_byte_and_wait(dut, 0x93)
    crc_after_byte = int(dut.crc_out.value)
    assert crc_after_byte != 0x6363, "CRC should change after loading byte"
    
    # Reset should restore initial value
    await reset_dut(dut)
    crc_after_reset = int(dut.crc_out.value)
    assert crc_after_reset == 0x6363, f"CRC should return to 0x6363 after reset, got 0x{crc_after_reset:04X}"
    
    # Test that we can start a new calculation after reset
    await load_byte_and_wait(dut, 0x70)
    
    # Calculate reference for single byte 0x70
    ref_crc_low, ref_crc_high = calculate_crc_a_reference([0x70])
    hw_crc = int(dut.crc_out.value)
    hw_crc_low = hw_crc & 0xFF
    hw_crc_high = (hw_crc >> 8) & 0xFF
    
    assert hw_crc_low == ref_crc_low, "CRC calculation should work correctly after reset"
    assert hw_crc_high == ref_crc_high, "CRC calculation should work correctly after reset"
    
    print("Reset functionality test passed ✓")

@cocotb.test()
async def test_busy_signal_timing(dut):
    """
    Test busy signal timing and behavior
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset DUT
    await reset_dut(dut)
    
    # Verify initial state
    assert dut.busy.value == 0, "Busy should be low initially"
    
    # Start loading a byte
    dut.data_in.value = 0x42
    dut.load_byte.value = 1
    await RisingEdge(dut.clk)
    dut.load_byte.value = 0
    
    # Busy should go high within a few cycles
    busy_high_time = 0
    for i in range(10):
        await RisingEdge(dut.clk)
        if dut.busy.value == 1:
            busy_high_time = i + 1
            break
    
    assert busy_high_time > 0, "Busy signal should go high after load_byte"
    assert busy_high_time <= 2, f"Busy should go high quickly, took {busy_high_time} cycles"
    
    # Wait for busy to go low and count cycles
    busy_cycles = 0
    while dut.busy.value == 1:
        await RisingEdge(dut.clk)
        busy_cycles += 1
        assert busy_cycles <= 10, "Busy signal should not stay high for more than 10 cycles"
    
    assert busy_cycles == 8, f"Busy should be high for exactly 8 cycles (8 bits), was {busy_cycles}"
    
    print(f"Busy signal timing test passed: high for {busy_cycles} cycles ✓")

@cocotb.test()
async def test_real_world_javacard_examples(dut):
    """
    Test real-world CRC calculations extracted from streamlined.log
    
    These are actual CRC calculations from working JavaCard communication sessions,
    providing validation against real protocol usage.
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Real-world test cases extracted from software/streamlined.log
    real_world_cases = [
        {
            "name": "SELECT Command (ISO14443 CL1)",
            "source": "streamlined.log line 333-334",
            "context": "SELECT command with UID during anti-collision",
            "data": [0x93, 0x70, 0x2F, 0xFB, 0xBC, 0x4A, 0x22],
            "expected_crc_low": 0x28,
            "expected_crc_high": 0xF2
        },
        {
            "name": "RATS Command", 
            "source": "streamlined.log line 439",
            "context": "Request for Answer To Select command",
            "data": [0xE0, 0x80],
            "expected_crc_low": 0x31,
            "expected_crc_high": 0x73
        },
        {
            "name": "I-block Applet Selection",
            "source": "streamlined.log line 549-550", 
            "context": "ISO14443-4 I-block with SELECT APDU for JavaCard applet",
            "data": [0x02, 0x00, 0xA4, 0x04, 0x00, 0x07, 0xA0, 0x00, 0x00, 0x01, 0x51, 0x00, 0x00],
            "expected_crc_low": 0x2E,
            "expected_crc_high": 0x0A
        }
    ]
    
    for case in real_world_cases:
        # Reset for new calculation
        await reset_dut(dut)
        
        # Load bytes one by one
        for byte_val in case["data"]:
            await load_byte_and_wait(dut, byte_val)
        
        # Get hardware result
        hw_crc = int(dut.crc_out.value)
        hw_crc_low = hw_crc & 0xFF
        hw_crc_high = (hw_crc >> 8) & 0xFF
        
        # Verify against real-world expected values
        data_str = " ".join([f"0x{b:02X}" for b in case["data"]])
        assert hw_crc_low == case["expected_crc_low"], f"{case['name']}: CRC low mismatch for [{data_str}]: HW=0x{hw_crc_low:02X}, Expected=0x{case['expected_crc_low']:02X}"
        assert hw_crc_high == case["expected_crc_high"], f"{case['name']}: CRC high mismatch for [{data_str}]: HW=0x{hw_crc_high:02X}, Expected=0x{case['expected_crc_high']:02X}"
        
        print(f"✅ {case['name']}: CRC = 0x{hw_crc_high:02X}{hw_crc_low:02X}")
        print(f"   Context: {case['context']}")
        print(f"   Source: {case['source']}")
        print(f"   Data: [{data_str}]")
        print("")
    
    print("All real-world JavaCard CRC examples validated successfully! ✓")