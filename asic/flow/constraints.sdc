# Retain the pinned LibreLane clock/drive/load/derating constraints, then specify
# the host-synchronous I/O timing envelope. No false or multicycle paths.
source [file join [file dirname [info script]] base.sdc]
set host_inputs [get_ports {ui_in[*] uio_in[*] ena rst_n}]
set_input_delay -clock [get_clocks clk] -min 1.0 $host_inputs
set_input_delay -clock [get_clocks clk] -max 4.0 $host_inputs
set_output_delay -clock [get_clocks clk] -min 0.0 [all_outputs]
set_output_delay -clock [get_clocks clk] -max 4.0 [all_outputs]
