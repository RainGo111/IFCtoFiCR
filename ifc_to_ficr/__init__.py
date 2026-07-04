"""ifc_to_ficr — single-tool IFC (IFC2X3) to FiCR RDF ABox converter.

Replaces the two-stage IFCtoLBD (Java) + lbd_to_ficr_converter.py pipeline.
Stage A extracts a BOT-conformant graph from the IFC; Stage B maps it to a
FiCR ABox conformant to the frozen TBox (https://w3id.org/ficr#, v1.1.0).
"""

__version__ = "1.2.1"
