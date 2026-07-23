# Main Controller Instruction Set Architecture

## Overview

The main controller uses a custom 18-bit instruction set architecture designed to schedule the execution of various sub-FSMs to facilitate NFC communcation. The instruction set provides general-purpose and control-flow operations as well as access to: CRC computation, EEPROM access, RC522 NFC communication.

**General Overview:**
- 18-bit instruction width
- 64 × 8-bit general-purpose RAM
- 512-word program ROM (9-bit fetch address), 512-word debug RAM that can be addressed via upper 10th bit
- 4-level call stack
- **BAR (Base Address Register)** for relative memory operations

## Memory Addressing Model

### BAR-Based Addressing

All RAM accesses are performed relative to the **BAR (Base Address Register)**:

```
Effective Address = RAM[BAR + arg]
```

* `arg` remains a 6-bit operand (0–63)
* `BAR` is implicitly added to all RAM accesses
* This enables efficient windowed memory access and block processing

## Instruction Format

All instructions follow the same 18-bit format:

```
Bits [17:12]: Opcode  (6 bits, 0-63)
Bits [11:6]:  Arg1    (6 bits, operand 1)
Bits [5:0]:   Arg2    (6 bits, operand 2)
```

The interpretation of arg1 and arg2 depends on the instruction's encoding type.

## Encoding Types

### DEFAULT Encoding (Type 0)

Standard encoding with two 6-bit operands:
- **Arg1**: First operand (0-63) - typically RAM address or relative offset
- **Arg2**: Second operand (0-63) - typically RAM address

**Example:** `ADD 5, 10` → Add RAM[5] + RAM[10], store in RAM[10]

### IMM_DST Encoding (Type 1)

Special encoding for 8-bit immediate values (IMMLD instruction):
- **Opcode[1:0]**: Upper 2 bits of 8-bit immediate
- **Arg1[5:0]**: Lower 6 bits of 8-bit immediate
- **Arg2[5:0]**: Destination RAM address

The IMMLD instruction has 4 variants (opcodes 60-63) to encode the full 8-bit range:
- `OP_IMMLD00` (60): Immediate values 0x00-0x3F
- `OP_IMMLD01` (61): Immediate values 0x40-0x7F
- `OP_IMMLD10` (62): Immediate values 0x80-0xBF
- `OP_IMMLD11` (63): Immediate values 0xC0-0xFF

**Example:** `IMMLD 0xFF, 10` → Load immediate 0xFF into RAM[10]

### ABS_ADDR Encoding (Type 2)

10-bit absolute addressing for control flow instructions:
- **Arg1[5:0]**: Lower 6 bits of 10-bit address (bits 5:0)
- **Arg2[3:0]**: Upper 4 bits of 10-bit address (bits 9:6)
- **Address reconstruction**: `{arg2[3:0], arg1[5:0]}` = 10-bit address (0-1023)
- **Note**: The 10-bit address spans a unified 1024-word space. Bit 9 (the 10th bit)
  selects the memory: `pc[9]=0` → 512-word program ROM, `pc[9]=1` → 512-word debug
  instruction RAM. Both are indexed by the low 9 bits `pc[8:0]`. Normal programs live in
  0-511; 512-1023 fetches debugger-loaded code.

**Example:** `CALL .subroutine` → Call subroutine at absolute address of .subroutine

## Label Addressing Modes

### Relative Signed Offset (6-bit, -32 to +31)
Used by: Most branch instructions (not implemented yet, reserved for future use)
- Offset calculated from PC+1 (next instruction)
- Two's complement for negative offsets

### Absolute Address (10-bit encoding)
Used by: CALL, JMPC, JMPNC (and JUMPE — but see the JUMPE note below)
- 10-bit address; bit 9 selects program ROM (0-511) vs. debug instruction RAM (512-1023),
  each 512 words indexed by `pc[8:0]`
- Label resolved to absolute address

### Unsigned Relative Offset (6-bit, 0-63)
Used by: INSROMRDL, INSROMRDH
- Offset calculated from current PC
- Forward jumps only (to access data constants)

