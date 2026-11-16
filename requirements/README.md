# Dependencies

The complete HDL/physical workflow is tested on Linux; use a Linux environment
(such as WSL2 for a Windows host) for the process-group/Podman tooling. The pure
Python models and data utilities do not require Linux-specific hardware tools.

The Python models, CSV analyzers, archival utilities, package exporter and result
verifier use the standard library. `requirements.txt` intentionally installs no
third-party packages. Python 3.10+ is required. This does not install HDL or ASIC
tools; they are external programs, not pip dependencies.

| Work | Required tools |
| --- | --- |
| Models / published results | Python 3.10+ |
| Core RTL tests / lint | GNU Make, Verilator, GCC/G++ and a working C++ build environment |
| Generic synthesis | Yosys with ABC |
| ASIC gate-level simulation | Icarus Verilog (`iverilog`, `vvp`) |
| FPGA implementation / core cost experiments | AMD Vivado with Zynq-7000 support and a working license |
| Physical ASIC flow | Rootless Podman, Python 3.11, the pinned ASIC environments/vendor sources and both SKY130 revisions |

`toolchain.json` records the host versions used for the current regression. A
newer or different version may work but must generate its own evidence. Do not
interpret a version list as a guarantee of bit-identical physical output.

On Debian/Ubuntu the nonproprietary host tools are commonly provided by packages
`make g++ verilator yosys iverilog git python3 python3-venv podman`. On Fedora the
corresponding names are `make gcc-c++ verilator yosys iverilog git python3 podman`;
Python 3.11 may need a separate versioned package. Distribution packages can be
older than the tested versions: check actual `--version` output before use.
Install packages using your own machine's package manager; setup scripts never
invoke sudo or alter the global Python environment. No agent CLI is required.

Vivado is separately installed from AMD. Put `vivado` on PATH (for example by
sourcing your installation's `settings64.sh`). The board is ZedBoard
`xc7z020clg484-1`; existing projects/bitstreams are not distributed as prerequisites.
See the FPGA setup specifications for source/IP/probe definitions.

For ASIC dependencies and PDK preparation use the explicit commands in
[ASIC setup](../docs/asic_setup.md). PDKs, vendor caches, installed environments, container images and new bulk
physical-run outputs are deliberately excluded from Git. One compact historical
reference GDS/netlist/LEF is intentionally included in `results/published/`. The
hardening and precheck PDK revisions differ; do not substitute one for the other.
