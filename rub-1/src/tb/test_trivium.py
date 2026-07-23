"""
Trivium Testbench

Tests for the Trivium PRNG implementation using cocotb.
Validates Trivium PRNG functionality against software reference implementation.

Test structure:
1. `test_prng_64` - Implements the test bench for 64-bit output 
2. `test_ready` - Tests ready signal functionality
3. `test_disabled` - Tests output of PRNG when disabled
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import random


async def reset_dut(dut):
    """
    Helper function to reset the DUT
    """
    dut.rst.value = 1
    dut.key.value = 0
    dut.iv.value = 0
    dut.enable.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

async def seed_trivium(dut, key, iv):
    """
    Helper function to seed the Trivium PRNG
    """
    dut.key.value = key
    dut.iv.value = iv
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

@cocotb.test()
async def test_prng_64(dut):
    """
    Test PRNG output functionality with an output of 64 bits.
    Test vectors are generated via this C implementation: https://github.com/cbouilla/trivium/blob/main/trivium64.c
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


    
    test_vectors= [(0x0, 0x0, 0xdf07fd641a9aa0d8), 
                   (0x1, 0x1, 0x0b439c19d5fd82cc), 
                    (0x123456789abcdef0, 0x0fedcba987654321, 0x97376644bf7238bd),
                    (0xDEADBEEF, 0xC0DEAFFE, 0x8131185a14fc93be),
                    ]
    
    
    
    await reset_dut(dut)
    
    for key, iv, EXPECTED in test_vectors:
        await seed_trivium(dut, key, iv)
    
        # Wait for warmup 
        await(RisingEdge(dut.rdy))
        
        # Get result and compare to test vector
        RESULT = int(dut.stream_out.value)
        dut._log.info("******************************************************************")
        dut._log.info(f"Key      = 0x{key:016X}")
        dut._log.info(f"IV       = 0x{iv:016X}")
        dut._log.info(f"Result = 0x{RESULT:016X}")
        dut._log.info(f"Expected  = 0x{EXPECTED:016X}")
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)

        assert RESULT == EXPECTED, \
            f"FAIL: expected 0x{EXPECTED:016X}, got 0x{RESULT:016X}"

    dut._log.info("SUCCESS: Trivium keystream matches expected value")

@cocotb.test()
async def test_disabled(dut):
    """
    Tests that PRNG output does NOT change when enable=0.
    """

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    await seed_trivium(dut, 0xDEADBEEF, 0xC0DEAFFE)

    await RisingEdge(dut.rdy)

    first_val = int(dut.stream_out.value)

    # Disable PRNG
    dut.enable.value = 0

    # Wait some cycles
    for _ in range(10):
        await RisingEdge(dut.clk)

    second_val = int(dut.stream_out.value)

    assert first_val == second_val, \
        f"PRNG changed while disabled: {first_val:016X} -> {second_val:016X}"

@cocotb.test()
async def test_invalid_key_iv(dut):
    """
    Tests that all-ones key/iv is rejected:
    - rdy must never assert
    """

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    dut.key.value = 0xFFFFFFFFFFFFFFFFFFFF
    dut.iv.value  = 0xFFFFFFFFFFFFFFFFFFFF
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    # Observe for a reasonable amount of cycles
    for _ in range(200):
        await RisingEdge(dut.clk)
        assert dut.rdy.value == 0, "rdy asserted with invalid key/iv"
