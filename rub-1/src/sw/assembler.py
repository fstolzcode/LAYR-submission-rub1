#!/usr/bin/env python3
"""
Main Controller Assembler

Assembles custom assembly language for the main controller into ROM memory format.
Supports CRC and other instruction types with label resolution.

Instruction Format (18-bit):
    [17:12] opcode  - 6 bits (0-63)
    [11:6]  arg1    - 6 bits (0-63) - first operand (source/RAM address)
    [5:0]   arg2    - 6 bits (0-63) - second operand (destination/RAM address)

Output Format:
    - 5-digit hexadecimal strings (e.g., "04140")
    - One instruction per line
    - Padded to ROM_SIZE (512) entries for ROM size
    - Written to .mem file for $readmemh in Verilog

Assembly Syntax:
    OPERATION arg0,arg1    - Two operand instruction
    OPERATION arg0         - Single operand instruction
    OPERATION              - No operand instruction
    .label:                - Label definition
    OPERATION .label       - Label reference (as arg0)
    @ comment              - Comment (full line or inline)

Examples:
    CRCRST                 - Reset CRC core
    CRCLD 5                - Load RAM[5] into CRC
    CRCH 10                - Store CRC high byte to RAM[10]
    CRCL 11                - Store CRC low byte to RAM[11]
    .loop:                 - Define label
    CRCLD .loop            - Reference label (uses relative offset)
"""

import sys
import types
import logging

# ============================================================================
# Constants
# ============================================================================
encodings = types.SimpleNamespace()
encodings.DEFAULT = 0
encodings.IMM_DST = 1
encodings.ABS_ADDR = 2  # 10-bit absolute addressing (CALL, JMPC, JMPNC)

# ============================================================================
# Module Configuration
# ============================================================================

# Module logger
logger = logging.getLogger(__name__)

# ROM configuration
ROM_SIZE = 512  # Number of ROM entries (must match rom.v)

# ============================================================================
# Instruction Set Architecture
# ============================================================================
# Each instruction is defined as: (mnemonic, opcode, num_operands)
# - mnemonic: Assembly instruction name (case-insensitive)
# - opcode: 6-bit opcode value (0-63)
# - num_operands: Expected number of operands (0, 1, or 2)

