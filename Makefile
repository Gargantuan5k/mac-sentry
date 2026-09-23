PYTHON ?= python3
VERILATOR ?= verilator
YOSYS ?= yosys
JOBS ?= 2
OPERAND_WIDTH ?= 8
ACC_WIDTH ?= 24
SEED ?= 20260923
BUILD := build/w$(OPERAND_WIDTH)_a$(ACC_WIDTH)

.PHONY: all test test-model test-rtl test-small lint synth vectors provenance
all: test lint synth

test: test-model test-rtl test-small

test-model:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

vectors:
	$(PYTHON) scripts/generate_vectors.py --operand-width $(OPERAND_WIDTH) --acc-width $(ACC_WIDTH) --seed $(SEED) --output $(BUILD)/vectors.txt

$(BUILD)/obj/Vmac_unprotected: rtl/mac_unprotected.sv tests/mac_tb.cpp
	mkdir -p $(BUILD)
	$(VERILATOR) --cc --exe --build -j $(JOBS) --Wall --top-module mac_unprotected --Mdir $(BUILD)/obj -GOPERAND_WIDTH=$(OPERAND_WIDTH) -GACC_WIDTH=$(ACC_WIDTH) -CFLAGS "-DACC_WIDTH=$(ACC_WIDTH)" rtl/mac_unprotected.sv $(CURDIR)/tests/mac_tb.cpp > $(BUILD)/compile.log 2>&1 || { cat $(BUILD)/compile.log; exit 1; }

test-rtl: vectors $(BUILD)/obj/Vmac_unprotected
	$(BUILD)/obj/Vmac_unprotected $(BUILD)/vectors.txt > $(BUILD)/simulation.log 2>&1 || { cat $(BUILD)/simulation.log; exit 1; }
	cat $(BUILD)/simulation.log
	$(PYTHON) scripts/provenance.py --output $(BUILD)/provenance.json

test-small:
	$(MAKE) test-rtl OPERAND_WIDTH=4 ACC_WIDTH=8

lint:
	$(VERILATOR) --lint-only --Wall --top-module mac_unprotected -GOPERAND_WIDTH=$(OPERAND_WIDTH) -GACC_WIDTH=$(ACC_WIDTH) rtl/mac_unprotected.sv

synth:
	mkdir -p $(BUILD)
	$(YOSYS) -Q -T -l $(BUILD)/synth.log -p 'read_verilog -sv rtl/mac_unprotected.sv; chparam -set OPERAND_WIDTH $(OPERAND_WIDTH) -set ACC_WIDTH $(ACC_WIDTH) mac_unprotected; synth -top mac_unprotected; check -assert; tee -o $(BUILD)/stat.json stat -json; write_verilog -noattr $(BUILD)/netlist.v; write_json $(BUILD)/netlist.json' > $(BUILD)/synth.stdout 2>&1 || { cat $(BUILD)/synth.stdout; exit 1; }
	$(PYTHON) scripts/provenance.py --output $(BUILD)/provenance.json
	@echo "Generic synthesis reports: $(BUILD)/stat.json and $(BUILD)/synth.log"

provenance:
	$(PYTHON) scripts/provenance.py --output $(BUILD)/provenance.json
