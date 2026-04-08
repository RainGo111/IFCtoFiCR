# ifc2FiCR

A two-stage pipeline for converting Industry Foundation Classes (IFC) building models into [FiCR ontology](https://w3id.org/bam/ficr#) instances (ABox), enabling semantic fire compliance and risk analysis on BIM data.

## Pipeline Overview

```
IFC (.ifc)  ──►  LBD Turtle (.ttl)  ──►  FiCR ABox (.ttl)
             ▲                        ▲
        IFCtoLBD (Java)        lbd_to_ficr_converter.py
```

| Stage | Tool | Input | Output |
|-------|------|-------|--------|
| 1. IFC → LBD | [IFCtoLBD](https://github.com/jyrkioraskari/IFCtoLBD) (v2.44.4) | `.ifc` | LBD Turtle (`.ttl`) with BOT topology, BEO elements, and PROPS properties |
| 2. LBD → FiCR | `lbd_to_ficr_converter.py` | LBD `.ttl` | FiCR ABox (`.ttl`) aligned with `ficr_tbox.ttl` |

## Prerequisites

- **Java 11+** — required by IFCtoLBD
- **Python 3.9+** with `rdflib >= 7.0.0`

```bash
pip install rdflib
```

## Project Structure

```
ifc2FiCR/
├── lbd_to_ficr_converter.py   # Stage 2: LBD → FiCR converter
├── FiCR_ontology/
│   └── ficr_tbox.ttl           # FiCR TBox (OWL 2, required by converter)
├── ifcs/                        # Input IFC files
├── lbd_outputs/                 # Stage 1 output: LBD Turtle files
├── ficr_outputs/                # Stage 2 output: FiCR ABox files
└── README.md
```

## Usage

### Stage 1: IFC → LBD

Download [IFCtoLBD CLI](https://github.com/jyrkioraskari/IFCtoLBD/releases) (JAR) and run:

```bash
java -jar IFCtoLBD_CLI_2_44_4.jar ifcs/your_model.ifc -l 3
```

The `-l 3` flag requests full geometric and property conversion. Move the output `.ttl` to `lbd_outputs/`.

### Stage 2: LBD → FiCR

**Single file:**

```bash
python lbd_to_ficr_converter.py lbd_outputs/your_model.ttl ficr_outputs/your_model_ficr.ttl
```

**Batch conversion:**

```bash
python lbd_to_ficr_converter.py --batch lbd_outputs ficr_outputs
```

The converter expects `FiCR_ontology/ficr_tbox.ttl` to be present alongside the script.

## What the Converter Does

The LBD → FiCR converter performs the following transformations:

1. **Class mapping** — Maps LBD building element types to FiCR classes:
   - `beo:Wall` → `ficr:Wall`, `beo:Slab` → `ficr:FloorSlab`, `beo:Door` → `ficr:Doorset`, etc.
   - Unmapped BEO/FURN/MEP types fall back to `bot:Element`

2. **Property mapping** — Converts `props:*` properties to `ficr:*` equivalents:
   - `props:area_property_simple` → `ficr:hasArea`
   - `props:thickness_property_simple` → `ficr:hasThickness`
   - `props:isExternal_property_simple` → `ficr:isExternal`
   - Full list in `_create_property_mapping()`

3. **Post-conversion inference** (no external reasoner needed):
   - Building classification → `ficr:MultiStoreyBuilding` / `ficr:SingleStoreyBuilding`
   - Storey classification → `ficr:BasementStorey` / `ficr:GroundAndAboveStorey` (by elevation)
   - Storey ordering → `ficr:isStoreyAbove` / `ficr:isStoreyBelow`
   - Wall reclassification → `ficr:ExternalWall` (where `isExternal = true`)
   - Space usage classification → via OmniClass codes or label text matching
   - Spatial adjacency → `bot:adjacentZone` (horizontal) / `bot:intersectsZone` (vertical)
   - Fire rating mapping → `ficr:hasREI` (from IFC `fireRating` property)

4. **BOT topology preservation** — Retains `bot:hasStorey`, `bot:hasSpace`, `bot:containsElement`, `bot:adjacentElement`, etc.

## Ontology Alignment

The converter is verified against **FiCR TBox v1.0.0** (`ficr_tbox.ttl`).

- Namespace: `https://w3id.org/bam/ficr#`
- Integrates [BOT](https://w3id.org/bot#) (Building Topology Ontology) for spatial structure
- All output instances include `owl:imports` pointing to the TBox IRI

## Tested IFC Models

| Model | Source | Elements | Triples |
|-------|--------|----------|---------|
| Duplex A (Architectural) | [buildingSMART Community Sample Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files) | ~250 | ~2,500 |
| Clinic Architectural | [buildingSMART Community Sample Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files) | ~150 | ~1,800 |

## Related Projects

- [FiCR Platform](https://github.com/RainGo111/FiCR) — Full-stack fire compliance analysis platform using FiCR ontology
- [IFCtoLBD](https://github.com/jyrkioraskari/IFCtoLBD) — IFC to Linked Building Data converter (upstream dependency)
- [buildingSMART Community Sample Test Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files) — IFC test models used for validation

## License

MIT