## Instruction Set Reference

| Mnemonic | Opcode | Operands | Encoding | Format | Description |
|----------|--------|----------|----------|--------|-------------|
| **CRC Instructions** |
| CRCRST | 0 | 0 | DEFAULT | `CRCRST` | Reset CRC-16 core |
| CRCLD | 1 | 1 | DEFAULT | `CRCLD src` | Load RAM[src] byte into CRC computation |
| CRCH | 2 | 1 | DEFAULT | `CRCH dst` | Write CRC high byte to RAM[dst] |
| CRCL | 3 | 1 | DEFAULT | `CRCL dst` | Write CRC low byte to RAM[dst] |
| **EEPROM Instructions** |
| ROMRST | 4 | 0 | DEFAULT | `ROMRST` | Reset EEPROM controller |
| ROMRD | 5 | 2 | DEFAULT | `ROMRD eep_addr, ram_dst` | Read EEPROM[eep_addr] → RAM[ram_dst] |
| **RC522 Instructions** |
| RC522RST | 6 | 0 | DEFAULT | `RC522RST` | Initialize/reset RC522 module |
| RC522PUSH | 7 | 1 | DEFAULT | `RC522PUSH src` | Push RAM[src] to RC522 FIFO |
| RC522POP | 8 | 1 | DEFAULT | `RC522POP dst` | Pop RC522 FIFO to RAM[dst] |
| RC522BLEN | 9 | 1 | DEFAULT | `RC522BLEN imm` | Set last byte length from immediate (0=8 bits, 1-7=1-7 bits) |
| RC522TRCVE | 10 | 0 | DEFAULT | `RC522TRCVE` | Start transceive operation |
| RC522BUFRST | 11 | 0 | DEFAULT | `RC522BUFRST` | Reset RC522 buffer |
| RC522WAIT | 12 | 0 | DEFAULT | `RC522WAIT` | Wait for RC522 operation to complete (reset) |
| RC522RXNUM | 39 | 1 | DEFAULT | `RC522RXNUM dst` | Get number of received bytes to RAM[dst] |
| **RNG Instructions** |
| RNGRST | 13 | 0 | DEFAULT | `RNGRST` | Reset random number generator |
| RNGGET | 14 | 1 | DEFAULT | `RNGGET dst` | Get random byte to RAM[dst] |
| **Comparison Instructions** |
| CMPEQ | 15 | 2 | DEFAULT | `CMPEQ src1, src2` | Compare RAM[src1] == RAM[src2], set cmp_flag |
| CMPLT | 16 | 2 | DEFAULT | `CMPLT src1, src2` | Compare RAM[src1] < RAM[src2], set cmp_flag |
| **Control Flow Instructions** |
| JMPC | 17 | 1 | ABS_ADDR | `JMPC addr` | Jump to addr if cmp_flag == 1 |
| JUMPE | 18 | 1 | ABS_ADDR | `JUMPE addr` | **Reserved / non-functional** — decoded but does not branch (see note) |
| CALL | 19 | 1 | ABS_ADDR | `CALL addr` | Push PC+1 to stack, jump to addr |
| RET | 20 | 0 | DEFAULT | `RET` | Pop address from stack, jump to it |
| JMPNC | 24 | 1 | ABS_ADDR | `JMPNC addr` | Jump to addr if cmp_flag == 0 |
| **Arithmetic Instructions** |
| ADD | 21 | 2 | DEFAULT | `ADD src, dst` | RAM[dst] = RAM[src] + RAM[dst] |
| XOR | 22 | 2 | DEFAULT | `XOR src, dst` | RAM[dst] = RAM[src] ^ RAM[dst] |
| AND | 23 | 2 | DEFAULT | `AND src, dst` | RAM[dst] = RAM[src] & RAM[dst] |
| **Data Movement Instructions** |
| INSROMRDL | 25 | 2 | DEFAULT | `INSROMRDL offset, dst` | Read ROM[PC+offset] low byte → RAM[dst] |
| INSROMRDH | 26 | 2 | DEFAULT | `INSROMRDH offset, dst` | Read ROM[PC+offset] high byte → RAM[dst] |
| MOV | 27 | 2 | DEFAULT | `MOV src, dst` | Copy RAM[src] → RAM[dst] |
| IMOV | 30 | 2 | DEFAULT | `IMOV ptr, dst` | Indirect move: RAM[dst] = RAM[RAM[ptr]] |
| SMOV | 41 | 2 | DEFAULT | `SMOV src, ptr` | Indirect store: RAM[RAM[ptr]] = RAM[src] |
| IMMLD | 60-63 | 2 | IMM_DST | `IMMLD imm8, dst` | Load 8-bit immediate → RAM[dst] |
| **AES Instructions** |
| AESRST | 31 | 0 | DEFAULT | `AESRST` | Reset AES-128 encryption wrapper |
| AESPUSHD | 32 | 1 | DEFAULT | `AESPUSHD src` | Push data byte RAM[src] to AES input buffer |
| AESPUSHK0 | 33 | 1 | DEFAULT | `AESPUSHK0 src` | Push key byte RAM[src] to key_in_0 (first share) |
| AESPUSHK1 | 34 | 1 | DEFAULT | `AESPUSHK1 src` | Push key byte RAM[src] to key_in_1 (second share) |
| AESPOP | 35 | 1 | DEFAULT | `AESPOP dst` | Pop output byte from AES to RAM[dst] |
| AESMODE | 36 | 1 | DEFAULT | `AESMODE imm` | Set AES mode from immediate operand (1=encrypt, 0=decrypt) |
| AESSTART | 37 | 0 | DEFAULT | `AESSTART` | Start AES operation (encrypt/decrypt) |
| AESBUFRST | 38 | 0 | DEFAULT | `AESBUFRST` | Reset AES buffers and counters |
| **UART Instructions** |
| UARTTX | 40 | 1 | DEFAULT | `UARTTX src` | Transmit RAM[src] via UART at 9600 baud |
| **Debug / Security Instructions** |
| LOCK | 42 | 1 | DEFAULT | `LOCK imm` | Set unlock register to imm[0] (`LOCK 1` unlocks, `LOCK 0` locks) |
| STACKFLSH | 46 | 0 | DEFAULT | `STACKFLSH` | Flush the call stack (call_sp = 0, call_full = 0) |
| SPIDBG | 43 | 1 | DEFAULT | `SPIDBG imm` | SPI debug enable = imm[0] |
| SPICS | 44 | 1 | DEFAULT | `SPICS imm` | Set SPI debug chip-select = imm[1:0] |
| SPITX | 45 | 2 | DEFAULT | `SPITX src, dst` | SPI debug: transmit RAM[src], store received byte → RAM[dst] |
| **BAR / Repeat / CRC Block Instructions** |
| REP | 28 | 2 | DEFAULT | `REP num_instr, num_rep` | Repeat next `num_instr` instructions `num_rep` times; increments BAR each iteration. Any taken branch exits REP |
| CRCPW | 29 | 2 | DEFAULT | `CRCPW first_byte, num_bytes` | Compute CRC over region and append result (little endian) at end |
| CRCPC | 47 | 2 | DEFAULT | `CRCPC first_byte, num_bytes` | Compute CRC and compare with stored value; sets cmp_flag |
| RPTZ  | 48 | 0  | DEFAULT | `RPTZ` | Reset BAR and REP/CRC internal counters (debug use) |

