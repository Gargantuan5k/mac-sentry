PYTHON ?= python3
VERILATOR ?= verilator
YOSYS ?= yosys
JOBS ?= 2
OPERAND_WIDTH ?= 8
ACC_WIDTH ?= 24
SEED ?= 20260923
BUILD := build/w$(OPERAND_WIDTH)_a$(ACC_WIDTH)
SECDED_BUILD := build/secded_w$(OPERAND_WIDTH)_a$(ACC_WIDTH)
SECDED_RTL := rtl/secded_encoder.sv rtl/secded_decoder.sv rtl/mac_secded.sv

.PHONY: all test test-model test-secded test-rtl test-small lint synth vectors provenance
.PHONY: secded-vectors test-secded-rtl test-secded-small lint-secded synth-secded
all: test lint lint-secded synth synth-secded

test: test-model test-rtl test-small test-secded-rtl test-secded-small

test-model:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

test-secded:
	$(PYTHON) -m unittest discover -s tests -p 'test_*secded.py' -v

secded-vectors: vectors
	mkdir -p $(SECDED_BUILD)
	$(PYTHON) scripts/generate_secded_vectors.py --operand-width $(OPERAND_WIDTH) --acc-width $(ACC_WIDTH) --seed $(SEED) --baseline $(BUILD)/vectors.txt --output $(SECDED_BUILD)/vectors.txt > $(SECDED_BUILD)/vectors.stdout

$(SECDED_BUILD)/obj/Vsecded_verify_top: $(SECDED_RTL) rtl/secded_functions.vh tests/secded_verify_top.sv tests/secded_tb.cpp
	mkdir -p $(SECDED_BUILD)
	$(VERILATOR) --cc --exe --build -j $(JOBS) --Wall -Irtl --top-module secded_verify_top --Mdir $(SECDED_BUILD)/obj -GOPERAND_WIDTH=$(OPERAND_WIDTH) -GACC_WIDTH=$(ACC_WIDTH) -CFLAGS "-DACC_WIDTH=$(ACC_WIDTH)" $(SECDED_RTL) tests/secded_verify_top.sv $(CURDIR)/tests/secded_tb.cpp > $(SECDED_BUILD)/compile.log 2>&1 || { cat $(SECDED_BUILD)/compile.log; exit 1; }

test-secded-rtl: $(SECDED_BUILD)/obj/Vsecded_verify_top secded-vectors
	$(SECDED_BUILD)/obj/Vsecded_verify_top $(SECDED_BUILD)/vectors.txt > $(SECDED_BUILD)/simulation.log 2>&1 || { cat $(SECDED_BUILD)/simulation.log; exit 1; }
	cat $(SECDED_BUILD)/simulation.log
	$(PYTHON) scripts/check_secded_harness.py --runner $(SECDED_BUILD)/obj/Vsecded_verify_top --vectors $(SECDED_BUILD)/vectors.txt > $(SECDED_BUILD)/harness_checks.log
	cat $(SECDED_BUILD)/harness_checks.log
	$(PYTHON) scripts/provenance.py --output $(SECDED_BUILD)/provenance.json

test-secded-small:
	$(MAKE) test-secded-rtl OPERAND_WIDTH=4 ACC_WIDTH=8

lint-secded:
	$(VERILATOR) --lint-only --Wall -Irtl --top-module mac_secded -GOPERAND_WIDTH=$(OPERAND_WIDTH) -GACC_WIDTH=$(ACC_WIDTH) $(SECDED_RTL)

synth-secded:
	mkdir -p $(SECDED_BUILD)
	$(YOSYS) -Q -T -l $(SECDED_BUILD)/synth.log -p 'read_verilog -sv -Irtl $(SECDED_RTL); chparam -set OPERAND_WIDTH $(OPERAND_WIDTH) -set ACC_WIDTH $(ACC_WIDTH) mac_secded; synth -top mac_secded; check -assert; tee -o $(SECDED_BUILD)/stat.json stat -json; write_verilog -noattr $(SECDED_BUILD)/netlist.v; write_json $(SECDED_BUILD)/netlist.json' > $(SECDED_BUILD)/synth.stdout 2>&1 || { cat $(SECDED_BUILD)/synth.stdout; exit 1; }
	$(PYTHON) scripts/provenance.py --output $(SECDED_BUILD)/provenance.json

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
