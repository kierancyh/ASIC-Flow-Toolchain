# ~/ll_designs/ll_policy/constraints.sdc
create_clock -name clk -period $::env(CLOCK_PERIOD) [get_ports clk]
set_clock_uncertainty 0.10 [get_clocks clk]
set_false_path -from [get_ports clk]
