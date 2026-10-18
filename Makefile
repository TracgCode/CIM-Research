TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(PWD)/rtl/top.v
TOPLEVEL ?= ALUWithMem
COCOTB_TEST_MODULES = tests.mainTest
PYTHONPATH := $(PWD)/tests:$(PYTHONPATH)
SIM ?= icarus
SIM_BUILD = sim_build_$(SIM)

include $(shell cocotb-config --makefiles)/Makefile.sim
