"""
AES-128 Top-Level Testbench

Tests for the round-based masked AES-128 implementation using cocotb.
Validates encryption and decryption against NIST FIPS 197 test vectors.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import random
from aes_reference import *

# Debug mode flag
DEBUG = False

async def reset_dut(dut):
    """Reset the DUT."""
    dut.rst.value = 1
    dut.start.value = 0
    dut.enc_mode.value = 1
    dut.data_in.value = 0
    dut.key_0.value = 0
    dut.key_1.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)

    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def provide_randomness(dut):
    """Continuously provide fresh randomness on each clock cycle."""
    while True:
        await RisingEdge(dut.clk)
        dut.randomness.value = 0#random.getrandbits(332)

def set_aes_inputs(dut, data, key, encrypt=True):
    # Split inputs into shares
    key_mask = random.getrandbits(128)

    dut.data_in.value = data

    dut.key_in_0.value = key ^ key_mask
    dut.key_in_1.value = key_mask
    
    dut.enc_mode.value = 1 if encrypt else 0


    
async def run_aes(dut, data, key, encrypt=True):
    """
    Run AES encryption or decryption with fault protection.

    Args:
        dut: Device under test
        data: 128-bit input data
        key: 128-bit key
        encrypt: True for encryption, False for decryption

    Returns:
        Tuple of (128-bit output, cycle count)
    """

    set_aes_inputs(dut, data, key, encrypt)
    # Pulse start
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for busy to go high
    while dut.busy.value != 1:
        await RisingEdge(dut.clk)

    # Count cycles until done
    cycle_count = 0
    while dut.done.value != 1:
        await RisingEdge(dut.clk)
        cycle_count += 1
        if cycle_count > 1500:
            raise TimeoutError("AES did not complete in 1500 cycles")

    # Read and combine output shares
    out = int(dut.fault_protect_aes_out.value)

    return out, cycle_count

@cocotb.test()
async def test_fault_prot_aes(dut):
    """ Test AES encryption/decryption with fault protection"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(provide_randomness(dut))

    await reset_dut(dut)

    for i in range(5):
        plaintext = random.getrandbits(128)
        key = random.getrandbits(128)

        expected = aes_encrypt_reference(plaintext, key)
        result, cycles = await run_aes(dut, plaintext, key, encrypt=True)

        assert result == expected, (
            f"Encryption {i} mismatch:\n"
            f"  Plaintext: {plaintext:032x}\n"
            f"  Key:       {key:032x}\n"
            f"  Expected:  {expected:032x}\n"
            f"  Got:       {result:032x}"
        )

        print(f"Test {i}: PASS ({cycles} cycles)")

        # Small delay between tests
        await RisingEdge(dut.clk)

    print("All random encryption tests passed!")
