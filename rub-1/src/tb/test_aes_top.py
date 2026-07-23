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
    dut.data_in_0.value = 0
    dut.data_in_1.value = 0
    dut.key_0.value = 0
    dut.key_1.value = 0
    dut.random_round.value = 0
    dut.random_ks.value = 0

    for _ in range(3):
        await RisingEdge(dut.clk)

    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def provide_randomness(dut):
    """Continuously provide fresh randomness on each clock cycle."""
    while True:
        await RisingEdge(dut.clk)
        dut.random_round.value = random.getrandbits(136)
        dut.random_ks.value = random.getrandbits(68)


async def run_aes(dut, data, key, encrypt=True):
    """
    Run AES encryption or decryption.

    Args:
        dut: Device under test
        data: 128-bit input data
        key: 128-bit key
        encrypt: True for encryption, False for decryption

    Returns:
        Tuple of (128-bit output, cycle count)
    """
    # Split inputs into shares
    data_mask = random.getrandbits(128)
    key_mask = random.getrandbits(128)

    dut.data_in_0.value = data ^ data_mask
    dut.data_in_1.value = data_mask
    dut.key_0.value = key ^ key_mask
    dut.key_1.value = key_mask
    dut.enc_mode.value = 1 if encrypt else 0

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
        if cycle_count > 700:
            raise TimeoutError("AES did not complete in 700 cycles")

    # Read and combine output shares
    out0 = int(dut.data_out_0.value)
    out1 = int(dut.data_out_1.value)

    return out0 ^ out1, cycle_count


# State machine state names for debug output (simplified state machine)
STATE_NAMES = {
    0: "IDLE",
    1: "KEY_EXPAND_FWD",
    2: "INIT_ADDKEY",
    3: "ROUND_PROCESS",
    4: "ROUND_ADDKEY",
    5: "DONE_STATE",
}


async def run_aes_debug(dut, data, key, encrypt=True, reference_states=None):
    """
    Run AES with detailed debug output, comparing against reference states.

    Args:
        dut: Device under test
        data: 128-bit input data
        key: 128-bit key
        encrypt: True for encryption, False for decryption
        reference_states: Optional list of (label, expected_state) from reference impl

    Returns:
        Tuple of (128-bit output, cycle count, list of state transitions)
    """
    mode_str = "ENCRYPT" if encrypt else "DECRYPT"
    print(f"\n{'='*70}")
    print(f"DEBUG: Running AES-128 {mode_str}")
    print(f"{'='*70}")
    print_state_matrix("Input data", data)
    print_state_matrix("Key", key)

    # Split inputs into shares (use zero mask for easier debugging)
    data_mask = 0  # Zero mask for debug visibility
    key_mask = 0

    dut.data_in_0.value = data ^ data_mask
    dut.data_in_1.value = data_mask
    dut.key_0.value = key ^ key_mask
    dut.key_1.value = key_mask
    dut.enc_mode.value = 1 if encrypt else 0

    # Pulse start
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for busy to go high
    while dut.busy.value != 1:
        await RisingEdge(dut.clk)

    # Track state transitions
    transitions = []
    last_state = -1
    last_round = -1
    last_col = -1
    cycle_count = 0

    # Reference state index for comparison
    ref_idx = 0 if reference_states else None

    while dut.done.value != 1:
        await RisingEdge(dut.clk)
        cycle_count += 1

        if cycle_count > 700:
            raise TimeoutError("AES did not complete in 700 cycles")

        # Read internal signals
        try:
            state_val = int(dut.state.value)
            round_ctr = int(dut.round_ctr.value)
            col_ctr = int(dut.col_ctr.value)
            state_0 = int(dut.state_0.value)
            state_1 = int(dut.state_1.value)
            rkey_0 = int(dut.rkey_0.value)
            rkey_1 = int(dut.rkey_1.value)
            ks_rdy = int(dut.ks_rdy.value)
            dp_rdy = int(dut.u_round_datapath.rdy.value)
            bypass_mc = int(dut.bypass_mc.value)
        except Exception as e:
            print(f"  [cycle {cycle_count}] Error reading signals: {e}")
            continue

        state_combined = state_0 ^ state_1
        rkey_combined = rkey_0 ^ rkey_1
        state_name = STATE_NAMES.get(state_val, f"UNKNOWN({state_val})")

        # Print on state transitions or round/column changes
        state_changed = state_val != last_state
        round_changed = round_ctr != last_round
        col_changed = col_ctr != last_col

        if state_changed or round_changed:
            print(f"\n[cycle {cycle_count:3d}] State: {state_name}, Round: {round_ctr}, Col: {col_ctr}")
            print(f"  ks_rdy={ks_rdy}, dp_rdy={dp_rdy}, bypass_mc={bypass_mc}")
            print(f"  state = {state_combined:032x}")
            print(f"  rkey  = {rkey_combined:032x}")

            # Record transition
            transitions.append({
                'cycle': cycle_count,
                'state': state_name,
                'round': round_ctr,
                'col': col_ctr,
                'state_val': state_combined,
                'rkey_val': rkey_combined,
            })

            # Compare with reference at key points
            if reference_states and not encrypt:
                if state_val == 3:  # INIT_ADDKEY - after initial AddRoundKey
                    pass  # State hasn't been updated yet
                elif state_val == 4 and col_ctr == 0 and state_changed:  # COLUMN_RESET start
                    # After INIT_ADDKEY or ROUND_ADDKEY, state should match reference
                    if ref_idx < len(reference_states):
                        ref_label, ref_state = reference_states[ref_idx]
                        if 'addkey' in ref_label:
                            if state_combined != ref_state:
                                print(f"  *** MISMATCH at {ref_label} ***")
                                print(f"      Expected: {ref_state:032x}")
                                print(f"      Got:      {state_combined:032x}")
                                print(f"      XOR diff: {state_combined ^ ref_state:032x}")
                            else:
                                print(f"  ✓ Matches {ref_label}")
                            ref_idx += 1

        last_state = state_val
        last_round = round_ctr
        last_col = col_ctr

    # Read and combine output shares
    out0 = int(dut.data_out_0.value)
    out1 = int(dut.data_out_1.value)
    result = out0 ^ out1

    print(f"\n{'='*70}")
    print(f"DEBUG: {mode_str} complete in {cycle_count} cycles")
    print_state_matrix("Output", result)

    return result, cycle_count, transitions