INSTRUCTION_SET = [
    # CRC Instructions
    ("CRCRST",       0,  0, encodings.DEFAULT),  # Reset CRC core --> Ready for loading data, get rid of old data
    ("CRCLD",        1,  1, encodings.DEFAULT),  # Load RAM[arg1] byte into CRC
    ("CRCH",         2,  1, encodings.DEFAULT),  # Write CRC HIGH byte to RAM[arg1]
    ("CRCL",         3,  1, encodings.DEFAULT),  # Write CRC LOW byte to RAM[arg1]

    # ROM/EEPROM Instructions
    ("ROMRST",       4,  0, encodings.DEFAULT),  # ROM Reset --> Resets the ROM module
    ("ROMRD",        5,  2, encodings.DEFAULT),  # Read from EEPROM to RAM (arg1=EEPROM addr, arg2=RAM addr)

    # RC522 Instructions
    ("RC522RST",     6,  0, encodings.DEFAULT),  # Initialize RC522 (no operands)
    ("RC522PUSH",    7,  1, encodings.DEFAULT),  # Push ram[arg1] to the RC522 data input
    ("RC522POP",     8,  1, encodings.DEFAULT),  # Pop RC522 data output to ram[arg1]
    ("RC522BLEN",    9,  1, encodings.DEFAULT),  # Set length of last byte (0 = 8, 1 = 1, 2 = 2 and so on)
    ("RC522TRCVE",  10,  0, encodings.DEFAULT),  # Initiate a transreceive command
    ("RC522BUFRST", 11,  0, encodings.DEFAULT),  # Reset the data input/output
    ("RC522WAIT",   12,  0, encodings.DEFAULT),  # Wait during initial reset
    ("RC522RXNUM",  39,  1, encodings.DEFAULT),  # Get number of received bytes to RAM[arg1]

    # AES Instructions
    ("AESRST",      31, 0, encodings.DEFAULT),  # Reset AES wrapper
    ("AESPUSHD",    32, 1, encodings.DEFAULT),  # Push RAM[arg1] to AES data register
    ("AESPUSHK0",   33, 1, encodings.DEFAULT),  # Push RAM[arg1] to AES key_in_0 register
    ("AESPUSHK1",   34, 1, encodings.DEFAULT),  # Push RAM[arg1] to AES key_in_1 register
    ("AESPOP",      35, 1, encodings.DEFAULT),  # Pop AES data output to RAM[arg1]
    ("AESMODE",     36, 1, encodings.DEFAULT),  # Set AES encryption/decryption mode to arg1
    ("AESSTART",    37, 0, encodings.DEFAULT),  # Start AES encryption/decryption
    ("AESBUFRST",   38, 0, encodings.DEFAULT),  # Reset AES buffers and counters

    # UART Instructions
    ("UARTTX",      40, 1, encodings.DEFAULT),  # Transmit RAM[arg1] via UART

    # RNG Instructions
    ("RNGRST",      13,  0, encodings.DEFAULT),  # Reset RNG (no operands)
    ("RNGGET",      14,  1, encodings.DEFAULT),  # Get random byte (arg1=RAM addr)

    # Comparison Instructions
    ("CMPEQ",       15,  2, encodings.DEFAULT),  # Compare equal (arg1, arg2)
    ("CMPLT",       16,  2, encodings.DEFAULT),  # Compare less than (arg1, arg2)

    # Control Flow Instructions
    ("JMPC",        17,  1, encodings.ABS_ADDR),  # Jump if compare flag set (10-bit absolute address)
    ("JMPNC",       24,  1, encodings.ABS_ADDR),  # Jump if compare flag not set (10-bit absolute address)
    ("JUMPE",       18,  1, encodings.ABS_ADDR),  # Jump if error flag set (10-bit absolute address)
    ("CALL",        19,  1, encodings.ABS_ADDR),  # Call subroutine (10-bit absolute address)
    ("RET",         20,  0, encodings.DEFAULT),  # Return from subroutine (no operands)

    # Data Movement Instructions
    ("IMMLD",       60,  2, encodings.IMM_DST), # ram[arg2] = arg1 (8 bit via hack)
    ("MOV",         27,  2, encodings.DEFAULT), # ram[arg2] = ram[arg1]
    ("IMOV",        30,  2, encodings.DEFAULT), # RAM[arg2] = RAM[RAM[arg1]]
    ("SMOV",        41,  2, encodings.DEFAULT), # RAM[RAM[arg2]] = RAM[arg1]

    # ROM Data Reading Instructions (PC-relative, unsigned offset 0-63)
    ("INSROMRDL",   25,  2, encodings.DEFAULT), # ram[arg2] = rom[pc+arg1][7:0] (low byte)
    ("INSROMRDH",   26,  2, encodings.DEFAULT), # ram[arg2] = rom[pc+arg1][15:8] (high byte)

    # Arithmetic
    ("ADD",         21,  2, encodings.DEFAULT), # ram[arg2] = ram[arg1] + ram[arg2]
    ("XOR",         22,  2, encodings.DEFAULT), # ram[arg2] = ram[arg1] ^ ram[arg2]
    ("AND",         23,  2, encodings.DEFAULT), # ram[arg2] = ram[arg1] & ram[arg2]

    ("LOCK",        42,  1, encodings.DEFAULT), # UNLOCK with LOCK 1
    ("STACKFLSH",   46,  0, encodings.DEFAULT), # flushes stack

    # extra stuff
    ("REP",         28,  2, encodings.DEFAULT), # FOR BAR in 0..arg2 DO rom[pc:pc+arg1] (any branch will implicitly break the loop)
    ("CRCPW",       29,  2, encodings.DEFAULT),
    ("CRCPC",       47,  2, encodings.DEFAULT),
    ("RPTZ",        48,  0, encodings.DEFAULT),


    ("SPIDBG",        43,  1, encodings.DEFAULT),
    ("SPICS",        44,  1, encodings.DEFAULT),
    ("SPITX",        45,  2, encodings.DEFAULT),
]

