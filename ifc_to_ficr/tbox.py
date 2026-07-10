"""Load the FiCR TBox (+ BOT) and validate emitted terms.

FiCR_ontology/ficr.ttl only owl:imports BOT and does not re-declare bot:
terms, so bot.ttl must be loaded alongside it — otherwise every bot:
pass-through triple (containsElement, adjacentZone, ...) would fail the
term gate.
"""

import logging
from dataclasses import dataclass

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ifc_to_ficr.namespaces import BOT, FICR

log = logging.getLogger(__name__)

# Reference fingerprint of the pinned TBox (FiCR_ontology/ficr.ttl v1.1.1).
# Counts of typed terms are restricted to the https://w3id.org/ficr#
# namespace; total_triples is the whole file. A mismatch only logs a WARNING
# (the TBox is under active development); output safety is enforced by the
# mapping-target validation and the emitted-term gate below.
PINNED_TBOX_FINGERPRINT = {
    "total_triples": 2098,
    "classes": 241,
    "object_properties": 62,
    "datatype_properties": 40,
    "named_individuals": 96,
}
PINNED_TBOX_VERSION = "1.1.1"


class TermValidationError(Exception):
    pass


@dataclass
class ValidationSets:
    classes: set
    object_properties: set
    data_properties: set
    version: str = "unknown"

    @property
    def properties(self) -> set:
        return self.object_properties | self.data_properties


def _check_fingerprint(ficr_graph: Graph, tbox_path: str) -> None:
    ns = str(FICR)

    def count(cls) -> int:
        return len({s for s in ficr_graph.subjects(RDF.type, cls)
                    if isinstance(s, URIRef) and str(s).startswith(ns)})

    actual = {
        "total_triples": len(ficr_graph),
        "classes": count(OWL.Class),
        "object_properties": count(OWL.ObjectProperty),
        "datatype_properties": count(OWL.DatatypeProperty),
        "named_individuals": count(OWL.NamedIndividual),
    }
    if actual != PINNED_TBOX_FINGERPRINT:
        detail = ", ".join(
            f"{key}={actual[key]} (pinned {PINNED_TBOX_FINGERPRINT[key]})"
            for key in PINNED_TBOX_FINGERPRINT
            if actual[key] != PINNED_TBOX_FINGERPRINT[key]
        )
        log.warning(
            "%s differs from the pinned v%s TBox fingerprint (%s) — the TBox "
            "has changed; term-level validation still applies",
            tbox_path, PINNED_TBOX_VERSION, detail,
        )


def _tbox_version(ficr_graph: Graph) -> str:
    value = ficr_graph.value(URIRef("https://w3id.org/ficr"), OWL.versionInfo)
    return str(value) if value is not None else "unknown"


def load_validation_sets(tbox_path: str, bot_path: str) -> ValidationSets:
    graph = Graph()
    graph.parse(tbox_path, format="turtle")
    _check_fingerprint(graph, tbox_path)
    version = _tbox_version(graph)
    graph.parse(bot_path, format="turtle")

    classes = set(graph.subjects(RDF.type, OWL.Class))
    classes |= set(graph.subjects(RDF.type, RDFS.Class))
    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    data_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))

    sets = ValidationSets(classes, object_properties, data_properties, version)
    # Sanity: both vocabularies actually loaded.
    for probe, what in ((FICR.hasID, "ficr"), (BOT.containsElement, "bot")):
        if probe not in sets.properties:
            raise TermValidationError(
                f"{what} vocabulary incomplete: {probe} not declared "
                f"(loaded {tbox_path} + {bot_path})"
            )
    log.info(
        "TBox v%s loaded: %d classes, %d object properties, %d data properties",
        version, len(classes), len(object_properties), len(data_properties),
    )
    return sets


def validate_graph_terms(graph: Graph, validation: ValidationSets) -> None:
    """Every ficr:/bot: term used in the ABox must exist in the TBox."""
    known = validation.classes | validation.properties
    offenders = set()
    for s, p, o in graph:
        for term in (s, p, o):
            if not isinstance(term, URIRef):
                continue
            t = str(term)
            if (t.startswith(str(FICR)) or t.startswith(str(BOT))) and term not in known:
                offenders.add(term)
    if offenders:
        listing = "\n  ".join(sorted(str(o) for o in offenders))
        raise TermValidationError(
            f"{len(offenders)} emitted term(s) not present in the TBox:\n  {listing}"
        )