@cocotb.test()
async def test_reference_encryption(dut):
    """Verify Python reference encryption matches NIST test vector."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    result = aes_encrypt_reference(NIST_PLAINTEXT, NIST_KEY)
    assert result == NIST_CIPHERTEXT, (
        f"Reference encryption mismatch:\n"
        f"  Expected: {NIST_CIPHERTEXT:032x}\n"
        f"  Got:      {result:032x}"
    )
    print(f"Reference encryption verified: {NIST_PLAINTEXT:032x} -> {result:032x}")


@cocotb.test()
async def test_reference_decryption(dut):
    """Verify Python reference decryption matches NIST test vector."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    result = aes_decrypt_reference(NIST_CIPHERTEXT, NIST_KEY)
    assert result == NIST_PLAINTEXT, (
        f"Reference decryption mismatch:\n"
        f"  Expected: {NIST_PLAINTEXT:032x}\n"
        f"  Got:      {result:032x}"
    )
    print(f"Reference decryption verified: {NIST_CIPHERTEXT:032x} -> {result:032x}")


@cocotb.test()
async def test_encryption_nist(dut):
    """Test encryption against NIST FIPS 197 Appendix C.1 test vector."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(provide_randomness(dut))

    await reset_dut(dut)

    result, cycles = await run_aes(dut, NIST_PLAINTEXT, NIST_KEY, encrypt=True)

    assert result == NIST_CIPHERTEXT, (
        f"Encryption mismatch:\n"
        f"  Plaintext:  {NIST_PLAINTEXT:032x}\n"
        f"  Key:        {NIST_KEY:032x}\n"
        f"  Expected:   {NIST_CIPHERTEXT:032x}\n"
        f"  Got:        {result:032x}"
    )

    print(f"NIST encryption test passed in {cycles} cycles")
    print(f"  Plaintext:  {NIST_PLAINTEXT:032x}")
    print(f"  Key:        {NIST_KEY:032x}")
    print(f"  Ciphertext: {result:032x}")


@cocotb.test()
async def test_decryption_nist(dut):
    """Test decryption against NIST FIPS 197 Appendix C.1 test vector."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(provide_randomness(dut))

    await reset_dut(dut)

    result, cycles = await run_aes(dut, NIST_CIPHERTEXT, NIST_KEY, encrypt=False)

    assert result == NIST_PLAINTEXT, (
        f"Decryption mismatch:\n"
        f"  Ciphertext: {NIST_CIPHERTEXT:032x}\n"
        f"  Key:        {NIST_KEY:032x}\n"
        f"  Expected:   {NIST_PLAINTEXT:032x}\n"
        f"  Got:        {result:032x}"
    )

    print(f"NIST decryption test passed in {cycles} cycles")
    print(f"  Ciphertext: {NIST_CIPHERTEXT:032x}")
    print(f"  Key:        {NIST_KEY:032x}")
    print(f"  Plaintext:  {result:032x}")


