# Cocotb-driven build configuration for Verilator simulations

# ============================================================================
# Phony targets
# ============================================================================
.PHONY: all spi_master eeprom crc clean help main_controller uart_tx uart_rx

# ============================================================================
# User-facing targets (using recursive make to pass variables correctly)
# ============================================================================

# Default target
all: spi_master eeprom crc uart_tx uart_rx

rc522_simple:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=rc522 TEST=test_simple_rc522_controller \
		VERILOG_SOURCES="$(PWD)/rtl/spi_master.v $(PWD)/rtl/crc.v $(PWD)/rtl/rc522.v"

rc522_overhauled:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=rc522_testmodule TEST=test_overhauled_rc522_controller \
		VERILOG_SOURCES="$(PWD)/rtl/spi_master.v $(PWD)/rtl/crc.v $(PWD)/rtl/rc522.v $(PWD)/rtl/rc522_testmodule.v"

rc522:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=rc522 TEST=test_rc522_controller \
		VERILOG_SOURCES="$(PWD)/rtl/rc522.v"

spi_master:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=spi_master TEST=test_spi_master \
		VERILOG_SOURCES="$(PWD)/rtl/spi_master.v"

main_controller:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=main_controller TEST=test_main_controller \
		VERILOG_SOURCES="$(PWD)/rtl/main_controller.v $(PWD)/rtl/uart_tx.v $(PWD)/rtl/uart_rx.v $(PWD)/rtl/rom.v $(PWD)/rtl/crc.v $(PWD)/rtl/spi_master.v $(PWD)/rtl/eeprom.v $(PWD)/rtl/rc522.v $(PWD)/rtl/rc522_wrapper.v $(PWD)/rtl/aes/aes_top.v $(PWD)/rtl/aes/aes_round_datapath.v $(PWD)/rtl/aes/aes_key_schedule.v $(PWD)/rtl/aes_sbox.v $(PWD)/rtl/aes_mix_columns.v $(PWD)/rtl/aes_shift_rows.v $(PWD)/rtl/gadgets/HPC2And.sv $(PWD)/rtl/gadgets/HPC2Not.sv $(PWD)/rtl/gadgets/HPC2Xor.sv $(PWD)/rtl/gadgets/dff.sv $(PWD)/rtl/gadgets/xor2.sv $(PWD)/rtl/aes_wrapper.v $(PWD)/rtl/aes/fault_protected_aes.v $(PWD)/rtl/fault_mux.v $(PWD)/rtl/trivium.v"

main_controller_app:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=main_controller TEST=test_main_controller_app \
		VERILOG_SOURCES="$(PWD)/rtl/main_controller.v $(PWD)/rtl/uart_tx.v $(PWD)/rtl/uart_rx.v $(PWD)/rtl/rom.v $(PWD)/rtl/crc.v $(PWD)/rtl/spi_master.v $(PWD)/rtl/eeprom.v $(PWD)/rtl/rc522.v $(PWD)/rtl/rc522_wrapper.v $(PWD)/rtl/aes/aes_top.v $(PWD)/rtl/aes/aes_round_datapath.v $(PWD)/rtl/aes/aes_key_schedule.v $(PWD)/rtl/aes_sbox.v $(PWD)/rtl/aes_mix_columns.v $(PWD)/rtl/aes_shift_rows.v $(PWD)/rtl/gadgets/HPC2And.sv $(PWD)/rtl/gadgets/HPC2Not.sv $(PWD)/rtl/gadgets/HPC2Xor.sv $(PWD)/rtl/gadgets/dff.sv $(PWD)/rtl/gadgets/xor2.sv $(PWD)/rtl/aes_wrapper.v $(PWD)/rtl/aes/fault_protected_aes.v $(PWD)/rtl/fault_mux.v $(PWD)/rtl/trivium.v"

uart_tx:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=uart_tx TEST=test_uart_tx \
		VERILOG_SOURCES="$(PWD)/rtl/uart_tx.v"
uart_rx:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=uart_rx TEST=test_uart_rx \
		VERILOG_SOURCES="$(PWD)/rtl/uart_rx.v"
crc:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=crc TEST=test_crc_iso14443a \
		VERILOG_SOURCES="$(PWD)/rtl/crc.v"

trivium:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=trivium TEST=test_trivium \
		VERILOG_SOURCES="$(PWD)/rtl/trivium.v"

aes-sbox:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=aes_sbox TEST=test_aes_sbox \
		VERILOG_SOURCES="$(PWD)/rtl/aes_sbox.v $(PWD)/rtl/gadgets/HPC2And.sv $(PWD)/rtl/gadgets/dff.sv"

