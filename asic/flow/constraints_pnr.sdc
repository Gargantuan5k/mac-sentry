# Implementation headroom for post-repair antenna loads; signoff stays at 10.
source [file join [file dirname [info script]] constraints.sdc]
set_max_fanout 8 [current_design]
