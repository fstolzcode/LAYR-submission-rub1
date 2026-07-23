import random
import cocotb
from cocotb.triggers import Timer


# ---------------- helpers ----------------

def unpack_state(state_int):
    matrix = [[0] * 4 for _ in range(4)]
    for col in range(4):
        for row in range(4):
            idx = col * 4 + row
            shift = 120 - idx * 8
            matrix[row][col] = (state_int >> shift) & 0xFF
    return matrix


def pack_state(matrix):
    state_int = 0
    for col in range(4):
        for row in range(4):
            idx = col * 4 + row
            shift = 120 - idx * 8
            state_int |= (matrix[row][col] & 0xFF) << shift
    return state_int


def xtime(b):
    return (((b << 1) & 0xFF) ^ (0x1B if b & 0x80 else 0)) & 0xFF


def mul(b, f):
    if f == 1:  return b
    if f == 2:  return xtime(b)
    if f == 3:  return xtime(b) ^ b
    if f == 9:  return xtime(xtime(xtime(b))) ^ b
    if f == 11: return xtime(xtime(xtime(b))) ^ xtime(b) ^ b
    if f == 13: return xtime(xtime(xtime(b))) ^ xtime(xtime(b)) ^ b
    if f == 14: return xtime(xtime(xtime(b))) ^ xtime(xtime(b)) ^ xtime(b)
    raise ValueError("bad factor")


def mix_single_column(c):
    a0, a1, a2, a3 = c
    return [
        mul(a0, 2) ^ mul(a1, 3) ^ mul(a2, 1) ^ mul(a3, 1),
        mul(a0, 1) ^ mul(a1, 2) ^ mul(a2, 3) ^ mul(a3, 1),
        mul(a0, 1) ^ mul(a1, 1) ^ mul(a2, 2) ^ mul(a3, 3),
        mul(a0, 3) ^ mul(a1, 1) ^ mul(a2, 1) ^ mul(a3, 2),
    ]


def inv_mix_single_column(c):
    a0, a1, a2, a3 = c
    return [
        mul(a0, 14) ^ mul(a1, 11) ^ mul(a2, 13) ^ mul(a3, 9),
        mul(a0, 9)  ^ mul(a1, 14) ^ mul(a2, 11) ^ mul(a3, 13),
        mul(a0, 13) ^ mul(a1, 9)  ^ mul(a2, 14) ^ mul(a3, 11),
        mul(a0, 11) ^ mul(a1, 13) ^ mul(a2, 9)  ^ mul(a3, 14),
    ]


def mix_columns_ref(m):
    out = [[0] * 4 for _ in range(4)]
    for col in range(4):
        nc = mix_single_column([m[r][col] for r in range(4)])
        for r in range(4):
            out[r][col] = nc[r]
    return out


def inv_mix_columns_ref(m):
    out = [[0] * 4 for _ in range(4)]
    for col in range(4):
        nc = inv_mix_single_column([m[r][col] for r in range(4)])
        for r in range(4):
            out[r][col] = nc[r]
    return out


# ---------------- tests ----------------

@cocotb.test()
async def test_mixcolumns_known_vector(dut):
    """MixColumns FIPS-197 known vector"""
    input_matrix = [
        [0xD4, 0xE0, 0xB8, 0x1E],
        [0xBF, 0xB4, 0x41, 0x27],
        [0x5D, 0x52, 0x11, 0x98],
        [0x30, 0xAE, 0xF1, 0xE5],
    ]
    expected_matrix = [
        [0x04, 0xE0, 0x48, 0x28],
        [0x66, 0xCB, 0xF8, 0x06],
        [0x81, 0x19, 0xD3, 0x26],
        [0xE5, 0x9A, 0x7A, 0x4C],
    ]

    dut.decrypt.value = 0
    dut.istate.value = pack_state(input_matrix)
    await Timer(1, units="ns")

    assert int(dut.ostate.value) == pack_state(expected_matrix)


@cocotb.test()
async def test_invmixcolumns_known_vector_roundtrip(dut):
    """InvMixColumns(MixColumns(x)) == x for known vector"""
    input_matrix = [
        [0xD4, 0xE0, 0xB8, 0x1E],
        [0xBF, 0xB4, 0x41, 0x27],
        [0x5D, 0x52, 0x11, 0x98],
        [0x30, 0xAE, 0xF1, 0xE5],
    ]

    state = pack_state(input_matrix)

    dut.decrypt.value = 0
    dut.istate.value = state
    await Timer(1, units="ns")
    mix_out = int(dut.ostate.value)

    dut.decrypt.value = 1
    dut.istate.value = mix_out
    await Timer(1, units="ns")

    assert int(dut.ostate.value) == state


@cocotb.test()
async def test_mixcolumns_random(dut):
    """MixColumns on random input"""
    random.seed(0xACE)
    state = random.getrandbits(128)

    dut.decrypt.value = 0
    dut.istate.value = state
    await Timer(1, units="ns")

    expected = pack_state(mix_columns_ref(unpack_state(state)))
    assert int(dut.ostate.value) == expected


@cocotb.test()
async def test_invmixcolumns_random(dut):
    """InvMixColumns on random input"""
    random.seed(0xBEEF)
    state = random.getrandbits(128)

    dut.decrypt.value = 1
    dut.istate.value = state
    await Timer(1, units="ns")

    expected = pack_state(inv_mix_columns_ref(unpack_state(state)))
    assert int(dut.ostate.value) == expected


@cocotb.test()
async def test_roundtrip_inv_after_mix(dut):
    """InvMixColumns(MixColumns(x)) == x"""
    state = random.getrandbits(128)

    dut.decrypt.value = 0
    dut.istate.value = state
    await Timer(1, units="ns")
    mix_out = int(dut.ostate.value)

    dut.decrypt.value = 1
    dut.istate.value = mix_out
    await Timer(1, units="ns")

    assert int(dut.ostate.value) == state


@cocotb.test()
async def test_roundtrip_mix_after_inv(dut):
    """MixColumns(InvMixColumns(x)) == x"""
    state = random.getrandbits(128)

    dut.decrypt.value = 1
    dut.istate.value = state
    await Timer(1, units="ns")
    inv_out = int(dut.ostate.value)

    dut.decrypt.value = 0
    dut.istate.value = inv_out
    await Timer(1, units="ns")

    assert int(dut.ostate.value) == state
