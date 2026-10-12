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
    try:
        res = convert(
            list(plans),
            venue_config=venue,
            out_dir=out,
            floors=sel,
            force=force,
            output_format=fmt,
            method=segmenter,
        )
    except (ValueError, FileNotFoundError, ImportError) as e:  # bad input / missing weights: clear message
        raise click.ClickException(str(e)) from e
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


@main.group()
def ml() -> None:
    """Learned segmenter: prepare data, bootstrap masks, train/fine-tune, evaluate (docs/ML_GUIDE.md)."""


@ml.command("prepare-cubicasa")
@click.argument("root", type=click.Path(exists=True))
@click.option("--out", required=True, help="output mask dataset folder")
@click.option("--max-side", default=2048, show_default=True)
@click.option("--limit", type=int, default=None, help="only the first N plans per split (quick tests)")
def ml_prepare(root, out, max_side, limit) -> None:
    """Convert an extracted CubiCasa5K folder into images/ + masks/ + split lists."""
    from .learned.cubicasa import prepare

    click.echo(json.dumps(prepare(root, out, max_side=max_side, limit=limit)))


@ml.command("bootstrap-masks")
@click.argument("plans", nargs=-1, type=click.Path(exists=True), required=True)
@click.option("--venue", type=click.Path(exists=True))
@click.option("--floors", default="", help="comma-separated floor ids")
@click.option("--out", required=True, help="output mask dataset folder (images/, masks/, previews/)")
def ml_bootstrap(plans, venue, floors, out) -> None:
    """Classical result -> starting masks for annotation (correct them, then fine-tune on them)."""
    from .api import process_floor
    from .config import load_venue_config, single_image_config
    from .learned.annotate import export_dataset

    cfg = load_venue_config(venue, input_file=plans[0]) if venue else single_image_config(plans[0])
    sel = [f for f in floors.split(",") if f]
    res = {s.id: process_floor(s, cfg) for s in cfg.floors if not sel or s.id in sel}
    ids = export_dataset(res, out)
    click.echo(f"wrote {len(ids)} masks to {out}: {', '.join(ids)}")


@ml.command("train")
@click.option("--data", multiple=True, required=True, help="mask dataset folder (repeatable)")
@click.option("--out", required=True, help="checkpoint path, e.g. weights/turn_seg.pt")
@click.option("--init", default=None, help="checkpoint to fine-tune from")
@click.option("--epochs", default=40, show_default=True)
@click.option("--batch", default=8, show_default=True)
@click.option("--crop", default=512, show_default=True)
@click.option("--lr", default=1e-4, show_default=True)
@click.option("--encoder", default="resnet34", show_default=True)
@click.option("--no-pretrained", is_flag=True, help="random encoder init (offline smoke tests)")
@click.option("--max-iters", type=int, default=None)
@click.option("--workers", default=2, show_default=True)
@click.option("--device", default=None)
def ml_train(data, out, init, epochs, batch, crop, lr, encoder, no_pretrained, max_iters, workers, device):
    """Train (or fine-tune with --init) the U-Net; best checkpoint by validation mIoU."""
    from .learned.train import train

    r = train(
        list(data),
        out,
        epochs=epochs,
        batch=batch,
        crop=crop,
        lr=lr,
        encoder=encoder,
        encoder_weights=None if no_pretrained else "imagenet",
        init=init,
        max_iters=max_iters,
        workers=workers,
        device=device,
    )
    click.echo(json.dumps({k: v for k, v in r.items() if k != "log"}))


@ml.command("eval")
@click.option("--data", multiple=True, required=True)
@click.option("--weights", required=True)
@click.option("--split", default="test", show_default=True)
def ml_eval(data, weights, split) -> None:
    """Per-class IoU of a checkpoint on a mask dataset split."""
    from .learned.model import load_checkpoint
    from .learned.train import evaluate

    model, ck = load_checkpoint(weights)
    click.echo(json.dumps(evaluate(model, list(data), split, tile=int(ck.get("crop", 512))), indent=1))


if __name__ == "__main__":
    main()
