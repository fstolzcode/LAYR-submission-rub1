#Simplified testbench for rc522

from collections import defaultdict
import cocotb
#from test_rc522_controller import *
from test_rc522_controller import RC522Model
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout
import logging

async def wait_for_main_state(dut, timeout_us, state_num):
    for _ in range(timeout_us):   
        if int(dut.main_state.value) == state_num:
            return
        await Timer(1, units="us")
    raise cocotb.result.SimTimeoutError("dut.rdy did not become 1 in time")

async def wait_for_init_state(dut, timeout_us, state_num):
    for _ in range(timeout_us):    
        cocotb.log.info(f"init_state_reg: {int(dut.init_state_reg.value):02X}, waiting for {state_num:02X}")
        if int(dut.init_state_reg.value) == state_num:
            return
        await Timer(1, units="us")
    raise cocotb.result.SimTimeoutError(f"state_num did not reach {state_num}")

async def next_state(dut, timout_us):
    current_state = int(dut.cnt.value)
    for _ in range(timeout_us):     
        await RisingEdge(du.clk)
        if int(dut.cnt.value) == current_state + 1:
            return dut.cnt.value
    raise cocotb.result.SimTimeoutError("cnt did not increase")

@cocotb.test()
async def test_simple_rc522_hw_init(dut):
    cocotb.start_soon(Clock(dut.clk, 100, units="ns").start())

    dut.rst.value = 0
    dut.setup_transaction.value = 0
    dut.start_transaction.value = 0
    dut.read_next_byte.value = 0
    dut.data_in.value = 0
    dut.num_bytes.value = 0
    dut.len_last_byte.value = 0

    rc522_model = RC522Model(
         sclk = dut.spi_master_inst.spi_sclk,
         cs_n = dut.spi_master_inst.spi_cs_1,
         mosi = dut.spi_master_inst.spi_mosi,
         miso = dut.spi_master_inst.spi_miso,
     )
    rc522_model.verbose_spi = True
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # Reset
    dut.rst.value = 1
    dut.spi_rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    dut.spi_rst.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await wait_for_init_state(dut, timeout_us=500000, state_num=0xFF)

    # check all the registers
    assert rc522_model.registers[0x2B] == 0xA9 
    assert rc522_model.registers[0x2C] == 0x03
    assert rc522_model.registers[0x2D] == 0xE8 
    assert rc522_model.registers[0x12] == 0 #we want this 0
    assert rc522_model.registers[0x13] == 0 #we want this 0
    assert rc522_model.registers[0x11] == 0x3D
    assert rc522_model.registers[0x15] == 0x40
    assert rc522_model.registers[0x26] == 0x58
    assert rc522_model.registers[0x18] == 0x86 
    assert rc522_model.registers[0x14] == 0x83

@cocotb.test()
async def test_simple_rc522_transaction(dut):
    cocotb.start_soon(Clock(dut.clk, 100, units="ns").start())

    rc522_model = RC522Model(
         sclk = dut.spi_master_inst.spi_sclk,
         cs_n = dut.spi_master_inst.spi_cs_1,
         mosi = dut.spi_master_inst.spi_mosi,
         miso = dut.spi_master_inst.spi_miso,
     )
    rc522_model.verbose_spi = True
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # Reset
    dut.rst.value = 1
    dut.spi_rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    dut.spi_rst.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    # initialize
    await wait_for_init_state(dut, timeout_us=500000, state_num=0xFF)
    await wait_for_main_state(dut, timeout_us=500000, state_num=1)
    #now do a transaction
    dut.data_in = 0x26 << 504; 
    dut.len_last_byte = 7;
    dut.num_bytes = 1;
    dut.setup_transaction = 1
    await RisingEdge(dut.clk)
    await wait_for_main_state(dut, timeout_us=500000, state_num = 2)
    dut.start_transaction = 1
    await wait_for_main_state(dut, timeout_us=500000, state_num = 3)
    dut.read_next_byte = 1
    await wait_for_main_state(dut, timeout_us=500000, state_num = 1)

