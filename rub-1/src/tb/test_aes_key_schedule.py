"""
AES Key Schedule Testbench

Tests for the AES-128 key schedule implementation using cocotb.
Validates key expansion against NIST FIPS 197 test vectors.

Test structure:
1. test_full_key_schedule - All 10 rounds of key expansion
2. test_reverse_key_schedule - Placeholder for decryption (not implemented)
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import random

# AES S-box (FIPS 197)
SBOX = (
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
)

# Round constants (FIPS 197)
RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36)

# NIST FIPS 197 Appendix A.1 test vector for AES-128
NIST_KEY = 0x2b7e151628aed2a6abf7158809cf4f3c
NIST_ROUND_KEYS = (
    0x2b7e151628aed2a6abf7158809cf4f3c,  # Round 0 (initial)
    0xa0fafe1788542cb123a339392a6c7605,  # Round 1
    0xf2c295f27a96b9435935807a7359f67f,  # Round 2
    0x3d80477d4716fe3e1e237e446d7a883b,  # Round 3
    0xef44a541a8525b7fb671253bdb0bad00,  # Round 4
    0xd4d1c6f87c839d87caf2b8bc11f915bc,  # Round 5
    0x6d88a37a110b3efddbf98641ca0093fd,  # Round 6
    0x4e54f70e5f5fc9f384a64fb24ea6dc4f,  # Round 7
    0xead27321b58dbad2312bf5607f8d292f,  # Round 8
    0xac7766f319fadc2128d12941575c006e,  # Round 9
    0xd014f9a8c9ee2589e13f0cc8b6630ca6,  # Round 10
)

# NIST FIPS 197 Appendix C.1 test vector for AES-128 (different key!)
NIST_C1_KEY = 0x000102030405060708090a0b0c0d0e0f
NIST_C1_ROUND_KEYS = (
    0x000102030405060708090a0b0c0d0e0f,  # K0
    0xd6aa74fdd2af72fadaa678f1d6ab76fe,  # K1
    0xb692cf0b643dbdf1be9bc5006830b3fe,  # K2
    0xb6ff744ed2c2c9bf6c590cbf0469bf41,  # K3
    0x47f7f7bc95353e03f96c32bcfd058dfd,  # K4
    0x3caaa3e8a99f9deb50f3af57adf622aa,  # K5
    0x5e390f7df7a69296a7553dc10aa31f6b,  # K6
    0x14f9701ae35fe28c440adf4d4ea9c026,  # K7
    0x47438735a41c65b9e016baf4aebf7ad2,  # K8
    0x549932d1f08557681093ed9cbe2c974e,  # K9
    0x13111d7fe3944a17f307a78b4d2b30c5,  # K10
)


def key_expansion_round(prev_key, rcon):
    """
    Reference implementation: compute one round of AES-128 key expansion.

    Args:
        prev_key: 128-bit previous round key
        rcon: Round constant for this round

    Returns:
        128-bit next round key
    """
    # Extract 32-bit words (W0, W1, W2, W3)
    w0 = (prev_key >> 96) & 0xFFFFFFFF
    w1 = (prev_key >> 64) & 0xFFFFFFFF
    w2 = (prev_key >> 32) & 0xFFFFFFFF
    w3 = prev_key & 0xFFFFFFFF

    # g-function on W3: RotWord + SubWord + Rcon
    # RotWord: rotate left by 1 byte
    rot = ((w3 << 8) | (w3 >> 24)) & 0xFFFFFFFF

    # SubWord: apply S-box to each byte
    sub = (
        (SBOX[(rot >> 24) & 0xFF] << 24) |
        (SBOX[(rot >> 16) & 0xFF] << 16) |
        (SBOX[(rot >> 8) & 0xFF] << 8) |
        SBOX[rot & 0xFF]
    )

    # XOR with Rcon (only affects MSB)
    g = sub ^ (rcon << 24)

    # Compute new words
    w0_new = w0 ^ g
    w1_new = w1 ^ w0_new
    w2_new = w2 ^ w1_new
    w3_new = w3 ^ w2_new

    return (w0_new << 96) | (w1_new << 64) | (w2_new << 32) | w3_new


def key_expansion_reverse(next_key, rcon):
    """
    Reference implementation: compute reverse key expansion (K_i → K_{i-1}).

    Used for decryption where we need to go backwards through the key schedule.

    Args:
        next_key: 128-bit round key K_i
        rcon: Round constant for this round (same as forward used)

    Returns:
        128-bit previous round key K_{i-1}
    """
    # Extract 32-bit words (W0', W1', W2', W3')
    w0_prime = (next_key >> 96) & 0xFFFFFFFF
    w1_prime = (next_key >> 64) & 0xFFFFFFFF
    w2_prime = (next_key >> 32) & 0xFFFFFFFF
    w3_prime = next_key & 0xFFFFFFFF

    # Reverse XOR chain (simple XORs, no S-box needed)
    # From forward: W3' = W3 ^ W2', so W3 = W3' ^ W2'
    # But W2' is not W2, it's the new W2. We need to unroll:
    # W3 = W3' ^ W2'
    # W2 = W2' ^ W1'
    # W1 = W1' ^ W0'
    w3 = w3_prime ^ w2_prime
    w2 = w2_prime ^ w1_prime
    w1 = w1_prime ^ w0_prime

    # g-function on reconstructed W3 (same as forward - uses forward S-box!)
    rot = ((w3 << 8) | (w3 >> 24)) & 0xFFFFFFFF
    sub = (
        (SBOX[(rot >> 24) & 0xFF] << 24) |
        (SBOX[(rot >> 16) & 0xFF] << 16) |
        (SBOX[(rot >> 8) & 0xFF] << 8) |
        SBOX[rot & 0xFF]
    )
    g = sub ^ (rcon << 24)

    # W0 = W0' ^ g(W3)
    w0 = w0_prime ^ g

    return (w0 << 96) | (w1 << 64) | (w2 << 32) | w3


async def reset_dut(dut):
    """Reset the DUT."""
    dut.rst.value = 1
    dut.start.value = 0
    dut.rcon.value = 0
    dut.reverse.value = 0
    dut.prev_key_0.value = 0
    dut.prev_key_1.value = 0
    dut.random_ks.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def run_key_expansion(dut, key, rcon):
    """
    Run one round of key expansion.

    Args:
        dut: Device under test
        key: 128-bit input key (will be split into shares)
        rcon: Round constant

    Returns:
        Tuple of (128-bit output key, cycle count)
    """
    # Split key into two random shares
    mask = random.getrandbits(128)
    share0 = key ^ mask
    share1 = mask

    # Set inputs
    dut.prev_key_0.value = share0
    dut.prev_key_1.value = share1
    dut.rcon.value = rcon
    dut.reverse.value = 0  # Forward mode
<<<<<<< HEAD
    dut.random_ks.value = random.getrandbits(168)
=======
    dut.random_ks.value = random.getrandbits(68)
>>>>>>> main

    # Pulse start
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for busy to go high (computation started)
    while dut.busy.value != 1:
        await RisingEdge(dut.clk)

    # Count cycles until completion
    cycle_count = 0
    while dut.rdy.value == 0:
        await RisingEdge(dut.clk)
        cycle_count += 1
        if cycle_count > 100:
            raise TimeoutError("Key schedule did not complete in 100 cycles")

    # Read and combine output shares
    out0 = int(dut.next_key_0.value)
    out1 = int(dut.next_key_1.value)

    return out0 ^ out1, cycle_count


async def run_key_expansion_reverse(dut, key, rcon):
    """
    Run one round of reverse key expansion (K_i → K_{i-1}).

    Args:
        dut: Device under test
        key: 128-bit input key K_i (will be split into shares)
        rcon: Round constant (same as forward round used)

    Returns:
        Tuple of (128-bit output key K_{i-1}, cycle count)
    """
    # Split key into two random shares
    mask = random.getrandbits(128)
    share0 = key ^ mask
    share1 = mask

    # Set inputs
    dut.prev_key_0.value = share0
    dut.prev_key_1.value = share1
    dut.rcon.value = rcon
    dut.reverse.value = 1  # Reverse mode
<<<<<<< HEAD
    dut.random_ks.value = random.getrandbits(168)
=======
    dut.random_ks.value = random.getrandbits(68)
>>>>>>> main

    # Pulse start
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for busy to go high (computation started)
    while dut.busy.value != 1:
        await RisingEdge(dut.clk)

    # Count cycles until completion
    cycle_count = 0
    while dut.rdy.value == 0:
        await RisingEdge(dut.clk)
        cycle_count += 1
        if cycle_count > 100:
            raise TimeoutError("Key schedule did not complete in 100 cycles")

    # Read and combine output shares
    out0 = int(dut.next_key_0.value)
    out1 = int(dut.next_key_1.value)

    return out0 ^ out1, cycle_count


@cocotb.test()
async def test_debug_sbox_bytes(dut):
    """
    Debug test: Check what S-box outputs we're actually getting.
    """
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # Reset
    await reset_dut(dut)

    # Use NIST key, no masking for simplicity
    key = NIST_KEY
    dut.prev_key_0.value = key
    dut.prev_key_1.value = 0  # No masking
    dut.rcon.value = RCON[0]
    dut.random_ks.value = 0  # No randomness

    # Pulse start
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for busy, then ready
    while dut.busy.value != 1:
        await RisingEdge(dut.clk)
    cycles = 0
    while dut.rdy.value == 0:
        await RisingEdge(dut.clk)
        cycles += 1

    # Read internal state (if accessible) or outputs
    out0 = int(dut.next_key_0.value)
    out1 = int(dut.next_key_1.value)
    result = out0 ^ out1

    print(f"Completed in {cycles} cycles")

    # Expected g-function components for NIST key:
    # W3 = 0x09cf4f3c
    # RotWord(W3) = 0xcf4f3c09
    # SubWord bytes: S[0xcf]=0x8a, S[0x4f]=0x84, S[0x3c]=0xeb, S[0x09]=0x01
    # g = 0x8b84eb01 (after XOR with rcon 0x01)

    print(f"Input key:    {key:032x}")
    print(f"W3:           {key & 0xFFFFFFFF:08x}")
    print(f"RotWord(W3):  {((key << 8) | (key >> 24)) & 0xFFFFFFFF:08x}")
    print(f"Output:       {result:032x}")
    print(f"Expected:     {NIST_ROUND_KEYS[1]:032x}")

    # Show the difference to help debug
    diff = result ^ NIST_ROUND_KEYS[1]
    print(f"XOR diff:     {diff:032x}")


@cocotb.test()
async def test_full_key_schedule(dut):
    """
    Test all 10 rounds of AES-128 key expansion using NIST test vector.
    """
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # Reset
    await reset_dut(dut)

    print(f"Initial key: {NIST_KEY:032x}")

    current_key = NIST_KEY
    total_cycles = 0

    for round_num in range(10):
        rcon = RCON[round_num]
        expected = NIST_ROUND_KEYS[round_num + 1]

        # Run hardware key expansion
        result, cycles = await run_key_expansion(dut, current_key, rcon)
        total_cycles += cycles

        # Verify against NIST test vector
        assert result == expected, (
            f"Round {round_num + 1} mismatch:\n"
            f"  Input:    {current_key:032x}\n"
            f"  Expected: {expected:032x}\n"
            f"  Got:      {result:032x}"
        )

        print(f"Round {round_num + 1}: {result:032x} (rcon=0x{rcon:02x}, {cycles} cycles)")

        # Use result as input for next round
        current_key = result

        # Small delay between rounds
        await RisingEdge(dut.clk)

    print(f"All 10 rounds passed! Total: {total_cycles} cycles ({total_cycles/10:.1f} avg per round)")


@cocotb.test()
async def test_reference_implementation(dut):
    """
    Verify Python reference implementation matches NIST test vectors.
    This ensures our reference is correct before comparing hardware against it.
    """
    # Start clock (required by cocotb even for pure Python test)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    current_key = NIST_KEY

    for round_num in range(10):
        rcon = RCON[round_num]
        expected = NIST_ROUND_KEYS[round_num + 1]

        result = key_expansion_round(current_key, rcon)

        assert result == expected, (
            f"Reference round {round_num + 1} mismatch:\n"
            f"  Expected: {expected:032x}\n"
            f"  Got:      {result:032x}"
        )

        current_key = result

    print("Reference implementation verified against NIST vectors!")


@cocotb.test()
async def test_reference_reverse(dut):
    """
    Verify Python reverse implementation matches NIST test vectors.
    This ensures our reference is correct before comparing hardware against it.
    """
    # Start clock (required by cocotb even for pure Python test)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    print("Verifying reverse reference: K_10 → K_0")

    current_key = NIST_ROUND_KEYS[10]

    for round_num in range(10, 0, -1):
        rcon = RCON[round_num - 1]
        expected = NIST_ROUND_KEYS[round_num - 1]

        result = key_expansion_reverse(current_key, rcon)

        assert result == expected, (
            f"Reference reverse {round_num} → {round_num-1} mismatch:\n"
            f"  Input:    {current_key:032x}\n"
            f"  Expected: {expected:032x}\n"
            f"  Got:      {result:032x}"
        )

        current_key = result

    assert current_key == NIST_KEY, "Did not recover original key!"
    print("Reference reverse implementation verified against NIST vectors!")


@cocotb.test()
async def test_key_schedule_nist_c1(dut):
    """
    Test key expansion with NIST Appendix C.1 key (0x000102030405060708090a0b0c0d0e0f).
    This is the key used by aes_top tests.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    print(f"Testing NIST Appendix C.1 key: {NIST_C1_KEY:032x}")

    current_key = NIST_C1_KEY
    total_cycles = 0

    for round_num in range(10):
        rcon = RCON[round_num]
        expected = NIST_C1_ROUND_KEYS[round_num + 1]

        result, cycles = await run_key_expansion(dut, current_key, rcon)
        total_cycles += cycles

        assert result == expected, (
            f"Round {round_num + 1} mismatch:\n"
            f"  Input:    {current_key:032x}\n"
            f"  Expected: {expected:032x}\n"
            f"  Got:      {result:032x}"
        )

        print(f"K{round_num} -> K{round_num + 1}: {result:032x} (rcon=0x{rcon:02x}) ✓")
        current_key = result
        await RisingEdge(dut.clk)

    print(f"NIST C.1 key expansion: all 10 rounds passed!")


