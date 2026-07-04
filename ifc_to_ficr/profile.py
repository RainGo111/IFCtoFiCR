"""Schema detection and per-schema profile registry.

All version-sensitive extraction data lives in a SchemaProfile; the core
(stage_a/stage_b) never mentions schema-specific names directly.
"""

import re
from dataclasses import dataclass, field

SUPPORTED_SCHEMAS = ("IFC2X3",)

_FILE_SCHEMA_RE = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'")


class UnsupportedSchemaError(Exception):
    def __init__(self, schema: str):
        self.schema = schema
        super().__init__(
            f"Unsupported IFC schema '{schema}'. "
            f"Supported schemas: {', '.join(SUPPORTED_SCHEMAS)}"
        )


class InvalidIfcError(Exception):
    pass


@dataclass(frozen=True)
class ElementRule:
    token: str        # beo-style token, e.g. 'Wall', 'StairFlight'
    namespace: str    # 'beo' | 'furn' | 'ifcowl'

    @property
    def kind(self) -> str:
        # URI kind word; rule verified across all element kinds in the golden
        # LBD file: the token lowercased ('StairFlight' -> 'stairflight').
        # Entities without a product vocabulary term fall back to the ifcOWL
        # pattern: 'ifcowl_ifcopeningelement'.
        if self.namespace == "ifcowl":
            return f"ifcowl_{self.token.lower()}"
        return self.token.lower()


@dataclass(frozen=True)
class SchemaProfile:
    schema_id: str
    # IFC class -> (URI kind word, bot class local name)
    spatial_classes: dict = field(default_factory=dict)
    # (parent IFC class, child IFC class) -> bot object property local name
    aggregation_map: dict = field(default_factory=dict)
    # IFC class (exact, no subtypes) -> ElementRule
    element_classes: dict = field(default_factory=dict)
    # IfcPropertySingleValue Name -> canonical props key
    pset_property_keys: dict = field(default_factory=dict)
    # IFC entity attribute name -> canonical props key
    attribute_keys: dict = field(default_factory=dict)


def detect_schema(ifc_path: str) -> str:
    """Read FILE_SCHEMA from the STEP header before any full parse."""
    with open(ifc_path, "r", encoding="latin-1", errors="replace") as fh:
        head = fh.read(8192)
    m = _FILE_SCHEMA_RE.search(head)
    if not m:
        raise InvalidIfcError(f"no FILE_SCHEMA header found in {ifc_path}")
    return m.group(1).upper()


def get_profile(schema_id: str) -> SchemaProfile:
    from ifc_to_ficr.profile_ifc2x3 import IFC2X3_PROFILE

    profiles = {"IFC2X3": IFC2X3_PROFILE}
    profile = profiles.get(schema_id.upper())
    if profile is None:
        raise UnsupportedSchemaError(schema_id)
    return profile
