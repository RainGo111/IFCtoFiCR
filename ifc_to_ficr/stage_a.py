"""Stage A: IFC -> in-memory BOT-conformant graph.

Replicates the extraction subset that IFCtoLBD produced, verified against
the golden baseline LBD file (archive/legacy_pipeline/Duplex_A_20110907.ttl):

- spatial tree (bot:Site/Building/Storey/Space, hasBuilding/hasStorey/hasSpace)
  from IfcRelAggregates,
- bot:containsElement from IfcRelContainedInSpatialStructure,
- bot:adjacentElement from IfcRelSpaceBoundary (channel confirmed present in
  the golden LBD file: 192 triples),
- bot:hasSubElement from element-to-element IfcRelAggregates,
- element typing: (IFC entity class, PredefinedType) recorded per element and
  mirrored as beo:/furn:/ifc: type triples for LBD comparability,
- the consumed props: subset (plain untyped string literals, exactly like the
  golden LBD file: booleans lowercase "true"/"false", numbers raw str(float)),
- rdfs:label from IfcRoot.Name.

No geometry, no quantities, no other property channels.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field

import ifcopenshell
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from ifc_to_ficr.guids import GuidError, ifc_guid_to_uuid
from ifc_to_ficr.namespaces import (
    BEO,
    BOT,
    FURN,
    IFC2X3OWL,
    INST,
    props_attribute,
    props_property,
)
from ifc_to_ficr.profile import SchemaProfile

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ElemType:
    ifc_class: str
    predefined_type: str | None

    @property
    def pair(self) -> tuple:
        return (self.ifc_class, self.predefined_type)


@dataclass
class StageAResult:
    graph: Graph
    typing: dict = field(default_factory=dict)   # element URIRef -> ElemType
    spatial: dict = field(default_factory=dict)  # spatial URIRef -> IFC class
    stats: dict = field(default_factory=dict)


def run(ifc_path: str, profile: SchemaProfile) -> StageAResult:
    ifc = ifcopenshell.open(ifc_path)
    graph = Graph()
    _bind(graph)
    result = StageAResult(graph=graph)
    result.stats = {
        "visited": Counter(),
        "skipped": [],
        "props_extracted": Counter(),
        "channel_counts": Counter(),
    }

    spatial_by_id = _extract_spatial(ifc, profile, result)
    elements_by_id = _extract_elements(ifc, profile, result)
    nodes_by_id = {**spatial_by_id, **elements_by_id}

    _extract_aggregations(ifc, profile, result, spatial_by_id, elements_by_id)
    _extract_fills(ifc, result, elements_by_id)
    _extract_containment(ifc, profile, result, spatial_by_id, elements_by_id)
    _extract_space_boundaries(ifc, result, spatial_by_id, elements_by_id)
    _extract_properties(ifc, profile, result, nodes_by_id)
    return result


def _bind(graph: Graph) -> None:
    graph.bind("bot", BOT)
    graph.bind("beo", BEO)
    graph.bind("furn", FURN)
    graph.bind("ifc", IFC2X3OWL)
    graph.bind("inst", INST)
    from ifc_to_ficr.namespaces import PROPS

    graph.bind("props", PROPS)


def _skip(result: StageAResult, what: str, reason: str) -> None:
    result.stats["skipped"].append((what, reason))
    log.warning("skipped %s: %s", what, reason)


def _node_uri(entity, kind: str) -> URIRef:
    return INST[f"{kind}_{ifc_guid_to_uuid(entity.GlobalId)}"]


def _label(entity) -> str | None:
    name = getattr(entity, "Name", None)
    return name if name else None


def _predefined_type(entity) -> str | None:
    try:
        value = entity.PredefinedType
    except AttributeError:
        return None
    return str(value) if value is not None else None


def _extract_spatial(ifc, profile, result) -> dict:
    nodes = {}
    for ifc_class, (kind, bot_local) in profile.spatial_classes.items():
        for entity in ifc.by_type(ifc_class, include_subtypes=False):
            result.stats["visited"][ifc_class] += 1
            try:
                uri = _node_uri(entity, kind)
            except GuidError as exc:
                _skip(result, f"{ifc_class} #{entity.id()}", str(exc))
                continue
            result.graph.add((uri, RDF.type, BOT[bot_local]))
            name = _label(entity)
            if name is not None:
                result.graph.add((uri, RDFS.label, Literal(name)))
            nodes[entity.id()] = uri
            result.spatial[uri] = ifc_class
            result.stats["channel_counts"][f"bot:{bot_local}"] += 1
    return nodes


def _extract_elements(ifc, profile, result) -> dict:
    nodes = {}
    for ifc_class, rule in profile.element_classes.items():
        for entity in ifc.by_type(ifc_class, include_subtypes=False):
            result.stats["visited"][ifc_class] += 1
            try:
                uri = _node_uri(entity, rule.kind)
            except GuidError as exc:
                _skip(result, f"{ifc_class} #{entity.id()}", str(exc))
                continue

            ptype = _predefined_type(entity)
            result.graph.add((uri, RDF.type, BOT.Element))
            if rule.namespace == "beo":
                result.graph.add((uri, RDF.type, BEO[rule.token]))
                if ptype is not None:
                    result.graph.add((uri, RDF.type, BEO[f"{rule.token}-{ptype}"]))
            elif rule.namespace == "furn":
                result.graph.add((uri, RDF.type, FURN[rule.token]))
            elif rule.namespace == "ifcowl":
                result.graph.add((uri, RDF.type, IFC2X3OWL[ifc_class]))

            name = _label(entity)
            if name is not None:
                result.graph.add((uri, RDFS.label, Literal(name)))
            nodes[entity.id()] = uri
            result.typing[uri] = ElemType(ifc_class, ptype)
            result.stats["channel_counts"]["bot:Element"] += 1
    return nodes


def _extract_aggregations(ifc, profile, result, spatial_by_id, elements_by_id) -> None:
    for rel in ifc.by_type("IfcRelAggregates"):
        try:
            parent = rel.RelatingObject
            children = rel.RelatedObjects or []
            if parent is None:
                continue
            for child in children:
                key = (parent.is_a(), child.is_a())
                if key in profile.aggregation_map:
                    prop = profile.aggregation_map[key]
                    parent_uri = spatial_by_id.get(parent.id())
                    child_uri = spatial_by_id.get(child.id())
                    if parent_uri is None or child_uri is None:
                        _skip(result, f"IfcRelAggregates #{rel.id()}",
                              f"untracked spatial node in {key}")
                        continue
                    result.graph.add((parent_uri, BOT[prop], child_uri))
                    result.stats["channel_counts"][f"bot:{prop}"] += 1
                elif parent.id() in elements_by_id and child.id() in elements_by_id:
                    result.graph.add((elements_by_id[parent.id()],
                                      BOT.hasSubElement,
                                      elements_by_id[child.id()]))
                    result.stats["channel_counts"]["bot:hasSubElement"] += 1
                # other aggregations (e.g. IfcProject->IfcSite) are out of scope
        except Exception as exc:  # defensive: never crash on a bad relationship
            _skip(result, f"IfcRelAggregates #{rel.id()}", repr(exc))


def _extract_fills(ifc, result, elements_by_id) -> None:
    """Host element -> filling element (wall->door, roof->window) as
    bot:hasSubElement, via IfcRelVoidsElement + IfcRelFillsElement.

    Verified against the golden LBD file: 38 of the 49 hasSubElement triples
    are host->filler pairs; the remainder come from IfcRelAggregates.
    """
    host_of_opening = {}
    for rel in ifc.by_type("IfcRelVoidsElement"):
        try:
            if rel.RelatedOpeningElement is not None and rel.RelatingBuildingElement is not None:
                host_of_opening[rel.RelatedOpeningElement.id()] = rel.RelatingBuildingElement
        except Exception as exc:
            _skip(result, f"IfcRelVoidsElement #{rel.id()}", repr(exc))
    for rel in ifc.by_type("IfcRelFillsElement"):
        try:
            opening = rel.RelatingOpeningElement
            filler = rel.RelatedBuildingElement
            host = host_of_opening.get(opening.id()) if opening else None
            if host is None or filler is None:
                continue
            host_uri = elements_by_id.get(host.id())
            filler_uri = elements_by_id.get(filler.id())
            if host_uri is None or filler_uri is None:
                _skip(result, f"IfcRelFillsElement #{rel.id()}",
                      "untracked host or filler")
                continue
            result.graph.add((host_uri, BOT.hasSubElement, filler_uri))
            result.stats["channel_counts"]["bot:hasSubElement"] += 1
        except Exception as exc:
            _skip(result, f"IfcRelFillsElement #{rel.id()}", repr(exc))


def _extract_containment(ifc, profile, result, spatial_by_id, elements_by_id) -> None:
    contained_ids = set()
    for rel in ifc.by_type("IfcRelContainedInSpatialStructure"):
        try:
            structure = rel.RelatingStructure
            container_uri = spatial_by_id.get(structure.id()) if structure else None
            if container_uri is None:
                _skip(result, f"IfcRelContainedInSpatialStructure #{rel.id()}",
                      "untracked container")
                continue
            for element in rel.RelatedElements or []:
                element_uri = elements_by_id.get(element.id())
                if element_uri is None:
                    _skip(result, f"{element.is_a()} #{element.id()}",
                          "contained element has no profile rule")
                    continue
                result.graph.add((container_uri, BOT.containsElement, element_uri))
                contained_ids.add(element.id())
                result.stats["channel_counts"]["bot:containsElement"] += 1
        except Exception as exc:
            _skip(result, f"IfcRelContainedInSpatialStructure #{rel.id()}", repr(exc))

    # Placement-derived containment, reverse-engineered from the golden LBD:
    # elements without direct containment whose ObjectPlacement is relative to
    # a spatial node's placement are contained in that node (stair flights,
    # stringers and railings -> storey). The roof slab, placed relative to the
    # roof element, correctly stays uncontained. Placement chain only — no
    # coordinates are read.
    spatial_by_placement = {}
    for entity_id, uri in spatial_by_id.items():
        placement = getattr(ifc.by_id(entity_id), "ObjectPlacement", None)
        if placement is not None:
            spatial_by_placement[placement.id()] = uri
    for entity_id, uri in elements_by_id.items():
        if entity_id in contained_ids:
            continue
        elem = result.typing.get(uri)
        # openings never receive containment in the golden LBD file, even
        # when placed relative to a space
        if elem is not None and profile.element_classes[elem.ifc_class].namespace == "ifcowl":
            continue
        try:
            placement = getattr(ifc.by_id(entity_id), "ObjectPlacement", None)
            parent = getattr(placement, "PlacementRelTo", None) if placement else None
            container_uri = spatial_by_placement.get(parent.id()) if parent else None
            if container_uri is not None:
                result.graph.add((container_uri, BOT.containsElement, uri))
                result.stats["channel_counts"]["bot:containsElement"] += 1
        except Exception as exc:
            _skip(result, f"placement containment #{entity_id}", repr(exc))


def _extract_space_boundaries(ifc, result, spatial_by_id, elements_by_id) -> None:
    seen = set()
    for rel in ifc.by_type("IfcRelSpaceBoundary"):
        try:
            space = rel.RelatingSpace
            element = rel.RelatedBuildingElement
            if element is None:
                result.stats["channel_counts"]["boundary:no-element"] += 1
                continue
            space_uri = spatial_by_id.get(space.id()) if space else None
            element_uri = elements_by_id.get(element.id())
            if space_uri is None or element_uri is None:
                result.stats["channel_counts"]["boundary:untracked-target"] += 1
                continue
            if (space_uri, element_uri) not in seen:
                seen.add((space_uri, element_uri))
                result.graph.add((space_uri, BOT.adjacentElement, element_uri))
                result.stats["channel_counts"]["bot:adjacentElement"] += 1
        except Exception as exc:
            _skip(result, f"IfcRelSpaceBoundary #{rel.id()}", repr(exc))


def _property_sets(entity):
    """IfcPropertySets attached directly to the instance.

    Type psets (IfcRelDefinesByType -> HasPropertySets) are intentionally NOT
    traversed: the golden LBD file carries no values from them — door/window/
    furniture style placeholders like 'Area'='Area' and 'FireRating'=
    'FireRating' are absent, while all consumed values (incl. the 'PSet_Revit_
    Type_*'-named psets) are attached per instance by the Revit exporter.
    """
    psets = []
    for rel in getattr(entity, "IsDefinedBy", None) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            definition = rel.RelatingPropertyDefinition
            if definition is not None and definition.is_a("IfcPropertySet"):
                psets.append(definition)
    return psets


def _value_to_string(value) -> str:
    # Replicates the golden LBD literal forms: lowercase booleans, raw floats.
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _extract_properties(ifc, profile, result, nodes_by_id) -> None:
    for entity_id, uri in nodes_by_id.items():
        entity = ifc.by_id(entity_id)
        try:
            for attribute, key in profile.attribute_keys.items():
                value = getattr(entity, attribute, None)
                if value:
                    result.graph.add((uri, props_attribute(key),
                                      Literal(_value_to_string(value))))
                    result.stats["props_extracted"][key] += 1

            for pset in _property_sets(entity):
                for prop in pset.HasProperties or []:
                    if not prop.is_a("IfcPropertySingleValue"):
                        continue
                    key = profile.pset_property_keys.get(prop.Name)
                    if key is None or prop.NominalValue is None:
                        continue
                    value = prop.NominalValue.wrappedValue
                    # Revit placeholder values (value string == property name,
                    # e.g. 'Area'='Area', 'FireRating'='FireRating') are absent
                    # from the golden LBD file — skip them.
                    if isinstance(value, str) and value == prop.Name:
                        result.stats["channel_counts"]["props:placeholder-skipped"] += 1
                        continue
                    result.graph.add((uri, props_property(key),
                                      Literal(_value_to_string(value))))
                    result.stats["props_extracted"][key] += 1
        except Exception as exc:
            _skip(result, f"properties of {entity.is_a()} #{entity_id}", repr(exc))
