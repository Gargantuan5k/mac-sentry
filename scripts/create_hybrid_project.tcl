# Fresh standalone project only. Invoke from repo root with Vivado batch mode.
# argv: NEW directory within this repository; optional "build" runs implementation.
set repo [file normalize [file join [file dirname [info script]] ..]]
if {[llength $argv] < 1 || [llength $argv] > 2} {
    error "Usage: -tclargs NEW_PROJECT_DIRECTORY ?build?"
}
set dest [file normalize [lindex $argv 0]]
if {![string match "${repo}/*" $dest]} {error "Project must be inside this repository"}
if {[file exists $dest]} {error "Refusing existing project/output directory: $dest"}
if {[llength [get_projects -quiet]] != 0} {error "Refusing to change an open project"}
if {[llength $argv] == 2 && [lindex $argv 1] ne "build"} {error "Unknown mode"}
create_project mac_sentry_hybrid $dest -part xc7z020clg484-1
set_property target_language Verilog [current_project]
set_property include_dirs [list [file join $repo rtl]] [get_filesets sources_1]
set source_names {
    rtl/secded_encoder.sv rtl/secded_decoder.sv rtl/signed_residue7.sv
    rtl/mac_residue7_check.sv fpga/zedboard/mac_hybrid_board_core.sv
    fpga/zedboard/hybrid_fault_sequencer.sv fpga/zedboard/zedboard_hybrid_top.sv
}
foreach name $source_names {add_files -norecurse [file join $repo $name]}
add_files -fileset constrs_1 -norecurse [file join $repo fpga zedboard zedboard_100mhz.xdc]
set_property top zedboard_hybrid_top [get_filesets sources_1]
# Explicit IP versions; simulation stand-ins are deliberately absent.
create_ip -name vio -vendor xilinx.com -library ip -version 3.0 -module_name vio_hybrid
set_property -dict [list CONFIG.C_NUM_PROBE_IN {5} CONFIG.C_NUM_PROBE_OUT {11} CONFIG.C_PROBE_IN0_WIDTH {1} CONFIG.C_PROBE_IN1_WIDTH {1} CONFIG.C_PROBE_IN2_WIDTH {24} CONFIG.C_PROBE_IN3_WIDTH {2} CONFIG.C_PROBE_IN4_WIDTH {2} CONFIG.C_PROBE_OUT0_WIDTH {1} CONFIG.C_PROBE_OUT0_INIT_VAL {0x1} CONFIG.C_PROBE_OUT1_WIDTH {1} CONFIG.C_PROBE_OUT1_INIT_VAL {0x0} CONFIG.C_PROBE_OUT2_WIDTH {1} CONFIG.C_PROBE_OUT2_INIT_VAL {0x0} CONFIG.C_PROBE_OUT3_WIDTH {8} CONFIG.C_PROBE_OUT3_INIT_VAL {0x0} CONFIG.C_PROBE_OUT4_WIDTH {8} CONFIG.C_PROBE_OUT4_INIT_VAL {0x0} CONFIG.C_PROBE_OUT5_WIDTH {3} CONFIG.C_PROBE_OUT5_INIT_VAL {0x0} CONFIG.C_PROBE_OUT6_WIDTH {25} CONFIG.C_PROBE_OUT6_INIT_VAL {0x0} CONFIG.C_PROBE_OUT7_WIDTH {3} CONFIG.C_PROBE_OUT7_INIT_VAL {0x0} CONFIG.C_PROBE_OUT8_WIDTH {24} CONFIG.C_PROBE_OUT8_INIT_VAL {0x0} CONFIG.C_PROBE_OUT9_WIDTH {30} CONFIG.C_PROBE_OUT9_INIT_VAL {0x0} CONFIG.C_PROBE_OUT10_WIDTH {1} CONFIG.C_PROBE_OUT10_INIT_VAL {0x0}] [get_ips vio_hybrid]
create_ip -name ila -vendor xilinx.com -library ip -version 6.2 -module_name ila_hybrid
set_property -dict [list CONFIG.C_NUM_OF_PROBES {44} CONFIG.C_DATA_DEPTH {1024} CONFIG.C_INPUT_PIPE_STAGES {0} CONFIG.C_PROBE0_WIDTH {1} CONFIG.C_PROBE1_WIDTH {1} CONFIG.C_PROBE2_WIDTH {1} CONFIG.C_PROBE3_WIDTH {8} CONFIG.C_PROBE4_WIDTH {8} CONFIG.C_PROBE5_WIDTH {3} CONFIG.C_PROBE6_WIDTH {25} CONFIG.C_PROBE7_WIDTH {3} CONFIG.C_PROBE8_WIDTH {24} CONFIG.C_PROBE9_WIDTH {30} CONFIG.C_PROBE10_WIDTH {1} CONFIG.C_PROBE11_WIDTH {1} CONFIG.C_PROBE12_WIDTH {1} CONFIG.C_PROBE13_WIDTH {1} CONFIG.C_PROBE14_WIDTH {1} CONFIG.C_PROBE15_WIDTH {1} CONFIG.C_PROBE16_WIDTH {1} CONFIG.C_PROBE17_WIDTH {2} CONFIG.C_PROBE18_WIDTH {24} CONFIG.C_PROBE19_WIDTH {30} CONFIG.C_PROBE20_WIDTH {1} CONFIG.C_PROBE21_WIDTH {1} CONFIG.C_PROBE22_WIDTH {1} CONFIG.C_PROBE23_WIDTH {2} CONFIG.C_PROBE24_WIDTH {4} CONFIG.C_PROBE25_WIDTH {2} CONFIG.C_PROBE26_WIDTH {8} CONFIG.C_PROBE27_WIDTH {8} CONFIG.C_PROBE28_WIDTH {3} CONFIG.C_PROBE29_WIDTH {25} CONFIG.C_PROBE30_WIDTH {3} CONFIG.C_PROBE31_WIDTH {24} CONFIG.C_PROBE32_WIDTH {30} CONFIG.C_PROBE33_WIDTH {25} CONFIG.C_PROBE34_WIDTH {3} CONFIG.C_PROBE35_WIDTH {24} CONFIG.C_PROBE36_WIDTH {25} CONFIG.C_PROBE37_WIDTH {25} CONFIG.C_PROBE38_WIDTH {3} CONFIG.C_PROBE39_WIDTH {3} CONFIG.C_PROBE40_WIDTH {24} CONFIG.C_PROBE41_WIDTH {24} CONFIG.C_PROBE42_WIDTH {1} CONFIG.C_PROBE43_WIDTH {1}] [get_ips ila_hybrid]
generate_target all [get_ips {vio_hybrid ila_hybrid}]
update_compile_order -fileset sources_1
set log [open [file join $dest build_identity.txt] w]
puts $log "Vivado [version -short]"
puts $log "Repository $repo"
puts $log "Part xc7z020clg484-1; physical clock 100MHz; default DSP inference"
puts $log "Sources $source_names"
close $log
if {[llength $argv] == 2} {
    launch_runs synth_1 -jobs 2
    wait_on_run synth_1
    if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis incomplete"}
    launch_runs impl_1 -to_step write_bitstream -jobs 2
    wait_on_run impl_1
    if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation incomplete"}
    open_run impl_1
    report_timing_summary -delay_type min_max -report_unconstrained -file [file join $dest timing_summary.rpt]
    report_utilization -hierarchical -file [file join $dest utilization.rpt]
    report_drc -file [file join $dest drc.rpt]
    report_methodology -file [file join $dest methodology.rpt]
    write_debug_probes [file join $dest hybrid.ltx]
}
# Review timing, DRC and clock coverage manually. A bitstream is not sign-off.
close_project
