import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, with_timeout
from cocotbext.uart import UartSource
import logging

# ============================================================================
# Helper Functions for Error Injection Testing
# ============================================================================

async def monitor_frame_error(dut, timeout_us=2000):
    """
    Monitor frame_error flag and return True if it pulses.

    This function must run concurrently with the test to catch the brief
    100ns pulse (1 clock cycle @ 10MHz). It samples frame_error on every
    rising edge of the system clock.

    Args:
        dut: Device under test
        timeout_us: Maximum time to wait in microseconds

    Returns:
        True if frame_error pulsed, False if timeout occurred
    """
    start_time = cocotb.utils.get_sim_time('us')

    while True:
        # Check if frame_error is high
        if dut.frame_error.value == 1:
            return True  # Error detected!

        # Wait for next clock edge
        await RisingEdge(dut.clk)

        # Check timeout
        current_time = cocotb.utils.get_sim_time('us')
        if current_time - start_time > timeout_us:
            return False  # Timeout without error

async def send_uart_byte_manual(dut, data_byte, valid_stop=True):
    """
    Manually construct and send UART byte bit-by-bit.

    This allows precise control over the UART frame, enabling injection
    of errors like invalid stop bits for testing.

    UART Frame: [START(0)] [D0] [D1] [D2] [D3] [D4] [D5] [D6] [D7] [STOP(1)]
    - Data bits are sent LSB-first
    - Start bit is always 0
    - Stop bit is normally 1, but can be set to 0 for error injection

    Args:
        dut: Device under test
        data_byte: 8-bit data to send (0x00-0xFF)
        valid_stop: If True, send stop bit as 1; if False, send as 0 (error)
    """
    BIT_PERIOD = 104.167  # microseconds (1/9600 baud)

    # Start bit (always 0)
    dut.rx_in.value = 0
    await Timer(BIT_PERIOD, unit="us")

    # Data bits (LSB first)
    for i in range(8):
        bit = (data_byte >> i) & 1
        dut.rx_in.value = bit
        await Timer(BIT_PERIOD, unit="us")

    # Stop bit (normally 1, but can inject 0 for error testing)
    dut.rx_in.value = 1 if valid_stop else 0
    await Timer(BIT_PERIOD, unit="us")

    # Return to idle (high)
    dut.rx_in.value = 1

async def verify_recovery(dut, uart_source, test_byte=0x42):
    """
    Send a valid byte and verify correct reception.

    This confirms the UART RX module has recovered from an error and
    can successfully receive subsequent valid frames.

    Args:
        dut: Device under test
        uart_source: UartSource instance for sending valid data
        test_byte: Byte to send for verification (default 0x42)

    Raises:
        AssertionError: If reception fails or frame_error is still high
    """
    await uart_source.write([test_byte])
    await with_timeout(RisingEdge(dut.ready), 2000, "us")

    assert dut.rx_out.value == test_byte, \
        f"Recovery failed: expected 0x{test_byte:02X}, got 0x{dut.rx_out.value:02X}"
    assert dut.frame_error.value == 0, \
        "frame_error still high after recovery"

# ============================================================================
# Test Cases
# ============================================================================

@cocotb.test()
async def test_uart_rx(dut):
    # Create logger for this test
    log = logging.getLogger("cocotb.test")
    log.setLevel(logging.INFO)

    log.info("=== UART RX Test Started ===")

    # Set up 10MHz clock (100ns period)
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    clock_uart = Clock(dut.clk_in, 6.5104, unit="us")
    cocotb.start_soon(clock_uart.start(start_high=False))

    uart_source = UartSource(dut.rx_in, baud=9600, bits=8, stop_bits=1)

    dut.en.value = 0
    dut.rst.value = 1
    await Timer(300, unit="ns")
    dut.rst.value = 0
    await Timer(300, unit="ns") 
    # Initialize input signals
    dut.en.value = 1

    test_data = [0x55, 0xaa, 0x00, 0xff, 0x12, 0x34]
    
    for byte in test_data:
        await uart_source.write([byte])
        await with_timeout(RisingEdge(dut.ready), 10000, "us")
        if dut.rx_out.value != byte:
            log.error(f"Expected: {byte:08b}, Actual: {dut.rx_out.value}")
            raise AssertionError(f"RX module did not receive the correct input.")
        else:
            log.info("Case {} passed".format(hex(byte)))

