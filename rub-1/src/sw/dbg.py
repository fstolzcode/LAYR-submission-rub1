#!/usr/bin/env python3
"""
Interactive debugger for the awesome-layr custom CPU.

Usage:
    python3 -i sw/dbg.py
    >>> ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
    >>> sync(ser)
    >>> dump_state(ser)
"""

import struct
import serial

# ============================================================
#  Protocol constants (mirrored from rtl/main_controller.v)
# ============================================================

# Debug opcodes
DBG_OP_NULL       = 0
DBG_OP_RDREG      = 1
DBG_OP_WRREG      = 2
DBG_OP_SINGLESTEP = 3
DBG_OP_RESET      = 4

# Register size selectors (2-bit, stored in bits [15:14] of the selector word)
DBG_REGSZ_1  = 0   # 1 byte
DBG_REGSZ_2  = 1   # 2 bytes
DBG_REGSZ_3  = 2   # 3 bytes
DBG_REGSZ_16 = 3   # 16 bytes

# Size selector -> byte count
REGSZ_VALUE = {0: 1, 1: 2, 2: 3, 3: 16}

# --- 1-byte register indices ---
DBG_REG1_FLAGS          = 0
DBG_REG1_CPUSTATE       = 1
DBG_REG1_SP             = 2
DBG_REG1_SPIFLAGS       = 3
DBG_REG1_SPITX_EEPROM   = 4
DBG_REG1_SPITX_RC522    = 5
DBG_REG1_SPIRX          = 6
DBG_REG1_RC522_IN       = 7
DBG_REG1_RC522_OUT      = 8
DBG_REG1_AESFLAGS       = 9
DBG_REG1_DBGCR          = 10
DBG_REG1_CALLFULL       = 11
DBG_REG1_CPUREG         = 64   # ram_data[0..63] at indices 64..127

# --- 2-byte register indices ---
DBG_REG2_PC    = 0
DBG_REG2_STACK = 1   # call_stack[0..3] at indices 1..4
DBG_REG2_BP    = 8   # breakpoints[0..7] at indices 8..15

# --- 3-byte register indices ---
DBG_REG3_IROM = 0      # instruction ROM, 0..1023
DBG_REG3_IRAM = 1024   # instruction RAM, 1024..1535

# --- 16-byte register indices ---
DBG_REG16_AESKEY0 = 0
DBG_REG16_AESKEY1 = 1
DBG_REG16_AESIN0  = 2
DBG_REG16_AESIN1  = 3
DBG_REG16_AESOUT0 = 4
DBG_REG16_AESOUT1 = 5

# CPU state names
CPU_STATES = {
    0: "FETCH",
    1: "EXECUTE",
    3: "WAIT_CRC",
    4: "WAIT_EEPROM",
    5: "WAIT_RC522",
    6: "WAIT_INSROMRD",
    7: "WAIT_AES",
    8: "WAIT_RNG",
    9: "WAIT_UARTTX_1",
    10: "WAIT_UARTTX_2",
    11: "WAIT_SPIDBG",
    12: "WAIT_SPIDBG_START",
}

DBG_NUM_HARDWARE_BREAKPOINTS = 8
DBG_IRAM_SIZE = 512
IROM_SIZE = 1024
NUM_CPU_REGS = 64
CALL_STACK_DEPTH = 4

# ============================================================
#  Low-level protocol functions
# ============================================================

def _make_sel(size, index):
    """Pack a 16-bit register selector: bits[15:14]=size, bits[13:0]=index."""
    return (size << 14) | (index & 0x3FFF)


def sync(ser):
    """Send 18 NULL bytes to force the debug FSM back to READ_INSN state."""
    ser.write(bytes(18))
    ser.flush()


def rdreg(ser, size, index):
    """Read a register. Returns the integer value."""
    sel = _make_sel(size, index)
    ser.write(struct.pack('<BH', DBG_OP_RDREG, sel))
    ser.flush()
    nbytes = REGSZ_VALUE[size]
    data = ser.read(nbytes)
    if len(data) != nbytes:
        raise TimeoutError(f"rdreg: expected {nbytes} bytes, got {len(data)}")
    return int.from_bytes(data, 'little')


