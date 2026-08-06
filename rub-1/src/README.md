# awesome-layr


## Running tests

### Python dependencies
The testbenches are cocotb based, so the Python side has to be set up first — the makefile calls `cocotb-config --makefiles`
and aborts with an error if that binary is not on the `PATH`. Using a virtual environment is recommended:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install cocotb cocotbext-uart pycryptodome        # required
pip install cocotbext-spi                             # optional, see below
```

- `cocotb` — simulation framework, also provides `cocotb-config` and the `Makefile.sim` included by our makefile
- `cocotbext-uart` — UART driver/monitor, used by the uart, eeprom, main controller and rc522 testbenches
- `pycryptodome` — AES reference model (imported as `Crypto.Cipher.AES`) for the main controller and rc522 testbenches.
  Note this is `pycryptodome`, *not* `pycryptodomex` — the testbenches import from `Crypto`, not `Cryptodome`

Nothing else is needed: the testbenches use plain `assert` and are launched by cocotb's makefile, so there is no pytest,
cocotb-bus or numpy dependency. The assembler in [sw/](sw/) is stdlib-only; `pyserial` is only required for
[sw/dbg.py](sw/dbg.py), which talks to real hardware and is not part of the test suite.

Tested with Python 3.11 (3.9+ should work) and cocotb 2.x. cocotb 1.x will not understand the module-qualified
`TESTCASE=module.test` form documented below.

### Verilator
Verilator has to be installed in order to run the tests, see the [toolchain installation guide](https://moodle.ruhr-uni-bochum.de/mod/page/view.php?id=3418580) in moodle.
To use the provided makefile, set the environment variable `VERILATOR_ROOT` to your verilator install directory. If you cloned from git and built from source,
the `VERILATOR_ROOT` should point to the git repository root. If the environment variable is not set, the makefile will assume the existence of a system-wide installation
at /usr/share/verilator and use this. Be aware that the version shipped with most distros (encountered this with Ubuntu 25.10) is too old for the cocotb toolchain, and cocotb will complain.

- Running the makefile with `-j $(nproc)` enables paralellism for the verilator build process, which increases build speed by a lot
  If your CPU is struggling too much and the desktop starts to lag, leaving out one or two cores can help `-j $(( $(nproc) - 2 ))`
- Passing `TESTCASE=fully.qualified.testcase.name` (e.g. `TESTCASE=test_main_controller.test_dbg_uart`) allows running a single cocotb test instead of the entire test suite for a module, which again saves some time if you're workin
  on a particular testcase

### Example invocations
All commands have to be run from this directory (`rub-1/src`), the makefile resolves `rtl/`, `tb/` and the waveform
output relative to `$(PWD)`:

```bash
export VERILATOR_ROOT=/path/to/verilator   # skip if verilator is installed system-wide

make -j $(nproc) crc                       # one module, full test suite
make -j $(nproc)                           # default target 'all': spi_master, eeprom, crc, uart_tx, uart_rx
make -j $(nproc) main_controller TESTCASE=test_main_controller.test_dbg_uart   # a single testcase
make -j $(nproc) crc TESTCASE=test_crc_iso14443a.test_single_byte_crc
```

Every module target runs `make clean` first, so switching between targets does not need a manual cleanup. Each run writes
an FST waveform to `dump.fst`, which can be inspected with GTKWave or Surfer.

### Available targets
- `all` (default) — `spi_master`, `eeprom`, `crc`, `uart_tx`, `uart_rx`
- Building blocks: `crc`, `spi_master`, `uart_tx`, `uart_rx`, `eeprom`, `trivium`
- AES: `aes-sbox`, `aes-key-schedule`, `aes-top`, `mix_columns`, `shift_rows`, `test_fault_mux`, `fault-protected-aes`
- RC522 reader: `rc522`, `rc522_simple`, `rc522_overhauled`
- Full SoC: `main_controller`, `main_controller_app`

The mix of hyphens and underscores in the target names is what the makefile actually defines, so copy the spelling as-is.

The `main_controller_app` target runs the SoC against an assembled ROM image and honours a few extra environment
variables: `ROM_PATH`, `STOP_PC`, `INSTR_TRACE` and `MAX_CYCLES`. [sw/build_linux.sh](sw/build_linux.sh) shows the
canonical invocation — it regenerates `rom.mem` with `sw/assembler.py` (no extra Python packages needed) before calling
make.
