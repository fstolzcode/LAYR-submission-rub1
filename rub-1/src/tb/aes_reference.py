"""
AES-128 Top-Level Testbench

Tests for the round-based masked AES-128 implementation using cocotb.
Validates encryption and decryption against NIST FIPS 197 test vectors.
"""

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

# Inverse S-box
INV_SBOX = (
    0x52, 0x09, 0x6a, 0xd5, 0x30, 0x36, 0xa5, 0x38, 0xbf, 0x40, 0xa3, 0x9e, 0x81, 0xf3, 0xd7, 0xfb,
    0x7c, 0xe3, 0x39, 0x82, 0x9b, 0x2f, 0xff, 0x87, 0x34, 0x8e, 0x43, 0x44, 0xc4, 0xde, 0xe9, 0xcb,
    0x54, 0x7b, 0x94, 0x32, 0xa6, 0xc2, 0x23, 0x3d, 0xee, 0x4c, 0x95, 0x0b, 0x42, 0xfa, 0xc3, 0x4e,
    0x08, 0x2e, 0xa1, 0x66, 0x28, 0xd9, 0x24, 0xb2, 0x76, 0x5b, 0xa2, 0x49, 0x6d, 0x8b, 0xd1, 0x25,
    0x72, 0xf8, 0xf6, 0x64, 0x86, 0x68, 0x98, 0x16, 0xd4, 0xa4, 0x5c, 0xcc, 0x5d, 0x65, 0xb6, 0x92,
    0x6c, 0x70, 0x48, 0x50, 0xfd, 0xed, 0xb9, 0xda, 0x5e, 0x15, 0x46, 0x57, 0xa7, 0x8d, 0x9d, 0x84,
    0x90, 0xd8, 0xab, 0x00, 0x8c, 0xbc, 0xd3, 0x0a, 0xf7, 0xe4, 0x58, 0x05, 0xb8, 0xb3, 0x45, 0x06,
    0xd0, 0x2c, 0x1e, 0x8f, 0xca, 0x3f, 0x0f, 0x02, 0xc1, 0xaf, 0xbd, 0x03, 0x01, 0x13, 0x8a, 0x6b,
    0x3a, 0x91, 0x11, 0x41, 0x4f, 0x67, 0xdc, 0xea, 0x97, 0xf2, 0xcf, 0xce, 0xf0, 0xb4, 0xe6, 0x73,
    0x96, 0xac, 0x74, 0x22, 0xe7, 0xad, 0x35, 0x85, 0xe2, 0xf9, 0x37, 0xe8, 0x1c, 0x75, 0xdf, 0x6e,
    0x47, 0xf1, 0x1a, 0x71, 0x1d, 0x29, 0xc5, 0x89, 0x6f, 0xb7, 0x62, 0x0e, 0xaa, 0x18, 0xbe, 0x1b,
    0xfc, 0x56, 0x3e, 0x4b, 0xc6, 0xd2, 0x79, 0x20, 0x9a, 0xdb, 0xc0, 0xfe, 0x78, 0xcd, 0x5a, 0xf4,
    0x1f, 0xdd, 0xa8, 0x33, 0x88, 0x07, 0xc7, 0x31, 0xb1, 0x12, 0x10, 0x59, 0x27, 0x80, 0xec, 0x5f,
    0x60, 0x51, 0x7f, 0xa9, 0x19, 0xb5, 0x4a, 0x0d, 0x2d, 0xe5, 0x7a, 0x9f, 0x93, 0xc9, 0x9c, 0xef,
    0xa0, 0xe0, 0x3b, 0x4d, 0xae, 0x2a, 0xf5, 0xb0, 0xc8, 0xeb, 0xbb, 0x3c, 0x83, 0x53, 0x99, 0x61,
    0x17, 0x2b, 0x04, 0x7e, 0xba, 0x77, 0xd6, 0x26, 0xe1, 0x69, 0x14, 0x63, 0x55, 0x21, 0x0c, 0x7d,
)

# Round constants
RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36)

