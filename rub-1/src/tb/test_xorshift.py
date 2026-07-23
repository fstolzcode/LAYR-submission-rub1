"""
Xorshift128 PRNG Testbench

Tests for the xorshift PRNG implementation using cocotb.
Validates random number generation against software reference implementation.

Test structure:
1. test_reset_functionality - Reset behavior and initial state
2. test_output_sequence - Output sequence validation against reference
3. test_continuous_operation - Multiple cycles of operation
4. test_deterministic_behavior - Repeatability after reset
5. test_64bit_per_cycle - Validates 64-bit output generation per cycle
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

class Xorshift128Reference:
    """
    Reference implementation of xorshift128 PRNG matching the C code.
    
    Original C implementation:
    uint32_t x = 123456789;
    uint32_t y = 362436069;
    uint32_t z = 521288629;
    uint32_t w = 88675123;
    uint32_t xorshift128() {
        uint32_t t = x ^ (x << 11);
        x = y; y = z; z = w;
        w ^= (w >> 19) ^ t ^ (t >> 8);
        return w;
    }
    """
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset to initial state matching C implementation"""
        self.x = 123456789
        self.y = 362436069  
        self.z = 521288629
        self.w = 88675123
    
    def next(self):
        """Generate next 32-bit random number"""
        t = self.x ^ ((self.x << 11) & 0xFFFFFFFF)
        self.x, self.y, self.z = self.y, self.z, self.w
        self.w = self.w ^ (self.w >> 19) ^ t ^ (t >> 8)
        self.w &= 0xFFFFFFFF  # Ensure 32-bit result
        return self.w
    
    def next_64bit(self):
        """Generate 64-bit random number (two iterations, matching RTL behavior)"""
        low = self.next()
        high = self.next()
        return (high << 32) | low

async def reset_dut(dut):
    """
    Helper function to reset the DUT
    """
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_reset_functionality(dut):
    """
    Test reset functionality and initial state
    """
    
    # Start 100MHz clock (10ns period)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset DUT
    await reset_dut(dut)
    
    # Get first output after reset (combinational output based on initial state)
    first_output = int(dut.rand_out.value)
    
    # Create reference and generate expected first 64-bit output
    ref = Xorshift128Reference()
    expected_output = ref.next_64bit()
    
    assert first_output == expected_output, f"First output after reset mismatch: HW=0x{first_output:016X}, REF=0x{expected_output:016X}"
    
    print(f"Reset functionality test passed: First output = 0x{first_output:016X} ✓")

@cocotb.test()
async def test_output_sequence(dut):
    """
    Test that output sequence matches reference implementation
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset DUT
    await reset_dut(dut)
    
    # Create reference implementation
    ref = Xorshift128Reference()
    
    # Test sequence of 20 outputs
    for i in range(20):
        # Get hardware output (before clock edge)
        hw_output = int(dut.rand_out.value)
        
        # Get expected output from reference
        expected_output = ref.next_64bit()
        
        assert hw_output == expected_output, f"Output sequence mismatch at cycle {i}: HW=0x{hw_output:016X}, REF=0x{expected_output:016X}"
        
        if i < 5:  # Print first few outputs for verification
            print(f"Cycle {i}: HW=0x{hw_output:016X}, REF=0x{expected_output:016X} ✓")
        
        # Advance to next state
        await RisingEdge(dut.clk)
    
    print("Output sequence test passed: 20 cycles validated ✓")

@cocotb.test()
async def test_continuous_operation(dut):
    """
    Test continuous operation over many cycles
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset DUT
    await reset_dut(dut)
    
    # Create reference implementation
    ref = Xorshift128Reference()
    
    # Test continuous operation for 100 cycles
    previous_outputs = set()
    
    for i in range(100):
        # Get hardware output (before clock edge)
        hw_output = int(dut.rand_out.value)
        
        # Get expected output from reference
        expected_output = ref.next_64bit()
        
        assert hw_output == expected_output, f"Continuous operation mismatch at cycle {i}: HW=0x{hw_output:016X}, REF=0x{expected_output:016X}"
        
        # Check for uniqueness (xorshift should have good distribution)
        assert hw_output not in previous_outputs, f"Duplicate output detected at cycle {i}: 0x{hw_output:016X}"
        previous_outputs.add(hw_output)
        
        # Advance to next state
        await RisingEdge(dut.clk)
    
    print(f"Continuous operation test passed: 100 unique outputs generated ✓")

@cocotb.test()
async def test_deterministic_behavior(dut):
    """
    Test that behavior is deterministic and repeatable after reset
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # First run: Reset and capture sequence
    await reset_dut(dut)
    
    first_sequence = []
    for i in range(10):
        await RisingEdge(dut.clk)
        first_sequence.append(int(dut.rand_out.value))
    
    # Second run: Reset and capture sequence again
    await reset_dut(dut)
    
    second_sequence = []
    for i in range(10):
        await RisingEdge(dut.clk)
        second_sequence.append(int(dut.rand_out.value))
    
    # Sequences should be identical
    for i, (first, second) in enumerate(zip(first_sequence, second_sequence)):
        assert first == second, f"Deterministic behavior failed at position {i}: First=0x{first:016X}, Second=0x{second:016X}"
    
    print("Deterministic behavior test passed: Sequences match after reset ✓")

@cocotb.test()
async def test_64bit_per_cycle(dut):
    """
    Test that module generates 64 bits per cycle (not 32 bits repeated)
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset DUT
    await reset_dut(dut)
    
    # Check several outputs to ensure upper and lower 32 bits are different
    for i in range(10):
        await RisingEdge(dut.clk)
        
        hw_output = int(dut.rand_out.value)
        lower_32 = hw_output & 0xFFFFFFFF
        upper_32 = (hw_output >> 32) & 0xFFFFFFFF
        
        # Upper and lower 32 bits should be different (they represent two different xorshift iterations)
        assert lower_32 != upper_32, f"Upper and lower 32 bits are identical at cycle {i}: 0x{hw_output:016X}"
        
        if i < 3:
            print(f"Cycle {i}: Lower=0x{lower_32:08X}, Upper=0x{upper_32:08X} ✓")
    
    print("64-bit per cycle test passed: Upper and lower 32 bits are distinct ✓")

@cocotb.test()
async def test_statistical_properties(dut):
    """
    Basic statistical test to ensure output has reasonable distribution
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    # Reset DUT
    await reset_dut(dut)
    
    # Collect outputs and analyze bit distribution
    outputs = []
    for i in range(100):
        await RisingEdge(dut.clk)
        outputs.append(int(dut.rand_out.value))
    
    # Count bits in each position (should be roughly balanced)
    bit_counts = [0] * 64
    for output in outputs:
        for bit_pos in range(64):
            if output & (1 << bit_pos):
                bit_counts[bit_pos] += 1
    
    # Check that no bit position is heavily biased (allow 30-70% range for 100 samples)
    for bit_pos, count in enumerate(bit_counts):
        percentage = count / len(outputs)
        assert 0.3 <= percentage <= 0.7, f"Bit {bit_pos} is biased: {percentage:.2%} (count={count}/100)"
    
    # Check that outputs are not all the same
    unique_outputs = set(outputs)
    assert len(unique_outputs) > 90, f"Too many duplicate outputs: {len(unique_outputs)} unique out of 100"
    
    print(f"Statistical properties test passed: {len(unique_outputs)} unique outputs, balanced bit distribution ✓")