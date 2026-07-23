# awesome-layr


## Running tests
Verilator has to be installed in order to run the tests, see the [toolchain installation guide](https://moodle.ruhr-uni-bochum.de/mod/page/view.php?id=3418580) in moodle.
To use the provided makefile, set the environment variable `VERILATOR_ROOT` to your verilator install directory. If you cloned from git and built from source,
the `VERILATOR_ROOT` should point to the git repository root. If the environment variable is not set, the makefile will assume the existence of a system-wide installation
at /usr/share/verilator and use this. Be aware that the version shipped with most distros (encountered this with Ubuntu 25.10) is too old for the cocotb toolchain, and cocotb will complain.

- Running the makefile with `-j $(nproc)` enables paralellism for the verilator build process, which increases build speed by a lot
  If your CPU is struggling too much and the desktop starts to lag, leaving out one or two cores can help `-j $(( $(nproc) - 2 ))`
- Passing `TESTCASE=fully.qualified.testcase.name` (e.g. `TESTCASE=test_main_Controller.test_dbg_uart`) allows running a single cocotb test instead of the entire test suite for a module, which again saves some time if you're workin
  on a particular testcase