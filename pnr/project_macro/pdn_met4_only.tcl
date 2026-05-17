source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

# ─────────────────────────────────────────────────────────────────────────────
# Voltage domain
# ─────────────────────────────────────────────────────────────────────────────
set_voltage_domain \
    -name CORE \
    -power $::env(VDD_NET) \
    -ground $::env(GND_NET)

# ═════════════════════════════════════════════════════════════════════════════
# KNOBS
# ═════════════════════════════════════════════════════════════════════════════

# met4 vertical stripes — use exactly one POWER/GROUND pair for stdcell grid.
# Core-relative alignment targets macro-side PDN crossing:
#   POWER @ 76.23, GROUND @ 231.23 (delta = 155 µm)
set MET4_OFFSET    50.0 ;# core-rel µm
set MET4_PITCH    400.0  ;# µm
set MET4_WIDTH      3.0  ;# µm
set MET4_SPACING  [expr {$MET4_PITCH / 2.0 - $MET4_WIDTH}]  ;# = 152.0 µm

# met5 horizontal stripes — full die width mesh
set MET5_OFFSET    18.0    ;# core-rel µm from bottom
set MET5_PITCH    153.18   ;# µm  standard sky130 met5 PDN pitch
set MET5_WIDTH     5   ;# µm
set MET5_SPACING   [expr {$MET5_PITCH / 2.0 - $MET5_WIDTH}]  ;# = 74.99 µm

# met3 horizontal stripes — full-die mesh for stdcell grid.
# Use regular distribution (same phase family as met5) to avoid isolated
# met1 channel bands near the macro region.
set MET3_OFFSET   18.0  ;# core-rel µm from bottom
set MET3_PITCH   153.18 ;# µm
set MET3_WIDTH     2.0  ;# µm
set MET3_SPACING [expr {$MET3_PITCH / 2.0 - $MET3_WIDTH}]  ;# = 74.59 µm

# ADC macro-local met3 horizontal straps must use macro-local coordinates.
# Keep these compact to fit inside macro height (225.76 µm).
set ADC_MET3_OFFSET   10.0
set ADC_MET3_PITCH   150.0
set ADC_MET3_WIDTH     2.0
set ADC_MET3_SPACING [expr {$ADC_MET3_PITCH / 2.0 - $ADC_MET3_WIDTH}]  ;# = 73.0 µm

# Note: no macro-local met4 knobs needed — stdcell_grid met4 spans full height.

# ═════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# Stdcell grid — met4 vertical stripes + met1 followpin rails
#
# met3 H stripes are intentionally excluded from the stdcell grid.
# When met3 H stripes alternate P/G at ~76 µm half-pitch, their geometry
# blocks the via1→via2→via3 stack: the via3 landing pad on met3 conflicts
# with the wrong-net met3 stripe at that Y, preventing via insertion and
# causing PDN-0178/0179 full-width channel failures at every met3 Y position.
#
# Using met4 V only: pitch=310 µm across 868 µm core → 3 P + 3 G straps.
# MET4_OFFSET=76.23 aligns strap-1 with the ADC VPWR pin center.
# ─────────────────────────────────────────────────────────────────────────────
define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    -pins {met4}

add_pdn_stripe \
    -grid stdcell_grid \
    -layer met4 \
    -width $MET4_WIDTH \
    -pitch $MET4_PITCH \
    -offset $MET4_OFFSET \
    -spacing $MET4_SPACING \
    -starts_with POWER

# met1 followpin rails — power and ground rails for every stdcell row
add_pdn_stripe \
    -grid stdcell_grid \
    -layer met1 \
    -width 0.48 \
    -followpins

# met1 → met4: via stack at every H/V crossing (no conflicting met3 geometry)
add_pdn_connect \
    -grid stdcell_grid \
    -layers {met1 met4}

add_pdn_stripe \
    -grid stdcell_grid \
    -layer met4 \
    -width $MET4_WIDTH \
    -pitch 99999.0 \
    -offset 31.74 \
    -nets {vssd1}

# define_pdn_grid \
#     -macro \
#     -instances {u_adc} \
#     -name adc_macro_pdn \
#     -starts_with POWER \
#     -grid_over_boundary \
#     -voltage_domain CORE \
#     -halo {60 30 60 0} \
#     -obstructions {met2} 

# # Macro-local horizontal met3 straps (tracks are horizontal on sky130).
# # These intersect local met4 straps and connect through add_pdn_connect.
# add_pdn_stripe \
#     -grid adc_macro_pdn \
#     -layer met3 \
#     -width $ADC_MET3_WIDTH \
#     -pitch $ADC_MET3_PITCH \
#     -offset $ADC_MET3_OFFSET \
#     -spacing $ADC_MET3_SPACING \
#     -starts_with POWER

# # met4 vertical straps are provided by stdcell_grid (full die height).
# # Connecting met3 H-stripes to those passing-through met4 stripes is
# # sufficient; a separate macro-local met4 would cause stdcell_grid met4
# # to be cut at the macro halo Y boundaries.
# add_pdn_connect \
#     -grid adc_macro_pdn \
#     -layers {met3 met4}