def wrreg(ser, size, index, value):
    """Write a register. No response is returned."""
    sel = _make_sel(size, index)
    nbytes = REGSZ_VALUE[size]
    ser.write(struct.pack('<BH', DBG_OP_WRREG, sel) + value.to_bytes(nbytes, 'little'))
    ser.flush()


def singlestep(ser):
    """Pulse the CPU clock once (one FSM transition)."""
    ser.write(bytes([DBG_OP_SINGLESTEP]))
    ser.flush()


# ============================================================
#  Convenience functions — CPU state
# ============================================================

def read_pc(ser):
    """Read the 10-bit program counter."""
    return rdreg(ser, DBG_REGSZ_2, DBG_REG2_PC) & 0x3FF


def write_pc(ser, value):
    """Write the program counter (10-bit)."""
    wrreg(ser, DBG_REGSZ_2, DBG_REG2_PC, value & 0x3FF)


def read_flags(ser):
    """Read CPU flags. Returns dict with 'cmp' and 'err'."""
    v = rdreg(ser, DBG_REGSZ_1, DBG_REG1_FLAGS)
    return {'cmp': bool(v & 1), 'err': bool(v & 2)}


def read_cpustate(ser):
    """Read the CPU FSM state as a human-readable string."""
    v = rdreg(ser, DBG_REGSZ_1, DBG_REG1_CPUSTATE) & 0xF
    return CPU_STATES.get(v, f"UNKNOWN({v})")


def read_sp(ser):
    """Read the call stack pointer."""
    return rdreg(ser, DBG_REGSZ_1, DBG_REG1_SP) & 0x3


def read_callfull(ser):
    """Read the call stack full flag."""
    return bool(rdreg(ser, DBG_REGSZ_1, DBG_REG1_CALLFULL) & 1)


# ============================================================
#  Convenience functions — CPU registers (work RAM)
# ============================================================

def read_reg(ser, i):
    """Read CPU work RAM register i (0..63)."""
    if not 0 <= i < NUM_CPU_REGS:
        raise ValueError(f"Register index must be 0..{NUM_CPU_REGS-1}")
    return rdreg(ser, DBG_REGSZ_1, DBG_REG1_CPUREG + i)


def write_reg(ser, i, value):
    """Write CPU work RAM register i (0..63)."""
    if not 0 <= i < NUM_CPU_REGS:
        raise ValueError(f"Register index must be 0..{NUM_CPU_REGS-1}")
    wrreg(ser, DBG_REGSZ_1, DBG_REG1_CPUREG + i, value & 0xFF)


# ============================================================
#  Convenience functions — debug control register
# ============================================================

def read_dbgcr(ser):
    """Read DBGCR. Returns dict with 'cpurun' and 'cpumemsel'."""
    v = rdreg(ser, DBG_REGSZ_1, DBG_REG1_DBGCR)
    return {'cpurun': bool(v & 1), 'cpumemsel': bool(v & 2)}


def write_dbgcr(ser, cpurun=0, cpumemsel=0):
    """Write DBGCR bits."""
    wrreg(ser, DBG_REGSZ_1, DBG_REG1_DBGCR, (int(cpumemsel) << 1) | int(cpurun))


def run(ser):
    """Set CPURUN=1 (free-run until breakpoint)."""
    cr = read_dbgcr(ser)
    write_dbgcr(ser, cpurun=1, cpumemsel=cr['cpumemsel'])
    print("CPU running")


def halt(ser):
    """Set CPURUN=0 (halt CPU)."""
    cr = read_dbgcr(ser)
    write_dbgcr(ser, cpurun=0, cpumemsel=cr['cpumemsel'])
    print("CPU halted")


# ============================================================
#  Convenience functions — call stack
# ============================================================

def read_callstack(ser):
    """Read all 4 call stack entries. Returns list of 10-bit PC values."""
    return [rdreg(ser, DBG_REGSZ_2, DBG_REG2_STACK + i) & 0x3FF for i in range(CALL_STACK_DEPTH)]


# ============================================================
#  Convenience functions — breakpoints
# ============================================================