## Assembler Directives

### .word - Embed Data Constant

Inserts an 18-bit data constant into ROM.

**Syntax:** `.word <value>`
- Value range: 0 to 0x3FFFF (18-bit)
- Takes 1 ROM location
- Typically used with INSROMRDL/INSROMRDH to read constants

**Example:**
```asm
.constants:
.word 0x12345    @ Stores 18-bit value in ROM
```

## Detailed Instruction Categories

### CRC Instructions

The CRC instructions provide hardware-accelerated CRC-16 computation.

**Typical Flow:**
1. `CRCRST` - Reset CRC core
2. `CRCLD` - Load bytes sequentially
3. `CRCH/CRCL` - Read 16-bit result

**Example - Compute CRC of 4 bytes:**
```asm
@ Reset CRC
CRCRST

@ Load data bytes from RAM[0] through RAM[3]
CRCLD 0
CRCLD 1
CRCLD 2
CRCLD 3

@ Read CRC result
CRCH 10    @ High byte → RAM[10]
CRCL 11    @ Low byte → RAM[11]
```

**Extended CRC Operations (`CRCPW first_byte, num_bytes`):**

> **Note:** These instructions **set** the base to `first_byte` (they overwrite BAR with
> `first_byte` and reset it to 0 when done). They do *not* add to the current BAR — any
> prior BAR value is discarded. `first_byte` therefore acts as an absolute start address.

