import random

import cocotb
from cocotb.triggers import Timer


def unpack_state(state_int):
    """Convert 128-bit integer state into a 4x4 byte matrix"""
    matrix = [[0] * 4 for _ in range(4)]
    for col in range(4):
        for row in range(4):
            idx = col * 4 + row
            shift = 120 - idx * 8
            matrix[row][col] = (state_int >> shift) & 0xFF
    return matrix


def pack_state(matrix):
    """Convert 4x4 byte matrix back to 128-bit integer"""
    state_int = 0
    for col in range(4):
        for row in range(4):
            idx = col * 4 + row
            shift = 120 - idx * 8
            state_int |= (matrix[row][col] & 0xFF) << shift
    return state_int


def shift_rows_ref(matrix):
    """Reference AES ShiftRows (encrypt): left rotate row r by r."""
    shifted = [[0] * 4 for _ in range(4)]
    for row in range(4):
        for col in range(4):
            shifted[row][col] = matrix[row][(col + row) % 4]
    return shifted


def inv_shift_rows_ref(matrix):
    """Reference AES InvShiftRows (decrypt): right rotate row r by r."""
    shifted = [[0] * 4 for _ in range(4)]
    for row in range(4):
        for col in range(4):
            shifted[row][col] = matrix[row][(col - row) % 4]
    return shifted


@cocotb.test()
async def test_shift_rows_known_vector(dut):
    """ShiftRows with known vector"""
    input_matrix = [
        [0x00, 0x04, 0x08, 0x0C],
        [0x01, 0x05, 0x09, 0x0D],
        [0x02, 0x06, 0x0A, 0x0E],
        [0x03, 0x07, 0x0B, 0x0F],
    ]
    state_in = pack_state(input_matrix)

    dut.decrypt.value = 0
    dut.istate.value = state_in
    await Timer(1, units="ns")

    expected_enc = pack_state(shift_rows_ref(input_matrix))
    observed_enc = int(dut.ostate.value)
    
    assert observed_enc == expected_enc


@cocotb.test()
async def test_inv_shift_rows_known_vector(dut):
    """InvShiftRows with known vector"""
    input_matrix = [
        [0x00, 0x04, 0x08, 0x0C],
        [0x01, 0x05, 0x09, 0x0D],
        [0x02, 0x06, 0x0A, 0x0E],
        [0x03, 0x07, 0x0B, 0x0F],
    ]
    state_in = pack_state(input_matrix)

    dut.decrypt.value = 1
    dut.istate.value = state_in
    await Timer(1, units="ns")

    expected_dec = pack_state(inv_shift_rows_ref(input_matrix))
    observed_dec = int(dut.ostate.value)
    
    assert observed_dec == expected_dec


@cocotb.test()
async def test_shift_rows_roundtrip_known_vector(dut):
    """InvShiftRows(ShiftRows(x)) == x for known vector"""
    input_matrix = [
        [0x00, 0x04, 0x08, 0x0C],
        [0x01, 0x05, 0x09, 0x0D],
        [0x02, 0x06, 0x0A, 0x0E],
        [0x03, 0x07, 0x0B, 0x0F],
    ]
    state_in = pack_state(input_matrix)

    # First: ShiftRows
    dut.decrypt.value = 0
    dut.istate.value = state_in
    await Timer(1, units="ns")
    observed_enc = int(dut.ostate.value)

    # Then: InvShiftRows
    dut.decrypt.value = 1
    dut.istate.value = observed_enc
    await Timer(1, units="ns")
    roundtrip = int(dut.ostate.value)
    
    assert roundtrip == state_in


@cocotb.test()
async def test_shift_rows_random(dut):
    """ShiftRows with random state"""
    random.seed(0x1234)
    state_in = random.getrandbits(128)
    matrix_in = unpack_state(state_in)

    dut.decrypt.value = 0
    dut.istate.value = state_in
    await Timer(1, units="ns")

    expected_enc = pack_state(shift_rows_ref(matrix_in))
    observed_enc = int(dut.ostate.value)
    
    assert observed_enc == expected_enc


@cocotb.test()
async def test_inv_shift_rows_random(dut):
    """InvShiftRows with random state"""
    random.seed(0x5678)
    state_in = random.getrandbits(128)
    matrix_in = unpack_state(state_in)

    dut.decrypt.value = 1
    dut.istate.value = state_in
    await Timer(1, units="ns")

    expected_dec = pack_state(inv_shift_rows_ref(matrix_in))
    observed_dec = int(dut.ostate.value)
    
    assert observed_dec == expected_dec


@cocotb.test()
async def test_shift_rows_roundtrip_random(dut):
    """InvShiftRows(ShiftRows(x)) == x for random state"""
    random.seed(0xABCD)
    state_in = random.getrandbits(128)

    # First: ShiftRows
    dut.decrypt.value = 0
    dut.istate.value = state_in
    await Timer(1, units="ns")
    observed_enc = int(dut.ostate.value)

    # Then: InvShiftRows
    dut.decrypt.value = 1
    dut.istate.value = observed_enc
    await Timer(1, units="ns")
    roundtrip = int(dut.ostate.value)
    
    assert roundtrip == state_in


@cocotb.test()
async def test_shift_rows_multiple_random(dut):
    """ShiftRows with multiple random states"""
    random.seed(0xDEAD)
    
    for i in range(10):
        state_in = random.getrandbits(128)
        matrix_in = unpack_state(state_in)

        dut.decrypt.value = 0
        dut.istate.value = state_in
        await Timer(1, units="ns")

        expected_enc = pack_state(shift_rows_ref(matrix_in))
        observed_enc = int(dut.ostate.value)
        
        assert observed_enc == expected_enc, f"Failed on iteration {i}"


@cocotb.test()
async def test_inv_shift_rows_multiple_random(dut):
    """InvShiftRows with multiple random states"""
    random.seed(0xBEEF)
    
    for i in range(10):
        state_in = random.getrandbits(128)
        matrix_in = unpack_state(state_in)

        dut.decrypt.value = 1
        dut.istate.value = state_in
        await Timer(1, units="ns")

        expected_dec = pack_state(inv_shift_rows_ref(matrix_in))
        observed_dec = int(dut.ostate.value)
        
        assert observed_dec == expected_dec, f"Failed on iteration {i}"


@cocotb.test()
async def test_shift_rows_roundtrip_multiple_random(dut):
    """InvShiftRows(ShiftRows(x)) == x for multiple random states"""
    random.seed(0xCAFE)
    
    for i in range(10):
        state_in = random.getrandbits(128)

        # First: ShiftRows
        dut.decrypt.value = 0
        dut.istate.value = state_in
        await Timer(1, units="ns")
        observed_enc = int(dut.ostate.value)

        # Then: InvShiftRows
        dut.decrypt.value = 1
        dut.istate.value = observed_enc
        await Timer(1, units="ns")
        roundtrip = int(dut.ostate.value)
        
        assert roundtrip == state_in, f"Failed on iteration {i}"