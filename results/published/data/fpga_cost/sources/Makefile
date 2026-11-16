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
MAX_RETRIES ?= 2
HYBRID_BUILD := build/hybrid_w$(OPERAND_WIDTH)_a$(ACC_WIDTH)_r$(MAX_RETRIES)
HYBRID_RTL := rtl/secded_encoder.sv rtl/secded_decoder.sv rtl/signed_residue7.sv rtl/mac_residue7_check.sv rtl/mac_hybrid.sv

.PHONY: all test test-model test-secded test-rtl test-small lint synth vectors provenance
.PHONY: secded-vectors test-secded-rtl test-secded-small lint-secded synth-secded
.PHONY: test-secded-board
.PHONY: test-hybrid-model hybrid-vectors test-hybrid-rtl test-hybrid-small test-hybrid-tiny lint-hybrid synth-hybrid
all: test lint lint-secded lint-hybrid synth synth-secded synth-hybrid

test: test-model test-rtl test-small test-secded-rtl test-secded-small test-secded-board test-hybrid-rtl test-hybrid-small test-hybrid-tiny

test-model:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

test-secded:
	$(PYTHON) -m unittest discover -s tests -p 'test_*secded.py' -v

test-hybrid-model:
	$(PYTHON) -m unittest discover -s tests -p 'test_hybrid.py' -v

hybrid-vectors: vectors
	mkdir -p $(HYBRID_BUILD)
	$(PYTHON) scripts/generate_hybrid_vectors.py --operand-width $(OPERAND_WIDTH) --acc-width $(ACC_WIDTH) --max-retries $(MAX_RETRIES) --seed $(SEED) --baseline $(BUILD)/vectors.txt --output $(HYBRID_BUILD)/vectors.txt > $(HYBRID_BUILD)/vectors.stdout

$(HYBRID_BUILD)/obj/Vhybrid_verify_top: $(HYBRID_RTL) rtl/mac_hybrid_injectable.sv rtl/mac_hybrid_datapath.vh rtl/secded_functions.vh tests/hybrid_verify_top.sv tests/hybrid_tb.cpp
	mkdir -p $(HYBRID_BUILD)
	$(VERILATOR) --cc --exe --build -j $(JOBS) --Wall -Irtl --top-module hybrid_verify_top --Mdir $(HYBRID_BUILD)/obj -GOPERAND_WIDTH=$(OPERAND_WIDTH) -GACC_WIDTH=$(ACC_WIDTH) -GMAX_RETRIES=$(MAX_RETRIES) -CFLAGS "-DACC_WIDTH=$(ACC_WIDTH) -DOPERAND_WIDTH=$(OPERAND_WIDTH)" $(HYBRID_RTL) rtl/mac_hybrid_injectable.sv tests/hybrid_verify_top.sv $(CURDIR)/tests/hybrid_tb.cpp > $(HYBRID_BUILD)/compile.log 2>&1 || { cat $(HYBRID_BUILD)/compile.log; exit 1; }

test-hybrid-rtl: $(HYBRID_BUILD)/obj/Vhybrid_verify_top hybrid-vectors
	$(HYBRID_BUILD)/obj/Vhybrid_verify_top $(HYBRID_BUILD)/vectors.txt > $(HYBRID_BUILD)/simulation.log 2>&1 || { cat $(HYBRID_BUILD)/simulation.log; exit 1; }
	cat $(HYBRID_BUILD)/simulation.log
	$(PYTHON) scripts/check_hybrid_harness.py --runner $(HYBRID_BUILD)/obj/Vhybrid_verify_top --vectors $(HYBRID_BUILD)/vectors.txt > $(HYBRID_BUILD)/harness_checks.log
	cat $(HYBRID_BUILD)/harness_checks.log
	$(PYTHON) scripts/provenance.py --output $(HYBRID_BUILD)/provenance.json

test-hybrid-small:
	$(MAKE) test-hybrid-rtl OPERAND_WIDTH=4 ACC_WIDTH=8

test-hybrid-tiny:
	$(MAKE) test-hybrid-rtl OPERAND_WIDTH=2 ACC_WIDTH=4

lint-hybrid:
	$(VERILATOR) --lint-only --Wall -Irtl --top-module mac_hybrid -GOPERAND_WIDTH=$(OPERAND_WIDTH) -GACC_WIDTH=$(ACC_WIDTH) -GMAX_RETRIES=$(MAX_RETRIES) $(HYBRID_RTL)

synth-hybrid:
	mkdir -p $(HYBRID_BUILD)
	$(YOSYS) -Q -T -l $(HYBRID_BUILD)/synth.log -p 'read_verilog -sv -Irtl $(HYBRID_RTL); chparam -set OPERAND_WIDTH $(OPERAND_WIDTH) -set ACC_WIDTH $(ACC_WIDTH) -set MAX_RETRIES $(MAX_RETRIES) mac_hybrid; synth -top mac_hybrid; check -assert; tee -o $(HYBRID_BUILD)/stat.json stat -json; write_verilog -noattr $(HYBRID_BUILD)/netlist.v; write_json $(HYBRID_BUILD)/netlist.json' > $(HYBRID_BUILD)/synth.stdout 2>&1 || { cat $(HYBRID_BUILD)/synth.stdout; exit 1; }
	$(PYTHON) scripts/provenance.py --output $(HYBRID_BUILD)/provenance.json

