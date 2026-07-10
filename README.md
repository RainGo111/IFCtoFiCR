# IFCtoFiCR

A single-tool converter from Industry Foundation Classes (IFC) building models
to [FiCR ontology](https://w3id.org/ficr) instances (ABox), enabling semantic
fire compliance and risk analysis on BIM data.

```text
IFC2X3 (.ifc)  ──►  ifc_to_ficr (Python)  ──►  FiCR ABox (.ttl)
                    Stage A: IFC → BOT graph
                    Stage B: BOT graph → FiCR ABox
```

The converter targets the **FiCR TBox** (`FiCR_ontology/ficr.ttl`, namespace
`https://w3id.org/ficr#`, currently v1.1.1), which imports
[BOT](https://w3id.org/bot#) for spatial topology. Output files are pure ABox:
instance data plus an `owl:imports <https://w3id.org/ficr>` header — no
embedded schema declarations.

> The previous two-stage pipeline (IFCtoLBD Java jar + `lbd_to_ficr_converter.py`,
> old namespace `bam/ficr#`) is archived under
> [`archive/legacy_pipeline/`](archive/legacy_pipeline/README.md); the golden
> baseline files it produced are preserved in git history.

## Setup

Python 3.10+; no Java required.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e .        # installs ifcopenshell + rdflib
```

`FiCR_ontology/` is not tracked in this repository (the ontology is developed
in the [FiCR Ontology](https://raingo111.github.io/FiCR-ontology/) project and
updated frequently). Before running the converter, place the current
`ficr.ttl` and `bot.ttl` (BOT 0.3.2) under `FiCR_ontology/`.

## Usage

```bash
# Convert (writes <input>_ficr.ttl next to the input by default)
.venv\Scripts\python -m ifc_to_ficr convert ifcs/model.ifc -o ficr_outputs/model_ficr.ttl

# Optional: dump the intermediate Stage A BOT graph (default: <input>_lbd.ttl)
.venv\Scripts\python -m ifc_to_ficr convert ifcs/model.ifc --emit-intermediate
```

**IFC2X3** is currently the only supported schema (other schemas exit with
code 3 and a clear message); support for further schemas such as IFC4 will
be added incrementally as more diverse models are processed — the
per-schema-profile architecture is designed for exactly that. A coverage
report (entities visited, converted per FiCR class, skipped with reasons,
properties extracted vs missing) is printed after every run. Existing output
files are never overwritten without `--force`.

Exit codes: `0` ok · `1` error · `2` usage · `3` unsupported schema ·
`4` TBox validation failure.

## What the converter does

**Stage A — IFC → in-memory BOT graph** (no geometry processing): extracts
the spatial tree (`bot:Site/Building/Storey/Space`), element containment,
space adjacency and sub-element decomposition, types every element as an
(IFC entity, PredefinedType) pair, and collects a curated property subset
(dimensions, isExternal/loadBearing, OmniClass classification, fire rating).
All version-sensitive knowledge lives in a per-schema profile
(`profile_ifc2x3.py`). The intermediate graph deliberately follows the
**Linked Building Data (LBD) vocabularies and conventions** — BOT for
topology, the BEO and PROPS namespaces and the instance-URI scheme
established by IFCtoLBD — which keeps it comparable with the wider LBD
ecosystem and with the outputs of the legacy pipeline.

**Stage B — BOT graph → FiCR ABox**: maps element types and properties to
FiCR terms, then infers the higher-level semantics: building/storey
classification and ordering, external walls, space classification via
OmniClass codes with label fallback (`ficr:hasSpaceUsage`), space adjacency
(`bot:adjacentZone` / `bot:intersectsZone`) and fire ratings
(`ficr:hasActualREI`).

**Safety gates**: schema gate and TBox term validation (mapping targets at
startup, every emitted `ficr:`/`bot:` term at the end) are hard errors; a
TBox fingerprint check warns when the ontology has changed since the
converter was last aligned with it.

## Project structure

```text
IFCtoFiCR/
├── ifc_to_ficr/              # converter package (CLI: python -m ifc_to_ficr)
├── FiCR_ontology/            # ficr.ttl + bot.ttl (local only, not tracked)
├── archive/legacy_pipeline/  # superseded two-stage pipeline
├── ifcs/                     # input IFC models (local only, not tracked)
├── ficr_outputs/             # converted FiCR ABox files (local only, not tracked)
├── pyproject.toml            # package metadata and dependencies
├── CHANGELOG.md              # change ledger
└── README.md
```

## Related Projects

- [FiCR Project Site](https://ficr-site.vercel.app/) — overview of the FiCR project
- [FiCR Ontology](https://raingo111.github.io/FiCR-ontology/) — the FiCR ontology documentation
- [FiCR Platform](https://github.com/RainGo111/FiCR) — full-stack fire compliance analysis platform (archived)
- [BOT — Building Topology Ontology](https://w3id.org/bot) — the spatial-topology backbone of both the intermediate graph and FiCR itself
- [W3C Linked Building Data Community Group](https://www.w3.org/community/lbd/) — origin of the LBD vocabularies (BOT, BEO, PROPS) this converter builds on
- [IFCtoLBD](https://github.com/jyrkioraskari/IFCtoLBD) — IFC to Linked Building Data converter; the legacy pipeline's stage 1, whose LBD output conventions (vocabularies, instance-URI scheme) Stage A intentionally replicates
- [buildingSMART Community Sample Test Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files) — IFC test models used for validation

## License

MIT