# Build lookup dictionary for fast instruction lookup
# Maps mnemonic (lowercase) -> (opcode, num_operands)
INSTRUCTION_MAP = {instr[0].lower(): tuple(instr[1:]) for instr in INSTRUCTION_SET}

# ============================================================================
# Instruction encodings
# ============================================================================

def encode_imm_dst_instruction(opcode, arg1=0, arg2=0):
    """
    Encode an 18-bit instruction from opcode and operands.

    Instruction format:
        Bits [17:12]: opcode (6 bits, lower 2 bits must be zero)
        Bits [13:6]:  arg1 (8 bits) - immediate operand
        Bits [5:0]:   arg2 (6 bits) - second operand

    Args:
        opcode: 6-bit opcode value (0-60, multiple of 4)
        arg1: 8-bit immediate/destination value (0-255), default 0
        arg2: 6-bit second operand (0-63), default 0

    Returns:
        5-digit hex string (e.g., "3c042")

    Example:
        >>> encode_imm_dst_instruction(60, 1, 2)
        "3c042"

        >>> encode_imm_dst_instruction(0, 0, 0)
        "00000"
    """
    assert 0 <= opcode <= 60
    assert 0 <= arg1 <= 255
    assert 0 <= arg2 <= 63
    assert not (opcode & 3)

    instruction = (opcode << 12) | (arg1 << 6) | (arg2 << 0)
    return f"{instruction:05x}"

def encode_abs_addr_instruction(opcode, address):
    """
    Encode an 18-bit instruction with 10-bit absolute address.

    This encoding is used for control flow instructions (CALL, JMPC, JMPNC, JUMPE)
    that use absolute addressing. The 10-bit address is split across arg1 and arg2:
        - arg1: Lower 6 bits of address (bits 5:0)
        - arg2: Upper 4 bits of address (bits 9:6)

    The RTL reconstructs the address as: pc <= {arg2[3:0], arg1}

    Instruction format:
        Bits [17:12]: opcode (6 bits)
        Bits [11:6]:  arg1 (6 bits) - address[5:0]
        Bits [5:0]:   arg2 (6 bits) - address[9:6] in lower 4 bits

    Args:
        opcode: 6-bit opcode value (0-63)
        address: 10-bit absolute address (0-1023)

    Returns:
        5-digit hex string (e.g., "4c901")

    Example:
        >>> encode_abs_addr_instruction(19, 100)  # CALL 100
        "4c901"
        # 100 = 0x64 = 0b0001100100
        # arg1 = 0b100100 = 36, arg2 = 0b000001 = 1
        # Instruction = (19 << 12) | (36 << 6) | 1 = 0x4C00 | 0x900 | 0x1 = 0x4C901

        >>> encode_abs_addr_instruction(17, 500)  # JMPC 500
        "44d07"
        # 500 = 0x1F4 = 0b0111110100
        # arg1 = 0b110100 = 52, arg2 = 0b000111 = 7
    """
    # Validate inputs
    assert 0 <= opcode <= 63, f"Opcode {opcode} out of range (0-63)"
    assert 0 <= address <= 1023, f"Address {address} out of range (0-1023 for 10-bit addressing)"

    # Split address: lower 6 bits in arg1, upper 4 bits in arg2
    arg1 = address & 0x3F          # Extract bits 5:0
    arg2 = (address >> 6) & 0x0F   # Extract bits 9:6

    # Pack into 18-bit instruction: [opcode:6][arg1:6][arg2:6]
    instruction = (opcode << 12) | (arg1 << 6) | arg2

    # Return as 5-digit hex string
    return f"{instruction:05x}"

