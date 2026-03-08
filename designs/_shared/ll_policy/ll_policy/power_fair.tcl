# power_fair.tcl
# Standalone OpenSTA script for controlled-activity ("fair") power reporting.

set lib $::env(LIBERTY)
set net $::env(NETLIST)
set top $::env(TOP)
set clk $::env(CLOCK_PORT)
set per $::env(CLOCK_PERIOD)
set out $::env(OUT_RPT)

read_liberty $lib
read_verilog $net
link_design $top

create_clock -name clk -period $per [get_ports $clk]

# Apply fixed activity assumptions.
# Different builds accept different argument styles; try multiple.
set applied 0

if {!$applied && [catch {set_power_activity -global -density 0.05 -duty 0.5} err] == 0} {
  set applied 1
}
if {!$applied && [catch {set_power_activity -global -toggle_rate 0.05 -static_probability 0.5} err] == 0} {
  set applied 1
}
if {!$applied && [catch {set_power_activity -global 0.05 0.5} err] == 0} {
  set applied 1
}

puts "POWER_ACTIVITY_APPLIED=$applied"

report_power > $out