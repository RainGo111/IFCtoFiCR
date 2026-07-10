"""Stage B: BOT-conformant graph -> FiCR ABox.

Faithful port of archive/legacy_pipeline/lbd_to_ficr_converter.py (semantics
identical), with:
- class-mapping keys swapped from beo:* CURIEs to (IFC entity, PredefinedType)
  pairs fed by the Stage A typing channel,
- property-mapping keys swapped to the profile's canonical props keys,
- all emitted vocabulary retargeted to https://w3id.org/ficr# (TBox v1.1.0),
- every emitted ficr:/bot: term validated against the TBox (hard error; the
  old converter silently dropped unknown terms instead),
- the old inline schema-stub block dropped (pure ABox output).

Pass order preserved from the old convert(): sweep -> _classify_building ->
_classify_storeys -> _link_storeys -> _classify_members -> _classify_spaces ->
_classify_walls -> _map_fire_ratings -> _infer_space_adjacency.
"""

import datetime
import logging
import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from ifc_to_ficr import __version__
from ifc_to_ficr.namespaces import (
    BOT,
    FICR,
    FICR_ONTOLOGY_IRI,
    INST,
    PROPS,
    props_attribute,
    props_key,
    props_property,
)
from ifc_to_ficr.stage_a import StageAResult
from ifc_to_ficr.tbox import TermValidationError, ValidationSets, validate_graph_terms

log = logging.getLogger(__name__)

# (IFC entity class, PredefinedType) -> ficr class local name.
# None as PredefinedType is the wildcard (matches any, incl. absent).
# Ported from the old beo:* mapping: beo:Wall -> ficr:Wall etc.
# IfcMember is intentionally absent: disambiguated in _classify_members().
CLASS_MAPPING = {
    ("IfcWall", None): "Wall",
    ("IfcWallStandardCase", None): "Wall",
    ("IfcCurtainWall", None): "Wall",            # no ficr:CurtainWall
    ("IfcSlab", "FLOOR"): "FloorSlab",
    ("IfcSlab", "ROOF"): "RoofSlab",
    ("IfcSlab", "LANDING"): "FloorSlab",         # stair landing slab
    ("IfcSlab", None): "FloorSlab",
    ("IfcRoof", None): "RoofSlab",
    ("IfcCovering", "CEILING"): "Ceiling",
    ("IfcCovering", None): "Ceiling",
    ("IfcWindow", None): "Window",
    ("IfcDoor", None): "Doorset",
    ("IfcStair", None): "Stair",
    ("IfcStairFlight", None): "StairFlight",
    ("IfcRailing", "NOTDEFINED"): "Railing",
    ("IfcRailing", None): "Railing",
    ("IfcBeam", None): "Beam",
    ("IfcFooting", "STRIP_FOOTING"): "WallFoundation",
    ("IfcFooting", None): "WallFoundation",
    ("IfcColumn", None): "Column",
    # IfcPlate intentionally unmapped -> bot:Element: in Revit exports plates
    # are curtain-wall glass panels (like mullions), not structural slabs.
    # The old Plate->FloorSlab rule misclassified them (see CHANGELOG 1.2.1).
    ("IfcFurnishingElement", None): "Furnishings",
    ("IfcOpeningElement", None): "Opening",
}

# canonical props key -> ficr property local name (the 10 consumed keys)
PROPERTY_MAPPING = {
    "globalIdIfcRoot": "hasID",
    "volume": "hasVolume",
    "length": "hasLength",
    "width": "hasWidth",
    "area": "hasArea",
    "thickness": "hasThickness",
    "elevation": "hasElevation",
    "unboundedHeight": "hasStoreyHeight",
    "isExternal": "isExternal",
    "loadBearing": "isLoadBearing",
}

# Layer 1 — OmniClass prefix rules (ported verbatim; sorted longest-first)
OMNICLASS_RULES = [
    ("13-11 19", "RoomSpace", "Kitchen"),
    ("13-11", "RoomSpace", "HabitableRoom"),
    ("13-15", "RoomSpace", "HabitableRoom"),
    ("13-41 41", "RoomSpace", "HabitableRoom"),
    ("13-41", "RoomSpace", "Bathroom"),
    ("13-51 24 11", "RoomSpace", "HabitableRoom"),
    ("13-51 24", "RoomSpace", "HabitableRoom"),
    ("13-51 21", "RoomSpace", "HabitableRoom"),
    ("13-51", "RoomSpace", "HabitableRoom"),
    ("13-75", "RoomSpace", "ServiceUsage"),
    ("13-81 31", "RoomSpace", "ServiceUsage"),
    ("13-81", "RoomSpace", "ServiceUsage"),
    ("13-85 21", "StairSpace", "CirculationUsage"),
    ("13-85", "RoomSpace", "CirculationUsage"),
]
OMNICLASS_RULES.sort(key=lambda r: len(r[0]), reverse=True)