def encode_default_instruction(opcode, arg1=0, arg2=0):
    """
    Encode an 18-bit instruction from opcode and operands.

    Instruction format:
        Bits [17:12]: opcode (6 bits)
        Bits [11:6]:  arg1 (6 bits) - first operand
        Bits [5:0]:   arg2 (6 bits) - second operand

    Args:
        opcode: 6-bit opcode value (0-63)
        arg1: 6-bit first operand (0-63), default 0
        arg2: 6-bit second operand (0-63), default 0

    Returns:
        5-digit hex string (e.g., "04140")

    Example:
        >>> encode_default_instruction(1, 5, 0)  # CRCLD with RAM[5]
        "04140"

        >>> encode_default_instruction(0, 0, 0)  # CRCRST (no operands)
        "00000"
    """
    # Validate inputs are in 6-bit range
    assert 0 <= opcode <= 63, f"Opcode {opcode} out of range (0-63)"
    assert 0 <= arg1 <= 63, f"Arg1 {arg1} out of range (0-63)"
    assert 0 <= arg2 <= 63, f"Arg2 {arg2} out of range (0-63)"

    # Pack into 18-bit instruction: [opcode:6][arg1:6][arg2:6]
    instruction = (opcode << 12) | (arg1 << 6) | (arg2 << 0)

    # Return as 5-digit hex string (18 bits requires 5 hex digits)
    return f"{instruction:05x}"

# ============================================================================
# Operand Parsing and Validation
# ============================================================================

def parse_operand(operand_str, rmin=None, rmax=None, supports_label=True):
    """
    Parse an operand string into a numeric value.

    Supports:
        - Decimal: "42"
        - Hexadecimal: "0x2A" or "0x2a"
        - Binary: "0b101010"
        - Label references: ".labelname" (returns None, handled separately)

    Args:
        operand_str: String representation of operand

    Returns:
        Integer value, or None if it's a label reference

    Raises:
        ValueError: If operand cannot be parsed
    """
    operand_str = operand_str.strip()

    # Check if it's a label reference
    if operand_str.startswith('.'):
        if supports_label: return None
        raise ValueError(f"Invalid operand '{operand_str}' - labels are not supported here.")

    # Try to parse as integer (supports 0x, 0b, decimal)
    try:
        out = int(operand_str, 0)
        if rmin is not None and out < rmin: raise ValueError(f"Invalid operand '{operand_str}' - must be at least {rmin}")
        if rmax is not None and out > rmax: raise ValueError(f"Invalid operand '{operand_str}' - must be at most {rmax}")
        return out
    except ValueError:
        raise ValueError(f"Invalid operand '{operand_str}' - must be a number{' or label' if supports_label else ''}")

# ============================================================================
# Assembly Parser
# ============================================================================

def parse_line(line):
    """
    Parse a single assembly line into components.

    Handles:
        - Empty lines (preserved in output)
        - Comments (@ prefix, full line or inline)
        - Label definitions (.labelname:)
        - Instructions with 0, 1, or 2 operands

    Args:
        line: Raw assembly line

    Returns:
        Tuple of (line_type, data):
            - ("empty", None) - Empty line
            - ("comment", comment_text) - Full-line comment
            - ("label", label_name) - Label definition
            - ("instruction", (mnemonic, [operands])) - Instruction

    Example:
        >>> parse_line("CRCLD 5")
        ("instruction", ("crcld", [5]))

        >>> parse_line(".loop:")
        ("label", "loop")

        >>> parse_line("@ This is a comment")
        ("comment", "@ This is a comment")
    """
    original_line = line
    line = line.strip()

    # Empty line
    if not line:
        return ("empty", None)

    # Full-line comment
    if line.startswith('@'):
        return ("comment", line)

    # Directive (.word for data constants)
    if line.startswith('.word'):
        # Parse directive: .word 0x1234
        # Remove inline comments first
        if '@' in line:
            line = line.split('@')[0].strip()

        tokens = line.split()
        if len(tokens) != 2:
            return ("error", "Invalid .word directive - format: .word <value>")

        try:
            value = int(tokens[1], 0)  # Supports 0x, 0b, decimal
            # Validate 18-bit range
            if value < 0 or value > 0x3FFFF:
                return ("error", f"Value {value:#x} out of range (0-0x3FFFF for 18-bit)")
            return ("directive", ("word", value))
        except ValueError:
            return ("error", f"Invalid value in .word directive: {tokens[1]}")

    # Label definition (.labelname:)
    if line.startswith('.') and ':' in line:
        # Extract label name (remove leading . and trailing :)
        label_name = line.split(':')[0][1:].strip().lower()
        return ("label", label_name)

    # Remove inline comments (everything after @)
    if '@' in line:
        line = line.split('@')[0]

    # Tokenize: split on spaces and commas, remove empty tokens
    line = line.replace(',', ' ')
    tokens = [t.strip() for t in line.split() if t.strip()]

    if not tokens:
        return ("empty", None)

    # First token is the mnemonic
    mnemonic = tokens[0].lower()

    # Remaining tokens are operands
    operand_strings = tokens[1:]

    return ("instruction", (mnemonic, operand_strings))

