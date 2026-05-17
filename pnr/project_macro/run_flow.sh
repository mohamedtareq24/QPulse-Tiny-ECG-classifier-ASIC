#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_flow.sh — Full LibreLane flow with PDN bridge injection
#
# Flow (normal):
#   1. Synthesis → GeneratePDN     (librelane --to OpenROAD.GeneratePDN)
#   2. Bridge patch                (patch_pdn_bridges.py injects 8 met4 wires)
#   3. RemovePDNObstructions → end (librelane --from Odb.RemovePDNObstructions)
#
# Flow (ECO signoff):
#   bash run_flow.sh ECO <BASE_TAG> <ECO_TAG>
#   Phase A: InsertECOBuffers → re-DRT → IRDropReport  (resumes from BASE_TAG step-46)
#   Phase B: Magic.StreamOut → full physical signoff    (resumes from Phase A IR-drop state)
#
# Usage:
#   cd openlane/project_macro
#   bash run_flow.sh [RUN_TAG]                    # default tag: run_v2
#   bash run_flow.sh ECO <BASE_TAG> <ECO_TAG>     # ECO signoff mode
#
# Prerequisites:
#   - librelane on PATH  (or inside nix-shell ~/librelane/shell.nix)
#   - openroad on PATH
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/config.json"
ECO_CONFIG="$SCRIPT_DIR/eco.json"
BRIDGE_SCRIPT="$SCRIPT_DIR/patch_pdn_bridges.py"

cd "$SCRIPT_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ── Sanity checks ─────────────────────────────────────────────────────────────
if ! command -v librelane &>/dev/null; then
    echo "ERROR: librelane not found on PATH."
    echo "       Run: nix-shell ~/librelane/shell.nix  then re-run this script."
    exit 1
fi

# ── Mode dispatch ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "ECO" ]]; then
    # ── ECO signoff mode ─────────────────────────────────────────────────────
    BASE_TAG="${2:?ERROR: ECO mode requires BASE_TAG as \$2}"
    ECO_TAG="${3:?ERROR: ECO mode requires ECO_TAG as \$3}"
    ECO_RUN_DIR="$SCRIPT_DIR/runs/$ECO_TAG"

    if [[ "$BASE_TAG" == "$ECO_TAG" ]]; then
        echo "ERROR: BASE_TAG and ECO_TAG must differ."
        echo "       Using the same tag would overwrite the base run."
        echo "       Example: bash run_flow.sh ECO Qpulse_adc_v1 Qpulse_adc_v1_signoff_v2"
        exit 1
    fi

    if [[ ! -f "$ECO_CONFIG" ]]; then
        echo "ERROR: eco.json not found at $ECO_CONFIG"
        exit 1
    fi

    # Find the most recent detailedrouting step in the base run (handles both
    # original PnR runs (step 46) and prior ECO runs (step 02, etc.)
    BASE_DRT_DIR="$(ls -d "$SCRIPT_DIR/runs/$BASE_TAG"/*-openroad-detailedrouting* 2>/dev/null | sort | tail -1)"
    BASE_DRT_STATE="$BASE_DRT_DIR/state_out.json"
    if [[ ! -f "$BASE_DRT_STATE" ]]; then
        echo "ERROR: No detailedrouting state_out.json found under runs/$BASE_TAG/"
        echo "       Ensure $BASE_TAG completed through detailed routing."
        exit 1
    fi
    log "  → Resuming from: $BASE_DRT_STATE"

    # Phase A — ECO buffer insertion + re-DRT + signoff prep (through IR drop)
    log "ECO Phase A — InsertECOBuffers → re-DRT → IRDropReport  (tag: $ECO_TAG)"
    librelane "$ECO_CONFIG" \
        --run-tag "$ECO_TAG" \
        --from Odb.InsertECOBuffers \
        --to OpenROAD.IRDropReport \
        --with-initial-state "$BASE_DRT_STATE"

    # Locate the IR-drop state produced by Phase A
    IRDROP_STATE="$(ls -d "$ECO_RUN_DIR"/*-openroad-irdropreport 2>/dev/null | sort | tail -1)/state_out.json"
    if [[ ! -f "$IRDROP_STATE" ]]; then
        echo "ERROR: IR-drop state_out.json not found in $ECO_RUN_DIR"
        exit 1
    fi
    log "  → IR-drop state: $IRDROP_STATE"

    # Phase B — Physical signoff (GDS, LEF, DRC, LVS, …)
    log "ECO Phase B — Magic.StreamOut → full physical signoff  (tag: $ECO_TAG)"
    librelane "$ECO_CONFIG" \
        --run-tag "$ECO_TAG" \
        --from Magic.StreamOut \
        --with-initial-state "$IRDROP_STATE"

    log "ECO signoff done. Results in: $ECO_RUN_DIR"
    exit 0
fi

# ── Normal flow ───────────────────────────────────────────────────────────────
RUN_TAG="${1:-run_v2}"
RUN_DIR="$SCRIPT_DIR/runs/$RUN_TAG"

if [[ ! -f "$BRIDGE_SCRIPT" ]]; then
    echo "ERROR: patch_pdn_bridges.py not found at $BRIDGE_SCRIPT"
    exit 1
fi

# ── Phase 1: Synthesis through GeneratePDN ───────────────────────────────────
log "Phase 1 — Synthesis → GeneratePDN  (tag: $RUN_TAG)"
librelane "$CONFIG" \
    --run-tag "$RUN_TAG" \
    --to OpenROAD.GeneratePDN

# ── Phase 2: Inject met4 PDN bridge wires ────────────────────────────────────
log "Phase 2 — Patching PDN bridges (patch_pdn_bridges.py)"
python3 "$BRIDGE_SCRIPT" "$RUN_DIR"

# Locate the patched state_out.json from the last generatepdn step
PDN_STATE="$(ls -d "$RUN_DIR"/*-openroad-generatepdn | sort | tail -1)/state_out.json"
if [[ ! -f "$PDN_STATE" ]]; then
    echo "ERROR: patched state_out.json not found at: $PDN_STATE"
    exit 1
fi
log "  → Resuming from: $PDN_STATE"

# ── Phase 3: RemovePDNObstructions → full completion ─────────────────────────
log "Phase 3 — Odb.RemovePDNObstructions → completion"
librelane "$CONFIG" \
    --run-tag "$RUN_TAG" \
    --from Odb.RemovePDNObstructions \
    --with-initial-state "$PDN_STATE"

log "Done. Results in: $RUN_DIR"