aes-key-schedule:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=aes_key_schedule TEST=test_aes_key_schedule \
		VERILOG_SOURCES="$(PWD)/rtl/aes/aes_key_schedule.v $(PWD)/rtl/aes_sbox.v $(PWD)/rtl/gadgets/HPC2And.sv $(PWD)/rtl/gadgets/HPC2Xor.sv $(PWD)/rtl/gadgets/HPC2Not.sv $(PWD)/rtl/gadgets/dff.sv $(PWD)/rtl/gadgets/xor2.sv"

eeprom:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=eeprom_testmodule TEST=test_spi_eeprom \
		VERILOG_SOURCES="$(PWD)/rtl/eeprom_testmodule.v $(PWD)/rtl/eeprom.v $(PWD)/rtl/spi_master.v"

mix_columns:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=aes_mix_columns TEST=test_aes_mix_columns \
		VERILOG_SOURCES="$(PWD)/rtl/aes_mix_columns.v"

shift_rows:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=aes_shift_rows TEST=test_aes_shift_rows \
		VERILOG_SOURCES="$(PWD)/rtl/aes_shift_rows.v"

aes-top:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=aes_top TEST=test_aes_top \
		VERILOG_SOURCES="$(PWD)/rtl/aes/aes_top.v $(PWD)/rtl/aes/aes_round_datapath.v $(PWD)/rtl/aes/aes_key_schedule.v $(PWD)/rtl/aes_sbox.v $(PWD)/rtl/aes_mix_columns.v $(PWD)/rtl/aes_shift_rows.v $(PWD)/rtl/gadgets/HPC2And.sv $(PWD)/rtl/gadgets/HPC2Xor.sv $(PWD)/rtl/gadgets/HPC2Not.sv $(PWD)/rtl/gadgets/dff.sv $(PWD)/rtl/gadgets/xor2.sv"

test_fault_mux:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=fault_mux TEST=test_fault_mux \
		VERILOG_SOURCES="$(PWD)/rtl/fault_mux.v $(PWD)/rtl/gadgets/HPC2And.sv $(PWD)/rtl/gadgets/HPC2Xor.sv $(PWD)/rtl/gadgets/dff.sv $(PWD)/rtl/gadgets/xor2.sv "

fault-protected-aes:
	@$(MAKE) clean > /dev/null 2>&1
	@$(MAKE) sim TOPLEVEL=fault_protected_aes TEST=test_aes_fault_protection \
		VERILOG_SOURCES="$(PWD)/rtl/aes/fault_protected_aes.v $(PWD)/rtl/fault_mux.v $(PWD)/rtl/aes/aes_top.v $(PWD)/rtl/aes/aes_round_datapath.v $(PWD)/rtl/aes/aes_key_schedule.v $(PWD)/rtl/aes_sbox.v $(PWD)/rtl/aes_mix_columns.v $(PWD)/rtl/aes_shift_rows.v $(PWD)/rtl/gadgets/HPC2And.sv $(PWD)/rtl/gadgets/HPC2Xor.sv $(PWD)/rtl/gadgets/HPC2Not.sv $(PWD)/rtl/gadgets/dff.sv $(PWD)/rtl/gadgets/xor2.sv"

# ============================================================================
# Variables
# ============================================================================


TOPLEVEL_LANG ?= verilog
SIM ?= verilator
COCOTB_TEST_MODULES ?= $(TEST)
MODULE ?= $(TEST)

# Verilator configuration
# VERILATOR_ROOT = /path/to/verilatoer

ifeq ($(VERILATOR_ROOT),)
    VERILATOR_ROOT = /usr/share/verilator
    $(info VERILATOR_ROOT environment variable not set, defaulting to $(VERILATOR_ROOT))
endif

VERILATOR_BIN_DIR = $(VERILATOR_ROOT)/bin
PATH ?= $(VERILATOR_ROOT)/bin:$(PATH)

# Export variables for cocotb
export VERILATOR_ROOT
export VERILATOR_BIN_DIR
export PATH

# Make the testbench package visible
export PYTHONPATH := $(PWD)/tb:$(PYTHONPATH)

# Enable FST waveform tracing for Verilator
ifeq ($(SIM),verilator)
    TRACE_OUTPUT ?= $(PWD)/dump.fst
    COMPILE_ARGS += --trace --trace-structs --trace-fst --threads 4 --Wall
	COMPILE_ARGS += --timing --Wall
    SIM_ARGS += --trace --trace-file $(TRACE_OUTPUT) --Wall
endif

COCOTB_MAKEFILE_DIR := $(shell cocotb-config --makefiles)
ifeq ($(strip $(COCOTB_MAKEFILE_DIR)),)
    $(error Unable to locate cocotb makefiles; ensure cocotb is installed and cocotb-config is on PATH)
endif

include $(COCOTB_MAKEFILE_DIR)/Makefile.sim