def read_bp(ser, i):
    """Read breakpoint i (0..7). Returns dict with 'enabled' and 'pc'."""
    if not 0 <= i < DBG_NUM_HARDWARE_BREAKPOINTS:
        raise ValueError(f"Breakpoint index must be 0..{DBG_NUM_HARDWARE_BREAKPOINTS-1}")
    v = rdreg(ser, DBG_REGSZ_2, DBG_REG2_BP + i)
    return {'enabled': bool(v & 0x400), 'pc': v & 0x3FF}


def write_bp(ser, i, pc, enabled=True):
    """Set breakpoint i to match a 10-bit PC value."""
    if not 0 <= i < DBG_NUM_HARDWARE_BREAKPOINTS:
        raise ValueError(f"Breakpoint index must be 0..{DBG_NUM_HARDWARE_BREAKPOINTS-1}")
    val = (int(enabled) << 10) | (pc & 0x3FF)
    wrreg(ser, DBG_REGSZ_2, DBG_REG2_BP + i, val)


def clear_bp(ser, i):
    """Disable breakpoint i."""
    write_bp(ser, i, 0, enabled=False)


def clear_all_bp(ser):
    """Disable all breakpoints."""
    for i in range(DBG_NUM_HARDWARE_BREAKPOINTS):
        clear_bp(ser, i)


# ============================================================
#  Convenience functions — instruction memory
# ============================================================

def read_irom(ser, addr):
    """Read an 18-bit instruction from ROM (0..1023)."""
    if not 0 <= addr < IROM_SIZE:
        raise ValueError(f"IROM address must be 0..{IROM_SIZE-1}")
    return rdreg(ser, DBG_REGSZ_3, DBG_REG3_IROM + addr) & 0x3FFFF


def read_iram(ser, addr):
    """Read an 18-bit instruction from IRAM (0..511)."""
    if not 0 <= addr < DBG_IRAM_SIZE:
        raise ValueError(f"IRAM address must be 0..{DBG_IRAM_SIZE-1}")
    return rdreg(ser, DBG_REGSZ_3, DBG_REG3_IRAM + addr) & 0x3FFFF


def write_iram(ser, addr, value):
    """Write an 18-bit instruction to IRAM (0..511)."""
    if not 0 <= addr < DBG_IRAM_SIZE:
        raise ValueError(f"IRAM address must be 0..{DBG_IRAM_SIZE-1}")
    wrreg(ser, DBG_REGSZ_3, DBG_REG3_IRAM + addr, value & 0x3FFFF)


def upload_iram(ser, program, base=0):
    """Write a list of 18-bit instructions to IRAM starting at base."""
    if base + len(program) > DBG_IRAM_SIZE:
        raise ValueError(f"Program ({len(program)} insns at base {base}) exceeds IRAM size ({DBG_IRAM_SIZE})")
    for i, insn in enumerate(program):
        write_iram(ser, base + i, insn)
    print(f"Uploaded {len(program)} instructions to IRAM[{base}..{base+len(program)-1}]")


def load_mem(ser, filename):
    """Load a .mem hex file into IRAM. Each line is one hex-encoded 18-bit instruction."""
    program = []
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('//') and not line.startswith('@'):
                program.append(int(line, 16))
    upload_iram(ser, program)
    return program


# ============================================================
#  Convenience functions — SPI / RC522
# ============================================================

def read_spiflags(ser):
    """Read SPI status flags."""
    v = rdreg(ser, DBG_REGSZ_1, DBG_REG1_SPIFLAGS)
    return {
        'cs0_open':    bool(v & 0x01),
        'cs1_open':    bool(v & 0x02),
        'tx_eeprom':   bool(v & 0x04),
        'tx_rc522':    bool(v & 0x08),
        'busy':        bool(v & 0x10),
    }


def read_spirx(ser):
    """Read SPI RX data register."""
    return rdreg(ser, DBG_REGSZ_1, DBG_REG1_SPIRX)


# ============================================================
#  Display / dump functions
# ============================================================

