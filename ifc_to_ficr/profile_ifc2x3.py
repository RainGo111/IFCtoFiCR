"""IFC2X3 schema profile — pure data, reverse-engineered from the golden files.

Sources of truth (golden baseline now under archive/legacy_pipeline/):
- URI kind words + typing tokens: Duplex_A_20110907.ttl instance URIs
  and beo:/furn:/ifc: rdf:type triples.
- Property source paths: the props: declaration blocks in the golden LBD file
  (rdfs:comment "IFC property set <Pset> property <key>") correlated with the
  IFCPROPERTYSINGLEVALUE entities in Duplex_A_20110907.ifc. Keys are
  matched by property NAME across all property sets (instance and type),
  exactly as IFCtoLBD did — e.g. isExternal aggregates Pset_WallCommon,
  Pset_SlabCommon, Pset_DoorCommon, Pset_WindowCommon, Pset_RoofCommon.
- Quantities (IfcElementQuantity) feed none of the consumed keys in the golden
  file (only 'GSA Space Areas' exists) and are therefore not extracted.
"""

from ifc_to_ficr.profile import ElementRule, SchemaProfile

# IFC class -> (URI kind word, bot class local name)
SPATIAL_CLASSES = {
    "IfcSite": ("site", "Site"),
    "IfcBuilding": ("building", "Building"),
    "IfcBuildingStorey": ("storey", "Storey"),
    "IfcSpace": ("space", "Space"),
}

# (relating class, related class) via IfcRelAggregates -> bot property
AGGREGATION_MAP = {
    ("IfcSite", "IfcBuilding"): "hasBuilding",
    ("IfcBuilding", "IfcBuildingStorey"): "hasStorey",
    ("IfcBuildingStorey", "IfcSpace"): "hasSpace",
}

# Exact entity classes (no subtype expansion). Tokens verified against the
# golden LBD file where instances exist; classes absent from the golden file
# (IfcWall, IfcCurtainWall, IfcColumn, IfcPlate) reuse the beo token from the
# old converter's class mapping with the same verified lowercasing rule.
ELEMENT_CLASSES = {
    "IfcWall": ElementRule("Wall", "beo"),
    "IfcWallStandardCase": ElementRule("Wall", "beo"),
    "IfcCurtainWall": ElementRule("CurtainWall", "beo"),
    "IfcSlab": ElementRule("Slab", "beo"),
    "IfcRoof": ElementRule("Roof", "beo"),
    "IfcCovering": ElementRule("Covering", "beo"),
    "IfcWindow": ElementRule("Window", "beo"),
    "IfcDoor": ElementRule("Door", "beo"),
    "IfcStair": ElementRule("Stair", "beo"),
    "IfcStairFlight": ElementRule("StairFlight", "beo"),
    "IfcRailing": ElementRule("Railing", "beo"),
    "IfcBeam": ElementRule("Beam", "beo"),
    "IfcFooting": ElementRule("Footing", "beo"),
    "IfcMember": ElementRule("Member", "beo"),
    "IfcColumn": ElementRule("Column", "beo"),
    "IfcPlate": ElementRule("Plate", "beo"),
    "IfcFurnishingElement": ElementRule("Furniture", "furn"),
    "IfcOpeningElement": ElementRule("IfcOpeningElement", "ifcowl"),
}

# IfcPropertySingleValue.Name -> canonical props key (consumed subset only)
PSET_PROPERTY_KEYS = {
    "Volume": "volume",                            # PSet_Revit_Dimensions
    "Length": "length",                            # PSet_Revit_(Type_)Dimensions
    "Width": "width",                              # PSet_Revit_* (3 psets)
    "Area": "area",                                # PSet_Revit_Dimensions
    "Thickness": "thickness",                      # PSet_Revit_* (3 psets)
    "Elevation": "elevation",                      # PSet_Revit_Constraints
    "Unbounded Height": "unboundedHeight",         # PSet_Revit_Dimensions
    "IsExternal": "isExternal",                    # Pset_*Common (5 psets)
    "LoadBearing": "loadBearing",                  # Pset_Wall/Slab/BeamCommon
    "OmniClass Table 13 Category": "omniClassTableCategory",  # PSet_Revit_Identity Data
    "Category Description": "categoryDescription",  # PSet_Revit_Other
    "FireRating": "fireRating",                    # Pset_DoorCommon
}

# Direct IFC entity attribute -> canonical props key
ATTRIBUTE_KEYS = {
    "GlobalId": "globalIdIfcRoot",
    "ObjectType": "objectTypeIfcObject",
}

IFC2X3_PROFILE = SchemaProfile(
    schema_id="IFC2X3",
    spatial_classes=SPATIAL_CLASSES,
    aggregation_map=AGGREGATION_MAP,
    element_classes=ELEMENT_CLASSES,
    pset_property_keys=PSET_PROPERTY_KEYS,
    attribute_keys=ATTRIBUTE_KEYS,
)
