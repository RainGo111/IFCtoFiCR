"""Namespaces shared by both stages.

All instance/vocabulary IRIs replicate the golden baseline LBD file
(archive/legacy_pipeline/Duplex_A_20110907.ttl) byte-for-byte.
"""

from rdflib import Namespace

INST = Namespace("https://lbd.example.com/")
BOT = Namespace("https://w3id.org/bot#")
BEO = Namespace("https://pi.pauwel.be/voc/buildingelement#")
FURN = Namespace("http://pi.pauwel.be/voc/furniture#")
MEP = Namespace("http://pi.pauwel.be/voc/distributionelement#")
PROPS = Namespace("http://lbd.arch.rwth-aachen.de/props#")
IFC2X3OWL = Namespace("https://standards.buildingsmart.org/IFC/DEV/IFC2x3/TC1/OWL#")
FICR = Namespace("https://w3id.org/ficr#")
OLD_FICR = Namespace("https://w3id.org/bam/ficr#")

FICR_ONTOLOGY_IRI = "https://w3id.org/ficr"
OLD_FICR_ONTOLOGY_IRI = "https://w3id.org/bam/ficr"


def props_property(key: str):
    """Predicate for a value sourced from an IfcPropertySet property."""
    return PROPS[f"{key}_property_simple"]


def props_attribute(key: str):
    """Predicate for a value sourced from a direct IFC entity attribute."""
    return PROPS[f"{key}_attribute_simple"]


def props_key(predicate) -> str | None:
    """Canonical key for a props: predicate, or None if not a props term."""
    s = str(predicate)
    if not s.startswith(str(PROPS)):
        return None
    local = s[len(str(PROPS)):]
    for suffix in ("_property_simple", "_attribute_simple"):
        if local.endswith(suffix):
            return local[: -len(suffix)]
    return local