@cocotb.test()
async def test_reverse_key_schedule(dut):
    """
    Test reverse key expansion for decryption: K_10 → K_9 → ... → K_0.

    Uses the hardware reverse mode to compute previous round keys from
    later ones, verifying against NIST test vectors.
    """
    # Start clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # Reset
    await reset_dut(dut)

    print("Testing reverse key schedule (K_10 → K_0)")

    # Start from round 10 key, work backwards
    current_key = NIST_ROUND_KEYS[10]
    total_cycles = 0

    for round_num in range(10, 0, -1):
        rcon = RCON[round_num - 1]  # Same Rcon as forward used
        expected = NIST_ROUND_KEYS[round_num - 1]

        # Run hardware reverse key expansion
        result, cycles = await run_key_expansion_reverse(dut, current_key, rcon)
        total_cycles += cycles

        # Verify against NIST test vector
        assert result == expected, (
            f"Reverse round {round_num} → {round_num-1} mismatch:\n"
            f"  Input:    {current_key:032x}\n"
            f"  Expected: {expected:032x}\n"
            f"  Got:      {result:032x}"
        )

        print(f"K_{round_num} → K_{round_num-1}: {result:032x} (rcon=0x{rcon:02x}, {cycles} cycles)")

        # Use result as input for next round
        current_key = result

        # Small delay between rounds
        await RisingEdge(dut.clk)

    assert current_key == NIST_KEY, "Did not recover original key!"
    print(f"Reverse key schedule: all 10 rounds passed! Total: {total_cycles} cycles")