# Layer 2 — keyword rules over categoryDescription (ported verbatim)
KEYWORD_RULES = [
    (["stair", "stairway"], "StairSpace", "CirculationUsage"),
    (["bathroom", "toilet", "wc"], "RoomSpace", "Bathroom"),
    (["kitchen"], "RoomSpace", "Kitchen"),
    (["bedroom", "living"], "RoomSpace", "HabitableRoom"),
    (["corridor", "hallway", "hall", "foyer"], "RoomSpace", "CirculationUsage"),
    (["service", "utility", "plant"], "RoomSpace", "ServiceUsage"),
    (["roof"], "RoofSpace", "ServiceUsage"),
    (["shaft", "duct"], "ShaftSpace", "ServiceUsage"),
    (["lift", "elevator"], "LiftShaft", "ServiceUsage"),
    (["atrium"], "AtriumSpace", "HabitableRoom"),
    (["balcony"], "BalconySpace", "HabitableRoom"),
    (["cavity", "void"], "CavitySpace", "ServiceUsage"),
]


class StageBConverter:
    def __init__(self, source: StageAResult, validation: ValidationSets):
        self.source = source
        self.source_graph = source.graph
        self.typing = source.typing
        self.validation = validation
        self.target_graph = Graph()
        self.stats = {
            "total_triples": 0,
            "converted_properties": 0,
            "preserved_relations": 0,
            "unmapped_properties": 0,
            "class_counts": {},
            "buildings_classified": 0,
            "storeys_classified": 0,
            "spaces_classified_omniclass": 0,
            "spaces_classified_text": 0,
            "spaces_unclassified": 0,
        }
        self._validate_mapping_targets()

    def _validate_mapping_targets(self) -> None:
        """Fail fast if any mapping target is missing from the frozen TBox."""
        missing = [
            f"ficr:{local}" for local in set(CLASS_MAPPING.values())
            if FICR[local] not in self.validation.classes
        ]
        missing += [
            f"ficr:{local}" for local in set(PROPERTY_MAPPING.values())
            if FICR[local] not in self.validation.properties
        ]
        if missing:
            raise TermValidationError(
                f"mapping targets not in TBox: {', '.join(sorted(missing))}"
            )

    # ── main flow (pass order identical to the old convert()) ──────────────

    def convert(self) -> Graph:
        self._setup_namespaces()
        for subject in set(self.source_graph.subjects()):
            if str(subject).startswith(str(PROPS)):
                continue
            for mapped in self._map_types(subject):
                self.target_graph.add((subject, RDF.type, mapped))
                local = str(mapped).rsplit("#", 1)[-1]
                self.stats["class_counts"][local] = \
                    self.stats["class_counts"].get(local, 0) + 1
            for prop, value in self.source_graph.predicate_objects(subject):
                if prop == RDF.type:
                    continue
                converted = self._convert_property(prop, value)
                if converted:
                    new_prop, new_value = converted
                    self.target_graph.add((subject, new_prop, new_value))

        self._classify_building()
        self._classify_storeys()
        self._link_storeys()
        self._classify_members()
        self._classify_spaces()
        self._classify_walls()
        self._map_fire_ratings()
        self._infer_space_adjacency()

        self.stats["total_triples"] = len(self.target_graph)
        validate_graph_terms(self.target_graph, self.validation)
        return self.target_graph

    def _setup_namespaces(self) -> None:
        self.target_graph.bind("ficr", FICR)
        self.target_graph.bind("bot", BOT)
        self.target_graph.bind("rdfs", RDFS)
        self.target_graph.bind("xsd", XSD)
        self.target_graph.bind("owl", OWL)

    # ── typing ──────────────────────────────────────────────────────────────

    def _map_types(self, subject) -> set:
        """FiCR classes for a subject.

        Elements: (IFC entity, PredefinedType) lookup with wildcard fallback;
        unmapped element classes downgrade to bot:Element (old behaviour for
        beo:Member and any unknown beo/furn/mep class). bot: types from the
        source graph (bot:Element, bot:Site, ...) pass through unchanged.
        """
        mapped = set()
        for obj_type in self.source_graph.objects(subject, RDF.type):
            if str(obj_type).startswith(str(BOT)):
                mapped.add(obj_type)
        elem = self.typing.get(subject)
        if elem is not None:
            local = CLASS_MAPPING.get(elem.pair) or CLASS_MAPPING.get((elem.ifc_class, None))
            if local is not None:
                mapped.add(FICR[local])
            else:
                mapped.add(BOT.Element)
        return mapped

    # ── properties (old _convert_property / _convert_data_value) ───────────

    def _convert_data_value(self, value) -> Literal:
        value_str = str(value)
        if value_str.lower() in ("true", "false"):
            return Literal(value_str.lower() == "true", datatype=XSD.boolean)
        try:
            num = float(value_str)
            return Literal(f"{num:.3f}", datatype=XSD.decimal)
        except ValueError:
            pass
        return Literal(value_str, datatype=XSD.string)

    def _convert_property(self, prop, value):
        key = props_key(prop)
        if key is not None and key in PROPERTY_MAPPING:
            ficr_prop = FICR[PROPERTY_MAPPING[key]]
            if ficr_prop in self.validation.data_properties:
                self.stats["converted_properties"] += 1
                return ficr_prop, self._convert_data_value(value)
            if ficr_prop in self.validation.object_properties:
                self.stats["preserved_relations"] += 1
                return ficr_prop, value
        if prop in self.validation.object_properties:
            self.stats["preserved_relations"] += 1
            return prop, value
        if prop in self.validation.data_properties:
            self.stats["converted_properties"] += 1
            return prop, self._convert_data_value(value)
        if prop == RDFS.label:
            return prop, value
        self.stats["unmapped_properties"] += 1
        return None

    # ── classification passes (ported verbatim) ────────────────────────────

    def _classify_building(self) -> None:
        for building in list(self.target_graph.subjects(RDF.type, BOT.Building)):
            storeys = list(self.target_graph.objects(building, BOT.hasStorey))
            n = len(storeys)
            if n >= 2:
                self.target_graph.remove((building, RDF.type, BOT.Building))
                self.target_graph.add((building, RDF.type, FICR.MultiStoreyBuilding))
                self.stats["buildings_classified"] += 1
            elif n == 1:
                self.target_graph.remove((building, RDF.type, BOT.Building))
                self.target_graph.add((building, RDF.type, FICR.SingleStoreyBuilding))
                self.stats["buildings_classified"] += 1

            if n > 0:
                self.target_graph.add((building, FICR.hasNumberOfStoreys,
                                       Literal(n, datatype=XSD.integer)))

            storey_data = []
            for s in storeys:
                elev = self.target_graph.value(s, FICR.hasElevation)
                height = self.target_graph.value(s, FICR.hasStoreyHeight)
                try:
                    e = float(str(elev)) if elev is not None else None
                except (ValueError, TypeError):
                    e = None
                try:
                    h = float(str(height)) if height is not None else None
                except (ValueError, TypeError):
                    h = None
                storey_data.append((s, e, h))

            tops = [e + h for _, e, h in storey_data if e is not None and h is not None]
            elevs = [e for _, e, _ in storey_data if e is not None]
            if tops and elevs:
                self.target_graph.add((building, FICR.hasBuildingHeight,
                                       Literal(f"{max(tops) - min(elevs):.3f}",
                                               datatype=XSD.decimal)))

            above_ground = [(s, e, h) for s, e, h in storey_data
                            if e is not None and e >= 0.0]
            if above_ground:
                above_ground.sort(key=lambda x: x[1])
                _, top_elev, top_height = above_ground[-1]
                self.target_graph.add((building, FICR.hasTopStoreyFloorHeight,
                                       Literal(f"{top_elev:.3f}", datatype=XSD.decimal)))
                if top_height is not None:
                    self.target_graph.add((building, FICR.hasTopStoreyHeight,
                                           Literal(f"{top_height:.3f}",
                                                   datatype=XSD.decimal)))

            total_area = 0.0
            has_any_area = False
            for s in storeys:
                for space in self.target_graph.objects(s, BOT.hasSpace):
                    area_val = self.target_graph.value(space, FICR.hasArea)
                    if area_val is not None:
                        try:
                            total_area += float(str(area_val))
                            has_any_area = True
                        except (ValueError, TypeError):
                            pass
            if has_any_area:
                self.target_graph.add((building, FICR.hasCombinedGrossFloorArea,
                                       Literal(f"{total_area:.3f}",
                                               datatype=XSD.decimal)))

    def _classify_storeys(self) -> None:
        for storey in list(self.target_graph.subjects(RDF.type, BOT.Storey)):
            elev_val = self.target_graph.value(storey, FICR.hasElevation)
            if elev_val is None:
                continue
            try:
                elev = float(str(elev_val))
            except (ValueError, TypeError):
                continue
            self.target_graph.remove((storey, RDF.type, BOT.Storey))
            if elev >= 0.0:
                self.target_graph.add((storey, RDF.type, FICR.GroundAndAboveStorey))
                self.target_graph.add((storey, FICR.isAboveGround,
                                       Literal(True, datatype=XSD.boolean)))
            else:
                self.target_graph.add((storey, RDF.type, FICR.BasementStorey))
                self.target_graph.add((storey, FICR.isAboveGround,
                                       Literal(False, datatype=XSD.boolean)))
            self.stats["storeys_classified"] += 1

    def _link_storeys(self) -> None:
        link_count = 0
        for building in self.target_graph.subjects(RDF.type, FICR.MultiStoreyBuilding):
            storeys = list(self.target_graph.objects(building, BOT.hasStorey))
            if len(storeys) < 2:
                continue
            storey_elev = []
            for s in storeys:
                elev = self.target_graph.value(s, FICR.hasElevation)
                if elev is not None:
                    try:
                        storey_elev.append((s, float(str(elev))))
                    except (ValueError, TypeError):
                        pass
            storey_elev.sort(key=lambda x: x[1])
            for i in range(len(storey_elev) - 1):
                lower, _ = storey_elev[i]
                upper, _ = storey_elev[i + 1]
                self.target_graph.add((upper, FICR.isStoreyAbove, lower))
                self.target_graph.add((lower, FICR.isStoreyBelow, upper))
                link_count += 1
        self.stats["storey_links"] = link_count

    def _classify_members(self) -> None:
        stair = mullion = beam = 0
        obj_type_prop = props_attribute("objectTypeIfcObject")
        members = [uri for uri, elem in self.typing.items()
                   if elem.ifc_class == "IfcMember"]
        for subject in members:
            label = str(self.source_graph.value(subject, RDFS.label) or "").lower()
            obj_type = str(self.source_graph.value(subject, obj_type_prop) or "").lower()
            if "stair" in label or "stringer" in obj_type:
                self.target_graph.remove((subject, RDF.type, BOT.Element))
                self.target_graph.add((subject, RDF.type, FICR.StairFlight))
                stair += 1
            elif "mullion" in label:
                mullion += 1
            else:
                self.target_graph.remove((subject, RDF.type, BOT.Element))
                self.target_graph.add((subject, RDF.type, FICR.Beam))
                beam += 1
        self.stats["members_stair"] = stair
        self.stats["members_mullion"] = mullion
        self.stats["members_beam"] = beam

    def _classify_spaces(self) -> None:
        omni_prop = props_property("omniClassTableCategory")
        desc_prop = props_property("categoryDescription")

        for space in list(self.target_graph.subjects(RDF.type, BOT.Space)):
            subclass_local = None
            usage_local = None

            omni_val = self.source_graph.value(space, omni_prop)
            if omni_val is not None:
                omni_str = str(omni_val).strip()
                for prefix, sc, us in OMNICLASS_RULES:
                    if omni_str.startswith(prefix):
                        subclass_local, usage_local = sc, us
                        break

            matched_layer = "omniclass" if subclass_local is not None else None

            if subclass_local is None:
                desc_val = self.source_graph.value(space, desc_prop)
                if desc_val is not None:
                    desc_lower = str(desc_val).lower()
                    for keywords, sc, us in KEYWORD_RULES:
                        if any(kw in desc_lower for kw in keywords):
                            subclass_local, usage_local = sc, us
                            matched_layer = "text"
                            break

            if subclass_local is not None:
                self.target_graph.remove((space, RDF.type, BOT.Space))
                self.target_graph.add((space, RDF.type, FICR[subclass_local]))
                self.target_graph.add((space, FICR.hasSpaceUsage, FICR[usage_local]))
                if matched_layer == "omniclass":
                    self.stats["spaces_classified_omniclass"] += 1
                else:
                    self.stats["spaces_classified_text"] += 1
            else:
                self.stats["spaces_unclassified"] += 1

    def _classify_walls(self) -> None:
        count = 0
        for wall in list(self.target_graph.subjects(RDF.type, FICR.Wall)):
            ext_val = self.target_graph.value(wall, FICR.isExternal)
            if ext_val is not None and str(ext_val).lower() == "true":
                self.target_graph.remove((wall, RDF.type, FICR.Wall))
                self.target_graph.add((wall, RDF.type, FICR.ExternalWall))
                count += 1
        self.stats["walls_external"] = count

    @staticmethod
    def _parse_fire_rating(raw: str):
        if not raw:
            return None
        raw = raw.strip()
        if raw.lower() in ("none", "fire rating", ""):
            return None
        m = re.match(r"(\d+)\s*[Hh][Rr]", raw)
        if m:
            return int(m.group(1)) * 60
        m = re.search(r"[RE]*I(\d+)", raw)
        if m:
            return int(m.group(1))
        m = re.match(r"(\d+)\s*min", raw, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    def _map_fire_ratings(self) -> None:
        # Emits ficr:hasActualREI (measured/known resistance); ficr:hasREI was
        # removed from the frozen TBox v1.1.0.
        fire_prop = props_property("fireRating")
        count = 0
        for subject in set(self.source_graph.subjects(fire_prop)):
            raw_val = str(self.source_graph.value(subject, fire_prop) or "")
            minutes = self._parse_fire_rating(raw_val)
            if minutes is not None:
                self.target_graph.add((subject, FICR.hasActualREI,
                                       Literal(minutes, datatype=XSD.integer)))
                count += 1
        self.stats["fire_ratings_mapped"] = count

    def _infer_space_adjacency(self) -> None:
        spaces = list(self.source_graph.subjects(RDF.type, BOT.Space))
        space_elements = {
            space: set(self.source_graph.objects(space, BOT.adjacentElement))
            for space in spaces
        }

        def has_type_containing(elem, keywords) -> bool:
            for t in self.source_graph.objects(elem, RDF.type):
                local = str(t).split("#")[-1].split("/")[-1]
                if any(k in local for k in keywords):
                    return True
            return False

        horiz = vert = party = 0
        for i, sp_a in enumerate(spaces):
            for sp_b in spaces[i + 1:]:
                shared = space_elements.get(sp_a, set()) & space_elements.get(sp_b, set())
                if not shared:
                    continue
                has_wall_or_door = any(
                    has_type_containing(e, ("Wall", "Door")) for e in shared
                )
                has_slab = any(
                    has_type_containing(e, ("Slab", "Floor", "Covering")) for e in shared
                )
                lbl_a = str(self.source_graph.value(sp_a, RDFS.label) or "")
                lbl_b = str(self.source_graph.value(sp_b, RDFS.label) or "")
                cross_unit = bool(lbl_a and lbl_b and lbl_a[0] != lbl_b[0])

                if has_wall_or_door:
                    self.target_graph.add((sp_a, BOT.adjacentZone, sp_b))
                    self.target_graph.add((sp_b, BOT.adjacentZone, sp_a))
                    horiz += 1
                    if cross_unit:
                        party += 1
                elif has_slab:
                    self.target_graph.add((sp_a, BOT.intersectsZone, sp_b))
                    self.target_graph.add((sp_b, BOT.intersectsZone, sp_a))
                    vert += 1

        self.stats["adjacency_horizontal"] = horiz
        self.stats["adjacency_party_wall"] = party
        self.stats["adjacency_vertical"] = vert


def run(source: StageAResult, validation: ValidationSets):
    converter = StageBConverter(source, validation)
    graph = converter.convert()
    return graph, converter.stats


def add_ontology_header(graph: Graph, output_stem: str) -> None:
    """owl:Ontology node with owl:imports, replicating the old IRI pattern."""
    ontology_iri = URIRef(f"{INST}instances/{output_stem}")
    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((ontology_iri, RDFS.comment, Literal(
        "FiCR ABox — converted from IFC by ifc_to_ficr. "
        "Import the FiCR TBox (https://w3id.org/ficr) for full reasoning.",
        lang="en")))
    graph.add((ontology_iri, OWL.imports, URIRef(FICR_ONTOLOGY_IRI)))


def serialize(graph: Graph, output_stem: str, source_ifc_name: str,
              tbox_version: str = "unknown") -> str:
    header = (
        f"# FiCR ABox Instance Data — {output_stem}\n"
        f"# TBox: {FICR_ONTOLOGY_IRI}  (FiCR_ontology/ficr.ttl v{tbox_version})\n"
        f"# Source IFC: {source_ifc_name}\n"
        f"# Generated by: ifc_to_ficr v{__version__} "
        f"on {datetime.date.today().isoformat()}\n"
        f"#\n"
    )
    return header + graph.serialize(format="turtle")