* Computes CRC over:

  ```
  RAM[first_byte] ... RAM[first_byte + num_bytes - 1]
  ```
* Writes result in **little-endian order**:

  ```
  RAM[first_byte + num_bytes]     = CRC low byte
  RAM[first_byte + num_bytes + 1] = CRC high byte
  ```
* **Restriction:** Cannot be used inside a `REP` block (it clobbers the REP/BAR counters)

#### CRCPC — CRC Compute and Compare

* Computes CRC over the same region (`RAM[first_byte] ... RAM[first_byte + num_bytes - 1]`)
* Compares against the stored CRC immediately after the region
  (`RAM[first_byte + num_bytes]` = low, `+ 1` = high)
* Sets `cmp_flag` accordingly
* **Restriction:** Cannot be used inside a `REP` block

### EEPROM Instructions

Access external SPI EEPROM for persistent storage.

**Example - Read from EEPROM:**
```asm
ROMRST              @ Reset EEPROM controller
IMMLD 0x05, 0       @ EEPROM address in RAM[0]
ROMRD 0, 10         @ Read EEPROM[0] → RAM[10]
```

### RC522 RFID Instructions

Interface with RC522 RFID reader module via internal controller.

**Typical Communication Flow:**
1. `RC522RST` - Initialize module
2. `RC522BUFRST` - Clear FIFO
3. `RC522PUSH` - Write command/data to FIFO
4. `RC522TRCVE` - Start transceive
5. `RC522WAIT` - Wait for completion
6. `RC522POP` - Read response from FIFO

**Example - Send Command and Get Response:**
```asm
RC522RST            @ Initialize RC522
RC522BUFRST         @ Clear buffer
IMMLD 0x26, 0       @ REQA command
RC522PUSH 0         @ Push command to FIFO
RC522BLEN 7         @ Set last-byte bit length to 7 (immediate operand)
RC522TRCVE          @ Start transceive
RC522POP 10         @ Read response byte 0 → RAM[10]
RC522POP 11         @ Read response byte 1 → RAM[11]
RC522RXNUM 12       @ Get number of received bytes → RAM[12]
```

### Comparison and Control Flow

**Compare Instructions:**
- Set `cmp_flag` based on comparison result
- Used with conditional jumps

**Control Flow General**
- The ROM is executed from top to bottom. 
- The order of operations in the code is mirrored in ROM. Thus, the first line of Code is executed first.
- Labels can be referenced, but are ignored during execution. 
- There are no differences between Data and Code. Datastructures like .words have to be jumped over.

**Control Flow Instructions:**
- **JMPC/JMPNC**: Conditional jumps based on cmp_flag
- **CALL/RET**: Subroutine calls with 4-level hardware stack
- **JUMPE**: Reserved. See note below.

> **Note on JUMPE (opcode 18):** In this silicon revision JUMPE is decoded but has no
> effect — it does **not** branch. The associated `err_flag` is never set by any
> instruction and is not wired to a branch decision, so JUMPE behaves as a NOP (PC simply
> advances).

