# Debug Controller Reference

## Overview

The main controller (`rtl/main_controller.v`) contains an on-chip **debug controller**: a
small UART-driven finite state machine that lets an external host inspect and control the
CPU while the system is running. It is not a separate module — it is a set of always-blocks
and functions inside `main_controller`, in the region marked
`// --- START DEBUG CONTROLLER ---` … `// --- END DEBUG CONTROLLER ---`, plus a little
support logic higher up in the file (the instruction-fetch mux, the `` `dbg_reset_fsm ``
reset macro, and the register write-back that lives inside the CPU's own FETCH state).

**Capabilities:**
- Read most CPU / peripheral state asynchronously during execution (registers, flags, RAM,
  ROM, instruction RAM, SPI/RC522 buffers).
- Halt / run / single-step the CPU.
- Read and write CPU-internal registers (PC, call stack, stack pointer, work RAM).
- Set hardware breakpoints on the program counter.
- Load code into the debug instruction RAM and execute from it.

The debug controller speaks a compact binary protocol over its own UART RX line and
answers on the shared UART TX line.

> This document describes the debug controller **as implemented in the taped-out RTL** and
> validated by `tb/test_main_controller.py`. It supersedes, for reference purposes, the
> earlier design notes in `debug_controller_notes.md` (kept for historical rationale); where
> the two disagree, this document reflects the silicon. Features that were planned but are
> not functional in this revision are listed under
> [Reserved / Not Implemented](#reserved--not-implemented-in-this-revision).

## Enabling and Disabling Debug Mode

The debug controller is gated by the top-level `mode` input (the **DEBUGMODE** line).

- **`mode == 0` (normal):** The debug FSM is held inactive, `DBGCR` is forced to 0, and the
  CPU runs freely regardless of any debug state.
- **`mode` rising (0 → 1):** On the first clock with `mode` high, a power-on reset of the
  debug block runs (the `` `dbg_reset_fsm `` macro): the FSM returns to its idle state and
  `DBGCR`, all breakpoints, and the parameter buffer are cleared. This is tracked by an
  internal `dbg_initialized` flag, so the debugger is always in a known state whenever
  debug mode is entered.
- **While `mode == 1`:** Because `DBGCR` was just cleared (`CPURUN = 0`), the CPU is halted
  **immediately** — it stalls in its FETCH state before executing the next instruction.
  This lets the host inspect a stable snapshot of the system.
- **`mode` falling (1 → 0):** Leaving debug mode performs a **full CPU reset** (`PC = 0`,
  state = FETCH). This is deliberate — the reset guard is
  `if (rst || (dbg_initialized && ~mode))`.

## Debug FSM

State register: `dbg_state` (3-bit).

| State | Value | Purpose |
|-------|-------|---------|
| `DBG_READ_INSN` | 0 | Idle. Wait for a command opcode byte on UART RX. |
| `DBG_READ_PARAM` | 1 | Accumulate the command's argument bytes into the parameter buffer. |
| `DBG_EXECUTE` | 2 | Execute the decoded command. |
| `DBG_WRITE_UART_START` | 3 | Begin transmitting one response byte. |
| `DBG_WRITE_UART_WAIT` | 4 | Wait for the UART to finish the byte, then advance / finish. |

Flow:
1. **READ_INSN** — On a UART-RX byte, latch it as the opcode and look up how many argument
   bytes follow. If zero, go straight to EXECUTE; otherwise go to READ_PARAM.
2. **READ_PARAM** — Store each incoming byte into the parameter buffer. `WRREG` is special:
   the number of value bytes is not known until its 2-byte register selector has arrived, so
   the expected length is patched once the selector's size field is seen.