@cocotb.test()
async def test_uart_rx_start_bit_glitch(dut):
    """
    Test start bit glitch detection (half-point validation).

    Injects a brief glitch on the RX line that triggers the start bit
    detection but doesn't persist until the half-point check. This
    validates that the UART RX correctly rejects spurious noise spikes.

    Test sequence:
    1. Initialize DUT
    2. Inject brief glitch (15 microseconds low pulse)
    3. Verify frame_error pulses
    4. Verify ready never asserts
    5. Verify module recovers and can receive valid data

    Expected behavior:
    - Glitch (15us) triggers IDLE→WAIT transition
    - Half-point check (~45.6us) finds rxd=HIGH → frame_error
    - Module returns to IDLE, ready for next byte
    """
    log = logging.getLogger("cocotb.test")
    log.setLevel(logging.INFO)

    log.info("\n" + "="*70)
    log.info("=== UART RX Start Bit Glitch Test ===")
    log.info("="*70)

    # Set up clocks
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    clock_uart = Clock(dut.clk_in, 6.5104, unit="us")
    cocotb.start_soon(clock_uart.start(start_high=False))

    uart_source = UartSource(dut.rx_in, baud=9600, bits=8, stop_bits=1)

    # Reset DUT
    dut.en.value = 0
    dut.rst.value = 1
    await Timer(300, unit="ns")
    dut.rst.value = 0
    await Timer(300, unit="ns")
    dut.en.value = 1

    # Ensure line is idle (high)
    dut.rx_in.value = 1
    await Timer(100, unit="us")

    log.info("Injecting start bit glitch (15us low pulse)...")

    # Start monitoring for frame_error (runs concurrently)
    error_monitor = cocotb.start_soon(monitor_frame_error(dut, timeout_us=100))

    # Inject glitch: brief low pulse
    # Duration: 15us ≈ 2.3 UART clock cycles
    # This is long enough to trigger state transition but short enough
    # to be detected as invalid at half-point check (~45.6us)
    dut.rx_in.value = 0
    await Timer(15, unit="us")
    dut.rx_in.value = 1

    # Wait for error detection
    error_detected = await error_monitor

    # Verify frame_error was detected
    assert error_detected, \
        "frame_error did not pulse - glitch not detected!"

    log.info("✓ frame_error pulsed correctly")

    # Verify ready never asserted during error handling
    assert dut.ready.value == 0, \
        "ready asserted during error - should remain low!"

    log.info("✓ ready stayed low (no spurious data output)")

    # Wait for module to return to idle
    await Timer(100, unit="us")

    # Verify recovery: send valid byte
    log.info("Verifying recovery with valid byte (0x55)...")
    await verify_recovery(dut, uart_source, test_byte=0x55)

    log.info("✓ Module recovered successfully")
    log.info("="*70)
    log.info("=== Start Bit Glitch Test PASSED ===")
    log.info("="*70 + "\n")

@cocotb.test()
async def test_uart_rx_framing_error(dut):
    """
    Test framing error detection (invalid stop bit).

    Manually constructs a UART frame with a valid start bit and data bits
    but an invalid stop bit (0 instead of 1). This validates that the
    UART RX correctly detects corrupted frames and doesn't output bad data.

    Test sequence:
    1. Initialize DUT
    2. Manually send byte 0xA5 with invalid stop bit (0 instead of 1)
    3. Verify frame_error pulses
    4. Verify ready never asserts (or data is discarded)
    5. Verify module recovers and can receive valid data

    Expected behavior:
    - Frame processes normally until stop bit
    - Stop bit validation fails (majority vote = 0, should be 1)
    - frame_error pulses, module returns to IDLE
    - No corrupted data output
    """
    log = logging.getLogger("cocotb.test")
    log.setLevel(logging.INFO)

    log.info("\n" + "="*70)
    log.info("=== UART RX Framing Error Test ===")
    log.info("="*70)

    # Set up clocks
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    clock_uart = Clock(dut.clk_in, 6.5104, unit="us")
    cocotb.start_soon(clock_uart.start(start_high=False))

    uart_source = UartSource(dut.rx_in, baud=9600, bits=8, stop_bits=1)

    # Reset DUT
    dut.en.value = 0
    dut.rst.value = 1
    await Timer(300, unit="ns")
    dut.rst.value = 0
    await Timer(300, unit="ns")
    dut.en.value = 1

    # Ensure line is idle (high)
    dut.rx_in.value = 1
    await Timer(100, unit="us")

    log.info("Sending byte 0xA5 with INVALID stop bit (0 instead of 1)...")

    # Start monitoring for frame_error (runs concurrently)
    error_monitor = cocotb.start_soon(monitor_frame_error(dut, timeout_us=1200))

    # Send byte with invalid stop bit
    # 0xA5 = 10100101 binary (LSB first: 1,0,1,0,0,1,0,1)
    await send_uart_byte_manual(dut, data_byte=0xA5, valid_stop=False)

    # Wait for error detection
    error_detected = await error_monitor

    # Verify frame_error was detected
    assert error_detected, \
        "frame_error did not pulse - invalid stop bit not detected!"

    log.info("✓ frame_error pulsed correctly")

    # Verify ready never asserted (or data discarded)
    assert dut.ready.value == 0, \
        "ready asserted with invalid frame - should remain low!"

    log.info("✓ ready stayed low (corrupted data not output)")

    # Wait for module to return to idle
    await Timer(200, unit="us")

    # Verify recovery: send valid byte
    log.info("Verifying recovery with valid byte (0x42)...")
    await verify_recovery(dut, uart_source, test_byte=0x42)

    log.info("✓ Module recovered successfully")
    log.info("="*70)
    log.info("=== Framing Error Test PASSED ===")
    log.info("="*70 + "\n")