**Example - Conditional Loop:**
```asm
@ Loop 10 times
IMMLD 0, 5          @ Counter = 0
IMMLD 10, 6         @ Limit = 10

.loop:
@ Do work here...

@ Increment counter
IMMLD 1, 7
ADD 7, 5            @ counter++

@ Check if counter < limit
CMPLT 5, 6          @ counter < limit?
JMPC .loop          @ Jump if yes

@ Continue after loop...
```

**Example - Subroutine Call:**
```asm
@ Main program
CALL .subroutine    @ Call subroutine
IMMLD 1, 0          @ Continue here after return

@ Subroutine definition
.subroutine:
IMMLD 0xFF, 10      @ Do some work
RET                 @ Return to caller
```

### Data Movement Instructions

**IMMLD - Immediate Load:**
Load 8-bit constants into RAM. Automatically selects correct encoding variant.

**Example:**
```asm
IMMLD 0x00, 0       @ Load 0x00 into RAM[0]
IMMLD 0x42, 1       @ Load 0x42 into RAM[1]
IMMLD 0xFF, 2       @ Load 0xFF into RAM[2]
```

**MOV - Move Register:**
Copy data between RAM locations without modifying source.

**Example:**
```asm
IMMLD 0x42, 5       @ RAM[5] = 0x42
MOV 5, 10           @ RAM[10] = RAM[5] (RAM[5] unchanged)
```

**INSROMRDL/INSROMRDH - Read ROM Constants:**
Read 16-bit constants stored in ROM using PC-relative addressing.

**Example:**
```asm
@ Read 16-bit constant from ROM
INSROMRDL .data, 10    @ Read low byte → RAM[10]
INSROMRDH .data, 11    @ Read high byte → RAM[11]
IMMLD 0, 0             @ Some instruction
IMMLD 0, 1             @ Another instruction

.data:
.word 0x12345          @ Constant: low=0x45, high=0x34
```

The offset is calculated automatically: if `.data` is 4 instructions away, assembler encodes offset=4.

**IMOV - Indirect Move:**
Indirect addressing: dereference a pointer stored in RAM.

**Example:**
```asm
IMMLD 5, 0          @ RAM[0] = 5 (pointer)
IMMLD 0x42, 5       @ RAM[5] = 0x42 (data at address 5)
IMOV 0, 10          @ RAM[10] = RAM[RAM[0]] = RAM[5] = 0x42
```

**SMOV - Indirect Store:**
Indirect addressing store — the counterpart of IMOV. Writes a source value to the
RAM location named by a pointer stored in RAM: `RAM[RAM[ptr]] = RAM[src]`.

**Example:**
```asm
IMMLD 5, 0          @ RAM[0] = 5 (pointer)
IMMLD 0x42, 1       @ RAM[1] = 0x42 (data to store)
SMOV 1, 0           @ RAM[RAM[0]] = RAM[1] → RAM[5] = 0x42
```

### RNG Instructions

The RNG (Random Number Generator) provides hardware-generated random bytes using an xorshift algorithm.

**Typical Flow:**
1. `RNGRST` - Reset/initialize RNG
2. `RNGGET` - Get random bytes as needed

**Example:**
```asm
RNGRST              @ Initialize RNG
RNGGET 0            @ Get random byte → RAM[0]
RNGGET 1            @ Get random byte → RAM[1]
RNGGET 2            @ Get random byte → RAM[2]
```

### AES Instructions

The AES instructions provide hardware-accelerated AES-128 encryption and decryption with masked key support (two key shares for side-channel protection).

**Typical Encryption Flow:**
1. `AESRST` - Reset AES wrapper
2. `AESBUFRST` - Clear buffers
3. `AESPUSHD` × 16 - Push 16 data bytes
4. `AESPUSHK0` × 16 - Push 16 bytes of first key share
5. `AESPUSHK1` × 16 - Push 16 bytes of second key share
6. `AESMODE` - Set mode via immediate operand (1=encrypt, 0=decrypt)
7. `AESSTART` - Start operation
8. `AESPOP` × 16 - Pop 16 output bytes

