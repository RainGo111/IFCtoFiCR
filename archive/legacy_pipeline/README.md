# Legacy two-stage pipeline (archived)

This directory preserves the stage-2 converter of the original two-stage
IFC-to-FiCR pipeline, which has been **superseded by the single-tool
`ifc_to_ficr` package** at the repository root.

## Contents

| File | Role |
| --- | --- |
| `lbd_to_ficr_converter.py` | Stage 2 — mapped an LBD graph into a FiCR ABox under the old `https://w3id.org/bam/ficr#` namespace, against the pre-freeze TBox. |

Stage 1 was [IFCtoLBD](https://github.com/jyrkioraskari/IFCtoLBD) v2.44.4
(Java CLI jar, downloadable from its releases page), which converted IFC2X3
STEP files into an LBD graph (BOT topology + beo:/props: product types and
properties).

## The golden baseline

This pipeline produced the golden baseline files (`Duplex_A_20110907.ifc` /
`.ttl` / `_ficr.ttl`) against which `ifc_to_ficr` was developed and verified:
Stage A matched the baseline LBD graph exactly (0/0 diff) and the final
output matched the baseline FiCR ABox after namespace normalisation with 0
unexpected differences (see `CHANGELOG.md` at the repo root). The baseline
data files were removed from the working tree on 2026-07-04 and remain
recoverable from git history (commit `3e220c2`); the input model is the
buildingSMART community sample "Duplex A (Architectural)".

## Status

Superseded. Do not use for new conversions — use the `ifc_to_ficr` CLI
instead (see the repository README). The old namespace `bam/ficr#` and the
inline schema-stub output of stage 2 are retired; the current FiCR TBox is
`FiCR_ontology/ficr.ttl` (`https://w3id.org/ficr#`).
