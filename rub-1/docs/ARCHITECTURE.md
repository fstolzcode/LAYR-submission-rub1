# System Architecture

## Overview

This chip is a custom **multi-cycle CPU** whose top module is
[`rtl/main_controller.v`](rtl/main_controller.v). Rather than being a general-purpose
processor, it is a compact controller core that **orchestrates a set of hardware
sub-FSMs** (crypto and I/O peripherals) to carry out an NFC authentication protocol with a
JavaCard. The CPU executes a small custom instruction set from ROM; each instruction either
performs a simple operation on internal RAM or issues a command to a peripheral and waits
for it to finish.

This document describes **how the CPU works** and gives an **overview of the submodules**.
It deliberately does **not** cover:
- the instruction set / assembly — see [`sw/INSTRUCTION_SET.md`](sw/INSTRUCTION_SET.md);
- the UART debug controller — see [`DEBUG_CONTROLLER.md`](DEBUG_CONTROLLER.md).

## Top-Level Interface (chip pins)

`main_controller` is the top module; its ports are the chip's external interface
([main_controller.v:2](rtl/main_controller.v#L2)):

| Signal | Dir | Description |
|--------|-----|-------------|
| `clk` | in | 10 MHz system clock |
| `uart_clk_in` | in | Slower reference clock for UART baud timing (baud = `uart_clk_in`/16) |
| `rst` | in | Active-high synchronous reset |
| `mode` | in | Debug switch (DEBUGMODE); see DEBUG_CONTROLLER.md |
| `uart_rxd` | in | UART receive (debug command channel) |
| `uart_txd` | out | UART transmit (CPU output / debug responses) |
| `spi_sclk` | out | Shared SPI clock |
| `spi_mosi` | out | Shared SPI MOSI |
| `spi_miso` | in | Shared SPI MISO |
| `spi_cs_0` | out | SPI chip select 0 → **EEPROM** (active low) |
| `spi_cs_1` | out | SPI chip select 1 → **RC522** (active low) |
| `busy` | out | High while the CPU is executing |
| `hard_fault` | out | Unrecoverable error (illegal opcode/state) |
| `unlock` | out | "Unlock the door" — driven by the `LOCK` instruction |

## Design Model: a controller that schedules sub-FSMs

The core idea: keep the CPU tiny and push all heavy lifting (crypto, SPI, NFC, CRC, UART)
into dedicated peripheral state machines. The CPU issues a one-cycle command to a
peripheral, then parks in a per-peripheral wait state polling a `busy`/`done` handshake,
and finally collects the result. This is why the CPU is **multi-cycle**: every instruction
walks through several FSM states, and peripheral instructions take as long as the
peripheral needs.

### Module hierarchy

```
main_controller (top)                         ── CPU control FSM + datapath + memories + debug ctrl
├── rom                     (rom_inst)         ── 512×18 program ROM (+ debug read port)
├── crc                     (crc_inst)         ── CRC-16 (ISO 14443-A / CRC_A)
├── trivium                 (rng_inst)         ── Trivium PRNG (randomness source)
├── spi_master              (spi_inst)         ── shared 8-bit SPI master
├── eeprom                  (eeprom_inst)      ── external SPI EEPROM reader   → spi_cs_0
├── rc522_wrapper           (rc522_wrapper_inst)
│   └── rc522                                  ── ISO 14443-A NFC reader (drives MFRC522) → spi_cs_1
├── aes_wrapper             (aes_wrapper_inst)
│   └── fault_protected_aes                    ── triple-run + masked majority vote
│       ├── aes_top                            ── masked AES-128 round core (2 shares)
│       │   ├── aes_key_schedule               ── masked key schedule
│       │   └── aes_round_datapath → aes_sbox  ── masked SubBytes
│       │   (+ aes_shift_rows, aes_mix_columns per share)
│       └── fault_mux                          ── masked bitwise majority voter
├── uart_rx                 (dbg_uart_rx)      ── debug command input  (see DEBUG_CONTROLLER.md)
└── uart_tx                 (dbg_uart_tx)      ── UART TX, shared CPU/debug
```

Masking primitives live in [`rtl/gadgets/`](rtl/gadgets/) (HPC2 gadgets) and are used inside
the AES S-box, key schedule, and fault mux.

---

## The Multi-Cycle CPU

### Memories

- **Program memory** — a unified 1024-word × 18-bit instruction space selected by `pc[9]`:
  addresses 0–511 come from the 512-word mask ROM ([`rom.v`](rtl/rom.v)), 512–1023 from the
  512-word debug instruction RAM. See INSTRUCTION_SET.md and DEBUG_CONTROLLER.md for details.
- **Work RAM** — 64 × 8-bit (`ram_data[0:63]`). All RAM accesses are relative to the **BAR
  (Base Address Register)**: `ram_data[BAR + operand]`. See INSTRUCTION_SET.md.

### Datapath registers

| Register | Width | Purpose |
|----------|-------|---------|
| `pc`, `pc_backup` | 10-bit | Program counter (backup used by ROM-data reads) |
| `opcode`, `arg1`, `arg2` | 6-bit | Decoded instruction fields |
| `ram_arg1`, `ram_arg2` | 8-bit | Operands read from work RAM at `BAR+arg` during FETCH |
| `result` | 8-bit | Value written back to RAM in WRITEBACK |
| `ram_data[0:63]` | 8-bit | General-purpose work RAM |
| `ram_base_register` (BAR) | 6-bit | Base offset added to every RAM access |
| `repeat_cnt`, `repeat_pc0`, `repeat_pcn` | — | Hardware `REP` loop state |
| `cmp_flag`, `err_flag` | 1-bit | Comparison flag; error flag |
| `call_stack[0:3]`, `call_sp`, `call_full` | — | 4-level hardware call stack |
| `busy_reg`, `hard_fault_reg`, `unlock_reg` | 1-bit | Drive the `busy` / `hard_fault` / `unlock` pins |

### Instruction cycle (main FSM)

The CPU FSM ([main_controller.v:28-41](rtl/main_controller.v#L28)) has a fetch/execute/
writeback backbone plus one wait state per peripheral:

| State | # | Role |
|-------|---|------|
| `FETCH` | 0 | Latch opcode + operand fields; read operands from work RAM (`BAR+arg`). Only advances when the debugger permits it (see DEBUG_CONTROLLER.md). |
| `EXECUTE` | 1 | Decode the opcode: either compute a `result` and go to WRITEBACK, or issue a peripheral command and go to the matching `WAIT_*` state. |
| `WRITEBACK` | 2 | Write `result` to work RAM, update flags, advance the PC (increment / branch / `REP` loopback / `CALL`/`RET`). |
| `WAIT_CRC` | 3 | Wait for the CRC core (byte load). |
| `WAIT_EEPROM` | 4 | Wait for an EEPROM read. |
| `WAIT_RC522` | 5 | Wait for the RC522 wrapper. |
| `WAIT_INSROMRD` | 6 | Wait for a PC-relative ROM/IRAM data read (PC is temporarily redirected, then restored from `pc_backup`). |
| `WAIT_AES` | 7 | Wait for the AES wrapper. |
| `WAIT_RNG` | 8 | Wait for the RNG to be ready. |
| `WAIT_UARTTX_1/2` | 9,10 | Two-phase UART transmit handshake. |
| `WAIT_SPIDBG`, `WAIT_SPIDBG_START` | 11,12 | Wait for a debug-SPI transfer. |
| `WAIT_CRCP` | 13 | Multi-byte CRC block loop (`CRCPW`/`CRCPC`). |

**Typical flow:** `FETCH → EXECUTE → WRITEBACK → FETCH` for internal ops (minimum ~3 cycles
per instruction), or `FETCH → EXECUTE → WAIT_x → … → WRITEBACK → FETCH` for peripheral ops
(as many cycles as the peripheral needs).

### The peripheral handshake pattern

Every peripheral is a self-contained sub-FSM sharing the same command/response shape:

1. **EXECUTE** raises the peripheral's enable plus a one-hot command strobe (e.g. `aes_en`
   + `aes_push_d`), latches any input byte, and transitions to that peripheral's `WAIT_*`
   state.
2. The **`WAIT_*`** state holds until the peripheral's `busy`/`done` signal clears, then
   captures the peripheral's output into `result`.
3. **WRITEBACK** stores `result` into work RAM (for read-type ops) and clears the strobes.

This uniform pattern is what lets one small controller drive AES, CRC, EEPROM, RC522, RNG,
UART, and SPI without a wide datapath.

### Control flow, flags, and loops

Handled in WRITEBACK (details in INSTRUCTION_SET.md):
- **PC update** — increment by default; absolute jump for taken branches; push/pop the
  4-level hardware call stack for `CALL`/`RET` (`call_full` marks overflow).
- **Flags** — `cmp_flag` (comparisons) drives conditional jumps; `err_flag` exists but is
  not wired to a functional branch in this revision (see the JUMPE note in INSTRUCTION_SET.md).
- **`REP` hardware loop** — repeats the next *N* instructions *M* times, auto-incrementing
  BAR each pass; any taken branch exits the loop.

### Reset and power-up

Reset is synchronous and active-high. The CPU is also fully reset when the debugger is
*disabled* after having been active: the reset guard is
`if (rst || (dbg_initialized && ~mode))` ([main_controller.v:376](rtl/main_controller.v#L376)),
so leaving debug mode returns `pc=0`, `state=FETCH`. On reset the PC, flags, call stack, BAR,
and `REP` state are all cleared.

### Status / control outputs

- `busy` — asserted whenever the CPU is running.
- `hard_fault` — raised on an illegal opcode or invalid state
  ([main_controller.v:830](rtl/main_controller.v#L830)). This is a **control-flow** fault flag
  only; it is separate from the AES data-fault correction, which is handled silently inside
  the AES subsystem.
- `unlock` — the door-unlock output, set/cleared by the `LOCK` instruction (`unlock_reg`).

---

## Peripheral & Crypto Subsystems

### SPI subsystem — shared master

[`spi_master.v`](rtl/spi_master.v) is a single 8-bit SPI master: **Mode 0 (CPOL=0, CPHA=0),
MSB-first**, SCLK ≈ 2.5 MHz (10 MHz / 4). It exposes two active-low chip selects and does
**no internal arbitration** — it inverts the two CS requests onto the pins and shifts
whatever `tx_data` it is given.

Bus sharing is wired in `main_controller` ([main_controller.v:162-263](rtl/main_controller.v#L162)):
- **`spi_cs_0` → EEPROM, `spi_cs_1` → RC522**; each slave has its own CS on a shared data bus.
- `tx_data`/`start_tx` are muxed combinationally on `spi_open_cs0`: when the EEPROM asserts
  its CS request it wins the bus, otherwise the RC522 owns it. In practice the firmware uses
  only one at a time.
- A **debug override** (`spi_dbg`) lets the debug controller drive the SPI bus directly.

### EEPROM controller

[`eeprom.v`](rtl/eeprom.v) is a **read-only** controller for ATMEL AT250xxB-series SPI
EEPROMs. It issues the `READ` command (0x03) with a 7-bit address, then clocks out data
bytes via the shared SPI master; the chip's internal address auto-increment allows streaming
sequential reads by re-pulsing `enable`. Backs the `ROMRD` instruction (CPU sets the address
from `BAR + operand`, pulses enable, waits in `WAIT_EEPROM`, latches the byte).

### RC522 NFC reader

Two modules:
- [`rc522.v`](rtl/rc522.v) — a full ISO 14443-A reader controller that drives an **external
  NXP MFRC522** over SPI: soft reset + initialization sequence (antenna on, timers, ASK
  modulation, version check for 0x88/0x91/0x92), transceive, FIFO I/O, and per-frame
  bit-length control (for short frames like REQA/WUPA). It uses `spi_cs_1`.
- [`rc522_wrapper.v`](rtl/rc522_wrapper.v) — the CPU-facing adapter that turns the byte-
  oriented RC522 opcodes (`RC522RST/PUSH/POP/BLEN/TRCVE/BUFRST/WAIT/RXNUM`) into the core's
  512-bit block interface (push/pop bytes into a shift buffer, set last-byte bit length,
  launch a transceive, read the received-byte count).

The CPU drives these via `rc522_en` + a `do_*` strobe and waits in `WAIT_RC522`.

### CRC-16 engine

[`crc.v`](rtl/crc.v) is a bit-serial CRC-16 with polynomial `0x8408` (reflected CCITT
0x1021) and init value `0x6363`, LSB-first, no final XOR — i.e. the **ISO 14443-A CRC_A**
used by MIFARE, matching the NFC role. It processes one byte per `load_byte` pulse. Backs
the CRC instructions (`CRCRST/CRCLD/CRCH/CRCL`) and the block variants (`CRCPW`, `CRCPC`),
which the CPU services via `WAIT_CRC` and the multi-byte `WAIT_CRCP` loop.

### AES-128 accelerator (masked + fault-protected)

A layered, side-channel- and fault-hardened AES-128 engine. Data path:

```
aes_wrapper → fault_protected_aes → aes_top → { aes_key_schedule, aes_round_datapath→aes_sbox }
                     └── fault_mux                 (+ aes_shift_rows, aes_mix_columns per share)
```

- [`aes_wrapper.v`](rtl/aes_wrapper.v) — byte-serial front end for the 8-bit CPU: shift 16
  bytes of plaintext and **two key shares** in, set mode, start, and shift the result out.
  Backs the `AES*` opcodes; the CPU waits in `WAIT_AES`.
- [`aes/fault_protected_aes.v`](rtl/aes/fault_protected_aes.v) — **fault countermeasure**:
  runs the cipher three times (re-masking the input each run) and does a masked bitwise
  **majority vote** to correct single faults before de-masking the output.
- [`aes/aes_top.v`](rtl/aes/aes_top.v) — masked AES-128 round core operating on **two Boolean
  shares** throughout; linear layers (AddRoundKey, ShiftRows, MixColumns) run per share, and
  only the nonlinear SubBytes uses masked gadgets.
- [`aes_sbox.v`](rtl/aes_sbox.v), [`aes/aes_key_schedule.v`](rtl/aes/aes_key_schedule.v),
  [`fault_mux.v`](rtl/fault_mux.v) — the nonlinear/masked blocks, built from the **HPC2
  gadgets** in [`gadgets/`](rtl/gadgets/).

> **Security summary.** Masking = HPC2 gadgets, **2 shares, first-order (glitch-robust)**;
> only the AND gadgets consume randomness. The key is entered as two shares; the plaintext is
> freshly re-masked on each of the three fault-protection runs. All randomness (332 bits per
> AES operation, plus the `RNGGET` byte) comes from a single Trivium instance.

### Random number generator (Trivium)

[`trivium.v`](rtl/trivium.v) is an unrolled Trivium stream cipher producing a 340-bit
parallel keystream ([main_controller.v:286](rtl/main_controller.v#L286)). Bits `[331:0]`
continuously feed the AES randomness bus; the top 8 bits `[339:332]` are the byte returned
by the `RNGGET` instruction (the CPU waits in `WAIT_RNG` until `rng_rdy`). `RNGRST` re-seeds
the warm-up.

> **Note (this revision).** Trivium is seeded with two **hardcoded** key/IV constants marked
> `CHANGE LATER` ([main_controller.v:290](rtl/main_controller.v#L290)), so the RNG is
> currently deterministic. The intended physical entropy source
> [`ring_oscillator.v`](rtl/ring_oscillator.v) exists but is **not instantiated** anywhere in
> the build.

### UART

- [`uart_tx.v`](rtl/uart_tx.v) — 8N1 transmitter, baud = `uart_clk_in`/16. A single instance
  is **shared** between the CPU (`UARTTX` instruction) and the debug controller, muxed by
  `mode`. The CPU uses the two-phase `WAIT_UARTTX_1/2` handshake.
- [`uart_rx.v`](rtl/uart_rx.v) — 8N1 receiver with majority-vote sampling and framing-error
  detection. It is **not** tied to a CPU opcode; it is the **debug command input** channel
  (see DEBUG_CONTROLLER.md).

---

## Clocking & Reset

- **`clk`** — 10 MHz system clock for the CPU and all peripheral FSMs.
- **`uart_clk_in`** — separate, slower reference used only for UART bit timing (baud =
  `uart_clk_in`/16); both UART instances are edge-synchronized to it.
- **`rst`** — active-high synchronous reset. Exiting debug mode also triggers a CPU reset.

## Notes on Non-Obvious / Reserved Details

- **`ring_oscillator.v` is not built** — the RNG uses Trivium with a fixed seed; the entropy
  path is intended-but-unwired in this snapshot.
- **`hard_fault` is control-flow only** (illegal opcode/state). AES data faults are corrected
  silently inside `fault_protected_aes` and do not raise `hard_fault`.
- **`rom.mem` contains 1024 lines but only the first 512 are loaded** (the ROM array is
  512 deep); some `1024`/`10-bit` comments in `rom.v` are stale — the physical ROM is 512×18,
  9-bit addressed.
- **Test stubs are not in the datapath.** [`eeprom_testmodule.v`](rtl/eeprom_testmodule.v)
  and [`rc522_testmodule.v`](rtl/rc522_testmodule.v) are standalone sim top-levels, each with
  their own `spi_master`; `rc522_testmodule.v` is out of sync with the current `rc522.v` port
  list and is test-only.
- [`test_gadget.v`](rtl/test_gadget.v) is a masking-gadget demonstrator, not part of the CPU.

## Module Reference

| Module | File | Role | Instantiated in |
|--------|------|------|-----------------|
| `main_controller` | `rtl/main_controller.v` | Top module: CPU control FSM + datapath + memories + debug controller | (top) |
| `rom` | `rtl/rom.v` | 512×18 program ROM + debug read port | main_controller |
| `crc` | `rtl/crc.v` | CRC-16 (ISO 14443-A CRC_A) | main_controller |
| `trivium` | `rtl/trivium.v` | Trivium PRNG / randomness source | main_controller |
| `spi_master` | `rtl/spi_master.v` | Shared 8-bit SPI master (mode 0) | main_controller |
| `eeprom` | `rtl/eeprom.v` | Read-only SPI EEPROM controller | main_controller |
| `rc522_wrapper` | `rtl/rc522_wrapper.v` | CPU-facing RC522 adapter | main_controller |
| `rc522` | `rtl/rc522.v` | ISO 14443-A NFC reader (MFRC522) | rc522_wrapper |
| `aes_wrapper` | `rtl/aes_wrapper.v` | Byte-serial AES command interface | main_controller |
| `fault_protected_aes` | `rtl/aes/fault_protected_aes.v` | Triple-run + masked majority vote | aes_wrapper |
| `aes_top` | `rtl/aes/aes_top.v` | Masked AES-128 round core (2 shares) | fault_protected_aes |
| `aes_key_schedule` | `rtl/aes/aes_key_schedule.v` | Masked key schedule | aes_top |
| `aes_round_datapath` | `rtl/aes/aes_round_datapath.v` | Masked SubBytes column datapath | aes_top |
| `aes_sbox` | `rtl/aes_sbox.v` | Masked AES S-box (HPC2) | aes_round_datapath, aes_key_schedule |
| `aes_shift_rows` | `rtl/aes_shift_rows.v` | (Inv)ShiftRows | aes_top |
| `aes_mix_columns` | `rtl/aes_mix_columns.v` | (Inv)MixColumns | aes_top |
| `fault_mux` | `rtl/fault_mux.v` | Masked bitwise majority voter | fault_protected_aes |
| `uart_tx` | `rtl/uart_tx.v` | UART transmitter (CPU + debug) | main_controller |
| `uart_rx` | `rtl/uart_rx.v` | UART receiver (debug input) | main_controller |
| gadgets | `rtl/gadgets/*.sv` | HPC2 masking primitives | AES masked blocks |
| `ring_oscillator` | `rtl/ring_oscillator.v` | Entropy source (**not instantiated**) | — |