**Example - AES Encryption:**
```asm
@ Reset AES
AESRST
AESBUFRST

@ Load 16-byte plaintext to data buffer
IMMLD 0, 0          @ Counter for loop
.load_data:
AESPUSHD 0          @ Push RAM[0] to AES data
IMMLD 1, 10
ADD 10, 0           @ counter++
IMMLD 16, 10
CMPLT 0, 10         @ counter < 16?
JMPC .load_data

@ Load 16-byte key share 0
IMMLD 0, 0
.load_key0:
AESPUSHK0 20        @ Push RAM[20+offset] to key_in_0
@ ... (similar loop)

@ Load 16-byte key share 1
IMMLD 0, 0
.load_key1:
AESPUSHK1 40        @ Push RAM[40+offset] to key_in_1
@ ... (similar loop)

@ Set mode and encrypt
AESMODE 1           @ 1 = encrypt (immediate operand, 0 = decrypt)
AESSTART            @ Start encryption

@ Read 16-byte ciphertext
IMMLD 0, 0
.read_output:
AESPOP 60           @ Pop to RAM[60+offset]
@ ... (similar loop)
```

### UART Instructions

The UART TX instruction transmits bytes via UART at 9600 baud. Note: UART transmission is only available when debug mode is disabled (`mode=0`).

**Example:**
```asm
@ Send "Hello" via UART
IMMLD 0x48, 0       @ 'H'
UARTTX 0
IMMLD 0x65, 0       @ 'e'
UARTTX 0
IMMLD 0x6C, 0       @ 'l'
UARTTX 0
UARTTX 0            @ 'l' again
IMMLD 0x6F, 0       @ 'o'
UARTTX 0
```

### Arithmetic Instructions

All arithmetic instructions modify the destination operand (arg2).

**ADD - Addition:**
```asm
IMMLD 5, 0          @ RAM[0] = 5
IMMLD 3, 1          @ RAM[1] = 3
ADD 0, 1            @ RAM[1] = RAM[0] + RAM[1] = 8
```

**XOR - Exclusive OR:**
```asm
IMMLD 0xAA, 0       @ RAM[0] = 0xAA
IMMLD 0x55, 1       @ RAM[1] = 0x55
XOR 0, 1            @ RAM[1] = 0xAA ^ 0x55 = 0xFF
```

**AND - Bitwise AND:**
```asm
IMMLD 0xFF, 0       @ RAM[0] = 0xFF
IMMLD 0x0F, 1       @ RAM[1] = 0x0F
AND 0, 1            @ RAM[1] = 0xFF & 0x0F = 0x0F
```

### Debug / Security Instructions

These instructions control the lock state, the debug SPI master, and the call stack.
`LOCK`, `SPIDBG`, and `SPICS` take their operand as an **immediate** (not a RAM address).

**LOCK - Lock/Unlock:**
Sets the unlock register from bit 0 of the immediate operand. `LOCK 1` unlocks,
`LOCK 0` locks.
```asm
LOCK 1              @ Unlock
LOCK 0              @ Lock
```

**STACKFLSH - Flush Call Stack:**
Resets the call stack pointer and the `call_full` flag (`call_sp = 0`, `call_full = 0`).
Takes no operands. Intended for reinitialization / error recovery.
```asm
STACKFLSH           @ Empty the 4-level call stack
```

**SPIDBG / SPICS / SPITX - Debug SPI Master:**
Direct access to the debug SPI master. `SPIDBG imm` enables/disables debug SPI (imm[0]);
`SPICS imm` selects the chip-select line (imm[1:0]); `SPITX src, dst` transmits RAM[src]
and writes the received byte to RAM[dst].
```asm
SPIDBG 1            @ Enable debug SPI
SPICS 1             @ Select chip-select line 1
IMMLD 0x9F, 0       @ Byte to send
SPITX 0, 10         @ Transmit RAM[0], received byte → RAM[10]
```

## Repeat Mechanism

### REP — Repeat Block Execution

The `REP` instruction enables compact loop execution without explicit branching.

**Syntax:**

```asm
REP num_instr, num_rep
```

**Behavior:**

* Repeats the next `num_instr` instructions
* Executes them `num_rep` times
* After each repetition:

  * `BAR` is incremented automatically
