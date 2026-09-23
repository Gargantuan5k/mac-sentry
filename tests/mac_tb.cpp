#include "Vmac_unprotected.h"
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
    if (argc != 2) { std::cerr << "Usage: Vmac_unprotected vectors.txt\n"; return 2; }
    std::ifstream input(argv[1]);
    if (!input) { std::cerr << "Cannot read vector file\n"; return 2; }
    VerilatedContext context;
    Vmac_unprotected dut{&context};
    std::string line;
    unsigned long cycle = 0;
    try {
        while (std::getline(input, line)) {
            ++cycle;
            std::istringstream row(line);
            int rst, clear, start, a, b, pre_ready, busy, done, valid, error, acc, ready;
            if (!(row >> rst >> clear >> start >> a >> b >> pre_ready >> busy >> done >> valid >> error >> acc >> ready))
                throw std::runtime_error("malformed vector");
            std::string extra;
            if (row >> extra) throw std::runtime_error("extra vector column");
            auto check = [&](const char* name, int64_t actual, int64_t expected) {
                if (actual != expected) {
                    std::ostringstream message;
                    message << name << ": expected " << expected << ", got " << actual;
                    throw std::runtime_error(message.str());
                }
            };
            dut.clk = 0;
            dut.rst = rst; dut.clear = clear; dut.start = start;
            dut.operand_a = a; dut.operand_b = b;
            dut.eval();
            check("ready before edge", dut.ready, pre_ready);
            dut.clk = 1;
            dut.eval();
            int64_t actual_acc = dut.accumulator;
            if (actual_acc & (int64_t{1} << (ACC_WIDTH - 1))) actual_acc -= int64_t{1} << ACC_WIDTH;
            check("busy", dut.busy, busy);
            check("done", dut.done, done);
            check("result_valid", dut.result_valid, valid);
            check("error", dut.error, error);
            check("accumulator", actual_acc, acc);
            check("ready after edge", dut.ready, ready);
            dut.clk = 0;
            dut.eval();
            check("accumulator stable off edge", dut.accumulator, static_cast<uint32_t>(acc) & ((uint32_t{1} << ACC_WIDTH) - 1));
        }
        if (!cycle) throw std::runtime_error("empty vector file");
    } catch (const std::exception& e) {
        std::cerr << "FAIL cycle " << cycle << ": " << e.what() << "\nVector: " << line << '\n';
        return 1;
    }
    dut.final();
    std::cout << "PASS: " << cycle << " cycles matched the Python reference\n";
    return 0;
}