# ============================================================================
# Label Resolution
# ============================================================================

def build_label_table(lines):
    """
    First pass: Build a table mapping label names to instruction addresses.

    Processes all lines to determine where each label is defined, counting
    only actual instructions (not comments, empty lines, or labels themselves).

    Args:
        lines: List of assembly source lines

    Returns:
        Dictionary mapping label_name (str) -> address (int)

    Raises:
        ValueError: If duplicate labels are found

    Example:
        Given assembly:
            CRCRST
            .loop:
            CRCLD 0

        Returns: {"loop": 1}  # .loop is at instruction address 1
    """
    label_table = {}
    instruction_address = 0  # Current instruction address

    for line_num, line in enumerate(lines, 1):
        line_type, data = parse_line(line)

        if line_type == "label":
            label_name = data

            # Check for duplicate labels
            if label_name in label_table:
                logger.error(
                    f"Line {line_num}: Duplicate label '.{label_name}' "
                    f"(previously defined at address {label_table[label_name]})"
                )
                sys.exit(1)

            # Record label at current instruction address
            label_table[label_name] = instruction_address
            logger.debug(f"Label '.{label_name}' defined at address {instruction_address}")

        elif line_type == "directive":
            # Directives like .word take one address slot
            instruction_address += 1

        elif line_type == "instruction":
            # Instruction takes one address slot
            instruction_address += 1

        elif line_type == "error":
            # Error in parse_line - report it
            logger.error(f"Line {line_num}: {data}")
            sys.exit(1)

    return label_table

def resolve_label_reference(label_name, current_address, label_table, line_num):
    """
    Resolve a label reference to a relative offset.

    Calculates the signed offset from the current instruction to the target
    label. The offset is calculated from the *next* instruction (PC after
    fetch), which is current_address + 1.

    Args:
        label_name: Name of label (without leading .)
        current_address: Address of current instruction
        label_table: Dictionary of label names -> addresses
        line_num: Source line number (for error messages)

    Returns:
        Signed offset value (-32 to +31 for 6-bit signed)

    Raises:
        SystemExit: If label is undefined or offset out of range

    Example:
        Current instruction at address 5, label at address 3:
        Offset = 3 - (5 + 1) = -3
    """
    # Check if label exists
    if label_name not in label_table:
        logger.error(
            f"Line {line_num}: Undefined label '.{label_name}'"
        )
        sys.exit(1)

    target_address = label_table[label_name]

    # Calculate offset from next instruction (PC + 1)
    offset = target_address - (current_address + 1)

    # Validate offset fits in 6-bit signed range (-32 to +31)
    if offset < -32 or offset > 31:
        logger.error(
            f"Line {line_num}: Label '.{label_name}' offset {offset} out of range "
            f"(-32 to +31 for 6-bit signed field). "
            f"Label is at address {target_address}, current instruction at {current_address}"
        )
        sys.exit(1)

    # Convert negative offsets to two's complement (6-bit)
    if offset < 0:
        offset = offset & 0x3F  # Mask to 6 bits

    return offset