* If any **branch is taken** during execution:

  * REP is immediately terminated
  * Control continues at branch target

**Key Properties:**

* Works like a hardware loop with implicit pointer increment
* Useful for block processing (e.g., arrays, buffers)
* No explicit loop counter needed

**Example:**

```asm
@ Process 8 bytes starting at BAR
REP 2, 8
CRCLD 0       @ Load byte at BAR+0
CRCLD 1       @ Load byte at BAR+1
```

### RPTZ — Reset Repeat/CRC State

**Syntax:**

```asm
RPTZ
```

**Behavior:**

* Resets:

  * BAR register
  * REP internal counters
  * CRC block operation state
* Intended primarily for debugging and safe reinitialization

## Complete Examples

### Example 1: CRC Calculation with Data Table

```asm
@ Calculate CRC-16 of data stored in ROM

@ Read data from ROM into RAM
INSROMRDL .data, 0     @ Byte 0
INSROMRDL .data+1, 1   @ Byte 1
INSROMRDL .data+2, 2   @ Byte 2
INSROMRDL .data+3, 3   @ Byte 3

@ Compute CRC
CRCRST
CRCLD 0
CRCLD 1
CRCLD 2
CRCLD 3

@ Store result
CRCH 10    @ High byte in RAM[10]
CRCL 11    @ Low byte in RAM[11]

@ Data table
.data:
.word 0x00041    @ Byte 0: 0x41
.word 0x00042    @ Byte 1: 0x42
.word 0x00043    @ Byte 2: 0x43
.word 0x00044    @ Byte 3: 0x44
```

### Example 2: Subroutine with Loop

```asm
@ Main program
IMMLD 5, 0              @ Input value
CALL .multiply_by_10    @ Call subroutine
@ Result in RAM[0]

@ Multiply by 10 subroutine (add value 10 times)
.multiply_by_10:
MOV 0, 1                @ Save input in RAM[1]
IMMLD 0, 0              @ Result = 0
IMMLD 0, 2              @ Counter = 0
IMMLD 10, 3             @ Limit = 10

.loop:
ADD 1, 0                @ Result += input
IMMLD 1, 4
ADD 4, 2                @ Counter++
CMPLT 2, 3              @ Counter < 10?
JMPC .loop              @ Loop if yes

RET                     @ Return with result in RAM[0]
```

### Example 3: Reading 16-bit Constant

```asm
@ Load 16-bit constant 0x1234 from ROM
INSROMRDL .constant, 10    @ Low byte (0x34) → RAM[10]
INSROMRDH .constant, 11    @ High byte (0x12) → RAM[11]

@ Now RAM[10]=0x34, RAM[11]=0x12 representing 0x1234

.constant:
.word 0x1234    @ 16-bit constant (upper 2 bits unused)
```

## Quick Reference

### Opcode Map (Sorted by Opcode)

| Opcode | Mnemonic | Opcode | Mnemonic | Opcode | Mnemonic |
|--------|----------|--------|----------|--------|----------|
| 0 | CRCRST | 17 | JMPC | 34 | AESPUSHK1 |
| 1 | CRCLD | 18 | JUMPE* | 35 | AESPOP |
| 2 | CRCH | 19 | CALL | 36 | AESMODE |
| 3 | CRCL | 20 | RET | 37 | AESSTART |
| 4 | ROMRST | 21 | ADD | 38 | AESBUFRST |
| 5 | ROMRD | 22 | XOR | 39 | RC522RXNUM |
| 6 | RC522RST | 23 | AND | 40 | UARTTX |
| 7 | RC522PUSH | 24 | JMPNC | 41 | SMOV |
| 8 | RC522POP | 25 | INSROMRDL | 42 | LOCK |
| 9 | RC522BLEN | 26 | INSROMRDH | 43 | SPIDBG |
| 10 | RC522TRCVE | 27 | MOV | 44 | SPICS |
| 11 | RC522BUFRST | 28 | REP | 45 | SPITX |
| 12 | RC522WAIT | 29 | CRCPW | 46 | STACKFLSH |
| 13 | RNGRST | 30 | IMOV | 47 | CRCPC |
| 14 | RNGGET | 31 | AESRST | 48 | RPTZ |
| 15 | CMPEQ | 32 | AESPUSHD | 60-63 | IMMLD |
| 16 | CMPLT | 33 | AESPUSHK0 | | |

