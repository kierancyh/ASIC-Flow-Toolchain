# ~/ll_designs/ll_policy/power_activity.tcl
# Fixed activity assumptions for fair (comparable) power reporting inside OpenROAD.
# Not workload-accurate, but consistent across designs.
#
# IMPORTANT:
# Different OpenSTA builds accept different argument styles for set_power_activity.
# So we try a few variants and fall back safely.

set applied 0

# Variant A: newer flag style (may fail on your build)
if {!$applied && [catch {set_power_activity -global -toggle_rate 0.05 -static_probability 0.5} err] == 0} {
  set applied 1
}

# Variant B: alternate flag naming (may fail on your build)
if {!$applied && [catch {set_power_activity -global -density 0.05 -duty 0.5} err] == 0} {
  set applied 1
}

# Variant C: older positional style (this is the one most likely to work on your build)
# Often interpreted as: set_power_activity -global <toggle_rate> <static_probability>
if {!$applied && [catch {set_power_activity -global 0.05 0.5} err] == 0} {
  set applied 1
}

puts "POWER_ACTIVITY_APPLIED=$applied"
if {!$applied} {
  puts "WARN: set_power_activity could not be applied on this OpenSTA build. Power may revert to defaults."
}