secded-vectors: vectors
	mkdir -p $(SECDED_BUILD)
	$(PYTHON) scripts/generate_secded_vectors.py --operand-width $(OPERAND_WIDTH) --acc-width $(ACC_WIDTH) --seed $(SEED) --baseline $(BUILD)/vectors.txt --output $(SECDED_BUILD)/vectors.txt > $(SECDED_BUILD)/vectors.stdout

$(SECDED_BUILD)/obj/Vsecded_verify_top: $(SECDED_RTL) rtl/secded_functions.vh rtl/mac_secded_datapath.vh tests/secded_verify_top.sv tests/secded_tb.cpp
	mkdir -p $(SECDED_BUILD)
	$(VERILATOR) --cc --exe --build -j $(JOBS) --Wall -Irtl --top-module secded_verify_top --Mdir $(SECDED_BUILD)/obj -GOPERAND_WIDTH=$(OPERAND_WIDTH) -GACC_WIDTH=$(ACC_WIDTH) -CFLAGS "-DACC_WIDTH=$(ACC_WIDTH) -DOPERAND_WIDTH=$(OPERAND_WIDTH)" $(SECDED_RTL) tests/secded_verify_top.sv $(CURDIR)/tests/secded_tb.cpp > $(SECDED_BUILD)/compile.log 2>&1 || { cat $(SECDED_BUILD)/compile.log; exit 1; }

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

test-secded-board:
	mkdir -p build/secded_board
	$(VERILATOR) --binary --timing -j $(JOBS) --Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Irtl --top-module zedboard_secded_tb --Mdir build/secded_board/obj $(SECDED_RTL) rtl/mac_secded_injectable.sv fpga/zedboard/zedboard_secded_top.sv tests/zedboard_debug_models.sv tests/zedboard_secded_tb.sv > build/secded_board/compile.log 2>&1 || { cat build/secded_board/compile.log; exit 1; }
	build/secded_board/obj/Vzedboard_secded_tb > build/secded_board/simulation.log 2>&1 || { cat build/secded_board/simulation.log; exit 1; }
	cat build/secded_board/simulation.log
	$(PYTHON) scripts/provenance.py --output build/secded_board/provenance.json

synth-secded:
	mkdir -p $(SECDED_BUILD)
	$(YOSYS) -Q -T -l $(SECDED_BUILD)/synth.log -p 'read_verilog -sv -Irtl $(SECDED_RTL); chparam -set OPERAND_WIDTH $(OPERAND_WIDTH) -set ACC_WIDTH $(ACC_WIDTH) mac_secded; synth -top mac_secded; check -assert; tee -o $(SECDED_BUILD)/stat.json stat -json; write_verilog -noattr $(SECDED_BUILD)/netlist.v; write_json $(SECDED_BUILD)/netlist.json' > $(SECDED_BUILD)/synth.stdout 2>&1 || { cat $(SECDED_BUILD)/synth.stdout; exit 1; }
	$(PYTHON) scripts/provenance.py --output $(SECDED_BUILD)/provenance.json

vectors:
	$(PYTHON) scripts/generate_vectors.py --operand-width $(OPERAND_WIDTH) --acc-width $(ACC_WIDTH) --seed $(SEED) --output $(BUILD)/vectors.txt

$(BUILD)/obj/Vmac_unprotected: rtl/mac_unprotected.sv tests/mac_tb.cpp
	mkdir -p $(BUILD)
	$(VERILATOR) --cc --exe --build -j $(JOBS) --Wall --top-module mac_unprotected --Mdir $(BUILD)/obj -GOPERAND_WIDTH=$(OPERAND_WIDTH) -GACC_WIDTH=$(ACC_WIDTH) -CFLAGS "-DACC_WIDTH=$(ACC_WIDTH) -DOPERAND_WIDTH=$(OPERAND_WIDTH)" rtl/mac_unprotected.sv $(CURDIR)/tests/mac_tb.cpp > $(BUILD)/compile.log 2>&1 || { cat $(BUILD)/compile.log; exit 1; }

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

.PHONY: test-asic-interface
test-asic-interface:
	$(PYTHON) scripts/test_asic_interface.py --jobs $(JOBS) --verilator $(VERILATOR) --yosys $(YOSYS)

.PHONY: test-hybrid-board
test-hybrid-board:
	$(PYTHON) scripts/test_hybrid_board.py --jobs $(JOBS) --verilator $(VERILATOR) --yosys $(YOSYS)

.PHONY: test-tmr
test-tmr:
	$(PYTHON) scripts/test_tmr.py --jobs $(JOBS) --verilator $(VERILATOR) --yosys $(YOSYS)

.PHONY: test-overnight-handoff
test-overnight-handoff:
	$(PYTHON) -m unittest discover -s tests -p 'test_overnight_handoff.py' -v
	$(PYTHON) scripts/check_overnight_handoff.py

.PHONY: test-hybrid-capture
test-hybrid-capture:
	$(PYTHON) scripts/test_hybrid_capture.py --jobs $(JOBS) --verilator $(VERILATOR)

.PHONY: test-asic-flow
test-asic-flow:
	$(PYTHON) -m unittest discover -s tests -p 'test_asic_flow.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_evidence_copy.py' -v
	$(PYTHON) scripts/test_asic_flow.py --jobs $(JOBS)

.PHONY: test-pilot test-fpga-cost
test-pilot:
	$(PYTHON) scripts/pilot_campaign.py --jobs $(JOBS) --verilator $(VERILATOR)

test-fpga-cost:
	$(PYTHON) scripts/fpga_cost.py --jobs $(JOBS)