def resolve_label_relative_unsigned(label_name, current_address, label_table, line_num):
    """
    Resolve a label reference to an unsigned relative offset.

    This function is used for INSROMRDL/INSROMRDH instructions which use
    unsigned PC-relative addressing. The offset is calculated from the
    current instruction to the target label.

    Unlike branches (which calculate from PC+1), INSROMRD instructions
    calculate from current PC because they temporarily modify PC in the
    EXECUTE state before restoring it:
        offset = target_address - current_address

    The offset must be positive (forward jumps only) and fit in 6 bits (0-63).

    Args:
        label_name: Name of label (without leading .)
        current_address: Address of current instruction
        label_table: Dictionary of label names -> addresses
        line_num: Source line number (for error messages)

    Returns:
        Unsigned offset value (0-63)

    Raises:
        SystemExit: If label is undefined, offset is negative, or out of range

    Example:
        Current instruction at address 5, label at address 10:
        Offset = 10 - 5 = 5 (forward jump)
    """
    # Check if label exists
    if label_name not in label_table:
        logger.error(
            f"Line {line_num}: Undefined label '.{label_name}'"
        )
        sys.exit(1)

    target_address = label_table[label_name]

    # Calculate offset from current instruction
    offset = target_address - current_address

    # Validate offset is non-negative (forward jumps only)
    if offset < 0:
        logger.error(
            f"Line {line_num}: INSROMRD offset {offset} is negative. "
            f"Label '.{label_name}' is at address {target_address}, "
            f"current instruction at {current_address}. "
            f"INSROMRDL/H can only jump forward (offset must be 0-63)."
        )
        sys.exit(1)

    # Validate offset fits in 6-bit unsigned range (0-63)
    if offset > 63:
        logger.error(
            f"Line {line_num}: INSROMRD offset {offset} out of range (0-63). "
            f"Label '.{label_name}' is at address {target_address}, "
            f"current instruction at {current_address}. "
            f"Target is too far (maximum forward offset is 63)."
        )
        sys.exit(1)

    logger.debug(
        f"Resolved label '.{label_name}' to unsigned relative offset {offset} "
        f"(current={current_address}, target={target_address})"
    )

    return offset

def resolve_label_absolute(label_name, label_table, line_num):
    """
    Resolve a label reference to an absolute address.

    This function is used for instructions that use absolute addressing
    (CALL, JMPC, JMPNC, JUMPE), where the target address is not relative
    to the current PC but is an absolute 10-bit address (0-1023).

    Args:
        label_name: Name of label (without leading .)
        label_table: Dictionary of label names -> addresses
        line_num: Source line number (for error messages)

    Returns:
        Absolute address (0-1023)

    Raises:
        SystemExit: If label is undefined or address out of range

    Example:
        Label '.target' is at address 100:
        Returns: 100 (absolute address, not relative offset)
    """
    # Check if label exists
    if label_name not in label_table:
        logger.error(
            f"Line {line_num}: Undefined label '.{label_name}'"
        )
        sys.exit(1)

    address = label_table[label_name]

    # Validate address fits in 10-bit range (0-1023)
    if address < 0 or address > 1023:
        logger.error(
            f"Line {line_num}: Label '.{label_name}' address {address} out of range "
            f"(0-1023 for 10-bit absolute addressing)"
        )
        sys.exit(1)

    logger.debug(
        f"Resolved label '.{label_name}' to absolute address {address}"
    )

    return address

# ============================================================================
# Instruction Assembly
# ============================================================================

