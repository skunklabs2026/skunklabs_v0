"""Reader for MMAUD / the CVPR UG2+ UAV tracking challenge release.

MMAUD ships as Google Drive zips whose sizes make a full download a poor first
step: `train.zip` is **139.7 GB**, `val.zip` 5.3 GB. Drive serves both with
`Accept-Ranges: bytes`, so this module treats a remote zip as random-access
storage instead: the central directory costs ~0.7 MB to read, and individual
members can be pulled on demand. Structure, sizes, per-modality cadence and
sensor timing all fall out of the index alone, with no bulk transfer; only the
cells that plot actual pixels or point clouds need a sample.

>>> LAYOUT <<<
Authoritative, from the challenge README bundled in the same Drive folder
(mirrored at <root>/meta/README.md):

    train/seq0001..seq0102/
        ground_truth/<ros_timestamp>.npy   Leica Nova MS60 position
        class/<ros_timestamp>.npy          UAV type
        Image/<ros_timestamp>.png          two fisheye cameras
        lidar_360/<ros_timestamp>.npy      Livox Mid360
        livox_avia/<ros_timestamp>.npy     Livox Avia
        radar_enhance_pcl/<ros_timestamp>.npy   mmWave radar
    val/seq0001..seq0016/
        Image, lidar_360, livox_avia, radar_enhance_pcl   (no labels in the zip)

Filenames are ROS timestamps — Unix epoch seconds at microsecond precision —
so time is recorded per sensor, and the modalities run at *different* rates
(~31 Hz camera, 15 Hz radar, 10 Hz both lidars). Any fusion has to align them.

Labels for `val` live outside the archive, in `validation_ref_new.csv`
(`Sequence, Timestamp, Position, Classification`). `test_timestamps.csv` is the
held-out query list with those two columns blank. Both are small; fetch them
with `scripts/fetch_mmaud.py --download meta`.

There is no audio in this release. MMAUD V1's four-node array is rosbag-only.

Usage:
    python scripts/mmaud_io.py                  # describe what is available
    python scripts/mmaud_io.py --index val      # remote structure, no bulk download
    python scripts/mmaud_io.py --sample val     # pull a small random sample
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import struct
import subprocess
import zlib
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - only the notebook pays the import cost
    import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "assets" / "datasets" / "mmaud"

#: Per-sequence subdirectories, in the order the README lists them.
MODALITIES = ("ground_truth", "class", "Image", "lidar_360", "livox_avia", "radar_enhance_pcl")

#: Nominal rates, measured from val.zip filename timestamps. Verify, don't trust.
NOMINAL_HZ = {"Image": 31.0, "radar_enhance_pcl": 15.0, "lidar_360": 10.0, "livox_avia": 10.0}

LABEL_COLUMNS = ("Sequence", "Timestamp", "Position", "Classification")


@dataclass(frozen=True)
class Archive:
    """One Drive-hosted zip, addressed by file id."""

    name: str
    file_id: str
    note: str

    @property
    def url(self) -> str:
        return (
            f"https://drive.usercontent.google.com/download"
            f"?id={self.file_id}&export=download&confirm=t"
        )


ARCHIVES: dict[str, Archive] = {
    "val": Archive(
        "val.zip",
        "1T7MLHfKsFYm8fjnJcn39ZrzFjHv-z-fh",
        "5.0 GB - 16 sequences, sensors only; labels in validation_ref_new.csv",
    ),
    "train": Archive(
        "train.zip",
        "1IswY1HUCXBxjWHKSJvd0vSTzghBxXqEY",
        "139.7 GB - 102 sequences, the only split with ground_truth/ and class/",
    ),
    "calibration": Archive(
        "fisheye_calibration.zip",
        "1LWGfTGRAgeY465rAD1mTpGXsmJHxb_3s",
        "6.7 GB - fisheye intrinsics and the calibration rosbag",
    ),
}

META_FILES = {
    "README.md": "1Y94-RMHJf7Yj2pi4he2ygyO-FRlzPev2",
    "test_timestamps.csv": "1Z7ail7Odhh61oAByFPIqwOg5eHk7diCw",
    "validation_ref_new.csv": "1x-1KtuzY5_Ug8iy5O6P_DgSwc9UU3h2a",
}


def mmaud_root() -> Path:
    """Dataset root: SKUNK_MMAUD_DIR, else assets/datasets/mmaud.

    Not a `backend.config.settings` field — nothing in `backend/` reads the
    dataset, so a tunable there would be dead weight in the README table and
    .env.example. Promote it if a trained model ever ships.
    """
    raw = os.environ.get("SKUNK_MMAUD_DIR", "").strip()
    return Path(raw).expanduser().resolve() if raw else DEFAULT_ROOT


# ---------------------------------------------------------------------------
# Remote zip, read over HTTP range requests
# ---------------------------------------------------------------------------

EOCD_SIG, EOCD64_SIG = b"PK\x05\x06", b"PK\x06\x06"
CD_SIG, LOCAL_SIG = b"PK\x01\x02", b"PK\x03\x04"
ZIP64_SENTINEL = 0xFFFFFFFF


@dataclass(frozen=True)
class Member:
    """One file inside the archive, and where to find its bytes."""

    path: str
    size: int
    compressed_size: int
    method: int
    header_offset: int

    @property
    def parts(self) -> list[str]:
        return self.path.strip("/").split("/")

    @property
    def split(self) -> str:
        return self.parts[0] if self.parts else ""

    @property
    def sequence(self) -> str:
        return self.parts[1] if len(self.parts) > 1 else ""

    @property
    def modality(self) -> str:
        return self.parts[2] if len(self.parts) > 2 else ""

    @property
    def timestamp(self) -> float:
        """ROS timestamp parsed from the filename, or NaN if not one."""
        stem = Path(self.path).stem
        try:
            return float(stem)
        except ValueError:
            return float("nan")

    @property
    def is_data(self) -> bool:
        """False for editor/uploader cruft that got zipped into the release.

        train.zip carries three `.baiduyun.uploading.cfg` leftovers under
        seq0045/ground_truth/. They are kept in the index — a stray file is
        worth seeing — but never read as data.
        """
        name = Path(self.path).name
        return not name.startswith(".") and Path(name).suffix in {".npy", ".png"}


class RemoteZip:
    """Random access to a zip over HTTP, without downloading the whole thing.

    Google Drive honours byte ranges on the usercontent endpoint, which makes
    a 130 GB archive browsable for the price of its central directory. curl is
    used rather than urllib so the redirect and cookie dance Drive requires
    stays in one well-tested place.
    """

    def __init__(self, archive: Archive, cache_dir: Path):
        self.archive = archive
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- transport ---------------------------------------------------------

    def _get(self, start: int, end: int) -> bytes:
        result = subprocess.run(
            ["curl", "-sfL", "-r", f"{start}-{end}", self.archive.url],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise OSError(f"range {start}-{end} failed: curl exit {result.returncode}")
        return result.stdout

    @cached_property
    def size(self) -> int:
        """Total bytes, from a one-byte ranged GET.

        Not from HEAD: Drive answers HEAD on its larger files with an HTML
        virus-scan interstitial and `Content-Length: 0`. A ranged GET returns
        206 with the real total in `Content-Range`, for every size.
        """
        cache = self.cache_dir / f"{self.archive.name}.size"
        if cache.exists():
            return int(cache.read_text().strip())
        result = subprocess.run(
            ["curl", "-sfL", "-D", "-", "-o", os.devnull, "-r", "0-0", self.archive.url],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            if line.lower().startswith("content-range:") and "/" in line:
                total = line.rsplit("/", 1)[1].strip()
                if total.isdigit() and int(total) > 0:
                    cache.write_text(total)
                    return int(total)
        raise OSError(f"could not determine size of {self.archive.name}")

    # -- central directory -------------------------------------------------

    @cached_property
    def _central_directory(self) -> bytes:
        cache = self.cache_dir / f"{self.archive.name}.cd"
        if cache.exists():
            return cache.read_bytes()

        total = self.size
        tail = self._get(max(0, total - 65536), total - 1)

        index = tail.rfind(EOCD_SIG)
        if index < 0:
            raise OSError("no end-of-central-directory record; not a zip?")
        _, cd_size, cd_offset = struct.unpack("<HII", tail[index + 10 : index + 20])

        # ZIP64 kicks in past 4 GB, which both real archives are.
        index64 = tail.rfind(EOCD64_SIG)
        if index64 >= 0 and (cd_size == ZIP64_SENTINEL or cd_offset == ZIP64_SENTINEL):
            cd_size = struct.unpack("<Q", tail[index64 + 40 : index64 + 48])[0]
            cd_offset = struct.unpack("<Q", tail[index64 + 48 : index64 + 56])[0]

        if not (0 < cd_size <= total and 0 <= cd_offset < total):
            raise OSError(f"implausible central directory: size={cd_size} offset={cd_offset}")

        blob = self._get(cd_offset, cd_offset + cd_size - 1)
        cache.write_bytes(blob)
        return blob

    @cached_property
    def members(self) -> list[Member]:
        """Every file in the archive. Directory entries are dropped."""
        blob = self._central_directory
        found: list[Member] = []
        cursor = 0
        while True:
            cursor = blob.find(CD_SIG, cursor)
            if cursor < 0 or cursor + 46 > len(blob):
                break
            method = struct.unpack("<H", blob[cursor + 10 : cursor + 12])[0]
            csize, usize = struct.unpack("<II", blob[cursor + 20 : cursor + 28])
            name_len, extra_len, comment_len = struct.unpack(
                "<HHH", blob[cursor + 28 : cursor + 34]
            )
            offset = struct.unpack("<I", blob[cursor + 42 : cursor + 46])[0]
            name = blob[cursor + 46 : cursor + 46 + name_len]
            extra = blob[cursor + 46 + name_len : cursor + 46 + name_len + extra_len]

            if ZIP64_SENTINEL in (usize, csize, offset):
                usize, csize, offset = _zip64_extra(extra, usize, csize, offset)

            if len(name) == name_len and name_len and not name.endswith(b"/"):
                found.append(
                    Member(name.decode("utf-8", "replace"), usize, csize, method, offset)
                )
            cursor += 46 + name_len + extra_len + comment_len
        return found

    def index(self) -> pd.DataFrame:
        """The archive as a table: one row per file, no bulk download."""
        import pandas as pd

        rows = [
            {
                "path": m.path,
                "split": m.split,
                "sequence": m.sequence,
                "modality": m.modality,
                "timestamp": m.timestamp,
                "size": m.size,
                "compressed": m.compressed_size,
            }
            for m in self.members
        ]
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        return frame.sort_values(["sequence", "modality", "timestamp"], ignore_index=True)

    # -- member extraction -------------------------------------------------

    def read(self, member: Member) -> bytes:
        """Pull and decompress one member. One range request per call."""
        blob = self._get(member.header_offset, _member_end(member))
        return _unwrap(member, blob)

    def read_many(self, members: list[Member], *, max_gap: int = 1_000_000):
        """Yield (member, bytes) for many members, sharing range requests.

        Small files written together sit together: the 81,403 label members in
        train.zip are 99.9% contiguous, so coalescing runs separated by less
        than `max_gap` turns 81,403 requests into ~100 and 140 GB of archive
        into a 17 MB transfer. Without this, per-member fetching is unusable at
        label scale.
        """
        for start, end, group in _coalesce(members, max_gap):
            blob = self._get(start, end)
            for member in group:
                yield member, _unwrap(member, blob[member.header_offset - start :])

    def extract(self, member: Member, dest_root: Path) -> Path:
        """Write one member under dest_root, preserving its path."""
        target = dest_root / member.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not (target.exists() and target.stat().st_size == member.size):
            target.write_bytes(self.read(member))
        return target


def _member_end(member: Member) -> int:
    """Upper bound on a member's extent.

    The central directory does not record the *local* header's extra-field
    length, which may differ from its own, so add slack rather than assume.
    """
    return member.header_offset + 30 + len(member.path.encode()) + 512 + member.compressed_size


def _unwrap(member: Member, blob: bytes) -> bytes:
    """Strip a local header off `blob` and decompress the member's payload."""
    if not blob.startswith(LOCAL_SIG):
        raise OSError(f"no local header at {member.header_offset} for {member.path}")
    name_len, extra_len = struct.unpack("<HH", blob[26:30])
    start = 30 + name_len + extra_len
    payload = blob[start : start + member.compressed_size]

    if member.method == 0:
        data = payload
    elif member.method == 8:
        data = zlib.decompressobj(-zlib.MAX_WBITS).decompress(payload)
    else:
        raise OSError(f"unsupported compression method {member.method} for {member.path}")
    if len(data) != member.size:
        raise OSError(f"{member.path}: expected {member.size} bytes, got {len(data)}")
    return data


