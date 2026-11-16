#include "Vhybrid_verify_top.h"
#include "Vhybrid_verify_top___024root.h"
#include "verilated.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#ifndef ACC_WIDTH
#define ACC_WIDTH 24
#endif
#ifndef OPERAND_WIDTH
#define OPERAND_WIDTH 8
#endif

int main(int argc, char** argv) {
    if (argc != 2) { std::cerr << "Usage: Vhybrid_verify_top vectors.txt\n"; return 2; }
    std::ifstream input(argv[1]);
    if (!input) { std::cerr << "Missing vectors\n"; return 2; }
    VerilatedContext context;
    Vhybrid_verify_top dut{&context};
    uint64_t record=0, count=0, cycles=0, checks=0, storage_events=0, attempt_events=0;
    std::string line;
    auto equal=[](const char* name, int64_t actual, int64_t expected) {
        if (actual != expected) {
            std::ostringstream error;
            error << name << ": expected " << expected << ", observed " << actual;
            throw std::runtime_error(error.str());
        }
    };
    auto signed_acc=[](uint64_t value) -> int64_t {
        return (value & (uint64_t{1} << (ACC_WIDTH-1)))
            ? static_cast<int64_t>(value)-(int64_t{1} << ACC_WIDTH) : static_cast<int64_t>(value);
    };
    try {
        std::string extra;
        if (!std::getline(input,line)) throw std::runtime_error("missing count");
        std::istringstream header(line);
        if (!(header >> count) || count == 0 || (header >> extra)) throw std::runtime_error("bad count");
        dut.clk=0; dut.rst=1; dut.eval();
        dut.clk=1; dut.eval(); dut.clk=0; dut.eval();
        while (std::getline(input,line)) {
            ++record;
            std::istringstream row(line);
            char kind;
            if (!(row >> kind)) throw std::runtime_error("empty row");
            if (kind == 'C') {
                uint64_t acc,a,b,candidate,predicted,observed;
                if (!(row >> acc >> a >> b >> candidate >> predicted >> observed))
                    throw std::runtime_error("bad checker row");
                dut.check_acc=acc; dut.check_a=a; dut.check_b=b; dut.check_candidate=candidate;
                dut.eval();
                equal("predicted residue",dut.prediction,predicted);
                equal("observed residue",dut.observation,observed);
                ++checks;
            } else if (kind == 'M') {
                int rst,clear,start,a,b,clean,eligible,pre_ready,busy,done,valid,error,ready;
                int corrected,detected,retried,retry_count;
                int64_t pre_acc,acc;
                uint64_t storage,candidate,checker,commit,pre_word,word;
                if (!(row >> rst >> clear >> start >> a >> b >> storage >> candidate >> checker
                          >> commit >> clean >> eligible >> pre_word >> pre_acc >> pre_ready
                          >> busy >> done >> valid >> error >> acc >> ready >> corrected
                          >> detected >> retried >> retry_count >> word))
                    throw std::runtime_error("bad MAC row");
                dut.rst=rst; dut.clear=clear; dut.start=start;
                // Verilator's C++ containers can be wider than the HDL ports.
                // In particular, negative 4-bit inputs must not retain bits 7:4.
                dut.operand_a=uint64_t(a) & ((uint64_t{1} << OPERAND_WIDTH)-1);
                dut.operand_b=uint64_t(b) & ((uint64_t{1} << OPERAND_WIDTH)-1);
                dut.candidate_fault_mask=candidate; dut.checker_fault_mask=checker;
                dut.commit_fault_mask=commit; dut.eval();
                if (storage) {
                    uint64_t old=dut.stored_codeword;
                    dut.rootp->hybrid_verify_top__DOT__dut__DOT__acc_codeword ^= storage;
                    dut.eval();
                    equal("storage injection fired",old ^ dut.stored_codeword,storage);
                    ++storage_events;
                }
                equal("candidate injection fired",dut.candidate_before_fault ^ dut.candidate_after_fault,candidate);
                equal("checker injection fired",dut.prediction_before_fault ^ dut.prediction_after_fault,checker);
                equal("commit injection fired",dut.commit_before_fault ^ dut.commit_after_fault,commit);
                const bool actual_eligible = dut.busy && !dut.rst && !dut.source_uncorrectable;
                equal("attempt eligibility",actual_eligible,eligible);
                if (actual_eligible && (candidate || checker || commit)) ++attempt_events;
                equal("pre word",dut.stored_codeword,pre_word);
                equal("pre accumulator",signed_acc(dut.accumulator),pre_acc);
                equal("pre ready",dut.ready,pre_ready);
                if (clean) equal("production pre ready",dut.clean_ready,pre_ready);
                dut.clk=1; dut.eval();
                equal("busy",dut.busy,busy); equal("done",dut.done,done);
                equal("valid",dut.result_valid,valid); equal("error",dut.error,error);
                equal("accumulator",signed_acc(dut.accumulator),acc);
                equal("ready",dut.ready,ready); equal("corrected",dut.corrected,corrected);
                equal("detected",dut.detected,detected); equal("retried",dut.retried,retried);
                equal("retry count",dut.retry_count,retry_count);
                equal("stored word",dut.stored_codeword,word);
                if (clean) {
                    equal("production busy",dut.clean_busy,busy); equal("production done",dut.clean_done,done);
                    equal("production valid",dut.clean_valid,valid); equal("production error",dut.clean_error,error);
                    equal("production accumulator",signed_acc(dut.clean_accumulator),acc);
                    equal("production ready",dut.clean_ready,ready);
                    equal("production corrected",dut.clean_corrected,corrected);
                    equal("production detected",dut.clean_detected,detected);
                    equal("production retried",dut.clean_retried,retried);
                    equal("production retry count",dut.clean_retry_count,retry_count);
                }
                dut.clk=0; dut.eval();
                equal("storage stable off edge",dut.stored_codeword,word);
                ++cycles;
            } else throw std::runtime_error("unknown row type");
            if (row >> extra) throw std::runtime_error("extra column");
        }
        if (input.bad()) throw std::runtime_error("vector read error");
        equal("record count",record,count);
    } catch (const std::exception& error) {
        std::cerr << "FAIL record " << record << ": " << error.what() << '\n' << line << '\n';
        std::cerr << "candidate=" << dut.candidate_after_fault
                  << " prediction=" << unsigned(dut.prediction_after_fault)
                  << " accumulator=" << signed_acc(dut.accumulator) << '\n';
        return 1;
    }
    dut.final();
    std::cout << "PASS: " << cycles << " MAC cycles, " << checks << " residue checks, "
              << storage_events << " storage injections, " << attempt_events
              << " active-attempt fault events matched Python\n";
}