\* JUMPE (18) is decoded but non-functional in this silicon revision — see the JUMPE note.

### Instruction Categories

| Category | Instructions | Count |
|----------|-------------|-------|
| CRC | CRCRST, CRCLD, CRCH, CRCL | 4 |
| EEPROM | ROMRST, ROMRD | 2 |
| RC522 | RC522RST, RC522PUSH, RC522POP, RC522BLEN, RC522TRCVE, RC522BUFRST, RC522WAIT, RC522RXNUM | 8 |
| RNG | RNGRST, RNGGET | 2 |
| Comparison | CMPEQ, CMPLT | 2 |
| Control Flow | JMPC, JMPNC, JUMPE*, CALL, RET | 5 |
| Arithmetic | ADD, XOR, AND | 3 |
| Data Movement | IMMLD, MOV, IMOV, SMOV, INSROMRDL, INSROMRDH | 6 |
| AES | AESRST, AESPUSHD, AESPUSHK0, AESPUSHK1, AESPOP, AESMODE, AESSTART, AESBUFRST | 8 |
| UART | UARTTX | 1 |
| Debug / Security | LOCK, STACKFLSH, SPIDBG, SPICS, SPITX | 5 |
| Repeat / CRC Block | REP, CRCPW, CRCPC, RPTZ | 4 |
| **Total** | | **50** |

\* JUMPE is decoded but non-functional in this silicon revision (reserved).

### Encoding Type Summary

| Encoding | Instructions | Key Feature |
|----------|-------------|-------------|
| DEFAULT | Most instructions | Standard 6-bit operands |
| IMM_DST | IMMLD | 8-bit immediate value |
| ABS_ADDR | CALL, JMPC, JMPNC, JUMPE | 10-bit absolute address |

## Notes

### Stack Depth
The hardware call stack has 4 levels. Exceeding this depth will set the `call_full` flag but continues using the top level (may cause incorrect returns).

### RAM Addressing
All RAM addresses are 6-bit (0-63), providing 64 bytes of general-purpose RAM.

### Label Syntax
- **Definition**: `.labelname:`
- **Reference**: `.labelname` (dot prefix required)
- Labels are case-insensitive


### Assembler Usage

```bash
python3 assembler.py [-v|--verbose] input.asm output.mem
```

- Input: Assembly source file (.asm)
- Output: ROM memory file (.mem) in hex format for Verilog $readmemh
- Verbose flag: Enable detailed assembly logging

### BAR Behavior

* BAR is implicitly applied to all RAM accesses
* Automatically incremented by `REP`
* Can be reset using `RPTZ`
* Enables efficient memory windowing

### REP Restrictions

* Any taken branch exits REP immediately
* Nested REP behavior is undefined (should be avoided)

### CRC Block Restrictions

* `CRCPW` and `CRCPC` **must not be used inside REP** (they overwrite the REP/BAR counters)
* They operate on a contiguous memory region starting at `first_byte`; they set the base to
  `first_byte` and reset it to 0 on completion (they do not add to the current BAR)

## Version Information

* Date: 18.03.2026
* Revision:

  * Added BAR-based addressing model
  * Added REP instruction (hardware loop with BAR increment)
  * Added CRCPW (CRC compute and write)
  * Added CRCPC (CRC compute and compare)
  * Added RPTZ (debug reset for BAR/REP/CRC state)
  * Documented SMOV, LOCK, STACKFLSH, and the debug SPI ops (SPIDBG/SPICS/SPITX)
  * Corrected ROM size (512 words), JUMPE status (reserved/non-functional),
    AESMODE/RC522BLEN immediate operands, and CRCPW/CRCPC base behavior
* Total instructions: 50
