# awesome-layr — RUB team 1

`awesome-layr` is a small controller with a custom 18-bit instruction set that performs an
NFC/JavaCard authentication protocol. It drives an external MFRC522 reader over SPI, computes
ISO 14443-A CRCs in hardware, and verifies a challenge with an AES-128 accelerator that is both
first-order masked (HPC2 gadgets) and fault-protected (triple execution with a masked majority vote).
A UART-driven debug controller is built into the CPU. The design was taped out on the IHP SG13G2
open PDK.

The submission is split into three directories: [docs/](docs/) for the documentation, [src/](src/) for
the RTL sources and testbenches, and [tapeout/](tapeout/) for the physical implementation flow together
with the handful of files that had to change for silicon.

## docs/

[ARCHITECTURE.md](docs/ARCHITECTURE.md) describes the chip pinout, the
multi-cycle CPU and how it schedules the peripheral sub-FSMs, and every peripheral and crypto block in
turn. It also contains the module hierarchy and a *Module Reference* table that maps each module to its
file, so per-module detail lives there rather than in this README.

[INSTRUCTION_SET.md](docs/INSTRUCTION_SET.md) is the programmer's manual — instruction encodings,
BAR-relative RAM addressing, the full instruction reference, the `REP` hardware-loop mechanism, and
assembler syntax with example programs. 

[DEBUG_CONTROLLER.md](docs/DEBUG_CONTROLLER.md) documents the
debug unit, which is embedded inside `main_controller.v` rather than being a separate module: its
command protocol, register map, breakpoints, halt/step/run behaviour and worked host-side examples.

## src/

[src/rtl/](src/rtl/) holds the synthesizable Verilog and SystemVerilog. The top module is
[main_controller.v](src/rtl/main_controller.v), which contains the CPU, its memories and the debug
controller, and instantiates everything else. The remaining sources group into the AES accelerator
([aes/](src/rtl/aes/) plus the `aes_*.v` files, with [gadgets/](src/rtl/gadgets/) providing the HPC2
masking primitives they are built from), the NFC path (`rc522.v`, `rc522_wrapper.v` and `crc.v`), the
Trivium PRNG that supplies the masking randomness, and the UART, SPI and EEPROM peripherals. Files
named `*_testmodule.v` are simulation-only wrappers that give a submodule its own top level and are not
part of the chip.

[src/sw/](src/sw/) is the firmware side. [assembler.py](src/sw/assembler.py) assembles the custom
instruction set into a ROM image and [disasm.py](src/sw/disasm.py) reads one back;
[asm_functions.asm](src/sw/asm_functions.asm) is the authentication application that runs on the chip,
and [memory_layout.txt](src/sw/memory_layout.txt) documents how it uses the 64-byte work RAM.
[build.sh](src/sw/build.sh) and [build_linux.sh](src/sw/build_linux.sh) assemble the program and
immediately run it in simulation. [dbg.py](src/sw/dbg.py) is a separate host-side tool: an interactive
debugger that speaks the debug protocol over a serial port to real hardware.

[src/tb/](src/tb/) contains the cocotb testbenches, one per module plus two at SoC level —
`test_main_controller.py` exercises the instruction set and the debug controller, and
`test_main_controller_app.py` runs a complete assembled program against a simulated NFC card.
`aes_reference.py` is a shared pure-Python AES model used by the AES testbenches. See
[src/README.md](src/README.md) for the required Python packages, the Verilator setup, and how to invoke
individual testbenches.

## tapeout/

[tapeout/](tapeout/) contains the LibreLane flow that produced the layout for IHP SG13G2.
[src/chip_top.sv](tapeout/src/chip_top.sv) is the pad-ring top level (module `rubteam1`) that wraps
`main_controller` in IHP IO cells, with `chip_top.sdc` next to it holding the timing constraints — a
10 MHz system clock plus an asynchronous 153.6 kHz UART clock. [librelane/config.yaml](tapeout/librelane/config.yaml)
is the flow configuration, including the source list, floorplan and pad ring order.
[librelane_plugin_magic_filler.py](tapeout/librelane_plugin_magic_filler.py) adds a custom
`Magic.MetalFiller` step that replaces the stock KLayout filler, which was needed to get metal fill
past the PDK's density rules. The [Makefile](tapeout/Makefile) drives all of this and is
self-documenting via `make help`; it also provisions the PDK and can run gate-level simulations of the
post-place-and-route netlist through [cocotb/chip_top_tb.py](tapeout/cocotb/chip_top_tb.py)
(`make sim-gl`, `make sim-gl2`).

[tapeout/src/awesome-layr/](tapeout/src/awesome-layr/) is an *overlay*, not a second copy of the
design: it contains only the files that had to change for silicon and is meant to be dropped on top of
a checkout of the [src/](src/) tree. The RTL change that mattered is in
[rc522.v](tapeout/src/awesome-layr/rtl/rc522.v) — the delay the RC522 startup sequence waits after
issuing the soft reset:

```verilog
-    reset_delay_cnt <= 20'd5;          // Load 50ms delay (at 10MHz)
+    reset_delay_cnt <= 20'd500000;     // Load 50ms delay (at 10MHz)
```

A real MFRC522 needs milliseconds to come out of soft reset, so the original count of 5 cycles only
ever worked in simulation, where it also kept run times short. Alongside it, `rom.v` loads its image as
`rom.mem` instead of `rtl/rom.mem` so the path resolves relative to each tool's working directory, and
`rtl/rom.mem` is the trimmed production firmware that was baked into the chip. The two testbenches
under `awesome-layr/tb/` are the gate-level variants: `test_main_controller_app.py` gains a `GL=1` mode
that maps the logical signals onto the flattened netlist's pad names, and `test_dbg_uart_gl.py` is a
dependency-free smoke test that reads the first ROM word back over the debug UART.

Two inputs to this flow are not part of the submission and have to be supplied before it can be run:
`tapeout/ip/` with the bondpad GDS/LEF, and `tapeout/final/` with the post-place-and-route netlist that
the gate-level simulations read (produced by `make copy-final` after a completed LibreLane run).