def dump_state(ser):
    """Print a summary of the CPU state."""
    pc = read_pc(ser)
    flags = read_flags(ser)
    sp = read_sp(ser)
    state = read_cpustate(ser)
    cr = read_dbgcr(ser)
    in_iram = pc >= 512

    print(f"  PC       = {pc:4d} (0x{pc:03x}){' [IRAM]' if in_iram else ' [ROM]'}")
    print(f"  State    = {state}")
    print(f"  Flags    = cmp={int(flags['cmp'])} err={int(flags['err'])}")
    print(f"  SP       = {sp}")
    print(f"  DBGCR    = cpurun={int(cr['cpurun'])} cpumemsel={int(cr['cpumemsel'])}")


def dump_regs(ser, n=16):
    """Print the first n CPU work RAM registers in a table."""
    print(f"  {'Reg':>4s}  {'Hex':>4s}  {'Dec':>4s}")
    print(f"  {'----':>4s}  {'----':>4s}  {'----':>4s}")
    for i in range(min(n, NUM_CPU_REGS)):
        v = read_reg(ser, i)
        print(f"  r{i:<3d}  0x{v:02x}  {v:4d}")


def dump_callstack(ser):
    """Print the call stack."""
    sp = read_sp(ser)
    stack = read_callstack(ser)
    for i, v in enumerate(stack):
        marker = " <-- SP" if i == sp else ""
        print(f"  [{i}] 0x{v:03x} ({v}){marker}")


def dump_breakpoints(ser):
    """Print all breakpoint registers."""
    for i in range(DBG_NUM_HARDWARE_BREAKPOINTS):
        bp = read_bp(ser, i)
        status = "ON " if bp['enabled'] else "off"
        print(f"  BP{i}: {status}  PC=0x{bp['pc']:03x} ({bp['pc']})")


def dump_iram(ser, start=0, count=16):
    """Hex dump a range of IRAM."""
    for addr in range(start, min(start + count, DBG_IRAM_SIZE)):
        v = read_iram(ser, addr)
        print(f"  IRAM[{addr:3d}] = 0x{v:05x}")


def dump_irom(ser, start=0, count=16):
    """Hex dump a range of IROM."""
    for addr in range(start, min(start + count, IROM_SIZE)):
        v = read_irom(ser, addr)
        print(f"  IROM[{addr:3d}] = 0x{v:05x}")


def step(ser, n=1):
    """Single-step n times, printing state after the last step."""
    for _ in range(n):
        singlestep(ser)
    dump_state(ser)


# ============================================================
#  Reference table (printed on import)
# ============================================================