3. **EXECUTE** — Dispatch on the opcode (see [Instruction Set](#instruction-set)).
4. **WRITE_UART_START / WRITE_UART_WAIT** — Only `RDREG` produces output. The FSM streams
   exactly the register's width in bytes back over UART, then returns to READ_INSN. All other
   commands return to READ_INSN directly.

The UART RX ready signal is edge-detected internally so each received byte advances the FSM
exactly once.

## Instruction Set

Every command starts with a single opcode byte, optionally followed by argument bytes. All
multi-byte fields are **little-endian**.

| Opcode | Value | Arg bytes | Description |
|--------|-------|-----------|-------------|
| `NULL` | 0 | 0 | No operation. The FSM stays in READ_INSN. Used to **resynchronize** a host that is unsure of the FSM state (send enough NULLs to flush any partial command). |
| `RDREG` | 1 | 2 | Read a register. Argument is a 2-byte register selector. Streams back 1/2/3/16 bytes (the register's width) on UART TX. |
| `WRREG` | 2 | 2 + N | Write a register. Argument is a 2-byte selector followed by `N` value bytes, where `N` is the selected register's width. |
| `SINGLESTEP` | 3 | 0 | Advance the CPU by one instruction (see [Run / Halt / Single-Step](#run--halt--single-step)). |
| `RESET` | 4 | 1 | **Reserved / not implemented** in this revision — accepts the module-index byte but performs no reset. See [Reserved](#reserved--not-implemented-in-this-revision). |

Note: the opcode's parameter count is looked up from only the low 3 bits of the opcode byte.

## Register Selector Encoding

Both `RDREG` and `WRREG` take a **16-bit little-endian register selector**:

```
Bits [15:14]: Size selector (0-3)
Bits [13:0]:  Register index (0-16383)
```

The size selector chooses which register bank / access width is used, and therefore how many
bytes are read back (`RDREG`) or expected as the value (`WRREG`):

| Size selector | Name | Width (bytes) | Bank |
|---------------|------|---------------|------|
| 0 | `REGSZ_1` | 1 | 8-bit registers / flags / CPU work RAM |
| 1 | `REGSZ_2` | 2 | PC / call stack / breakpoints |
| 2 | `REGSZ_3` | 3 | Instruction ROM / instruction RAM (18-bit words) |
| 3 | `REGSZ_16` | 16 | AES 128-bit registers (**reserved**, see below) |

The width mapping is `{1, 2, 3, 16}` — it is **not** `1 << size`.

Constructing a selector (host side): `selector = (size << 14) | index`, transmitted as 2
little-endian bytes. For example, size `REGSZ_2` (1) with index 0 (PC) is
`(1 << 14) | 0 = 0x4000`, sent as bytes `00 40`.

## Register Map

Each size class has its own index space. Not every index is populated; reads of an
unmapped index return 0 and writes are ignored.

### Size class `REGSZ_1` (1 byte)

| Index | Name | R/W | Meaning |
|-------|------|-----|---------|
| 0 | `FLAGS` | R | `{6'b0, err_flag, cmp_flag}` |
| 1 | `CPUSTATE` | R | CPU main-FSM state (FETCH = 0; see main controller) |
| 2 | `SP` | R/W | Call-stack pointer |
| 3 | `SPIFLAGS` | R | `{3'b0, spi_busy, spi_start_tx_rc522, spi_start_tx_eeprom, spi_open_cs1, spi_open_cs0}` |
| 4 | `SPITX_EEPROM` | R | SPI transmit buffer (EEPROM) |
| 5 | `SPITX_RC522` | R | SPI transmit buffer (RC522) |
| 6 | `SPIRX` | R | SPI receive data |
| 7 | `RC522_IN` | R | RC522 data input |
| 8 | `RC522_OUT` | R | RC522 data output |
| 9 | `AESFLAGS` | — | **Reserved** (read path commented out → reads 0) |
| 10 | `DBGCR` | R/W | Debug control register (see [DBGCR](#debug-control-register-dbgcr)) |
| 11 | `CALLFULL` | R/W | Call-stack-full flag |
| 64 + i | `CPUREG` | R/W | CPU work RAM: index `64 + i` maps to `ram_data[i]`, for `i` in 0..63 |

### Size class `REGSZ_2` (2 bytes)

| Index | Name | R/W | Meaning |
|-------|------|-----|---------|
| 0 | `PC` | R/W | Program counter (10-bit) |
| 1 … 4 | `STACK` | R/W | Hardware call stack entries 0..3 (base index `STACK = 1`) |
| 8 … 15 | `BP` | R/W | Hardware breakpoint registers 0..7 (base index `BP = 8`) |

### Size class `REGSZ_3` (3 bytes — 18-bit instruction words)

| Index | Name | R/W | Meaning |
|-------|------|-----|---------|
| 0 … 1023 | `IROM` | R | Program mask ROM (read-only). *See IROM aliasing note.* |
| 1024 … 1535 | `IRAM` | R/W | Debug instruction RAM `dbg_iram` (512 × 18-bit); base index `IRAM = 1024` (`0x400`). |

> **These are debugger register indices, not CPU program-counter addresses.** The same
> IRAM word `dbg_iram[i]` is register index `1024 + i` here, but the CPU *executes* it at
> `PC = 512 + i` (see [Memory Map & Execution Source](#memory-map--execution-source)). The
> IROM index range is a full 1024 words, so IRAM begins right after it at 1024 — this is
> independent of the physical ROM being only 512 words.

### Size class `REGSZ_16` (16 bytes) — **Reserved**

Indices 0..5 are defined for the AES key/input/output shares (`AESKEY0/1`, `AESIN0/1`,
`AESOUT0/1`) but the read and write paths are commented out in this revision, so all reads
return 0 and there is no write path. See [Reserved](#reserved--not-implemented-in-this-revision).

## Debug Control Register (DBGCR)

`DBGCR` is a 2-bit register at `REGSZ_1` index 10.

| Bit | Name | Function |
|-----|------|----------|
| 0 | `CPURUN` | 1 = allow the CPU to run freely (subject to breakpoints). 0 = CPU halts in FETCH. |
| 1 | `CPUMEMSEL` | **Reserved / unused.** Declared but never read. Execution memory is selected by `PC[9]`, not this bit (see [Memory Map](#memory-map--execution-source)). |

`DBGCR` is reset to 0 when debug mode is entered and forced to 0 whenever `mode == 0`, so it
always reads as 0 while the debugger is inactive.

## Breakpoints

There are **8** hardware breakpoint registers (`REGSZ_2` indices 8..15). Each is an 11-bit
value:

```
Bit [10]:  Enable (1 = active)
Bits [9:0]: Match PC
```

A breakpoint fires when an enabled register's PC field equals the current PC. Because the
run/halt decision is only sampled while the CPU is in its FETCH state, breakpoints
effectively trigger at instruction boundaries (not on internal ROM/data reads).

A breakpoint hit **does not clear `CPURUN`** — it only suppresses CPU advancement while the
PC matches. This gives GDB-like behavior:
- With `CPURUN = 1`, issuing `SINGLESTEP` at a breakpoint acts like **continue**: the CPU
  runs until the next enabled breakpoint.
- With `CPURUN = 0`, `SINGLESTEP` performs a true one-instruction step.

## Run / Halt / Single-Step

The CPU advances only when its internal run signal is asserted:

```
run_cpu = !mode | ( (CPURUN & ~any_breakpoint_hit) | singlestep )
```

- `!mode` — with the debugger disabled the CPU always runs.
- `CPURUN & ~any_breakpoint_hit` — free-run while `DBGCR.CPURUN` is set and no enabled
  breakpoint matches the current PC.
- `singlestep` — asserted for exactly the one cycle the `SINGLESTEP` command is in EXECUTE,
  forcing the CPU to take a single step regardless of `CPURUN`.

This signal is evaluated in the CPU's FETCH state, so the CPU always halts at a clean
instruction boundary.

## Memory Map & Execution Source

The CPU fetches instructions from one of two 512-word memories, selected by bit 9 of the
program counter:

```
instruction = PC[9] ? dbg_iram[PC[8:0]] : rom[PC[8:0]]
```

- **PC 0–511** → 512-word program mask ROM.
- **PC 512–1023** → 512-word debug instruction RAM (`dbg_iram`).

So a host can load code into IRAM via `WRREG` (`REGSZ_3`, indices 1024..1535), then set the
PC to `512 + offset` and single-step to execute it. (This is the same unified 1024-word
address space described in `sw/INSTRUCTION_SET.md`.)

The debugger's own view of memory is expressed through the register indices above, **not** a
flat byte address space:

| Region | Access | Selector |
|--------|--------|----------|
| Program ROM (IROM) | read-only | `REGSZ_3`, index `0 + word` |
| Debug instruction RAM (IRAM) | read/write | `REGSZ_3`, index `1024 + word` |
| CPU work RAM | read/write | `REGSZ_1`, index `64 + byte` |

**Two numbering schemes.** The debugger `REGSZ_3` index is deliberately *not* the same as
the CPU program counter — they address the same two physical memories with different bases:

| Memory | Physical | CPU PC (execution) | Debugger `REGSZ_3` index |
|--------|----------|--------------------|--------------------------|
| Program ROM | 512 words | 0 – 511 | 0 – 1023 (512–1023 **alias** the low 512) |
| Debug IRAM (`dbg_iram`) | 512 words | 512 – 1023 (via `PC[9]`) | 1024 – 1535 |

So IRAM word `i` is executed at `PC = 512 + i` but read/written over the debug protocol at
index `1024 + i`. The debugger reserves a full 1024-word IROM index range (hence IRAM starts
at 1024); because the physical ROM is only 512 words (9-bit `dbg_address`), IROM indices
512–1023 alias back onto ROM words 0–511.

## UART Interface

The debug controller has a **dedicated `uart_rx`** for receiving commands. Responses are
sent on a **single shared `uart_tx`** that is multiplexed by `mode`: while `mode == 1` the
TX line carries debug responses; while `mode == 0` it carries the CPU's own `UARTTX` output.

## Worked Examples

All bytes below are shown in hex, in transmission order (little-endian fields).

### Read the program counter
```
TX → 01 00 40      @ RDREG, selector = REGSZ_2(1)<<14 | PC(0) = 0x4000
RX ← <lo> <hi>     @ 2 bytes, little-endian = current PC
```

### Read CPU state and a work-RAM byte
```
TX → 01 01 00      @ RDREG, REGSZ_1 | CPUSTATE(1); RX ← 1 byte (FETCH = 0)
TX → 01 40 00      @ RDREG, REGSZ_1 | CPUREG(64) = RAM[0]; RX ← 1 byte
```

### Write the PC, then single-step
```
TX → 02 00 40 03 00   @ WRREG, REGSZ_2 | PC(0), value = 3 (2 bytes LE)
TX → 03               @ SINGLESTEP  (CPU executes one instruction; PC → 4)
```

### Load an instruction into IRAM and run it
```
TX → 02 00 84 <lo> <mid> <hi>   @ WRREG, REGSZ_3 | IRAM(1024) = 18-bit word (3 bytes LE)
TX → 02 00 40 00 02             @ WRREG, PC = 512  (0x0200 LE)  → execute from IRAM[0]
TX → 03                         @ SINGLESTEP
```

### Set a breakpoint and continue to it
```
TX → 02 08 40 03 04   @ WRREG, REGSZ_2 | BP(8), value = 0x0403 = PC 3, enabled
TX → 02 0A 00 01      @ WRREG, REGSZ_1 | DBGCR(10), value = 1 (CPURUN = 1)
                      @ CPU free-runs and halts in FETCH at PC 3
TX → 03               @ SINGLESTEP with CPURUN still set → "continue" to next breakpoint
```

### Resynchronize the debugger
```
TX → 00 00 00 ...     @ NULL bytes; leaves the FSM in READ_INSN regardless of prior state
```

## Reserved / Not Implemented in This Revision

These are present in the design/parameters but are **not functional** in the taped-out RTL:

- **`RESET` command (opcode 4):** Accepts its 1-byte module-index operand but performs no
  reset — the execute step is a stub (no reset-assert counter and no module mapping). No
  submodule can currently be reset via the debugger. (The CPU is still reset implicitly when
  debug mode is exited.)
- **AES debug registers (`REGSZ_16`, and `REGSZ_1` `AESFLAGS`):** The read paths are
  commented out, so reads return 0; there is no `REGSZ_16` write path. AES state is not
  accessible via the debugger in this revision.
- **`DBGCR.CPUMEMSEL` (bit 1):** Declared but never read. Execution memory is selected by
  `PC[9]`, not this bit.
- **IROM index range vs. physical ROM:** The `IROM` register range spans 1024 indices, but
  the physical program ROM is only 512 words (9-bit address). IROM indices 512–1023 therefore
  **alias** the low 512 words.

## Quick Reference

### Command opcodes
| Opcode | Value | Args |
|--------|-------|------|
| NULL | 0 | 0 |
| RDREG | 1 | 2 (selector) |
| WRREG | 2 | 2 (selector) + N (value) |
| SINGLESTEP | 3 | 0 |
| RESET | 4 | 1 (reserved) |

### Size selectors
| Selector | Value | Width |
|----------|-------|-------|
| REGSZ_1 | 0 | 1 byte |
| REGSZ_2 | 1 | 2 bytes |
| REGSZ_3 | 2 | 3 bytes |
| REGSZ_16 | 3 | 16 bytes (reserved) |

### Register indices
| Size | Index | Register |
|------|-------|----------|
| REGSZ_1 | 0 | FLAGS |
| REGSZ_1 | 1 | CPUSTATE |
| REGSZ_1 | 2 | SP |
| REGSZ_1 | 3–8 | SPI / RC522 buffers |
| REGSZ_1 | 9 | AESFLAGS (reserved) |
| REGSZ_1 | 10 | DBGCR |
| REGSZ_1 | 11 | CALLFULL |
| REGSZ_1 | 64 + i | CPU work RAM `ram_data[i]` |
| REGSZ_2 | 0 | PC |
| REGSZ_2 | 1–4 | Call stack |
| REGSZ_2 | 8–15 | Breakpoints 0–7 |
| REGSZ_3 | 0–1023 | IROM (read-only) |
| REGSZ_3 | 1024–1535 | IRAM (read/write) |
| REGSZ_16 | 0–5 | AES registers (reserved) |

## Testing

The protocol described here is exercised by the debug testcases in
`tb/test_main_controller.py`: `test_dbg_halt` (DEBUGMODE halt + reset-on-exit),
`test_dbg_uart` (FSM/UART parse, RDREG of sizes 1/2/3), `test_dbg_stepping`
(SINGLESTEP vs. free-run via `DBGCR.CPURUN`), `test_dbg_iram` (write IRAM, execute from
ROM vs. IRAM), `test_dbg_pc_manipulation` (write PC / call stack / SP / call_full), and
`test_dbg_breakpoints` (breakpoints + continue-to-breakpoint). The host-side command
framing is built by the `build_wrreg` helper (`opcode + (size<<14 | index) + value`, all
little-endian).