# NIST FIPS 197 Appendix C.1 test vector for AES-128
NIST_KEY = 0x000102030405060708090a0b0c0d0e0f
NIST_PLAINTEXT = 0x00112233445566778899aabbccddeeff
NIST_CIPHERTEXT = 0x69c4e0d86a7b0430d8cdb78070b4c55a


def xtime(b):
    """Multiply by 2 in GF(2^8)."""
    return ((b << 1) ^ 0x1b) & 0xff if b & 0x80 else (b << 1) & 0xff


def mul4(b):
    """Multiply by 4 in GF(2^8)."""
    return xtime(xtime(b))


def mix_column(col):
    """Apply MixColumns to a single column (4 bytes)."""
    a0 = (col >> 24) & 0xff
    a1 = (col >> 16) & 0xff
    a2 = (col >> 8) & 0xff
    a3 = col & 0xff

    s = a0 ^ a1 ^ a2 ^ a3

    m0 = s ^ xtime(a0 ^ a1) ^ a0
    m1 = s ^ xtime(a1 ^ a2) ^ a1
    m2 = s ^ xtime(a2 ^ a3) ^ a2
    m3 = s ^ xtime(a3 ^ a0) ^ a3

    return (m0 << 24) | (m1 << 16) | (m2 << 8) | m3


def inv_mix_column(col):
    """Apply InvMixColumns to a single column (4 bytes)."""
    m0 = (col >> 24) & 0xff
    m1 = (col >> 16) & 0xff
    m2 = (col >> 8) & 0xff
    m3 = col & 0xff

    p0 = mul4(m0)
    p1 = mul4(m1)
    p2 = mul4(m2)
    p3 = mul4(m3)

    t02 = p0 ^ p2
    t13 = p1 ^ p3

    b0 = t02 ^ m0
    b1 = t13 ^ m1
    b2 = t02 ^ m2
    b3 = t13 ^ m3

    return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3


def aes_encrypt_reference(plaintext, key):
    """Reference AES-128 encryption."""
    # Convert to state array (column-major)
    state = plaintext

    # Key expansion
    round_keys = [key]
    for i in range(10):
        w0 = (round_keys[-1] >> 96) & 0xffffffff
        w1 = (round_keys[-1] >> 64) & 0xffffffff
        w2 = (round_keys[-1] >> 32) & 0xffffffff
        w3 = round_keys[-1] & 0xffffffff

        # g-function
        rot = ((w3 << 8) | (w3 >> 24)) & 0xffffffff
        sub = (SBOX[(rot >> 24) & 0xff] << 24) | (SBOX[(rot >> 16) & 0xff] << 16) | \
              (SBOX[(rot >> 8) & 0xff] << 8) | SBOX[rot & 0xff]
        g = sub ^ (RCON[i] << 24)

        w0_new = w0 ^ g
        w1_new = w1 ^ w0_new
        w2_new = w2 ^ w1_new
        w3_new = w3 ^ w2_new

        round_keys.append((w0_new << 96) | (w1_new << 64) | (w2_new << 32) | w3_new)

    # Initial AddRoundKey
    state ^= round_keys[0]

    for rnd in range(10):
        # SubBytes
        new_state = 0
        for i in range(16):
            byte = (state >> (120 - i*8)) & 0xff
            new_state |= SBOX[byte] << (120 - i*8)
        state = new_state

        # ShiftRows (row 0: no shift, row 1: shift 1, row 2: shift 2, row 3: shift 3)
        # State is column-major: [c0_r0, c0_r1, c0_r2, c0_r3, c1_r0, ...]
        def get_byte(s, row, col):
            return (s >> (120 - (col*4 + row)*8)) & 0xff

        def set_byte(row, col, val):
            return val << (120 - (col*4 + row)*8)

        new_state = 0
        for col in range(4):
            new_state |= set_byte(0, col, get_byte(state, 0, col))
            new_state |= set_byte(1, col, get_byte(state, 1, (col + 1) % 4))
            new_state |= set_byte(2, col, get_byte(state, 2, (col + 2) % 4))
            new_state |= set_byte(3, col, get_byte(state, 3, (col + 3) % 4))
        state = new_state

        # MixColumns (skip in last round)
        if rnd < 9:
            new_state = 0
            for col in range(4):
                col_val = (state >> (96 - col*32)) & 0xffffffff
                mixed = mix_column(col_val)
                new_state |= mixed << (96 - col*32)
            state = new_state

        # AddRoundKey
        state ^= round_keys[rnd + 1]

    return state


