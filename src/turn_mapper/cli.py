"""``turn-mapper`` command line (thin wrapper over turn_mapper.api)."""

from __future__ import annotations

import json
import sys

import click

from . import __version__


@click.group()
@click.version_option(__version__)
def main() -> None:
    """TURN-Mapper: floor plan -> navigation graph (.turnmap)."""


@main.command()
@click.argument("plan", type=click.Path(exists=True))
def inspect(plan: str) -> None:
    """Describe a plan file (pages, vector/raster, images, text) to help write a venue config."""
    from .ingest import inspect_file

    click.echo(json.dumps(inspect_file(plan), indent=1))


@main.command()
@click.argument("plans", nargs=-1, type=click.Path(exists=True), required=True)
@click.option("--venue", "venue", type=click.Path(exists=True), help="venue config YAML")
@click.option("--out", "out", default="runs/latest", show_default=True)
@click.option("--floors", default="", help="comma-separated floor ids (default: all in config)")
@click.option(
    "--split",
    type=click.Choice(["dev", "test", "all"]),
    default="all",
    show_default=True,
    help="restrict to dev or test buildings declared in the venue config",
)
@click.option("--force", is_flag=True, help="package floors even if validation fails (recorded in package)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "turnmap", "both"]),
    default="json",
    show_default=True,
    help="json = venue.json + images/; turnmap = zipped package",
)
@click.option("--segmenter", default="classical", show_default=True, help="classical | learned")
def run(plans, venue, out, floors, split, force, fmt, segmenter) -> None:
    """Run the pipeline and write <out>/venue.json (or .turnmap) + <out>/qa/index.html."""
    from .api import convert
    from .config import load_venue_config

    sel = [f for f in floors.split(",") if f] or None
    if venue and split != "all":
        cfg = load_venue_config(venue)
        wanted = set((cfg.splits or {}).get(split, []))
        sel = [f.id for f in cfg.floors if f.building in wanted and (not sel or f.id in sel)]
    res = convert(
        list(plans),
        venue_config=venue,
        out_dir=out,
        floors=sel,
        force=force,
        output_format=fmt,
        method=segmenter,
    )
    for f in res.floors:
        status = "PASS" if f["passed"] else "FAIL"
        click.echo(
            f"{f['id']:6s} {status}  rooms={f['n_rooms']:3d} doors={f['n_doors']:3d} nodes={f['n_nodes']:4d} "
            f"pois={f['n_pois']:3d} comps={f['n_components']} errors={len(f['errors'])} "
            f"warnings={len(f['warnings'])} scale={f['scale']:.4f}({f['scale_source']}) "
            f"[{f['split']}] {f['seconds']:.1f}s"
        )
    click.echo(f"package: {res.package}\nreport:  {res.report}\nmanifest: {res.manifest}")
    sys.exit(0 if res.all_passed else 1)


@main.command()
@click.argument("package", type=click.Path(exists=True))
def validate(package: str) -> None:
    """Validate a venue.json or .turnmap (schema + geometry rules)."""
    from .api import validate_package

    r = validate_package(package)
    for fid, f in r["floors"].items():
        click.echo(f"{fid}: {len(f['errors'])} errors, {len(f['warnings'])} warnings")
        for e in f["errors"][:20]:
            click.echo(f"   ERROR {e['code']} {e['ref'] or ''} {e['message']}")
    for e in r["venue"]:
        click.echo(f"venue ERROR {e['message']}")
    click.echo("PASSED" if r["passed"] else "FAILED")
    sys.exit(0 if r["passed"] else 1)


if __name__ == "__main__":
    main()
