# CHANGELOG — ifc_to_ficr

Intentional deviations of the new single-tool converter relative to the old
two-stage pipeline (IFCtoLBD 2.44.4 + lbd_to_ficr_converter.py) and its golden
output `golden/Duplex_A_20110907_ficr.ttl`. Rule ids (MIG-*/IMP-*) match the
buckets in the classified diff report produced by `ifc-to-ficr verify`.

## 1.2.1 — 2026-07-04

### Fixed

- **IfcPlate no longer maps to ficr:FloorSlab.** Exposed by
  `Clinic_Architectural.ifc` (first model with plates): all 172 IfcPlate
  instances are glazed curtain-wall panels (`Decomposes` IfcCurtainWall),
  which the verbatim-ported `Plate -> FloorSlab` rule (intended for
  structural plates) misclassified as floor slabs — semantically wrong for
  fire analysis. Plates now fall back to `bot:Element`, consistent with the
  treatment of curtain-wall mullions; they stay reachable from their
  `ficr:Wall`-typed curtain wall via `bot:hasSubElement`. The archived Duplex
  baseline contains no plates, so its output is unaffected.

## 1.2.0 — 2026-07-04

### Repository simplified to "current tool + archive"

- **golden/ dissolved.** The three baseline data files (`Duplex_A_20110907
  .ifc/.ttl/_ficr.ttl`) moved into `archive/legacy_pipeline/`, joining the
  tools that produced them (kept for reproducibility). The development-time
  verification result they anchored is recorded in the 1.1.0 notes below.
- **Verification machinery removed.** `verify.py`, the `verify` CLI
  subcommand (exit code 5) and the pytest suite (`tests/`) were
  development-time scaffolding for the golden diff; the tool is now
  convert-only. Runtime safety gates remain: schema gate, TBox fingerprint
  gate, and the emitted-term gate.
- **Ontology directory renamed by the maintainer**: `onto/` ->
  `FiCR_ontology/` (contents unchanged: `ficr.ttl` frozen v1.1.0 +
  `bot.ttl`). CLI defaults, error messages, output headers and docs updated
  accordingly. The legacy `ficr.properties` artifact moved to the archive.
- README rewritten for the simplified layout.
- `lbd_outputs/` working directory removed (nothing writes there; the
  `--emit-intermediate` debug dump defaults to `<input>_lbd.ttl` next to the
  input). Build artifact `ifc_to_ficr.egg-info/` deleted (regenerates on
  install).

## 1.1.0 — 2026-07-04

### Frozen TBox adopted (maintainer action, upstream of this tool)

- `onto/ficr.ttl` replaced with the final frozen TBox v1.1.0, edited and saved
  in Protégé; consistency verified with HermiT. Edits: `ficr:hasREI` removed,
  `ficr:NotRequired` removed, `ficr:hasActualREI` kept with its
  `ficr:FabricElement` domain dropped. The file is read-only and
  authoritative.

### Changed

- **REI retarget.** `_map_fire_ratings` now emits `ficr:hasActualREI`
  (xsd:integer) instead of the removed `ficr:hasREI`. The golden dataset's
  fireRating values are all placeholders, so the REI channel is empty and
  this change produces zero verification diffs. The layer-2 normalizer gained
  the rename rule `ficr:hasREI -> ficr:hasActualREI` (counted in the report;
  expected 0 hits on the golden).
- **TBox fingerprint gate.** `tbox.py` hard-codes the fingerprint of the
  frozen TBox (2110 total triples; in the `ficr#` namespace: 241 classes,
  65 object properties, 42 datatype properties, 96 named individuals). Any
  mismatch at startup is a hard error: "onto/ficr.ttl is not the frozen
  v1.1.0 TBox".

### Repository