def aes_decrypt_reference(ciphertext, key):
    """Reference AES-128 decryption (equivalent inverse cipher)."""
    state = ciphertext

    # Key expansion (forward to get all keys)
    round_keys = [key]
    for i in range(10):
        w0 = (round_keys[-1] >> 96) & 0xffffffff
        w1 = (round_keys[-1] >> 64) & 0xffffffff
        w2 = (round_keys[-1] >> 32) & 0xffffffff
        w3 = round_keys[-1] & 0xffffffff

        rot = ((w3 << 8) | (w3 >> 24)) & 0xffffffff
        sub = (SBOX[(rot >> 24) & 0xff] << 24) | (SBOX[(rot >> 16) & 0xff] << 16) | \
              (SBOX[(rot >> 8) & 0xff] << 8) | SBOX[rot & 0xff]
        g = sub ^ (RCON[i] << 24)

        w0_new = w0 ^ g
        w1_new = w1 ^ w0_new
        w2_new = w2 ^ w1_new
        w3_new = w3 ^ w2_new

        round_keys.append((w0_new << 96) | (w1_new << 64) | (w2_new << 32) | w3_new)

    # Initial AddRoundKey with k10
    state ^= round_keys[10]

    for rnd in range(10):
        round_key = round_keys[9 - rnd]

        # InvSubBytes
        new_state = 0
        for i in range(16):
            byte = (state >> (120 - i*8)) & 0xff
            new_state |= INV_SBOX[byte] << (120 - i*8)
        state = new_state

        # InvShiftRows
        def get_byte(s, row, col):
            return (s >> (120 - (col*4 + row)*8)) & 0xff

        def set_byte(row, col, val):
            return val << (120 - (col*4 + row)*8)

        new_state = 0
        for col in range(4):
            new_state |= set_byte(0, col, get_byte(state, 0, col))
            new_state |= set_byte(1, col, get_byte(state, 1, (col - 1) % 4))
            new_state |= set_byte(2, col, get_byte(state, 2, (col - 2) % 4))
            new_state |= set_byte(3, col, get_byte(state, 3, (col - 3) % 4))
        state = new_state

        # InvMixColumns (skip in last round)
        if rnd < 9:
            # For equivalent inverse cipher, apply InvMixColumns to round key
            processed_key = 0
            for col in range(4):
                col_val = (round_key >> (96 - col*32)) & 0xffffffff
                imc = inv_mix_column(mix_column(col_val))
                processed_key |= imc << (96 - col*32)
            round_key = processed_key

            new_state = 0
            for col in range(4):
                col_val = (state >> (96 - col*32)) & 0xffffffff
                imc = inv_mix_column(mix_column(col_val))
                new_state |= imc << (96 - col*32)
            state = new_state

        # AddRoundKey
        state ^= round_key

    return state


# =========================================================================
# Debug Helper Functions
# =========================================================================

def print_state_matrix(label, state_val):
    """Print 128-bit value as a 4x4 AES state matrix (column-major)."""
    print(f"{label}:")
    print(f"  hex: {state_val:032x}")
    # Column-major: state[127:96]=col0, state[95:64]=col1, etc.
    # Each column: [31:24]=row0, [23:16]=row1, [15:8]=row2, [7:0]=row3
    for row in range(4):
        row_bytes = []
        for col in range(4):
            byte_val = (state_val >> (120 - (col*32 + row*8))) & 0xff
            row_bytes.append(f"{byte_val:02x}")
        print(f"  row{row}: {' '.join(row_bytes)}")


def get_nist_round_keys():
    """Return NIST test vector round keys K0-K10."""
    return [
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
        0x13111d7fe3944a17f307a78b4d2b30c5,  # K10 - this is different from key schedule test
    ]