def print_reference():
    print("""
================================================================================
  AWESOME-LAYR CPU DEBUGGER — PROTOCOL REFERENCE
================================================================================

  DEBUG OPCODES
  ─────────────────────────────────────────────────────────────────────────────
  Opcode  Value  Params (bytes)  Response      Description
  ─────────────────────────────────────────────────────────────────────────────
  NULL       0   0               none          Sync / no-op
  RDREG      1   2 (selector)    1/2/3/16 B    Read register
  WRREG      2   2 + value       none          Write register
  SINGLESTEP 3   0               none          Pulse CPU clock once
  RESET      4   1 (module idx)  none          Reset submodule (stub)

  REGISTER SELECTOR FORMAT (16-bit, little-endian)
  ─────────────────────────────────────────────────────────────────────────────
  Bits [15:14] = size selector    Bits [13:0] = register index

  Size sel  Bytes  Selector bits
      0       1    DBG_REGSZ_1
      1       2    DBG_REGSZ_2
      2       3    DBG_REGSZ_3
      3      16    DBG_REGSZ_16

  BYTE-LEVEL ENCODING
  ─────────────────────────────────────────────────────────────────────────────
  RDREG:  TX [0x01] [sel_lo] [sel_hi]          → RX [val_0] ... [val_n-1]
  WRREG:  TX [0x02] [sel_lo] [sel_hi] [val_0] ... [val_n-1]
  STEP:   TX [0x03]
  NULL:   TX [0x00]

  All multi-byte values are LITTLE-ENDIAN (LSB first).
  sel = (size_selector << 14) | register_index

  1-BYTE REGISTERS (REGSZ_1, index 0..127)
  ─────────────────────────────────────────────────────────────────────────────
  Index   Name            R/W   Description
   0      FLAGS            R    {err_flag, cmp_flag}
   1      CPUSTATE         R    CPU FSM state (4 bits)
   2      SP               R    Call stack pointer
   3      SPIFLAGS         R    {busy,tx_rc522,tx_eeprom,cs1,cs0}
   4      SPITX_EEPROM     R    SPI TX buffer (EEPROM)
   5      SPITX_RC522      R    SPI TX buffer (RC522)
   6      SPIRX            R    SPI RX data
   7      RC522_IN         R    RC522 data input
   8      RC522_OUT        R    RC522 data output
   9      AESFLAGS         R    AES status (stub)
  10      DBGCR           R/W   Debug control {cpumemsel, cpurun}
  11      CALLFULL         R    Call stack full flag
  64-127  CPUREG[0..63]   R/W   CPU work RAM (ram_data)

  2-BYTE REGISTERS (REGSZ_2, index 0..15)
  ─────────────────────────────────────────────────────────────────────────────
  Index   Name            R/W   Description
   0      PC              R/W   Program counter (10 bits)
   1-4    STACK[0..3]     R/W   Hardware call stack (10 bits each)
   8-15   BP[0..7]        R/W   Breakpoints: bit[10]=enable, bits[9:0]=PC

  3-BYTE REGISTERS (REGSZ_3, index 0..1535)
  ─────────────────────────────────────────────────────────────────────────────
  Index        Name            R/W   Description
   0-1023      IROM[0..1023]    R    Instruction ROM (18-bit words)
   1024-1535   IRAM[0..511]    R/W   Instruction RAM (18-bit words)

  16-BYTE REGISTERS (REGSZ_16, index 0..5)
  ─────────────────────────────────────────────────────────────────────────────
  Index   Name            R/W   Description
   0-1    AESKEY[0..1]     -    AES key (not implemented)
   2-3    AESIN[0..1]      -    AES input (not implemented)
   4-5    AESOUT[0..1]     -    AES output (not implemented)

  CPU STATES
  ─────────────────────────────────────────────────────────────────────────────
  0=FETCH  1=EXECUTE  3=WAIT_CRC  4=WAIT_EEPROM  5=WAIT_RC522
  6=WAIT_INSROMRD  7=WAIT_AES  8=WAIT_RNG  9=WAIT_UARTTX_1
  10=WAIT_UARTTX_2  11=WAIT_SPIDBG  12=WAIT_SPIDBG_START

  AVAILABLE FUNCTIONS
  ─────────────────────────────────────────────────────────────────────────────
  sync(ser)                       Reset debug FSM (send 18 NULLs)
  rdreg(ser, size, index)         Raw register read → int
  wrreg(ser, size, index, val)    Raw register write

  read_pc / write_pc              Program counter
  read_flags                      CPU flags → {cmp, err}
  read_cpustate                   CPU state → string
  read_sp                         Call stack pointer
  read_reg / write_reg(ser, i)    Work RAM register i (0..63)
  read_dbgcr / write_dbgcr        Debug control register
  read_callstack                  All 4 stack entries → list
  read_bp / write_bp / clear_bp   Breakpoint registers
  read_irom(ser, addr)            Read ROM instruction
  read_iram / write_iram          Read/write IRAM instruction
  upload_iram(ser, [insns])       Bulk-write instructions to IRAM
  load_mem(ser, "file.mem")       Load .mem file into IRAM

  dump_state(ser)                 Print PC, flags, SP, DBGCR, state
  dump_regs(ser, n=16)            Print first n work registers
  dump_callstack(ser)             Print call stack
  dump_breakpoints(ser)           Print all 8 breakpoints
  dump_iram(ser, start, count)    Hex dump IRAM range
  dump_irom(ser, start, count)    Hex dump IROM range

  step(ser, n=1)                  Single-step n times, print state
  run(ser) / halt(ser)            Set/clear CPURUN
  clear_all_bp(ser)               Disable all breakpoints
================================================================================
""")

print_reference()