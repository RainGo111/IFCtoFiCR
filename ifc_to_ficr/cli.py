"""Command-line interface.

  ifc-to-ficr convert INPUT.ifc [-o OUT.ttl] [--emit-intermediate [PATH]] ...

Exit codes: 0 ok, 1 error, 2 usage, 3 unsupported schema,
4 TBox validation failure.
"""

import argparse
import logging
import sys
from pathlib import Path

from ifc_to_ficr import __version__, coverage, stage_a, stage_b
from ifc_to_ficr.profile import (
    InvalidIfcError,
    UnsupportedSchemaError,
    detect_schema,
    get_profile,
)
from ifc_to_ficr.tbox import TermValidationError, load_validation_sets

log = logging.getLogger("ifc_to_ficr")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_UNSUPPORTED_SCHEMA = 3
EXIT_TBOX_VALIDATION = 4

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TBOX = REPO_ROOT / "FiCR_ontology" / "ficr.ttl"
DEFAULT_BOT = REPO_ROOT / "FiCR_ontology" / "bot.ttl"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ifc-to-ficr",
        description="Single-tool IFC (IFC2X3) to FiCR RDF ABox converter",
    )
    parser.add_argument("--version", action="version",
                        version=f"ifc_to_ficr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser("convert", help="convert IFC to FiCR ABox")
    p_convert.add_argument("input", help="input IFC file")
    p_convert.add_argument("--tbox", default=str(DEFAULT_TBOX),
                           help="frozen FiCR TBox (default: FiCR_ontology/ficr.ttl)")
    p_convert.add_argument("--bot", default=str(DEFAULT_BOT),
                           help="local BOT ontology (default: FiCR_ontology/bot.ttl)")
    p_convert.add_argument("-v", "--verbose", action="store_true")
    p_convert.add_argument("-o", "--output",
                           help="output Turtle path (default: <input>_ficr.ttl)")
    p_convert.add_argument("--emit-intermediate", nargs="?", const="",
                           default=None, metavar="PATH",
                           help="dump the Stage A BOT graph "
                                "(default path: <input>_lbd.ttl)")
    p_convert.add_argument("--coverage", metavar="PATH",
                           help="also write the coverage report to a file")
    p_convert.add_argument("--force", action="store_true",
                           help="overwrite existing output files")
    return parser


def _cmd_convert(args) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output \
        else input_path.with_name(input_path.stem + "_ficr.ttl")
    output_stem = output_path.stem

    intermediate_path = None
    if args.emit_intermediate is not None:
        intermediate_path = Path(args.emit_intermediate) if args.emit_intermediate \
            else input_path.with_name(input_path.stem + "_lbd.ttl")

    if not args.force:
        for path in (output_path, intermediate_path):
            if path is not None and path.exists():
                print(f"error: {path} already exists "
                      f"(use --force or -o to pick another path)", file=sys.stderr)
                return EXIT_ERROR

    schema = detect_schema(args.input)
    profile = get_profile(schema)
    log.info("schema %s -> profile %s", schema, profile.schema_id)

    result = stage_a.run(args.input, profile)
    validation = load_validation_sets(args.tbox, args.bot)
    final_graph, stats_b = stage_b.run(result, validation)

    if intermediate_path is not None:
        result.graph.serialize(destination=str(intermediate_path), format="turtle")
        log.info("Stage A graph written to %s", intermediate_path)

    stage_b.add_ontology_header(final_graph, output_stem)
    output_path.write_text(
        stage_b.serialize(final_graph, output_stem, input_path.name,
                          validation.version),
        encoding="utf-8",
    )
    print(f"FiCR ABox written to {output_path} ({len(final_graph)} triples)")

    report = coverage.render(result.stats, stats_b)
    print(report)
    if args.coverage:
        Path(args.coverage).write_text(report, encoding="utf-8")
    return EXIT_OK


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        return _cmd_convert(args)
    except UnsupportedSchemaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED_SCHEMA
    except TermValidationError as exc:
        print(f"error: TBox validation failed: {exc}", file=sys.stderr)
        return EXIT_TBOX_VALIDATION
    except (InvalidIfcError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
