#include "Vsecded_verify_top.h"
#include "Vsecded_verify_top___024root.h"
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

int main(int argc, char** argv) {
    if (argc != 2) { std::cerr << "Usage: Vsecded_verify_top vectors.txt\n"; return 2; }
    std::ifstream input(argv[1]);
    if (!input) { std::cerr << "Cannot read vectors\n"; return 2; }
    VerilatedContext context;
    Vsecded_verify_top dut{&context};
    uint64_t record = 0, cycles = 0, codecs = 0, injections = 0, expected_records = 0;
    std::string line;
    auto check = [](const char* name, int64_t actual, int64_t expected) {
        if (actual != expected) {
            std::ostringstream message;
            message << name << ": expected " << expected << ", got " << actual;
            throw std::runtime_error(message.str());
        }
    };
    auto signed_acc = [](uint64_t raw) -> int64_t {
        return (raw & (uint64_t{1} << (ACC_WIDTH-1)))
            ? static_cast<int64_t>(raw) - (int64_t{1} << ACC_WIDTH) : raw;
    };
    try {
        if (!std::getline(input, line)) throw std::runtime_error("missing record count");
        std::istringstream header(line);
        std::string extra;
        if (!(header >> expected_records) || !expected_records || (header >> extra))
            throw std::runtime_error("invalid record count");
        // Initial reset precedes comparisons of state that was undefined at power-up.
        dut.clk = 0; dut.rst = 1; dut.eval();
        dut.clk = 1; dut.eval();
        dut.clk = 0; dut.eval();
        while (std::getline(input, line)) {
            ++record;
            std::istringstream row(line);
            char kind;
            if (!(row >> kind)) throw std::runtime_error("empty record");
            if (kind == 'C') {
                uint64_t data, received, encoded, decoded, repaired, syndrome;
                int corrected, uncorrectable;
                if (!(row >> data >> received >> encoded >> decoded >> repaired >> syndrome
                          >> corrected >> uncorrectable)) throw std::runtime_error("malformed codec record");
                dut.codec_data = data; dut.codec_word = received; dut.eval();
                check("encoded word", dut.encoded_word, encoded);
                check("decoded data", dut.decoded_data, decoded);
                check("repaired word", dut.repaired_word, repaired);
                check("syndrome", dut.syndrome, syndrome);
                check("codec correction", dut.codec_corrected, corrected);
                check("codec failure", dut.codec_uncorrectable, uncorrectable);
                ++codecs;
            } else if (kind == 'M') {
                int rst, clear, start, a, b, pre_ready, busy, done, valid, error, ready, corrected;
                int64_t pre_acc, acc;
                uint64_t mask, before_word, after_word;
                if (!(row >> rst >> clear >> start >> a >> b >> mask >> before_word >> pre_acc
                          >> pre_ready >> busy >> done >> valid >> error >> acc >> ready
                          >> corrected >> after_word)) throw std::runtime_error("malformed MAC record");
                dut.rst = rst; dut.clear = clear; dut.start = start;
                dut.operand_a = a; dut.operand_b = b;
                dut.eval();
                if (mask) {
                    const uint64_t old_word = dut.stored_codeword;
                    dut.rootp->secded_verify_top__DOT__dut__DOT__acc_codeword ^= mask;
                    dut.eval();
                    check("injection fired", old_word ^ dut.stored_codeword, mask);
                    ++injections;
                }
                check("stored word before edge", dut.stored_codeword, before_word);
                check("decoded readback before edge", signed_acc(dut.accumulator), pre_acc);
                check("ready before edge", dut.ready, pre_ready);
                dut.clk = 1; dut.eval();
                check("busy", dut.busy, busy);
                check("done", dut.done, done);
                check("valid", dut.result_valid, valid);
                check("error", dut.error, error);
                check("accumulator", signed_acc(dut.accumulator), acc);
                check("ready", dut.ready, ready);
                check("corrected pulse", dut.corrected, corrected);
                check("stored word after edge", dut.stored_codeword, after_word);
                dut.clk = 0; dut.eval();
                check("storage stable off edge", dut.stored_codeword, after_word);
                ++cycles;
            } else throw std::runtime_error("unknown record kind");
            if (row >> extra) throw std::runtime_error("extra column");
        }
        if (input.bad()) throw std::runtime_error("vector read error");
        check("record count", record, expected_records);
    } catch (const std::exception& e) {
        std::cerr << "FAIL record " << record << ": " << e.what() << "\n" << line << '\n';
        return 1;
    }
    dut.final();
    std::cout << "PASS: " << cycles << " MAC cycles, " << codecs << " codec checks, "
              << injections << " acknowledged injections matched Python\n";
}
