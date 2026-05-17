#!/usr/bin/env python3
"""
patch_pdn_bridges.py
--------------------
Run after OpenROAD.GeneratePDN to inject met4 bridge wires into the ODB,
then update state_out.json so the next LibreLane step picks up the patched DB.

Usage (from inside nix-shell):
  python3 patch_pdn_bridges.py <run_dir>

Example:
  python3 /home/zkp_egy2/Desktop/old_desktop/Tarek/ECG/tape_out/pnr/openlane/project_macro/patch_pdn_bridges.py \
      /home/zkp_egy2/Desktop/old_desktop/Tarek/ECG/tape_out/pnr/openlane/project_macro/runs/pdn_def_edit

It will:
  1. Find the GeneratePDN step directory inside <run_dir>
  2. Generate a TCL script that loads the ODB, adds bridges, writes patched ODB
  3. Run openroad on it
  4. Copy state_out.json -> state_out.json.orig and update odb/def paths
"""

import json, os, shutil, subprocess, sys, glob, tempfile

# ── Bridge definitions (DEF units = nm) ──────────────────────────────────────
# vccd1: from full-height strap center X=55520 to VPWR pin center X=81750
# vssd1: from VGND pin center X=236750 to full-height strap center X=255520
BRIDGES = [
    # (net_name, x1, y_center, x2, y_center, width_nm)
    # vccd1: strap X=55520 → VPWR pin X=81750, 4 bridges across pin height
    ("vccd1", 55520, 773500, 81750, 776500, 3000),  # Y centre 775000
    ("vccd1", 55520, 818500, 81750, 821500, 3000),  # Y centre 820000
    ("vccd1", 55520, 861380, 81750, 864380, 3000),  # Y centre 862880
    ("vccd1", 55520, 925500, 81750, 928500, 3000),  # Y centre 927000
    # vssd1: VGND pin X=236750 → strap X=255520, 4 bridges across pin height
    ("vssd1", 236750, 773500, 255520, 776500, 3000),  # Y centre 775000
    ("vssd1", 236750, 818500, 255520, 821500, 3000),  # Y centre 820000
    ("vssd1", 236750, 861380, 255520, 864380, 3000),  # Y centre 862880
    ("vssd1", 236750, 925500, 255520, 928500, 3000),  # Y centre 927000
]

SKY130 = ("/home/zkp_egy2/.ciel/ciel/sky130/versions/"
          "8afc8346a57fe1ab7934ba5a6056ea8b43078e71/"
          "sky130A/libs.ref/sky130_fd_sc_hd")
MACRO_LEF = ("/home/zkp_egy2/Desktop/old_desktop/Tarek/ECG/tape_out/pnr/"
             "lef/tt_um_TT06_SAR_wulffern.lef")

def find_generatepdn_dir(run_dir):
    matches = sorted(glob.glob(os.path.join(run_dir, "*openroad-generatepdn")))
    if not matches:
        sys.exit(f"ERROR: no generatepdn step found in {run_dir}")
    return matches[-1]

def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: patch_pdn_bridges.py <run_dir>")
    run_dir = os.path.abspath(sys.argv[1])
    step_dir = find_generatepdn_dir(run_dir)
    print(f"GeneratePDN step dir: {step_dir}")

    state_path = os.path.join(step_dir, "state_out.json")
    orig_backup = state_path + ".orig"

    # Always read the ORIGINAL (unpatched) state so odb_in is the real ODB.
    # If a previous run already patched state_out.json, read from .orig.
    read_path = orig_backup if os.path.exists(orig_backup) else state_path
    with open(read_path) as f:
        state = json.load(f)

    odb_in  = state["odb"]
    def_in  = state["def"]
    # If state was already pointing to a _bridged path, strip the suffix first.
    odb_in  = odb_in.replace("_bridged.odb", ".odb")
    def_in  = def_in.replace("_bridged.def", ".def")
    odb_out = odb_in.replace(".odb", "_bridged.odb")
    def_out = def_in.replace(".def", "_bridged.def")

    print(f"Input  ODB: {odb_in}")
    print(f"Output ODB: {odb_out}")

    # Build TCL
    tcl_lines = [
        f"read_lef {SKY130}/techlef/sky130_fd_sc_hd__nom.tlef",
        f"read_lef {SKY130}/lef/sky130_ef_sc_hd.lef",
        f"read_lef {SKY130}/lef/sky130_fd_sc_hd.lef",
        f"read_lef {MACRO_LEF}",
        f"read_db  {odb_in}",
        "",
        "set db    [ord::get_db]",
        "set block [[$db getChip] getBlock]",
        "",
    ]

    # Pre-fetch the existing SWire for each net (reuse, don't create new).
    # Creating a new dbSWire produces a disconnected segment in DEF/PSM.
    for net_name in {b[0] for b in BRIDGES}:
        tcl_lines += [
            f"set net_{net_name}  [$block findNet {net_name}]",
            f"set sw_{net_name}   [lindex [$net_{net_name} getSWires] 0]",
            f"if {{$sw_{net_name} eq {{}}}} {{",
            f"    set sw_{net_name} [odb::dbSWire_create $net_{net_name} ROUTED]",
            f"}}",
            "",
        ]

    for net_name, x1, y1, x2, y2, w in BRIDGES:
        half_w = w // 2
        yc = (y1 + y2) // 2
        ywlo = yc - half_w
        ywhi = yc + half_w
        tcl_lines += [
            f"# ── {net_name} bridge {x1}→{x2} nm ──",
            f"odb::dbSBox_create $sw_{net_name} \\"
            f" [[$block getTech] findLayer met4] \\"
            f" {x1} {ywlo} {x2} {ywhi} STRIPE",
            "",
        ]

    tcl_lines += [
        f"write_db  {odb_out}",
        f"write_def {def_out}",
        "puts \"Bridges added. ODB written.\"",
        "exit",
    ]

    tcl_script = tempfile.NamedTemporaryFile(suffix=".tcl", mode="w",
                                             delete=False)
    tcl_script.write("\n".join(tcl_lines))
    tcl_script.close()
    print(f"TCL script: {tcl_script.name}")

    ret = subprocess.run(["openroad", "-no_splash", tcl_script.name],
                         check=False)
    os.unlink(tcl_script.name)

    if ret.returncode != 0:
        sys.exit("ERROR: openroad failed")

    if not os.path.exists(odb_out):
        sys.exit(f"ERROR: expected output ODB not found: {odb_out}")

    # Patch state_out.json — always re-write from the original state
    if not os.path.exists(orig_backup):
        shutil.copy2(state_path, orig_backup)
        print(f"Original state backed up to: {orig_backup}")

    state["odb"] = odb_out
    state["def"] = def_out
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"state_out.json patched: odb → {odb_out}")
    print("\nNow resume the flow:")
    print(f"  librelane config.json --run-tag <your_tag> "
          f"--from OpenROAD.CutRows "
          f"--with-initial-state {state_path}")

if __name__ == "__main__":
    main()
