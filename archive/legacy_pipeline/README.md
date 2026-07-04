# Legacy two-stage pipeline (archived)

This directory preserves the original two-stage IFC-to-FiCR pipeline and the
golden baseline files it produced. It has been **superseded by the
single-tool `ifc_to_ficr` package** at the repository root.

## Contents

| File | Role |
| --- | --- |
| `IFCtoLBD_CLI_2_44_4.jar` | Stage 1 — IFCtoLBD v2.44.4 (Java). Converted IFC2X3 STEP files into an LBD graph (BOT topology + beo:/props: product types and properties). |
| `lbd_to_ficr_converter.py` | Stage 2 — mapped the LBD graph into a FiCR ABox under the old `https://w3id.org/bam/ficr#` namespace, against the pre-freeze TBox. |
| `Duplex_A_20110907.ifc` | Golden baseline input — buildingSMART community sample model (IFC2X3). |
| `Duplex_A_20110907.ttl` | Golden baseline stage-1 output (LBD graph) produced by the jar from the model above. |
| `Duplex_A_20110907_ficr.ttl` | Golden baseline stage-2 output (old-namespace FiCR ABox) produced by `lbd_to_ficr_converter.py`. |

## Why it is kept

The three `Duplex_A_20110907*` files were the **audit baseline** used to
develop and verify `ifc_to_ficr`: its Stage A output was diffed byte-exact
against the LBD file (0/0), and its final output against the FiCR ABox after
namespace normalisation (79× MIG-01 + 2× MIG-02 + 1× IMP-01 classified
diffs, 0 unexpected — see `CHANGELOG.md` at the repo root). The tool
versions that generated the baseline are archived with it for
reproducibility.

To reproduce stage 1 (requires Java 11+):

```bash
java -jar IFCtoLBD_CLI_2_44_4.jar Duplex_A_20110907.ifc -l 3
```

To reproduce stage 2 (requires Python 3.9+ with rdflib, and the pre-freeze
TBox at `FiCR_ontology/ficr_tbox.ttl` relative to the working directory):

```bash
python lbd_to_ficr_converter.py Duplex_A_20110907.ttl Duplex_A_20110907_ficr.ttl
```

## Status

Superseded. Do not use for new conversions — use the `ifc_to_ficr` CLI
instead (see the repository README). The old namespace `bam/ficr#` and the
inline schema-stub output of stage 2 are retired; the current frozen TBox is
`FiCR_ontology/ficr.ttl` (`https://w3id.org/ficr#`, v1.1.0).
