"""Fetch MMAUD — the metadata, an archive index, or a random sample.

Nothing here downloads a whole archive by default. `train.zip` is 130 GB and
`val.zip` 5.0 GB, and neither is needed to answer most questions: Drive serves
both with `Accept-Ranges: bytes`, so `--index` reads an archive's structure for
~0.7 MB and `--sample` pulls a handful of real frames out of the middle of it.
Only `--archive` transfers the lot, and it asks first.

    meta     3 files, <300 KB   README + labels + the held-out query list
    index    0.7-17 MB          full file listing, sizes and timestamps
    labels   ~17 MB             every ground-truth position and class, as one CSV
    sample   tens of MB         real frames, selected reproducibly
    archive  5-130 GB           everything

>>> AUDIO <<<
Not in these archives, and not fetched here. MMAUD's rig has a four-node
microphone array, but the released zips carry only camera, lidar and radar.
Audio lives in the raw V1 rosbags (OneDrive, ~72 GB; `rosbag decompress` then
sbrodeur/ros-audio-convert), and there is a small pre-aligned audio+image+
ground-truth pack linked from ntu-aris/MMAUD issue #32. Both are behind
SharePoint logins, so they need a browser. Note also that the authors consider
the V2/V3 audio unusable — carpark recording next to a working repair shop,
with the UAV far from the rig (issue #25).

Licence: CC BY-NC-SA 4.0. Non-commercial academic use.

Usage:
    python scripts/fetch_mmaud.py                   # what is available, and what it costs
    python scripts/fetch_mmaud.py --download meta   # the small files the notebook needs
    python scripts/fetch_mmaud.py --index val       # structure only, no bulk transfer
    python scripts/fetch_mmaud.py --labels train    # all 40k labels, ~17 MB
    python scripts/fetch_mmaud.py --sample val      # real frames for the plotting cells
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # curl only, fixed argv, no shell; see _curl  # nosec B404
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mmaud_io import (
    ARCHIVES,
    META_FILES,
    RemoteZip,
    discover,
    fetch_labels,
    fetch_sample,
    mmaud_root,
)

HOMEPAGE = "https://ntu-aris.github.io/MMAUD/"
CHALLENGE = "https://ug2-uav-tracking.github.io/dataset24_t5.html"
AUDIO_ISSUE = "https://github.com/ntu-aris/MMAUD/issues/32"

DRIVE_FILE = (
    "https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
)


def _curl(url: str, target: Path, *, resume: bool = False) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    found = shutil.which("curl")
    if found is None:
        raise OSError("curl is required to download MMAUD, and is not on PATH")
    command = [found, "-fL", "--progress-bar", "-o", str(target), url]
    if resume:
        command.insert(1, "-C")
        command.insert(2, "-")
    # Fixed argv, no shell; the URL comes from the DRIVE_FILE template.
    subprocess.run(command, check=True)  # nosec B603


def describe(root: Path) -> None:
    print(f"MMAUD sources        destination: {root}\n")
    print("  meta       <300 KB   README.md, validation_ref_new.csv, test_timestamps.csv")
    print("                       labels for val live here, not in the archive")
    print("  index      0.7-17MB  per-archive file listing via HTTP range requests")
    print("  labels     ~17 MB    all 40k ground-truth positions + classes, one CSV")
    print("                       train only; val labels are in meta/")
    print("  sample     ~10-80 MB real frames, reproducible selection")
    print("\n  archives (full download, --archive NAME --yes):")
    for key, archive in ARCHIVES.items():
        print(f"    {key:<12} {archive.note}")

    print(f"\n  audio      not here. See the module docstring and {AUDIO_ISSUE}")
    print(f"\nProject page : {HOMEPAGE}")
    print(f"Challenge    : {CHALLENGE}")
    print("\nAlready have the data elsewhere?  export SKUNK_MMAUD_DIR=/path/to/mmaud")
    print()
    print(discover(root).describe())


def download_meta(root: Path) -> int:
    dest = root / "meta"
    for name, file_id in META_FILES.items():
        target = dest / name
        print(f"  {name}", flush=True)
        try:
            _curl(DRIVE_FILE.format(file_id=file_id), target)
        except subprocess.CalledProcessError as exc:
            print(f"    failed ({exc}); fetch by hand from {HOMEPAGE}", file=sys.stderr)
            return 1
    print(f"\nWrote {len(META_FILES)} files to {dest}")
    return 0


def cache_index(key: str, root: Path) -> int:
    remote = RemoteZip(ARCHIVES[key], root / "cache")
    try:
        frame = remote.index()
    except OSError as exc:
        print(f"Could not read {ARCHIVES[key].name}: {exc}", file=sys.stderr)
        print("Drive rate-limits; wait and retry, or download by hand.", file=sys.stderr)
        return 1

    print(f"{ARCHIVES[key].name}: {remote.size / 1e9:.2f} GB, {len(frame):,} files")
    if frame.empty:
        return 0
    grouped = frame.groupby("modality").agg(
        files=("path", "size"), mb=("size", lambda s: s.sum() / 1e6)
    )
    print(grouped.round(1).to_string())
    print(f"sequences: {frame['sequence'].nunique()}")
    print(f"\nIndex cached under {root / 'cache'} — later reads are offline.")
    return 0


def download_archive(key: str, root: Path, *, confirmed: bool) -> int:
    archive = ARCHIVES[key]
    remote = RemoteZip(archive, root / "cache")
    try:
        size = remote.size
    except OSError as exc:
        print(f"Could not size {archive.name}: {exc}", file=sys.stderr)
        return 1

    free = shutil.disk_usage(root if root.exists() else root.parent).free
    print(f"{archive.name}: {size / 1e9:.1f} GB   free here: {free / 1e9:.0f} GB")
    print("Unzipping needs roughly the same again alongside it.")
    if not confirmed:
        print("\nNot downloading. Re-run with --yes if that is really what you want,")
        print("or use --sample for a slice that answers most questions.")
        return 1
    if free < size * 2:
        print(
            "\nRefusing: less free space than the archive plus its unzipped size.",
            file=sys.stderr,
        )
        return 1

    target = root / "archives" / archive.name
    print(f"\n-> {target}  (resumable; re-run to continue an interrupted transfer)")
    try:
        _curl(archive.url, target, resume=True)
    except subprocess.CalledProcessError as exc:
        print(f"\nTransfer failed ({exc}). Re-run to resume.", file=sys.stderr)
        return 1
    print("\nDone. Unzip it, then: python scripts/mmaud_io.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=None, help="Defaults to SKUNK_MMAUD_DIR.")
    parser.add_argument("--download", choices=["meta"], help="Fetch the small metadata files.")
    parser.add_argument(
        "--index", choices=sorted(ARCHIVES), help="Cache an archive's file listing."
    )
    parser.add_argument(
        "--sample", choices=sorted(ARCHIVES), help="Pull a small random sample."
    )
    parser.add_argument(
        "--per-modality", type=int, default=12, help="Files per modality (--sample)."
    )
    parser.add_argument(
        "--sequences", type=int, default=3, help="Sequences to draw from (--sample)."
    )
    parser.add_argument("--seed", type=int, default=7, help="Sample selection seed.")
    parser.add_argument(
        "--modalities",
        help="Comma-separated subset for --sample, e.g. Image or lidar_360,ground_truth.",
    )
    parser.add_argument(
        "--labels", choices=sorted(ARCHIVES), help="Pull every ground-truth label as a CSV."
    )
    parser.add_argument("--archive", choices=sorted(ARCHIVES), help="Download a whole archive.")
    parser.add_argument("--yes", action="store_true", help="Confirm a full archive download.")
    args = parser.parse_args()

    root = args.dest or mmaud_root()

    if args.download:
        return download_meta(root)
    if args.index:
        return cache_index(args.index, root)
    if args.labels:
        fetch_labels(args.labels, root=root)
        return 0
    if args.sample:
        fetch_sample(
            args.sample,
            root=root,
            per_modality=args.per_modality,
            sequences=args.sequences,
            seed=args.seed,
            modalities=tuple(args.modalities.split(",")) if args.modalities else None,
        )
        return 0
    if args.archive:
        return download_archive(args.archive, root, confirmed=args.yes)

    describe(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