def assemble_instruction(mnemonic, operand_strings, current_address, label_table, line_num):
    """
    Assemble a single instruction into encoded hex string.

    Args:
        mnemonic: Instruction mnemonic (lowercase)
        operand_strings: List of operand strings (may contain label references)
        current_address: Address of this instruction
        label_table: Dictionary of label names -> addresses
        line_num: Source line number (for error messages)

    Returns:
        5-digit hex string encodings of instruction

    Raises:
        SystemExit: On assembly errors (invalid instruction, wrong operand count, etc.)
    """
    # Look up instruction definition
    if '.' in mnemonic:
        mnemonic, flags = mnemonic.split('.', 1)
    else:
        flags = ""

    if mnemonic not in INSTRUCTION_MAP:
        logger.error(
            f"Line {line_num}: Unknown instruction '{mnemonic}'"
        )
        sys.exit(1)

    opcode, expected_operands, encoding = INSTRUCTION_MAP[mnemonic]

    # Validate operand count
    if len(operand_strings) != expected_operands:
        logger.error(
            f"Line {line_num}: Instruction '{mnemonic}' expects {expected_operands} "
            f"operand(s), got {len(operand_strings)}"
        )
        sys.exit(1)

    # Parse operands
    arg1 = 0
    arg2 = 0

    # For ABS_ADDR encoding, we handle operands differently (10-bit absolute address)
    if encoding == encodings.ABS_ADDR:
        if expected_operands >= 1:
            # First operand is a 10-bit absolute address (label or numeric value)
            if operand_strings[0].startswith('.'):
                # Label reference - resolve to absolute address
                label_name = operand_strings[0][1:].lower()  # Remove leading .
                arg1 = resolve_label_absolute(label_name, label_table, line_num)
            else:
                # Numeric value - must be 0-1023 (10-bit)
                arg1 = parse_operand(operand_strings[0], 0, 1023)
    # For INSROMRDL/INSROMRDH, use unsigned PC-relative addressing (forward-only)
    elif mnemonic in ['insromrdl', 'insromrdh']:
        if expected_operands >= 1:
            # First operand: 6-bit unsigned relative offset (label or numeric value)
            if operand_strings[0].startswith('.'):
                # Label reference - resolve to unsigned relative offset
                label_name = operand_strings[0][1:].lower()  # Remove leading .
                arg1 = resolve_label_relative_unsigned(label_name, current_address, label_table, line_num)
            else:
                # Numeric value - must be 0-63 (6-bit unsigned)
                arg1 = parse_operand(operand_strings[0], 0, 63)

        if expected_operands >= 2:
            arg2 = parse_operand(operand_strings[1], 0, 63, supports_label=False)

    # For IMMLD (IMM_DST encoding), first operand is 8-bit immediate
    elif encoding == encodings.IMM_DST:
        if expected_operands >= 1:
            # Numeric value - must be 0-255 (8-bit immediate)
            arg1 = parse_operand(operand_strings[0], 0, 255, supports_label=False)

        if expected_operands >= 2:
            # Second operand: RAM address (standard 6-bit)
            arg2 = parse_operand(operand_strings[1], 0, 63, supports_label=False)
    else:
        # DEFAULT encoding uses standard operand parsing
        if expected_operands >= 1:
            # First operand (can be label or value)
            if operand_strings[0].startswith('.'):
                # Label reference
                label_name = operand_strings[0][1:].lower()  # Remove leading .
                arg1 = resolve_label_reference(label_name, current_address, label_table, line_num)
            else:
                # Numeric value
                arg1 = parse_operand(operand_strings[0], 0, 63)

        if expected_operands >= 2:
            # Second operand (typically numeric, labels usually only in arg1)
            arg2 = parse_operand(operand_strings[1], 0, 63, supports_label=False)

    # Encode instruction
    match encoding:
        case encodings.DEFAULT: encoded = encode_default_instruction(opcode, arg1, arg2)
        case encodings.IMM_DST: encoded = encode_imm_dst_instruction(opcode, arg1, arg2)
        case encodings.ABS_ADDR: encoded = encode_abs_addr_instruction(opcode, arg1)
        case _: assert False, "Invalid instruction encoding"

    logger.debug(
        f"Line {line_num}: {mnemonic.upper()} {','.join(operand_strings)} "
        f"-> opcode={opcode}, arg1={arg1}, arg2={arg2} -> {encoded}"
    )

    return encoded

# ============================================================================
# Assembly Output Generation
# ============================================================================

