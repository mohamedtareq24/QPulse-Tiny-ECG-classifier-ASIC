# System Clock (Physical Pin Mapping Only)
set_property -dict {PACKAGE_PIN K17 IOSTANDARD LVCMOS33} [get_ports sys_clock]

# Active-Low Reset (Mapped to Onboard Switch 0)
set_property -dict {PACKAGE_PIN G15 IOSTANDARD LVCMOS33} [get_ports arst_n_0]
set_property -dict {PACKAGE_PIN V15 IOSTANDARD LVCMOS33} [get_ports tx_0]
set_property -dict {PACKAGE_PIN T14 IOSTANDARD LVCMOS33} [get_ports rx_0]

# Minimal wrapper-level ILA (u_ila_0)

















create_debug_core u_ila_0 ila
set_property ALL_PROBE_SAME_MU true [get_debug_cores u_ila_0]
set_property ALL_PROBE_SAME_MU_CNT 4 [get_debug_cores u_ila_0]
set_property C_ADV_TRIGGER true [get_debug_cores u_ila_0]
set_property C_DATA_DEPTH 2048 [get_debug_cores u_ila_0]
set_property C_EN_STRG_QUAL true [get_debug_cores u_ila_0]
set_property C_INPUT_PIPE_STAGES 1 [get_debug_cores u_ila_0]
set_property C_TRIGIN_EN false [get_debug_cores u_ila_0]
set_property C_TRIGOUT_EN false [get_debug_cores u_ila_0]
set_property port_width 1 [get_debug_ports u_ila_0/clk]
connect_debug_port u_ila_0/clk [get_nets [list bd_i/clk_wiz/inst/clk_out1]]
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe0]
set_property port_width 3 [get_debug_ports u_ila_0/probe0]
connect_debug_port u_ila_0/probe0 [get_nets [list {bd_i/ecg_wrapper_0/inst/win_idx[0]} {bd_i/ecg_wrapper_0/inst/win_idx[1]} {bd_i/ecg_wrapper_0/inst/win_idx[2]}]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe1]
set_property port_width 5 [get_debug_ports u_ila_0/probe1]
connect_debug_port u_ila_0/probe1 [get_nets [list {bd_i/ecg_wrapper_0/inst/argmax_oh_c[0]} {bd_i/ecg_wrapper_0/inst/argmax_oh_c[1]} {bd_i/ecg_wrapper_0/inst/argmax_oh_c[2]} {bd_i/ecg_wrapper_0/inst/argmax_oh_c[3]} {bd_i/ecg_wrapper_0/inst/argmax_oh_c[4]}]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe2]
set_property port_width 8 [get_debug_ports u_ila_0/probe2]
connect_debug_port u_ila_0/probe2 [get_nets [list {bd_i/ecg_wrapper_0/inst/btx_tdata[0]} {bd_i/ecg_wrapper_0/inst/btx_tdata[1]} {bd_i/ecg_wrapper_0/inst/btx_tdata[2]} {bd_i/ecg_wrapper_0/inst/btx_tdata[3]} {bd_i/ecg_wrapper_0/inst/btx_tdata[4]} {bd_i/ecg_wrapper_0/inst/btx_tdata[5]} {bd_i/ecg_wrapper_0/inst/btx_tdata[6]} {bd_i/ecg_wrapper_0/inst/btx_tdata[7]}]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe3]
set_property port_width 80 [get_debug_ports u_ila_0/probe3]
connect_debug_port u_ila_0/probe3 [get_nets [list {bd_i/ecg_wrapper_0/inst/out_tdata[0]} {bd_i/ecg_wrapper_0/inst/out_tdata[1]} {bd_i/ecg_wrapper_0/inst/out_tdata[2]} {bd_i/ecg_wrapper_0/inst/out_tdata[3]} {bd_i/ecg_wrapper_0/inst/out_tdata[4]} {bd_i/ecg_wrapper_0/inst/out_tdata[5]} {bd_i/ecg_wrapper_0/inst/out_tdata[6]} {bd_i/ecg_wrapper_0/inst/out_tdata[7]} {bd_i/ecg_wrapper_0/inst/out_tdata[8]} {bd_i/ecg_wrapper_0/inst/out_tdata[9]} {bd_i/ecg_wrapper_0/inst/out_tdata[10]} {bd_i/ecg_wrapper_0/inst/out_tdata[11]} {bd_i/ecg_wrapper_0/inst/out_tdata[12]} {bd_i/ecg_wrapper_0/inst/out_tdata[13]} {bd_i/ecg_wrapper_0/inst/out_tdata[14]} {bd_i/ecg_wrapper_0/inst/out_tdata[15]} {bd_i/ecg_wrapper_0/inst/out_tdata[16]} {bd_i/ecg_wrapper_0/inst/out_tdata[17]} {bd_i/ecg_wrapper_0/inst/out_tdata[18]} {bd_i/ecg_wrapper_0/inst/out_tdata[19]} {bd_i/ecg_wrapper_0/inst/out_tdata[20]} {bd_i/ecg_wrapper_0/inst/out_tdata[21]} {bd_i/ecg_wrapper_0/inst/out_tdata[22]} {bd_i/ecg_wrapper_0/inst/out_tdata[23]} {bd_i/ecg_wrapper_0/inst/out_tdata[24]} {bd_i/ecg_wrapper_0/inst/out_tdata[25]} {bd_i/ecg_wrapper_0/inst/out_tdata[26]} {bd_i/ecg_wrapper_0/inst/out_tdata[27]} {bd_i/ecg_wrapper_0/inst/out_tdata[28]} {bd_i/ecg_wrapper_0/inst/out_tdata[29]} {bd_i/ecg_wrapper_0/inst/out_tdata[30]} {bd_i/ecg_wrapper_0/inst/out_tdata[31]} {bd_i/ecg_wrapper_0/inst/out_tdata[32]} {bd_i/ecg_wrapper_0/inst/out_tdata[33]} {bd_i/ecg_wrapper_0/inst/out_tdata[34]} {bd_i/ecg_wrapper_0/inst/out_tdata[35]} {bd_i/ecg_wrapper_0/inst/out_tdata[36]} {bd_i/ecg_wrapper_0/inst/out_tdata[37]} {bd_i/ecg_wrapper_0/inst/out_tdata[38]} {bd_i/ecg_wrapper_0/inst/out_tdata[39]} {bd_i/ecg_wrapper_0/inst/out_tdata[40]} {bd_i/ecg_wrapper_0/inst/out_tdata[41]} {bd_i/ecg_wrapper_0/inst/out_tdata[42]} {bd_i/ecg_wrapper_0/inst/out_tdata[43]} {bd_i/ecg_wrapper_0/inst/out_tdata[44]} {bd_i/ecg_wrapper_0/inst/out_tdata[45]} {bd_i/ecg_wrapper_0/inst/out_tdata[46]} {bd_i/ecg_wrapper_0/inst/out_tdata[47]} {bd_i/ecg_wrapper_0/inst/out_tdata[48]} {bd_i/ecg_wrapper_0/inst/out_tdata[49]} {bd_i/ecg_wrapper_0/inst/out_tdata[50]} {bd_i/ecg_wrapper_0/inst/out_tdata[51]} {bd_i/ecg_wrapper_0/inst/out_tdata[52]} {bd_i/ecg_wrapper_0/inst/out_tdata[53]} {bd_i/ecg_wrapper_0/inst/out_tdata[54]} {bd_i/ecg_wrapper_0/inst/out_tdata[55]} {bd_i/ecg_wrapper_0/inst/out_tdata[56]} {bd_i/ecg_wrapper_0/inst/out_tdata[57]} {bd_i/ecg_wrapper_0/inst/out_tdata[58]} {bd_i/ecg_wrapper_0/inst/out_tdata[59]} {bd_i/ecg_wrapper_0/inst/out_tdata[60]} {bd_i/ecg_wrapper_0/inst/out_tdata[61]} {bd_i/ecg_wrapper_0/inst/out_tdata[62]} {bd_i/ecg_wrapper_0/inst/out_tdata[63]} {bd_i/ecg_wrapper_0/inst/out_tdata[64]} {bd_i/ecg_wrapper_0/inst/out_tdata[65]} {bd_i/ecg_wrapper_0/inst/out_tdata[66]} {bd_i/ecg_wrapper_0/inst/out_tdata[67]} {bd_i/ecg_wrapper_0/inst/out_tdata[68]} {bd_i/ecg_wrapper_0/inst/out_tdata[69]} {bd_i/ecg_wrapper_0/inst/out_tdata[70]} {bd_i/ecg_wrapper_0/inst/out_tdata[71]} {bd_i/ecg_wrapper_0/inst/out_tdata[72]} {bd_i/ecg_wrapper_0/inst/out_tdata[73]} {bd_i/ecg_wrapper_0/inst/out_tdata[74]} {bd_i/ecg_wrapper_0/inst/out_tdata[75]} {bd_i/ecg_wrapper_0/inst/out_tdata[76]} {bd_i/ecg_wrapper_0/inst/out_tdata[77]} {bd_i/ecg_wrapper_0/inst/out_tdata[78]} {bd_i/ecg_wrapper_0/inst/out_tdata[79]}]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe4]
set_property port_width 16 [get_debug_ports u_ila_0/probe4]
connect_debug_port u_ila_0/probe4 [get_nets [list {bd_i/ecg_wrapper_0/inst/in_tdata[0]} {bd_i/ecg_wrapper_0/inst/in_tdata[1]} {bd_i/ecg_wrapper_0/inst/in_tdata[2]} {bd_i/ecg_wrapper_0/inst/in_tdata[3]} {bd_i/ecg_wrapper_0/inst/in_tdata[4]} {bd_i/ecg_wrapper_0/inst/in_tdata[5]} {bd_i/ecg_wrapper_0/inst/in_tdata[6]} {bd_i/ecg_wrapper_0/inst/in_tdata[7]} {bd_i/ecg_wrapper_0/inst/in_tdata[8]} {bd_i/ecg_wrapper_0/inst/in_tdata[9]} {bd_i/ecg_wrapper_0/inst/in_tdata[10]} {bd_i/ecg_wrapper_0/inst/in_tdata[11]} {bd_i/ecg_wrapper_0/inst/in_tdata[12]} {bd_i/ecg_wrapper_0/inst/in_tdata[13]} {bd_i/ecg_wrapper_0/inst/in_tdata[14]} {bd_i/ecg_wrapper_0/inst/in_tdata[15]}]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe5]
set_property port_width 10 [get_debug_ports u_ila_0/probe5]
connect_debug_port u_ila_0/probe5 [get_nets [list {bd_i/ecg_wrapper_0/inst/win_val[0]} {bd_i/ecg_wrapper_0/inst/win_val[1]} {bd_i/ecg_wrapper_0/inst/win_val[2]} {bd_i/ecg_wrapper_0/inst/win_val[3]} {bd_i/ecg_wrapper_0/inst/win_val[4]} {bd_i/ecg_wrapper_0/inst/win_val[5]} {bd_i/ecg_wrapper_0/inst/win_val[6]} {bd_i/ecg_wrapper_0/inst/win_val[7]} {bd_i/ecg_wrapper_0/inst/win_val[8]} {bd_i/ecg_wrapper_0/inst/win_val[9]}]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe6]
set_property port_width 3 [get_debug_ports u_ila_0/probe6]
connect_debug_port u_ila_0/probe6 [get_nets [list {bd_i/ecg_wrapper_0/inst/ctrl_reg[0]} {bd_i/ecg_wrapper_0/inst/ctrl_reg[1]} {bd_i/ecg_wrapper_0/inst/ctrl_reg[2]}]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe7]
set_property port_width 16 [get_debug_ports u_ila_0/probe7]
connect_debug_port u_ila_0/probe7 [get_nets [list {bd_i/ecg_wrapper_0/inst/brx_tdata[0]} {bd_i/ecg_wrapper_0/inst/brx_tdata[1]} {bd_i/ecg_wrapper_0/inst/brx_tdata[2]} {bd_i/ecg_wrapper_0/inst/brx_tdata[3]} {bd_i/ecg_wrapper_0/inst/brx_tdata[4]} {bd_i/ecg_wrapper_0/inst/brx_tdata[5]} {bd_i/ecg_wrapper_0/inst/brx_tdata[6]} {bd_i/ecg_wrapper_0/inst/brx_tdata[7]} {bd_i/ecg_wrapper_0/inst/brx_tdata[8]} {bd_i/ecg_wrapper_0/inst/brx_tdata[9]} {bd_i/ecg_wrapper_0/inst/brx_tdata[10]} {bd_i/ecg_wrapper_0/inst/brx_tdata[11]} {bd_i/ecg_wrapper_0/inst/brx_tdata[12]} {bd_i/ecg_wrapper_0/inst/brx_tdata[13]} {bd_i/ecg_wrapper_0/inst/brx_tdata[14]} {bd_i/ecg_wrapper_0/inst/brx_tdata[15]}]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe8]
set_property port_width 1 [get_debug_ports u_ila_0/probe8]
connect_debug_port u_ila_0/probe8 [get_nets [list bd_i/ecg_wrapper_0/inst/brx_tready]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe9]
set_property port_width 1 [get_debug_ports u_ila_0/probe9]
connect_debug_port u_ila_0/probe9 [get_nets [list bd_i/ecg_wrapper_0/inst/brx_tvalid]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe10]
set_property port_width 1 [get_debug_ports u_ila_0/probe10]
connect_debug_port u_ila_0/probe10 [get_nets [list bd_i/ecg_wrapper_0/inst/btx_tready]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe11]
set_property port_width 1 [get_debug_ports u_ila_0/probe11]
connect_debug_port u_ila_0/probe11 [get_nets [list bd_i/ecg_wrapper_0/inst/btx_tvalid]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe12]
set_property port_width 1 [get_debug_ports u_ila_0/probe12]
connect_debug_port u_ila_0/probe12 [get_nets [list bd_i/ecg_wrapper_0/inst/engine_mode]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe13]
set_property port_width 1 [get_debug_ports u_ila_0/probe13]
connect_debug_port u_ila_0/probe13 [get_nets [list bd_i/ecg_wrapper_0/inst/engine_soft_reset]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe14]
set_property port_width 1 [get_debug_ports u_ila_0/probe14]
connect_debug_port u_ila_0/probe14 [get_nets [list bd_i/ecg_wrapper_0/inst/engine_start]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe15]
set_property port_width 1 [get_debug_ports u_ila_0/probe15]
connect_debug_port u_ila_0/probe15 [get_nets [list bd_i/ecg_wrapper_0/inst/in_tready]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe16]
set_property port_width 1 [get_debug_ports u_ila_0/probe16]
connect_debug_port u_ila_0/probe16 [get_nets [list bd_i/ecg_wrapper_0/inst/in_tvalid]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe17]
set_property port_width 1 [get_debug_ports u_ila_0/probe17]
connect_debug_port u_ila_0/probe17 [get_nets [list bd_i/ecg_wrapper_0/inst/out_hs_d]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe18]
set_property port_width 1 [get_debug_ports u_ila_0/probe18]
connect_debug_port u_ila_0/probe18 [get_nets [list bd_i/ecg_wrapper_0/inst/out_tready]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe19]
set_property port_width 1 [get_debug_ports u_ila_0/probe19]
connect_debug_port u_ila_0/probe19 [get_nets [list bd_i/ecg_wrapper_0/inst/out_tvalid]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe20]
set_property port_width 1 [get_debug_ports u_ila_0/probe20]
connect_debug_port u_ila_0/probe20 [get_nets [list bd_i/ecg_wrapper_0/inst/rx]]
create_debug_port u_ila_0 probe
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe21]
set_property port_width 1 [get_debug_ports u_ila_0/probe21]
connect_debug_port u_ila_0/probe21 [get_nets [list bd_i/ecg_wrapper_0/inst/tx]]
set_property C_CLK_INPUT_FREQ_HZ 300000000 [get_debug_cores dbg_hub]
set_property C_ENABLE_CLK_DIVIDER false [get_debug_cores dbg_hub]
set_property C_USER_SCAN_CHAIN 1 [get_debug_cores dbg_hub]
connect_debug_port dbg_hub/clk [get_nets u_ila_0_clk_out1]
