# ifc2FiCR

A single-tool converter from Industry Foundation Classes (IFC) building models
to [FiCR ontology](https://w3id.org/ficr) instances (ABox), enabling semantic
fire compliance and risk analysis on BIM data.

```text
IFC2X3 (.ifc)  ──►  ifc_to_ficr (Python)  ──►  FiCR ABox (.ttl)
                    Stage A: IFC → BOT graph
                    Stage B: BOT graph → FiCR ABox
```

The converter targets the **frozen FiCR TBox v1.1.0**
(`FiCR_ontology/ficr.ttl`, namespace `https://w3id.org/ficr#`), which imports
[BOT](https://w3id.org/bot#) for spatial topology. Output files are pure ABox:
instance data plus an `owl:imports <https://w3id.org/ficr>` header — no
embedded schema declarations.

> The previous two-stage pipeline (IFCtoLBD Java jar + `lbd_to_ficr_converter.py`,
> old namespace `bam/ficr#`) and the golden baseline files it produced are
> archived under [`archive/legacy_pipeline/`](archive/legacy_pipeline/README.md).

## Setup

Python 3.10+; no Java required.

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e .        # installs ifcopenshell + rdflib
```

## Usage

```bash
# Convert (writes <input>_ficr.ttl next to the input by default)
.venv\Scripts\python -m ifc_to_ficr convert ifcs/model.ifc -o ficr_outputs/model_ficr.ttl

# Optional: dump the intermediate Stage A BOT graph (default: <input>_lbd.ttl)
.venv\Scripts\python -m ifc_to_ficr convert ifcs/model.ifc --emit-intermediate
```

Only **IFC2X3** is supported; other schemas exit with code 3 and a clear
message. A coverage report (entities visited, converted per FiCR class,
skipped with reasons, properties extracted vs missing) is printed after every
run. Existing output files are never overwritten without `--force`.

Exit codes: `0` ok · `1` error · `2` usage · `3` unsupported schema ·
`4` TBox validation failure.

## What the converter does

**Stage A — IFC → in-memory BOT graph** (no geometry processing):

- Spatial tree `bot:Site/Building/Storey/Space` + `bot:hasBuilding/hasStorey/hasSpace`
  from `IfcRelAggregates`; `bot:containsElement` from
  `IfcRelContainedInSpatialStructure` (plus placement-chain containment for
  stair components); `bot:adjacentElement` from `IfcRelSpaceBoundary`;
  `bot:hasSubElement` from element aggregation and
  `IfcRelVoidsElement`/`IfcRelFillsElement` (wall→door, roof→window).
- Element typing as (IFC entity, PredefinedType) pairs via the IFC2X3
  schema profile (`profile_ifc2x3.py`).
- The consumed property subset from Revit property sets (volume, length,
  width, area, thickness, elevation, unbounded height, isExternal,
  loadBearing, OmniClass category, category description, fire rating) plus
  `GlobalId`/`ObjectType` attributes.

**Stage B — BOT graph → FiCR ABox**:

- Class mapping (IFC entity, PredefinedType) → FiCR classes
  (`ficr:Wall`, `ficr:FloorSlab`, `ficr:Doorset`, …); unmapped element types
  fall back to `bot:Element`.
- Property mapping to `ficr:hasArea`, `ficr:hasThickness`, `ficr:isExternal`,
  … (xsd:decimal at 3 decimals, xsd:boolean, xsd:string).
- Post-conversion inference: Multi/SingleStoreyBuilding, Basement/
  GroundAndAboveStorey + `isAboveGround`, `isStoreyAbove/Below`,
  `ficr:ExternalWall`, space classification via OmniClass codes with label
  fallback (`ficr:RoomSpace` + `ficr:hasSpaceUsage` …), space adjacency
  (`bot:adjacentZone` / `bot:intersectsZone`), fire rating →
  `ficr:hasActualREI`.

**Safety gates** (all hard errors):

- Schema gate — only IFC2X3 input is accepted.
- TBox fingerprint gate — refuses to run against anything but the frozen
  TBox v1.1.0 (triple/term counts hard-coded in `tbox.py`).
- Term gate — every emitted `ficr:`/`bot:` term must exist in
  `FiCR_ontology/ficr.ttl` + `FiCR_ontology/bot.ttl`.

## Provenance and validation

The converter was developed against a golden baseline produced by the
archived legacy pipeline (Duplex A, buildingSMART community sample, 268
elements): its Stage A output matched the baseline LBD graph exactly
(0 missing / 0 extra triples across all consumed channels) and its final
output matched the baseline FiCR ABox after namespace normalisation, with
every remaining difference classified as an expected migration or documented
improvement (0 unexpected). The classification ledger is `CHANGELOG.md`; the
baseline files live in `archive/legacy_pipeline/`.

## Project structure

```text
FiCR_ifcs/
├── ifc_to_ficr/              # the converter package (CLI: python -m ifc_to_ficr)
├── FiCR_ontology/
│   ├── ficr.ttl              # frozen FiCR TBox v1.1.0 (read-only, authoritative)
│   └── bot.ttl               # BOT 0.3.2 (imported by FiCR)
├── archive/legacy_pipeline/  # superseded two-stage pipeline + golden baseline files
├── ifcs/                     # input IFC files
├── ficr_outputs/             # converted FiCR ABox files
├── CHANGELOG.md              # intentional-deviations ledger
└── README.md
```

## Tested IFC Models

| Model | Source |
| --- | --- |
| Duplex A (Architectural) | [buildingSMART Community Sample Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files) |
| Clinic Architectural | [buildingSMART Community Sample Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files) |

Duplex A (268 elements, ~2,600 output triples) is the golden baseline
archived in `archive/legacy_pipeline/`; Clinic Architectural (3,196 entities,
~31,400 output triples) exercises curtain walls, large member sets and live
fire-rating values.

## Related Projects

- [FiCR Ontology](https://raingo111.github.io/FiCR-ontology/) — the FiCR ontology documentation
- [FiCR Platform](https://github.com/RainGo111/FiCR) — full-stack fire compliance analysis platform using the FiCR ontology
- [IFCtoLBD](https://github.com/jyrkioraskari/IFCtoLBD) — IFC to Linked Building Data converter (upstream dependency of the archived legacy pipeline)
- [buildingSMART Community Sample Test Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files) — IFC test models used for validation

## License

MIT