def assemble(lines):
    """
    Assemble source lines into ROM memory format.

    Two-pass assembly:
        Pass 1: Build label table (label names -> addresses)
        Pass 2: Assemble instructions, resolving label references

    Args:
        lines: List of assembly source lines

    Returns:
        List of hex strings (one per ROM entry, padded to ROM_SIZE)

    Example:
        Input:
            ["CRCRST", "CRCLD 5", "CRCH 10"]

        Output:
            ["00000", "04140", "08280", "00000", ... (padded to ROM_SIZE)]
    """
    logger.info(f"Starting assembly of {len(lines)} source lines")

    # Pass 1: Build label table
    logger.debug("Pass 1: Building label table")
    label_table = build_label_table(lines)
    logger.debug(f"Found {len(label_table)} labels: {label_table}")

    # Pass 2: Assemble instructions
    logger.debug("Pass 2: Assembling instructions")
    output = []
    instruction_address = 0

    for line_num, line in enumerate(lines, 1):
        line_type, data = parse_line(line)

        if line_type == "directive":
            directive_name, value = data

            if directive_name == "word":
                # Emit raw 18-bit value as hex string
                encoded = f"{value:05x}"
                output.append(encoded)
                instruction_address += 1
                logger.debug(
                    f"Line {line_num}: .word {value:#x} -> {encoded} "
                    f"(address {instruction_address - 1})"
                )

        elif line_type == "instruction":
            mnemonic, operand_strings = data

            # Assemble instruction
            encoded = assemble_instruction(
                mnemonic, operand_strings, instruction_address,
                label_table, line_num
            )

            output.append(encoded)
            instruction_address += 1

        elif line_type == "error":
            # Error in parse_line - report it
            logger.error(f"Line {line_num}: {data}")
            sys.exit(1)

        # Labels, comments, and empty lines don't generate output

    logger.info(f"Assembled {len(output)} instructions")

    # Pad output to ROM_SIZE
    if len(output) > ROM_SIZE:
        logger.error(
            f"Program too large: {len(output)} instructions exceeds ROM size {ROM_SIZE}"
        )
        sys.exit(1)

    # Pad with NOP (opcode 0, all zeros)
    padding_needed = ROM_SIZE - len(output)
    output.extend(["00000"] * padding_needed)
    logger.debug(f"Padded with {padding_needed} NOPs to reach ROM size {ROM_SIZE}")

    return output

# ============================================================================
# Main Entry Point
# ============================================================================

def main(args):
    """
    Assembler entry point.

    Reads assembly source file, assembles to ROM format, and writes output.

    Usage:
        assembler.py [-v|--verbose] input.asm output.mem

    Args:
        args: Command-line arguments (sys.argv)
    """
    # Parse command-line arguments
    verbose = False
    input_file = None
    output_file = None

    i = 1
    while i < len(args):
        if args[i] in ['-v', '--verbose']:
            verbose = True
            i += 1
        elif input_file is None:
            input_file = args[i]
            i += 1
        elif output_file is None:
            output_file = args[i]
            i += 1
        else:
            i += 1

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(levelname)s: %(message)s'
    )

    # Validate arguments
    if not input_file or not output_file:
        logger.error("Usage: %s [-v|--verbose] input.asm output.mem", args[0])
        sys.exit(1)

    logger.info(f"Reading input file: {input_file}")

    # Read input assembly file
    try:
        with open(input_file, 'r') as f:
            lines = f.readlines()
    except IOError as e:
        logger.error(f"Failed to read input file '{input_file}': {e}")
        sys.exit(1)

    logger.info(f"Read {len(lines)} lines from {input_file}")

    # Assemble
    output = assemble(lines)

    logger.info(f"Writing output file: {output_file}")

    # Write output file
    try:
        with open(output_file, 'w') as f:
            for hex_str in output:
                f.write(hex_str + '\n')
    except IOError as e:
        logger.error(f"Failed to write output file '{output_file}': {e}")
        sys.exit(1)

    logger.info(f"Assembly completed successfully")
    logger.info(f"Generated {ROM_SIZE} ROM entries ({len([x for x in output if x != '00000'])} instructions, "
                f"{output.count('00000')} padding)")

if __name__ == "__main__":
    main(sys.argv)
