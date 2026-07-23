import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, with_timeout
from cocotbext.uart import UartSink
import logging

@cocotb.test()
async def test_ocdc_controller_unlock(dut):
    # Create logger for this test
    log = logging.getLogger("cocotb.test")
    log.setLevel(logging.INFO)

    log.info("=== UART TX Test Started ===")

    # Set up 10MHz clock (100ns period)
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    clock_uart = Clock(dut.clk_in, 6.5104, unit="us")
    cocotb.start_soon(clock_uart.start(start_high=False))

    uart_sink = UartSink(dut.tx_out, baud=9600, bits=8)

    # Initialize input signals
    dut.en.value = 0

    test_data = [0x55, 0xaa, 0x00, 0xff, 0x12, 0x34]
    for byte in test_data:
        await RisingEdge(dut.ready)

        dut.en.value = 1
        dut.tx_in.value = byte

    await RisingEdge(dut.ready)
    dut.en.value = 0

    received_data = await with_timeout(uart_sink.read(count=len(test_data)), 200000, "us")
    if list(received_data) != test_data:
        raise AssertionError(f"UART sink did not receive the same input data")
