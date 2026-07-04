"""IFC GlobalId (22-char base64) -> canonical dashed UUID.

Replicates the golden LBD URI local names: the compressed GlobalId is
decompressed to a 36-char UUID, so special chars ($, _) never reach URIs.
Anchor: '1xS3BCk291UvhgP2a6eflK' -> '7b7032cc-b822-417b-9aea-642906a29bd4'.
"""

import uuid

import ifcopenshell.guid

_GUID_ALPHABET = set(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
)


class GuidError(ValueError):
    """Raised for GlobalIds that cannot be decompressed."""


def ifc_guid_to_uuid(guid: str) -> str:
    if not isinstance(guid, str) or len(guid) != 22 or not set(guid) <= _GUID_ALPHABET:
        raise GuidError(f"invalid IFC GlobalId: {guid!r}")
    try:
        hex32 = ifcopenshell.guid.expand(guid)
        return str(uuid.UUID(hex32))
    except Exception as exc:
        raise GuidError(f"cannot decompress IFC GlobalId {guid!r}: {exc}") from exc
