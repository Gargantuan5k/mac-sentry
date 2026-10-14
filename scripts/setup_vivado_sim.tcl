# Run from the Vivado Tcl Console with an existing project open:
# source /absolute/path/to/mac_sentry/scripts/setup_vivado_sim.tcl
# Configures default 8/24 behavioral simulation; does not launch it.
set mac_repo [file normalize [file join [file dirname [info script]] ..]]
if {[llength [get_projects -quiet]] == 0} {
    error "Open your Vivado project before sourcing this script."
}
set mac_vectors [file join $mac_repo build w8_a24 vectors.txt]
set mac_manifest [file join $mac_repo build w8_a24 vectors.json]
if {![file exists $mac_vectors] || ![file exists $mac_manifest]} {
    error "Run 'make vectors' in $mac_repo first."
}
set mac_fd [open $mac_manifest r]
set mac_manifest_text [read $mac_fd]
close $mac_fd
if {![regexp {"cycles"\s*:\s*([0-9]+)} $mac_manifest_text -> mac_cycles]} {
    error "Cannot read cycle count from $mac_manifest"
}
foreach {mac_fileset mac_relative} {
    sources_1 rtl/mac_unprotected.sv
    sim_1 tests/mac_tb.sv
} {
    set mac_source [file join $mac_repo $mac_relative]
    if {[llength [get_files -quiet $mac_source]] == 0} {
        add_files -fileset $mac_fileset -norecurse $mac_source
    }
    set_property file_type SystemVerilog [get_files $mac_source]
}
set_property used_in_synthesis false [get_files [file join $mac_repo tests mac_tb.sv]]
set_property used_in_implementation false [get_files [file join $mac_repo tests mac_tb.sv]]
set_property target_simulator XSim [current_project]
set_property top mac_tb [get_filesets sim_1]
set_property generic {OPERAND_WIDTH=8 ACC_WIDTH=24} [get_filesets sim_1]
# Use a property dictionary so the leading '-' in the value is not parsed
# as an option to set_property itself.
set_property -dict [list xsim.simulate.xsim.more_options \
    "-testplusarg \"VECTORS=$mac_vectors\" -testplusarg EXPECTED_CYCLES=$mac_cycles"] \
    [get_filesets sim_1]
set_property xsim.simulate.runtime all [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
puts "Ready: mac_tb, 8/24, $mac_cycles cycles. Select Run Behavioral Simulation."