@cocotb.test()
async def test_decryption_debug(dut):
    """Debug test for decryption - traces internal state vs reference."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(provide_randomness(dut))

    await reset_dut(dut)

    # Expected round keys for NIST key 000102030405060708090a0b0c0d0e0f
    expected_keys = [
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
    ]

    # Use zero masks for easier debugging
    dut.data_in_0.value = NIST_CIPHERTEXT
    dut.data_in_1.value = 0
    dut.key_0.value = NIST_KEY
    dut.key_1.value = 0
    dut.enc_mode.value = 0  # Decrypt

    # Pulse start
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for busy
    while dut.busy.value != 1:
        await RisingEdge(dut.clk)

    # Track key expansion during KEY_EXPAND_FWD
    print("\n=== Key Expansion Phase (K0→K10) ===")
    key_expand_count = 0
    cycle = 0
    last_state = -1
    last_ks_rdy = 0

    while True:
        await RisingEdge(dut.clk)
        cycle += 1

        if cycle > 700:
            raise TimeoutError("AES did not complete in 700 cycles")

        try:
            state_val = int(dut.state.value)
            ks_rdy = int(dut.ks_rdy.value)
            ks_start = int(dut.ks_start.value)
            ks_rcon = int(dut.ks_rcon.value)
            key_expand_ctr = int(dut.key_expand_ctr.value)
            rkey_0 = int(dut.rkey_0.value)
            rkey_1 = int(dut.rkey_1.value)
            rkey = rkey_0 ^ rkey_1
            ks_next_0 = int(dut.u_key_schedule.next_key_0.value)
            ks_next_1 = int(dut.u_key_schedule.next_key_1.value)
            ks_next = ks_next_0 ^ ks_next_1
            ks_state = int(dut.u_key_schedule.state.value)
        except Exception as e:
            print(f"  [cycle {cycle}] Error reading: {e}")
            continue

        state_name = STATE_NAMES.get(state_val, f"UNKNOWN({state_val})")

        # During KEY_EXPAND_FWD, track each key generated
        if state_val == 1:  # KEY_EXPAND_FWD
            # Print when ks_rdy rises
            if ks_rdy and not last_ks_rdy:
                key_expand_count += 1
                exp_key = expected_keys[key_expand_count] if key_expand_count <= 10 else 0
                match = "✓" if ks_next == exp_key else "✗"
                print(f"  [cycle {cycle}] ks_rdy↑: ks_next_key=K{key_expand_count}={ks_next:032x} (exp: {exp_key:032x}) {match}")
                if ks_next != exp_key:
                    print(f"    ks_state={ks_state}, key_expand_ctr={key_expand_ctr}, ks_rcon=0x{ks_rcon:02x}")
                    print(f"    rkey_0={rkey_0:032x}, rkey_1={rkey_1:032x}")
                    print(f"    ks_next_0={ks_next_0:032x}, ks_next_1={ks_next_1:032x}")

        last_ks_rdy = ks_rdy

        # After KEY_EXPAND_FWD completes
        if state_val == 2 and last_state == 1:  # Just entered INIT_ADDKEY
            print(f"\n=== INIT_ADDKEY: rkey (should be K10) = {rkey:032x} ===")
            print(f"    Expected K10: {expected_keys[10]:032x}")
            if rkey != expected_keys[10]:
                print(f"    ✗ MISMATCH!")

        # Track round keys during decryption rounds
        if state_val == 4 and last_state == 3:  # ROUND_ADDKEY after ROUND_PROCESS
            round_ctr = int(dut.round_ctr.value)
            exp_key_idx = 9 - round_ctr  # Round 0 uses K9, round 1 uses K8, etc.
            exp_key = expected_keys[exp_key_idx]
            try:
                ks_next = int(dut.u_key_schedule.next_key_0.value) ^ int(dut.u_key_schedule.next_key_1.value)
                print(f"Round {round_ctr} AddKey: ks_next_key={ks_next:032x} (expected K{exp_key_idx}={exp_key:032x})")
                if ks_next != exp_key:
                    print(f"    ✗ KEY MISMATCH!")
            except Exception:
                pass

        if state_val == 5:  # DONE_STATE
            break

        last_state = state_val

    # Read output
    out0 = int(dut.data_out_0.value)
    out1 = int(dut.data_out_1.value)
    result = out0 ^ out1

    print(f"\n=== Final Result ===")
    print(f"Output:   {result:032x}")
    print(f"Expected: {NIST_PLAINTEXT:032x}")
    if result != NIST_PLAINTEXT:
        print(f"✗ DECRYPTION FAILED!")
    else:
        print(f"✓ SUCCESS!")


@cocotb.test()
async def test_roundtrip(dut):
    """Test that decrypt(encrypt(plaintext)) == plaintext."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(provide_randomness(dut))

    await reset_dut(dut)

    # Random test data
    plaintext = random.getrandbits(128)
    key = random.getrandbits(128)

    # Encrypt
    ciphertext, enc_cycles = await run_aes(dut, plaintext, key, encrypt=True)
    print(f"Encryption: {plaintext:032x} -> {ciphertext:032x} ({enc_cycles} cycles)")

    # Reset between operations
    await reset_dut(dut)

    # Decrypt
    decrypted, dec_cycles = await run_aes(dut, ciphertext, key, encrypt=False)
    print(f"Decryption: {ciphertext:032x} -> {decrypted:032x} ({dec_cycles} cycles)")

    assert decrypted == plaintext, (
        f"Roundtrip mismatch:\n"
        f"  Original:  {plaintext:032x}\n"
        f"  Encrypted: {ciphertext:032x}\n"
        f"  Decrypted: {decrypted:032x}"
    )

    print(f"Roundtrip test passed!")
    print(f"  Total cycles: {enc_cycles + dec_cycles}")


@cocotb.test()
async def test_multiple_encryptions(dut):
    """Test multiple random encryptions against Python reference."""
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
