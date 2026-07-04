"""End-of-run coverage report: entities visited, entities converted per FiCR
class, entities skipped with reasons, properties extracted vs missing."""

from collections import Counter

# Consumed keys of the IFC2X3 profile (property + attribute channels), listed
# explicitly so the report can flag keys with zero extractions.
CONSUMED_PROPERTY_KEYS = (
    "volume", "length", "width", "area", "thickness", "elevation",
    "unboundedHeight", "isExternal", "loadBearing",
    "omniClassTableCategory", "categoryDescription", "fireRating",
)
CONSUMED_ATTRIBUTE_KEYS = ("globalIdIfcRoot", "objectTypeIfcObject")


def render(stage_a_stats: dict, stage_b_stats: dict | None) -> str:
    lines = ["", "=" * 62, "COVERAGE REPORT", "=" * 62]

    visited: Counter = stage_a_stats.get("visited", Counter())
    lines.append(f"\nEntities visited ({sum(visited.values())} total):")
    for cls, n in sorted(visited.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {cls:<32} {n}")

    if stage_b_stats:
        class_counts = stage_b_stats.get("class_counts", {})
        lines.append(f"\nEntities converted per class "
                     f"({sum(class_counts.values())} type assertions):")
        for cls, n in sorted(class_counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {cls:<32} {n}")

    skipped = stage_a_stats.get("skipped", [])
    lines.append(f"\nSkipped ({len(skipped)}):")
    reasons = Counter(reason for _, reason in skipped)
    for reason, n in reasons.most_common():
        lines.append(f"  [{n}x] {reason}")
    if not skipped:
        lines.append("  (none)")

    extracted: Counter = stage_a_stats.get("props_extracted", Counter())
    lines.append("\nProperties extracted vs missing (consumed keys):")
    for key in (*CONSUMED_PROPERTY_KEYS, *CONSUMED_ATTRIBUTE_KEYS):
        n = extracted.get(key, 0)
        marker = "" if n else "   <-- MISSING (0 extracted)"
        lines.append(f"  {key:<28} {n}{marker}")

    if stage_b_stats:
        lines.append("\nStage B statistics:")
        for key in ("total_triples", "converted_properties", "preserved_relations",
                    "unmapped_properties", "buildings_classified",
                    "storeys_classified", "storey_links",
                    "spaces_classified_omniclass", "spaces_classified_text",
                    "spaces_unclassified", "members_stair", "members_mullion",
                    "members_beam", "walls_external", "fire_ratings_mapped",
                    "adjacency_horizontal", "adjacency_vertical",
                    "adjacency_party_wall"):
            if key in stage_b_stats:
                lines.append(f"  {key:<32} {stage_b_stats[key]}")

    lines.append("=" * 62)
    return "\n".join(lines)