def _coalesce(members: list[Member], max_gap: int) -> list[tuple[int, int, list[Member]]]:
    """Group members into (start, end, members) byte runs for shared fetches."""
    ordered = sorted(members, key=lambda m: m.header_offset)
    if not ordered:
        return []
    runs: list[tuple[int, int, list[Member]]] = []
    group = [ordered[0]]
    start, end = ordered[0].header_offset, _member_end(ordered[0])
    for member in ordered[1:]:
        if member.header_offset - end <= max_gap:
            group.append(member)
            end = max(end, _member_end(member))
        else:
            runs.append((start, end, group))
            group = [member]
            start, end = member.header_offset, _member_end(member)
    runs.append((start, end, group))
    return runs


def _zip64_extra(extra: bytes, usize: int, csize: int, offset: int) -> tuple[int, int, int]:
    """Replace saturated 32-bit fields from the ZIP64 extra record (id 0x0001)."""
    cursor = 0
    while cursor + 4 <= len(extra):
        header_id, data_len = struct.unpack("<HH", extra[cursor : cursor + 4])
        body = extra[cursor + 4 : cursor + 4 + data_len]
        if header_id == 0x0001:
            values = list(struct.unpack(f"<{len(body) // 8}Q", body[: len(body) // 8 * 8]))
            for field in ("usize", "csize", "offset"):
                current = {"usize": usize, "csize": csize, "offset": offset}[field]
                if current == ZIP64_SENTINEL and values:
                    value = values.pop(0)
                    if field == "usize":
                        usize = value
                    elif field == "csize":
                        csize = value
                    else:
                        offset = value
            break
        cursor += 4 + data_len
    return usize, csize, offset


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def sample_members(
    members: list[Member],
    *,
    per_modality: int = 12,
    sequences: int | None = 3,
    seed: int = 7,
    modalities: tuple[str, ...] | None = None,
) -> list[Member]:
    """A reproducible random slice: N files per modality, from a few sequences.

    Sampling whole sequences rather than uniformly across the archive keeps the
    timestamps of different sensors overlapping, which is what makes the
    cross-modality alignment checks meaningful.
    """
    rng = np.random.default_rng(seed)
    chosen_sequences = sorted({m.sequence for m in members if m.sequence})
    if sequences is not None and len(chosen_sequences) > sequences:
        picks = rng.choice(len(chosen_sequences), size=sequences, replace=False)
        chosen_sequences = [chosen_sequences[i] for i in sorted(picks)]
    wanted = set(chosen_sequences)

    out: list[Member] = []
    for sequence in chosen_sequences:
        for modality in modalities or MODALITIES:
            pool = [
                m
                for m in members
                if m.sequence == sequence and m.modality == modality and m.is_data
            ]
            if not pool:
                continue
            pool.sort(key=lambda m: m.timestamp)
            if len(pool) <= per_modality:
                out.extend(pool)
            else:
                # Evenly spaced rather than uniform-random, so the sample spans
                # the whole sequence instead of clumping.
                step = len(pool) / per_modality
                out.extend(pool[int(i * step)] for i in range(per_modality))
    assert wanted  # sequences were selected above
    return out


def fetch_labels(archive_key: str = "train", *, root: Path | None = None) -> Path:
    """Pull every ground-truth position and class label into one CSV.

    The whole supervision signal for the 102 training sequences is ~12 MB of
    tiny .npy files inside a 139.7 GB archive. Coalesced range reads make that
    a ~17 MB transfer, so the notebook can analyse *all* the labels while only
    ever sampling pixels and point clouds.
    """
    import pandas as pd

    root = Path(root) if root is not None else mmaud_root()
    out = root / "labels" / f"{archive_key}_labels.csv"
    if out.exists():
        print(f"Already have {out}")
        return out

    remote = RemoteZip(ARCHIVES[archive_key], root / "cache")
    wanted = [
        m for m in remote.members if m.modality in ("ground_truth", "class") and m.is_data
    ]
    if not wanted:
        raise ValueError(f"{ARCHIVES[archive_key].name} has no ground_truth/ or class/")

    runs = _coalesce(wanted, 1_000_000)
    volume = sum(end - start for start, end, _ in runs)
    print(
        f"{len(wanted):,} label files in {len(runs)} range request(s), ~{volume / 1e6:.0f} MB"
    )

    records: dict[tuple[str, float], dict[str, object]] = {}
    for done, (member, blob) in enumerate(remote.read_many(wanted), 1):
        key = (member.sequence, member.timestamp)
        row = records.setdefault(
            key, {"sequence": member.sequence, "timestamp": member.timestamp}
        )
        value = np.load(io.BytesIO(blob), allow_pickle=False).ravel()
        if member.modality == "ground_truth":
            row["x"], row["y"], row["z"] = (float(v) for v in value[:3])
        else:
            row["class_id"] = int(value[0])
        if done % 20000 == 0:
            print(f"  {done:,}/{len(wanted):,}")

    frame = pd.DataFrame(
        sorted(records.values(), key=lambda r: (r["sequence"], r["timestamp"]))
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    print(f"\n{len(frame):,} labelled frames -> {out}")
    return out


def load_local_labels(root: Path | None = None, split: str = "train") -> pd.DataFrame:
    """Read the CSV written by `fetch_labels`, with range/velocity helpers."""
    import pandas as pd

    root = Path(root) if root is not None else mmaud_root()
    path = root / "labels" / f"{split}_labels.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} — run scripts/fetch_mmaud.py --labels {split}")
    frame = pd.read_csv(path)
    frame["range"] = np.linalg.norm(frame[["x", "y", "z"]].to_numpy(), axis=1)
    return frame.sort_values(["sequence", "timestamp"], ignore_index=True)


def fetch_sample(
    archive_key: str = "val",
    *,
    root: Path | None = None,
    per_modality: int = 12,
    sequences: int | None = 3,
    seed: int = 7,
    modalities: tuple[str, ...] | None = None,
) -> Path:
    """Download a small random sample into <root>/sample, preserving structure."""
    root = Path(root) if root is not None else mmaud_root()
    remote = RemoteZip(ARCHIVES[archive_key], root / "cache")
    picks = sample_members(
        remote.members,
        per_modality=per_modality,
        sequences=sequences,
        seed=seed,
        modalities=modalities,
    )
    dest = root / "sample"
    total = sum(m.size for m in picks)
    print(f"{len(picks)} files, {total / 1e6:.1f} MB uncompressed -> {dest}")
    for i, (member, blob) in enumerate(remote.read_many(picks), 1):
        target = dest / member.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        if i % 20 == 0 or i == len(picks):
            print(f"  {i}/{len(picks)}")
    return dest


# ---------------------------------------------------------------------------
# Local data — a fetched sample, or a full unzip
# ---------------------------------------------------------------------------


@dataclass
class LocalData:
    """Whatever is on disk under the dataset root."""

    root: Path
    sample_dir: Path | None = None
    meta_dir: Path | None = None
    cached_indexes: tuple[str, ...] = ()

    @property
    def present(self) -> bool:
        return self.sample_dir is not None

    def describe(self) -> str:
        lines = [f"root: {self.root}"]
        lines.append(
            f"  sample   : {self.sample_dir}" if self.sample_dir else "  sample   : -- none --"
        )
        if self.meta_dir:
            found = sorted(p.name for p in self.meta_dir.glob("*"))
            lines.append(f"  meta     : {', '.join(found) or '-- empty --'}")
        else:
            lines.append("  meta     : -- none -- (scripts/fetch_mmaud.py --download meta)")
        lines.append(f"  cached indexes: {', '.join(self.cached_indexes) or '-- none --'}")
        return "\n".join(lines)


def discover(root: Path | None = None) -> LocalData:
    """What is available locally, without touching the network."""
    root = Path(root) if root is not None else mmaud_root()
    sample = root / "sample"
    meta = root / "meta"
    cache = root / "cache"
    return LocalData(
        root=root,
        sample_dir=sample if sample.is_dir() and any(sample.rglob("*.*")) else None,
        meta_dir=meta if meta.is_dir() else None,
        cached_indexes=tuple(sorted(p.name.removesuffix(".cd") for p in cache.glob("*.cd")))
        if cache.is_dir()
        else (),
    )


def local_index(data: LocalData | Path | None = None) -> pd.DataFrame:
    """Index a local sample (or full unzip) with the same columns as `index()`."""
    import pandas as pd

    if not isinstance(data, LocalData):
        data = discover(data)
    if data.sample_dir is None:
        columns = ["path", "split", "sequence", "modality", "timestamp", "size"]
        return pd.DataFrame(columns=columns)

    rows = []
    for path in sorted(data.sample_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(data.sample_dir)
        member = Member(relative.as_posix(), path.stat().st_size, 0, 0, 0)
        rows.append(
            {
                "path": str(path),
                "split": member.split,
                "sequence": member.sequence,
                "modality": member.modality,
                "timestamp": member.timestamp,
                "size": member.size,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["sequence", "modality", "timestamp"], ignore_index=True)


def load_labels(path: Path) -> pd.DataFrame:
    """Parse validation_ref_new.csv / test_timestamps.csv into typed columns.

    `Position` is a bracketed string in the CSV; it is split into x/y/z here so
    every downstream cell gets numbers. Blank rows (the held-out test list) come
    back as NaN rather than being dropped — how much is withheld is itself worth
    seeing.
    """
    import pandas as pd

    frame = pd.read_csv(path)
    missing = [c for c in LABEL_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")

    def _xyz(value: object) -> tuple[float, float, float]:
        if not isinstance(value, str) or not value.strip():
            return (np.nan, np.nan, np.nan)
        parsed = ast.literal_eval(value.strip())
        return tuple(float(v) for v in parsed[:3])  # type: ignore[return-value]

    xyz = np.array([_xyz(v) for v in frame["Position"]], dtype=np.float64)
    frame["x"], frame["y"], frame["z"] = xyz.T
    frame["Classification"] = pd.to_numeric(frame["Classification"], errors="coerce")
    frame["range"] = np.linalg.norm(xyz, axis=1)
    return frame.drop(columns=["Position"])


def load_array(path: Path) -> np.ndarray:
    """Load a .npy point cloud / label array from the sample."""
    return np.load(path, allow_pickle=False)


def load_image(path: Path) -> np.ndarray:
    """Load a fisheye frame as RGB."""
    import cv2

    raw = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if raw is None:
        raise OSError(f"could not decode {path}")
    return cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)


def read_bytes_as_array(blob: bytes) -> np.ndarray:
    """Decode a .npy payload held in memory (used when reading straight from the zip)."""
    return np.load(io.BytesIO(blob), allow_pickle=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="Defaults to SKUNK_MMAUD_DIR.")
    parser.add_argument(
        "--index", choices=sorted(ARCHIVES), help="Read a remote archive's structure (~0.7 MB)."
    )
    parser.add_argument(
        "--sample", choices=sorted(ARCHIVES), help="Fetch a small random sample of members."
    )
    parser.add_argument("--per-modality", type=int, default=12)
    parser.add_argument("--sequences", type=int, default=3)
    args = parser.parse_args()

    root = args.root or mmaud_root()

    if args.sample:
        fetch_sample(
            args.sample, root=root, per_modality=args.per_modality, sequences=args.sequences
        )

    if args.index:
        remote = RemoteZip(ARCHIVES[args.index], root / "cache")
        frame = remote.index()
        print(f"{ARCHIVES[args.index].name}: {remote.size / 1e9:.2f} GB, {len(frame):,} files")
        grouped = frame.groupby("modality").agg(
            files=("path", "size"), mb=("size", lambda s: s.sum() / 1e6)
        )
        print(grouped.round(1).to_string())
        print(f"sequences: {frame['sequence'].nunique()}")

    print()
    print(discover(root).describe())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