def aes_decrypt_reference_detailed(ciphertext, key, debug=False):
    """
    Reference AES-128 decryption with detailed round-by-round output.
    Uses equivalent inverse cipher structure matching the hardware.

    Returns: (plaintext, round_states) where round_states is a list of intermediate values
    """
    state = ciphertext
    round_states = []

    # Key expansion (forward to get all keys)
    round_keys = [key]
    for i in range(10):
        w0 = (round_keys[-1] >> 96) & 0xffffffff
        w1 = (round_keys[-1] >> 64) & 0xffffffff
        w2 = (round_keys[-1] >> 32) & 0xffffffff
        w3 = round_keys[-1] & 0xffffffff

        rot = ((w3 << 8) | (w3 >> 24)) & 0xffffffff
        sub = (SBOX[(rot >> 24) & 0xff] << 24) | (SBOX[(rot >> 16) & 0xff] << 16) | \
              (SBOX[(rot >> 8) & 0xff] << 8) | SBOX[rot & 0xff]
        g = sub ^ (RCON[i] << 24)

        w0_new = w0 ^ g
        w1_new = w1 ^ w0_new
        w2_new = w2 ^ w1_new
        w3_new = w3 ^ w2_new

        round_keys.append((w0_new << 96) | (w1_new << 64) | (w2_new << 32) | w3_new)

    if debug:
        print("\n=== Reference Decryption (Equivalent Inverse Cipher) ===")
        print_state_matrix("Input ciphertext", state)
        print_state_matrix("Round key K10", round_keys[10])

    # Initial AddRoundKey with k10
    state ^= round_keys[10]
    round_states.append(('after_init_addkey', state))
    if debug:
        print_state_matrix("After initial AddRoundKey (state ^ K10)", state)

    for rnd in range(10):
        round_key = round_keys[9 - rnd]
        if debug:
            print(f"\n--- Round {rnd} (using K{9-rnd}) ---")

        # InvSubBytes
        new_state = 0
        for i in range(16):
            byte = (state >> (120 - i*8)) & 0xff
            new_state |= INV_SBOX[byte] << (120 - i*8)
        state = new_state
        round_states.append((f'r{rnd}_after_invsub', state))
        if debug:
            print_state_matrix("After InvSubBytes", state)

        # InvShiftRows
        def get_byte(s, row, col):
            return (s >> (120 - (col*4 + row)*8)) & 0xff

        def set_byte(row, col, val):
            return val << (120 - (col*4 + row)*8)

        new_state = 0
        for col in range(4):
            new_state |= set_byte(0, col, get_byte(state, 0, col))
            new_state |= set_byte(1, col, get_byte(state, 1, (col - 1) % 4))
            new_state |= set_byte(2, col, get_byte(state, 2, (col - 2) % 4))
            new_state |= set_byte(3, col, get_byte(state, 3, (col - 3) % 4))
        state = new_state
        round_states.append((f'r{rnd}_after_invsr', state))
        if debug:
            print_state_matrix("After InvShiftRows", state)

        # InvMixColumns (skip in last round)
        if rnd < 9:
            # For equivalent inverse cipher, apply InvMixColumns to round key
            processed_key = 0
            for col in range(4):
                col_val = (round_key >> (96 - col*32)) & 0xffffffff
                imc = inv_mix_column(mix_column(col_val))
                processed_key |= imc << (96 - col*32)
            round_key = processed_key
            if debug:
                print_state_matrix(f"Round key K{9-rnd} after InvMC(MC())", round_key)

            new_state = 0
            for col in range(4):
                col_val = (state >> (96 - col*32)) & 0xffffffff
                imc = inv_mix_column(mix_column(col_val))
                new_state |= imc << (96 - col*32)
            state = new_state
            round_states.append((f'r{rnd}_after_invmc', state))
            if debug:
                print_state_matrix("After InvMixColumns(MixColumns())", state)
        else:
            if debug:
                print("(MixColumns bypassed - final round)")

        # AddRoundKey
        state ^= round_key
        round_states.append((f'r{rnd}_after_addkey', state))
        if debug:
            print_state_matrix("After AddRoundKey", state)

    if debug:
        print(f"\n=== Final plaintext: {state:032x} ===")

    return state, round_states