@cocotb.test()
async def test_uart_rx_multiple_errors(dut):
    """
    Test robust error handling under stress.

    Sends multiple errors in sequence to verify the UART RX handles
    repeated errors gracefully without getting stuck or accumulating state.

    Test sequence:
    1. Send 3 start bit glitches in rapid succession
    2. Send valid byte (should work)
    3. Send frame with invalid stop bit
    4. Send valid byte (should work)
    5. Verify frame_error pulsed exactly 4 times total

    Expected behavior:
    - Each error is detected independently
    - Valid frames are received correctly between errors
    - Module remains in working state throughout
    """
    log = logging.getLogger("cocotb.test")
    log.setLevel(logging.INFO)

    log.info("\n" + "="*70)
    log.info("=== UART RX Multiple Errors Test ===")
    log.info("="*70)

    # Set up clocks
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    clock_uart = Clock(dut.clk_in, 6.5104, unit="us")
    cocotb.start_soon(clock_uart.start(start_high=False))

    uart_source = UartSource(dut.rx_in, baud=9600, bits=8, stop_bits=1)

    # Reset DUT
    dut.en.value = 0
    dut.rst.value = 1
    await Timer(300, unit="ns")
    dut.rst.value = 0
    await Timer(300, unit="ns")
    dut.en.value = 1

    # Ensure line is idle (high)
    dut.rx_in.value = 1
    await Timer(100, unit="us")

    error_count = 0

    # Test 1: Three start bit glitches
    log.info("Sending 3 start bit glitches...")
    for i in range(3):
        error_monitor = cocotb.start_soon(monitor_frame_error(dut, timeout_us=100))
        dut.rx_in.value = 0
        await Timer(15, unit="us")
        dut.rx_in.value = 1
        await Timer(100, unit="us")

        error_detected = await error_monitor
        if error_detected:
            error_count += 1
            log.info(f"  ✓ Glitch {i+1} detected")

    assert error_count == 3, f"Expected 3 glitch errors, got {error_count}"

    # Test 2: Valid byte after glitches
    log.info("Sending valid byte 0x11...")
    await verify_recovery(dut, uart_source, test_byte=0x11)
    log.info("  ✓ Valid byte received correctly")

    # Test 3: Framing error
    log.info("Sending byte with invalid stop bit...")
    error_monitor = cocotb.start_soon(monitor_frame_error(dut, timeout_us=1200))
    await send_uart_byte_manual(dut, data_byte=0x33, valid_stop=False)
    error_detected = await error_monitor

    if error_detected:
        error_count += 1
        log.info("  ✓ Framing error detected")

    await Timer(200, unit="us")

    # Test 4: Valid byte after framing error
    log.info("Sending valid byte 0x22...")
    await verify_recovery(dut, uart_source, test_byte=0x22)
    log.info("  ✓ Valid byte received correctly")

    # Verify total error count
    assert error_count == 4, \
        f"Expected 4 total errors (3 glitches + 1 framing), got {error_count}"

    log.info("="*70)
    log.info(f"=== Multiple Errors Test PASSED (4/4 errors detected) ===")
    log.info("="*70 + "\n")
