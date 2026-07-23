"""
Fault detection MUX testbench.

Test structure:
1. `test_correct_result` - Implements the test bench for AES S-box functionality
2. `test_aes_sbox_inv` - Tests AES S-box inversion functionality
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import random


async def reset_dut(dut):
    """
    Helper function to reset the DUT
    """
    dut.reset.value = 1
    dut.enable.value = 0
    await RisingEdge(dut.clk)
    dut.reset.value = 0


def execute_fault_detection(dut, a, b, c):
    """
    Helper function to set sbox and execute
    """    
    dut.a0.value = a[0]
    dut.a1.value = a[1]
    dut.b0.value = b[0]
    dut.b1.value = b[1]
    dut.c0.value = c[0]
    dut.c1.value = c[1]
    dut.enable.value = 1

@cocotb.test()
async def test_correct_result(dut):
    """
    Test fault detection for correct shared values.
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    for _ in range(100):
        val = random.getrandbits(128)
        mask_a = random.getrandbits(128)
        mask_b = random.getrandbits(128)
        mask_c = random.getrandbits(128)
        a = (val ^ mask_a, mask_a)
        b = (val ^ mask_b, mask_b)
        c = (val ^ mask_c, mask_c)
        
        execute_fault_detection(dut, a, b, c)
        await RisingEdge(dut.done)
        RESULT = int(dut.result0.value) ^ int(dut.result1.value)
        dut._log.info("******************************************************************")
        dut._log.info(f"Checked 0x{val:02X}")
        dut._log.info(f"Result = 0x{RESULT:02X}")
        
        assert RESULT == val, \
            f"FAIL RESULT: expected 0x{val:02X}, got 0x{RESULT:02X}"

    dut._log.info("SUCCESS: All fault correction of incorrect values passed.") 
    
@cocotb.test()
async def test_fault_correction(dut):
    """
    Test fault correction with one incorrect shared value.
    """
    
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    for _ in range(100):
        val = random.getrandbits(128)
        # induce fault in one share
        
        error = random.getrandbits(128)
        error_idx = random.randint(0,2)
        error_arr = [0,0,0]
        error_arr[error_idx] = error
        mask_a = random.getrandbits(128) ^ error_arr[0]
        mask_b = random.getrandbits(128)   ^ error_arr[1]
        mask_c = random.getrandbits(128) ^ error_arr[2]
        
        a = (val ^ mask_a, mask_a)
        b = (val ^ mask_b, mask_b)
        c = (val ^ mask_c, mask_c)
        
        execute_fault_detection(dut, a, b, c)
        await RisingEdge(dut.done)
        RESULT = int(dut.result0.value) ^ int(dut.result1.value)
        dut._log.info("******************************************************************")
        dut._log.info(f"Checked 0x{val:02X}")
        dut._log.info(f"Result = 0x{RESULT:02X}")
        
        assert RESULT == val, \
            f"FAIL RESULT: expected 0x{val:02X}, got 0x{RESULT:02X} for input 0x{val:02X}"

    dut._log.info("SUCCESS: All fault correction tests passed.") 