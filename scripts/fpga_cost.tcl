# Fresh, core-only OOC experiment; no existing .xpr is opened or modified.
# argv: source snapshot, fresh output, variant, worker count.
lassign $argv source_root output variant workers
set stage initialization
proc note {key value} {
    global output
    set f [open [file join $output metrics.tsv] a]
    puts $f "$key\t$value"
    close $f
}
proc audit_lanes {label} {
    global variant output
    if {$variant ne "tmr"} {return}
    set f [open [file join $output ${label}_lanes.tsv] w]
    puts $f "lane\tregister\tcount\tcells"
    foreach lane {lane0 lane1 lane2} {
        foreach {register expected} {acc_state 24 saved_a 8 saved_b 8} {
            set cells [get_cells -hierarchical -filter "NAME =~ ${lane}/${register}_reg* && REF_NAME =~ FD*"]
            puts $f "$lane\t$register\t[llength $cells]\t$cells"
            # Vivado may duplicate a flop (e.g. acc_state_reg[0]__0). Extra
            # physical copies cost area; they do not mean a logical bit merged.
            # Require every canonical bit and reject unrecognized/aliased names.
            set pattern [format {^%s/%s_reg\[([0-9]+)\](__[0-9]+|_replica(_[0-9]+)?)?$} $lane $register]
            foreach cell $cells {
                if {![regexp -- $pattern $cell whole bit suffix] || $bit >= $expected} {
                    close $f;error "TMR_REDUNDANCY: unrecognized register $cell"
                }
            }
            for {set bit 0} {$bit < $expected} {incr bit} {
                set canonical [format {%s/%s_reg[%d]} $lane $register $bit]
                if {[lsearch -exact $cells $canonical] < 0} {
                    close $f;error "TMR_REDUNDANCY: missing canonical bit $canonical"
                }
            }
        }
        set logic [get_cells -hierarchical -filter "NAME =~ ${lane}/* && REF_NAME =~ LUT*"]
        puts $f "$lane\tarithmetic_luts\t[llength $logic]\t$logic"
        if {[llength $logic] == 0} {close $f;error "TMR_REDUNDANCY: no lane logic"}
    }
    close $f
}
if {[catch {
    file mkdir $output
    set_param general.maxThreads $workers
    create_project -in_memory -part xc7z020clg484-1
    set_property target_language Verilog [current_project]
    set_property include_dirs [list [file join $source_root rtl]] [current_fileset]
    set files {secded_encoder.sv secded_decoder.sv signed_residue7.sv mac_residue7_check.sv mac_unprotected.sv mac_secded.sv mac_hybrid.sv mac_tmr_lane.sv mac_tmr.sv}
    foreach name $files {read_verilog -sv [file join $source_root rtl $name]}
    note tool_version [version -short]
    note part xc7z020clg484-1
    note period_ns 10.000
    note dsp_policy max_dsp_0
    note scope production_core_only_OOC
    set stage synthesis
    # Same policy for every variant. Preserve equivalent state; verify TMR below.
    synth_design -top mac_$variant -part xc7z020clg484-1 -mode out_of_context -flatten_hierarchy none -keep_equivalent_registers -max_dsp 0 -generic {OPERAND_WIDTH=8 ACC_WIDTH=24}
    create_clock -name core_clk -period 10.000 [get_ports clk]
    set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports clk]
    set inputs [get_ports -filter {DIRECTION == IN && NAME != clk}]
    set_input_delay -clock core_clk -max 2.000 $inputs
    set_input_delay -clock core_clk -min 0.200 $inputs
    set_output_delay -clock core_clk -max 2.000 [get_ports -filter {DIRECTION == OUT}]
    set_output_delay -clock core_clk -min 0.200 [get_ports -filter {DIRECTION == OUT}]
    set_clock_uncertainty 0.200 [get_clocks core_clk]
    write_xdc [file join $output constraints.xdc]
    report_utilization -hierarchical -file [file join $output synth_utilization.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -file [file join $output synth_timing.rpt]
    write_checkpoint [file join $output synth.dcp]
    audit_lanes synth
    # DONT_TOUCH after synthesis prevents later physical merging of the audited lanes.
    if {$variant eq "tmr"} {set_property DONT_TOUCH true [get_cells {lane0 lane1 lane2}]}
    set stage implementation
    opt_design
    place_design
    phys_opt_design
    route_design
    set stage reports
    report_utilization -hierarchical -file [file join $output routed_utilization.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -file [file join $output routed_timing.rpt]
    report_route_status -file [file join $output route_status.rpt]
    report_drc -file [file join $output drc.rpt]
    check_timing -verbose -file [file join $output check_timing.rpt]
    write_checkpoint [file join $output routed.dcp]
    write_verilog -mode funcsim [file join $output routed.v]
    audit_lanes routed
    set setup [get_timing_paths -delay_type max -max_paths 1]
    set hold [get_timing_paths -delay_type min -max_paths 1]
    if {[llength $setup]!=1 || [llength $hold]!=1} {error "MISSING_TIMING_PATHS"}
    note setup_slack_ns [get_property SLACK $setup]
    note hold_slack_ns [get_property SLACK $hold]
    foreach {key filter} {lut {REF_NAME =~ LUT*} ff {REF_NAME =~ FD*} dsp {REF_NAME =~ DSP*}} {
        note $key [llength [get_cells -hierarchical -filter "IS_PRIMITIVE && ($filter)"]]
    }
    note complete 1
    close_project
} detail]} {
    note failed_stage $stage
    set f [open [file join $output failure.txt] w]
    puts $f $detail
    puts $f $::errorInfo
    close $f
    puts stderr "FPGA_COST_FAILED at $stage: $detail"
    exit 1
}
exit 0
