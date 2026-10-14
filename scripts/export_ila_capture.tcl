# Source this file in Vivado Hardware Manager after a capture completes.
# Then: mac_save_ila /absolute/path/to/captures/signed_mac
# Exports the selected, already-uploaded capture; never arms or changes hardware.
proc mac_save_ila {base_path} {
    set base_path [file normalize $base_path]
    set data [current_hw_ila_data]
    if {[llength $data] != 1} {
        error "Select one completed ILA capture in Hardware Manager first."
    }
    foreach extension {.ila .csv} {
        if {[file exists "${base_path}${extension}"]} {
            error "Refusing to overwrite ${base_path}${extension}; use a new capture name."
        }
    }
    file mkdir [file dirname $base_path]
    write_hw_ila_data "${base_path}.ila" $data
    write_hw_ila_data -csv_file "${base_path}.csv" $data
    puts "Saved ${base_path}.ila and ${base_path}.csv"
}
