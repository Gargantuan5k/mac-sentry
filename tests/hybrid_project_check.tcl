# Pure Tcl contract checks, not a Vivado/IP implementation test.
set script [file normalize [lindex $argv 0]]
set scratch [file normalize [lindex $argv 1]]
set open_project 0
set creates 0
set files {}
set configs [dict create]
proc get_projects {args} {global open_project; if {$open_project} {return existing}; return {}}
proc current_project {} {return project}
proc get_filesets {name} {return $name}
proc get_ips {args} {return [lindex $args 0]}
proc create_project {name dest args} {
    global creates
    if {$args ne "-part xc7z020clg484-1"} {error "wrong part"}
    incr creates
    file mkdir $dest
}
proc add_files {args} {global files; lappend files [lindex $args end]}
proc set_property {args} {
    global configs
    if {[lindex $args 0] eq "-dict"} {dict set configs [lindex $args 2] [lindex $args 1]}
}
proc create_ip {args} {
    if {$args ni {
        {-name vio -vendor xilinx.com -library ip -version 3.0 -module_name vio_hybrid}
        {-name ila -vendor xilinx.com -library ip -version 6.2 -module_name ila_hybrid}
    }} {error "unexpected IP/version: $args"}
}
proc generate_target {args} {}
proc update_compile_order {args} {}
proc version {args} {return "test stand-in, not Vivado"}
proc close_project {} {}
set argv [list [file join $scratch new_project]]
source $script
if {$creates != 1 || [llength $files] != 8} {error "wrong project/source count"}
foreach path $files {
    if {![file isfile $path] || [string match "*/tests/*" $path]} {error "invalid design source $path"}
}
set vio_in_widths {1 1 24 2 2}
set vio_out_widths {1 1 1 8 8 3 25 3 24 30 1}
set ila_widths {1 1 1 8 8 3 25 3 24 30 1 1 1 1 1 1 1 2 24 30 1 1 1 2 4 2 8 8 3 25 3 24 30 25 3 24 25 25 3 3 24 24 1 1}
set v [dict get $configs vio_hybrid]
set a [dict get $configs ila_hybrid]
if {[dict get $v CONFIG.C_NUM_PROBE_IN] != [llength $vio_in_widths] ||
    [dict get $v CONFIG.C_NUM_PROBE_OUT] != [llength $vio_out_widths] ||
    [dict get $a CONFIG.C_NUM_OF_PROBES] != [llength $ila_widths]} {error "probe counts"}
foreach direction {IN OUT} widths [list $vio_in_widths $vio_out_widths] {
    set i 0
    foreach width $widths {
        if {[dict get $v CONFIG.C_PROBE_${direction}${i}_WIDTH] != $width} {error "VIO width $direction $i"}
        if {$direction eq "OUT" && [dict get $v CONFIG.C_PROBE_OUT${i}_INIT_VAL] != ($i==0)} {error "VIO reset-safe defaults"}
        incr i
    }
}
set i 0
foreach width $ila_widths {
    if {[dict get $a CONFIG.C_PROBE${i}_WIDTH] != $width} {error "ILA width $i"}
    incr i
}
if {[dict get $a CONFIG.C_DATA_DEPTH] != 1024 || [dict get $a CONFIG.C_INPUT_PIPE_STAGES] != 0} {error "ILA timing/depth"}
if {![catch {source $script} message] || ![string match "Refusing existing*" $message]} {error "existing output not refused"}
set argv [list /tmp/m3_forbidden_outside_project]
if {![catch {source $script} message] || $message ne "Project must be inside this repository"} {error "outside path not refused"}
set open_project 1
set argv [list [file join $scratch unused]]
if {![catch {source $script} message] || $message ne "Refusing to change an open project"} {error "open project not refused"}
if {$creates != 1} {error "destructive repeated create"}
puts "PASS Tcl project contract and refusal controls (Vivado NOT RUN)"
