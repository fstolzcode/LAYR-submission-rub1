import sys
import assembler

INSTRUCTION_OPCODE_MAP = {i[1]: i for i in assembler.INSTRUCTION_SET}

opcode_justify = max(map(lambda e: len(e), assembler.INSTRUCTION_MAP.keys()))

filename = sys.argv[1] if len(sys.argv) == 2 else "rom.mem"
instructions = open(filename, "r").readlines()

for i, e in enumerate(instructions):
    instr = int(e, 16)
    immld_op = (instr & 0b111100000000000000) >> 12
    immld_arg0 = (instr & 0b000011111111000000) >> 6
    immld_arg1 = (instr & 0b000000000000111111) >> 0

    op = (instr & 0b111111000000000000) >> 12
    arg0 = (instr & 0b000000111111000000) >> 6
    arg1 = (instr & 0b000000000000111111) >> 6

    addr_arg0 = ((instr & 0b000000111111000000) >> 6) | ((instr & 0b000000000000001111) << 6)

    decoded = next(filter(lambda e: e is not None, map(lambda e: INSTRUCTION_OPCODE_MAP.get(e), [op, immld_op])))

    print(f"{i: 4}: {decoded[0].rjust(opcode_justify)}", end="")
    match decoded[3]:
        case assembler.encodings.DEFAULT:
            if decoded[2] > 0: print(f"{arg0: 4}", end="")
            if decoded[2] > 1: print(f", {arg1: 4}", end="")
        case assembler.encodings.IMM_DST:
            print(f"{immld_arg0: 4}, {immld_arg1: 4}", end="")
        case assembler.encodings.ABS_ADDR:
            print(f"{addr_arg0: 4}", end="")

    print()