- **Archive restructure.** `IFCtoLBD_CLI_2_44_4.jar` and
  `lbd_to_ficr_converter.py` moved from `golden/` to
  `archive/legacy_pipeline/` (with a README explaining the superseded
  two-stage pipeline). `golden/` now contains only the three baseline data
  files (`.ifc`, LBD `.ttl`, FiCR `.ttl`); their paths are unchanged.
- `README.md` rewritten for the single-tool pipeline (new namespace, CLI,
  verification methodology).

## 1.0.0 — 2026-07-04

### Expected migrations (mandated by the task spec)

- **MIG-01 — pure ABox.** The old output embedded ~79 inline schema-stub
  triples (`owl:Class` / `owl:DatatypeProperty` / `owl:ObjectProperty` typings
  plus `rdfs:range`) so Protégé would type predicates without the TBox. The
  new output contains instance data only; the TBox is referenced via
  `owl:imports <https://w3id.org/ficr>`.
- **MIG-02 — ontology header retarget.** `owl:imports` now points to
  `https://w3id.org/ficr` (frozen TBox v1.1.0) instead of
  `https://w3id.org/bam/ficr`, and the `rdfs:comment` text was updated
  accordingly. The ontology node IRI pattern
  (`https://lbd.example.com/instances/<output-stem>`) is unchanged.
- **Namespace migration.** All `ficr:` terms moved from
  `https://w3id.org/bam/ficr#` to `https://w3id.org/ficr#`. Rename table
  applied during verification normalisation: `ficr:hasElementUsage ->
  ficr:hasPhysicalObjectFireSafetyRole`, `ficr:islocatedIn ->
  ficr:isLocatedIn`. Both renames matched **0 triples** in the golden output —
  the old converter never emitted either term.

### Expected improvements

- **IMP-01 — roof slab no longer double-typed as FloorSlab.** The old
  converter mapped every LBD type triple independently, so the roof slab
  (IfcSlab with PredefinedType=ROOF, typed `beo:Slab` + `beo:Slab-ROOF` in
  LBD) received both `ficr:FloorSlab` (via `beo:Slab`) and `ficr:RoofSlab`
  (via `beo:Slab-ROOF`). The new class mapping is keyed by
  (IFC entity, PredefinedType) and resolves each element to exactly one most
  specific class: `(IfcSlab, ROOF) -> ficr:RoofSlab`. Asserting both
  `ficr:FloorSlab` and `ficr:RoofSlab` on one instance was a contradiction
  (floor vs roof), not a feature. Affects 1 triple in the golden diff.

### Hardening (no diff impact on the golden dataset)

- **TBox term gate.** Every emitted `ficr:`/`bot:` term is validated against
  the frozen TBox (`onto/ficr.ttl` + `onto/bot.ttl`); an unknown term is a
  hard error (exit 4). The old converter silently dropped unknown mapped
  properties and never validated classes.
- **Schema gate.** Non-IFC2X3 input exits with code 3 and a message listing
  supported schemas, instead of undefined behaviour.

### Documented reverse-engineering findings (behaviour replicated, not changed)

- OmniClass classification data comes from Revit property-set strings
  (`'OmniClass Table 13 Category'`, `'Category Description'`); the IFC file
  contains no `IfcClassificationReference`/`IfcRelAssociatesClassification`
  entities, so the spec's stated channel is realised via these Psets.
- `bot:hasSubElement` combines element-to-element `IfcRelAggregates`
  (stair/roof decomposition, 11 triples) with host->filler pairs derived from
  `IfcRelVoidsElement`+`IfcRelFillsElement` (wall->door, roof->window,
  38 triples).
- Elements without direct spatial containment inherit containment from the
  spatial node their `ObjectPlacement` is relative to (stair flights,
  stringers, railings -> storey); openings are excluded. Placement chain only,
  no coordinates.
- Revit placeholder property values (string value equal to the property name,
  e.g. `'Area'='Area'`, `'FireRating'='FireRating'`) are skipped, matching the
  golden extraction; type-object property sets are not traversed.
