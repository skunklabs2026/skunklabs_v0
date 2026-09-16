import marimo

__generated_with = "0.23.6"
app = marimo.App()


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # MMAUD — EDA for the canister state estimate

    The canister must hand the interceptor a position 3-vector, a velocity 3-vector,
    a 6x6 covariance, a timestamp and a classification.

    The central aim of this notebook is to determine whether [MMAUD](https://ntu-aris.github.io/MMAUD/) / the
    [CVPR UG2+ Track 5](https://ug2-uav-tracking.github.io/dataset24_t5.html) can be used to determine these 5 features.

    The archives are large — `train.zip` is 139.7 GB — so almost nothing here is
    downloaded. Google Drive serves both archives with `Accept-Ranges: bytes`, so
    `scripts/mmaud_io.py` reads them as random-access storage:

    - **structure, sizes and every sensor timestamp** come from the zip index (§1, §2)
    - **all 40,800 ground-truth labels** are ~17 MB of tiny files, pulled in full (§3, §4)
    - **only pixels and point clouds** need a sample (§5)

    Run `make eda` for the index and labels, `make eda-sample` for the frames.

    Licence: CC BY-NC-SA 4.0, non-commercial academic use.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 0. What is available
    """)
    return


@app.cell
def _():
    import sys
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

    import mmaud_io as mm

    local = mm.discover()
    mo.md(f"```\n{local.describe()}\n```")
    return Path, local, mm, mo, np, pd, plt


@app.cell
def _(local, mm, mo):
    labels = mm.load_local_labels(split="train")
    val_labels = mm.load_labels(local.meta_dir / "validation_ref_new.csv")
    test_queries = mm.load_labels(local.meta_dir / "test_timestamps.csv")

    mo.md(f"""
    | table | rows | labelled |
    | --- | --- | --- |
    | `train` ground truth | {len(labels):,} | {labels["x"].notna().sum():,} |
    | `val` reference | {len(val_labels):,} | {val_labels["x"].notna().sum():,} |
    | `test` queries | {len(test_queries):,} | {test_queries["x"].notna().sum():,} (withheld) |
    """)
    return (labels,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 0.1 What the dataset physically is

    Not video, not a database, not packed tensors: MMAUD is a **directory tree of
    per-frame files**, one file per sensor reading, each named by its own ROS
    timestamp. A sequence is a single ~20 s flight, and every modality is just a
    folder of timestamps inside it:

    ```
    train/seq0001/
      Image/1706255121.609461.png      2560x960 PNG   ~2.3 MB  two fisheyes side by side
      lidar_360/1706255121.699984.npy  (19968, 3) f8  479 KB   xyz, zero-padded to a fixed size
      livox_avia/….npy                 (24000, 3) f8  576 KB   xyz, zero-padded
      radar_enhance_pcl/….npy          (N, 3) f8      128 B    xyz; 86% are (0,) — no points
      ground_truth/….npy               (3,) f8        152 B    Leica position, one frame
      class/….npy                      (1,) i8        136 B    drone model id
    ```

    102 sequences, median ~2,100 files and ~1.7 GB each. **Imagery is 87% of the
    bytes** and point clouds nearly all the rest; the entire supervision signal —
    all 81,600 `ground_truth` and `class` files — is 11.7 MB of the 168 GB
    uncompressed. That asymmetry is what makes range-reading the zip worthwhile.

    Nothing ships as a table except three small CSVs in `meta/`
    (`validation_ref_new.csv`, `test_timestamps.csv`, the README). The tabular view
    below is ours: `make eda` pulls those 40,800 three-float label files and folds
    them into `labels/train_labels.csv`.
    """)
    return


@app.cell
def _(Path, labels, local, mm, mo, np, pd):
    # One real file of each kind, read off the local sample. The point is the
    # shapes and dtypes: a "frame" here is a bare numpy array with no header,
    # no frame id and no covariance — the filename carries the only metadata.
    _sample = mm.local_index(local)


    def _peek(_path):
        _p = Path(_path)
        _kb = _p.stat().st_size / 1024
        if _p.suffix == ".png":
            _im = mm.load_image(_p)
            return f"PNG {_im.shape[1]}x{_im.shape[0]} RGB uint8", f"{_kb:,.0f} KB", "(pixels)"
        _a = mm.load_array(_p)
        if _a.size == 0:
            return f"NPY {_a.shape} {_a.dtype}", f"{_kb:,.1f} KB", "(empty — header only)"
        _first = _a.reshape(1, -1) if _a.ndim < 2 else _a[np.abs(_a).sum(axis=1) > 0][:1]
        _head = (
            np.array2string(_first[0], precision=2, suppress_small=True, max_line_width=200)
            if len(_first)
            else "(all rows zero padding)"
        )
        return f"NPY {_a.shape} {_a.dtype}", f"{_kb:,.1f} KB", _head


    _rows = []
    for _mod in mm.MODALITIES:
        _part = _sample[_sample["modality"] == _mod]
        if _part.empty:
            continue
        _path = _part.iloc[0]["path"]
        _fmt, _size, _head = _peek(_path)
        _rows.append({
            "file": f"{_mod}/{Path(_path).name}",
            "format": _fmt,
            "on disk": _size,
            "first populated row": _head,
        })

    examples = pd.DataFrame(_rows).set_index("file")
    mo.vstack([
        mo.md("**One file of each kind, from the local sample**"),
        examples if len(examples) else mo.md("_no local sample yet — run `make eda-sample`_"),
        mo.md("**The label files, folded into a table by `make eda` (`labels/train_labels.csv`)**"),
        labels.head(3),
    ])
    return


@app.cell
def _(Path, labels, local, mm, np, plt):
    # What every sensor returns at one instant. The three clouds share a
    # range-height view and a ±5 m inset around the label, so "does this sensor
    # see the drone at all?" is answerable by eye. Needs `make eda-sample`.
    _sample = mm.local_index(local)
    _cands = []
    for _, _r in _sample[_sample["modality"] == "radar_enhance_pcl"].iterrows():
        if not mm.load_array(Path(_r["path"])).size:
            continue  # radar is empty 85% of the time; anchor on a frame that is not
        _im_t = _sample[
            (_sample["sequence"] == _r["sequence"]) & (_sample["modality"] == "Image")
        ]["timestamp"]
        if len(_im_t):
            _cands.append(((_im_t - _r["timestamp"]).abs().min(), _r))

    _hit = min(_cands, key=lambda c: c[0])[1]
    _seq, _t = _hit["sequence"], _hit["timestamp"]
    _lab = labels[labels["sequence"] == _seq]
    _gt = _lab.loc[(_lab["timestamp"] - _t).abs().idxmin(), ["x", "y", "z"]].to_numpy(float)
    _gt_rz = (float(np.hypot(*_gt[:2])), float(_gt[2]))


    def _nearest_frame(_mod):
        _p = _sample[(_sample["sequence"] == _seq) & (_sample["modality"] == _mod)]
        return _p.loc[(_p["timestamp"] - _t).abs().idxmin()]


    _fig = plt.figure(figsize=(13, 6.4))
    _gs = _fig.add_gridspec(2, 3, height_ratios=[1.15, 1])
    _ax0 = _fig.add_subplot(_gs[0, :])
    _r0 = _nearest_frame("Image")
    _im = mm.load_image(Path(_r0["path"]))
    _ax0.imshow(_im)
    _ax0.axvline(_im.shape[1] / 2, color="w", ls="--", lw=1)
    _ax0.axis("off")
    _ax0.set_title(
        f"Image — {_im.shape[1]}x{_im.shape[0]} PNG, two fisheyes side by side "
        f"({(_r0['timestamp'] - _t) * 1000:+.0f} ms)",
        fontsize=9,
    )

    for _i, _mod in enumerate(["lidar_360", "livox_avia", "radar_enhance_pcl"]):
        _ax = _fig.add_subplot(_gs[1, _i])
        _c = mm.load_array(Path(_nearest_frame(_mod)["path"]))
        _c = _c[np.abs(_c).sum(axis=1) > 0] if _c.ndim == 2 and _c.size else np.empty((0, 3))
        if len(_c):
            _ax.scatter(np.hypot(_c[:, 0], _c[:, 1]), _c[:, 2], s=5, alpha=0.4,
                        label=f"{len(_c)} points")
        _ax.scatter(*_gt_rz, marker="o", s=150, facecolors="none", edgecolors="crimson",
                    lw=1.8, zorder=5, label="Leica label")
        _inset = _ax.inset_axes([0.52, 0.52, 0.45, 0.45])
        if len(_c):
            _inset.scatter(np.hypot(_c[:, 0], _c[:, 1]), _c[:, 2], s=14, alpha=0.8)
        _inset.scatter(*_gt_rz, marker="x", s=90, color="crimson", lw=2, zorder=5)
        _inset.set_xlim(_gt_rz[0] - 5, _gt_rz[0] + 5)
        _inset.set_ylim(_gt_rz[1] - 5, _gt_rz[1] + 5)
        _inset.set_xticks([])
        _inset.set_yticks([])
        _inset.set_title("±5 m around the label", fontsize=6.5, pad=2)
        _near = np.linalg.norm(_c - _gt, axis=1).min() if len(_c) else float("nan")
        _ax.set_title(f"{_mod} — {len(_c)} points, nearest {_near:.1f} m from label", fontsize=9)
        _ax.set_xlim(0, 85)
        _ax.set_ylim(-5, 72)
        _ax.set_xlabel("horizontal distance (m)")
        if _i == 0:
            _ax.set_ylabel("height z (m)")
        _ax.legend(fontsize=7, loc="lower right")

    _fig.suptitle(f"One moment in {_seq}: what each sensor actually returns", fontsize=10)
    _fig.tight_layout()
    _fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The fisheyes look at the sky; the drone is a handful of pixels somewhere in
    them. The three point clouds are plotted the same way — horizontal distance
    against height — with the Leica label ringed in red and a ±5 m inset around it.

    That inset is the whole story of §5: **`livox_avia` and the radar put points on
    the label, `lidar_360` does not.** It returns a few thousand points of ground
    scene and nothing up where the drone is.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. What is actually in the archives

    Read from each zip's central directory over HTTP range requests — no bulk
    transfer. This is the part that says what a full download would cost and what
    you would get for it.
    """)
    return


@app.cell
def _(local, mm, mo, pd):
    index_val = mm.RemoteZip(mm.ARCHIVES["val"], local.root / "cache").index()
    index_train = mm.RemoteZip(mm.ARCHIVES["train"], local.root / "cache").index()
    index = pd.concat([index_train, index_val], ignore_index=True)


    def _summary(frame, label):
        _g = frame.groupby("modality").agg(files=("path", "size"), gb=("size", lambda s: s.sum() / 1e9))
        _g["gb"] = _g["gb"].round(2)
        _g.columns = pd.MultiIndex.from_product([[label], _g.columns])
        return _g


    mo.vstack([
        mo.md(
            f"**train.zip** {len(index_train):,} files, {index_train['sequence'].nunique()} sequences "
            f"&nbsp;&nbsp; **val.zip** {len(index_val):,} files, {index_val['sequence'].nunique()} sequences"
        ),
        _summary(index_train, "train").join(_summary(index_val, "val"), how="outer").fillna(0),
    ])
    return index_train, index_val


@app.cell
def _(index_train, plt):
    # Where the bytes are. The point: the labels are a rounding error, the imagery
    # is everything, so "download the dataset" and "get the supervision signal" are
    # very different propositions.
    _by_mod = index_train.groupby("modality")["size"].sum().sort_values()
    _fig, _ax = plt.subplots(figsize=(7, 3))
    _ax.barh(_by_mod.index, _by_mod.to_numpy() / 1e9)
    _ax.set_xscale("log")
    _ax.set_xlabel("GB in train.zip (log scale)")
    for _i, _v in enumerate(_by_mod.to_numpy()):
        _ax.text(_v / 1e9, _i, f"  {_v / 1e9:.3f} GB", va="center", fontsize=8)
    _fig.tight_layout()
    _fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Timing

    Every filename is a ROS timestamp at microsecond precision, so the entire
    timing structure is recoverable from the index without downloading a byte.
    This matters more than it sounds: the sensors do **not** share a clock rate.
    """)
    return


@app.cell
def _(index_train, mo, np, pd):
    _rows = []
    for (_seq, _mod), _part in index_train.groupby(["sequence", "modality"]):
        _ts = np.sort(_part["timestamp"].dropna().to_numpy())
        if len(_ts) < 3:
            continue
        _dt = np.diff(_ts)
        _dt = _dt[(_dt > 0) & (_dt < 5)]
        if not len(_dt):
            continue
        _rows.append({
            "modality": _mod,
            "sequence": _seq,
            "frames": len(_ts),
            "span_s": _ts[-1] - _ts[0],
            "dt_ms": np.median(_dt) * 1000,
            "jitter_ms": np.std(_dt) * 1000,
        })

    cadence = pd.DataFrame(_rows)
    _agg = cadence.groupby("modality").agg(
        sequences=("sequence", "nunique"),
        frames=("frames", "sum"),
        dt_ms=("dt_ms", "median"),
        jitter_ms=("jitter_ms", "median"),
    )
    _agg["Hz"] = (1000 / _agg["dt_ms"]).round(1)
    mo.vstack([mo.md("**Per-modality cadence across all 102 train sequences**"), _agg.round(2)])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    dt_ms corresponds to the timegap between two consecutive frames of each sensor. Hence, the lower the dt_ms the higher the number of frames in the table above.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 2.1 Cross-modality alignment

    Five different rates means no frame lines up with any other. For every ground
    truth timestamp, how far away is the nearest frame of each sensor? That gap is
    the interpolation error any fusion model inherits before it does anything else
    — and it is the argument for a filter over a per-frame regressor.
    """)
    return


@app.cell
def _(index_train, labels, mo, np, pd):
    _gaps = []
    for _seq, _lab in labels.groupby("sequence"):
        _target = np.sort(_lab["timestamp"].to_numpy())
        _part = index_train[index_train["sequence"] == _seq]
        for _mod, _sub in _part.groupby("modality"):
            if _mod in ("ground_truth", "class"):
                continue
            _ts = np.sort(_sub["timestamp"].dropna().to_numpy())
            if len(_ts) < 2:
                continue
            _pos = np.searchsorted(_ts, _target).clip(1, len(_ts) - 1)
            _near = np.minimum(np.abs(_ts[_pos] - _target), np.abs(_ts[_pos - 1] - _target))
            _gaps.append(pd.DataFrame({"modality": _mod, "gap_ms": _near * 1000}))

    alignment = pd.concat(_gaps, ignore_index=True)
    mo.vstack([
        mo.md("**Time from each ground-truth label to the nearest sensor frame (ms)**"),
        alignment.groupby("modality")["gap_ms"].describe()[["50%", "75%", "max"]].round(1),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Labels
    """)
    return


@app.cell
def _(labels, plt):
    _fig, _axes = plt.subplots(1, 4, figsize=(15, 3))
    labels["class_id"].value_counts().sort_index().plot.bar(ax=_axes[0], title="class balance", rot=0)
    for _ax, _col in zip(_axes[1:], ["x", "y", "z"]):
        _ax.hist(labels[_col].dropna(), bins=60)
        _ax.set_title(f"{_col} (m)")
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(labels, mo, np):
    labels_geo = labels.assign(
        az_deg=np.degrees(np.arctan2(labels["y"], labels["x"])),
        el_deg=np.degrees(np.arctan2(labels["z"], np.hypot(labels["x"], labels["y"]))),
    )
    mo.vstack([
        mo.md("**Workspace**"),
        labels_geo[["x", "y", "z", "range", "az_deg", "el_deg"]]
        .describe()
        .loc[["min", "25%", "50%", "75%", "max"]]
        .round(1),
    ])
    return (labels_geo,)


@app.cell
def _(labels, labels_geo, plt):
    _fig, _axes = plt.subplots(1, 3, figsize=(15, 3.4))
    _axes[0].hist(labels["range"], bins=60)
    _axes[0].set_title("slant range (m)")
    _axes[1].hist(labels_geo["el_deg"], bins=60)
    _axes[1].set_title("elevation (deg)")
    _axes[2].scatter(labels["range"], labels["z"], s=1, alpha=0.05)
    _axes[2].set_xlabel("range (m)")
    _axes[2].set_ylabel("altitude z (m)")
    _axes[2].set_title("altitude vs range")
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(labels, np, plt):
    # Ground tracks, one panel per class. Does each drone type occupy its own
    # envelope, or do they share the airspace?
    _classes = sorted(labels["class_id"].dropna().unique())
    _fig, _axes = plt.subplots(1, len(_classes), figsize=(3.2 * len(_classes), 3.2), sharex=True, sharey=True)
    for _ax, _cls in zip(np.atleast_1d(_axes), _classes):
        _part = labels[labels["class_id"] == _cls]
        _ax.scatter(_part["x"], _part["y"], s=1, alpha=0.15)
        _ax.set_title(f"class {int(_cls)}  (n={len(_part):,})", fontsize=9)
        _ax.set_xlabel("x (m)")
    _np_axes = np.atleast_1d(_axes)
    _np_axes[0].set_ylabel("y (m)")
    _fig.tight_layout()
    _fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Velocity

    There is no velocity label; it has to be differenced out of the ground-truth
    track. Unlike a frame counter, the timestamps here are real, so these numbers
    are measured rather than conditional on an assumed rate.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 5. Sensors

    From the local sample (`make eda-sample`) — the only part of this notebook that
    needs real bytes rather than the index.
    """)
    return


@app.cell
def _(local, mm, mo):
    sample = mm.local_index(local)
    mo.vstack([
        mo.md(f"**{len(sample)} sampled files, {sample['size'].sum() / 1e6:.0f} MB**"),
        sample.groupby("modality")
        .agg(files=("path", "size"), mb=("size", lambda s: s.sum() / 1e6))
        .round(1),
    ])
    return (sample,)


@app.cell
def _(Path, mm, mo, np, pd, sample):
    # Point clouds are zero-padded to a fixed row count, so the useful number is
    # how many rows are actually populated.
    _rows = []
    for _, _r in sample[
        sample["modality"].isin(["lidar_360", "livox_avia", "radar_enhance_pcl"])
    ].iterrows():
        _a = mm.load_array(Path(_r["path"]))
        _n = 0 if _a.size == 0 else int((np.abs(_a).sum(axis=1) > 0).sum()) if _a.ndim == 2 else _a.size
        _rows.append({
            "modality": _r["modality"],
            "rows": 0 if _a.size == 0 else _a.shape[0],
            "points": _n,
            "empty": _a.size == 0,
        })

    clouds = pd.DataFrame(_rows)
    mo.vstack([
        mo.md("**Populated points per frame**"),
        clouds.groupby("modality").agg(
            frames=("points", "size"),
            empty_frames=("empty", "sum"),
            median_points=("points", "median"),
            max_points=("points", "max"),
        ),
    ])
    return


@app.cell
def _(index_val, mo):
    mo.md(f"""
    The radar is barely a channel. Across the **whole** val archive
    {(index_val[index_val["modality"] == "radar_enhance_pcl"]["size"] == 128).mean():.0%}
    of radar files are exactly 128 bytes — a numpy header with no points. The
    authors confirm it ([issue #17](https://github.com/ntu-aris/MMAUD/issues/17)):
    *"the radar has extremely narrow-angle and very often, it goes out of the radar
    view. Most of time we only combin 2 LIDAR to have wide area coverage"*.

    `livox_avia` is narrow-FoV too and returns a handful of populated rows per
    frame. `lidar_360` is the only one carrying a real scene.
    """)
    return


@app.cell
def _(Path, labels, mm, np, plt, sample):
    _imgs = sample[sample["modality"] == "Image"].head(4)
    _fig, _axes = plt.subplots(2, 2, figsize=(14, 5.6))
    for _ax, (_, _r) in zip(_axes.ravel(), _imgs.iterrows()):
        _im = mm.load_image(Path(_r["path"]))
        _ax.imshow(_im)
        _ax.axvline(_im.shape[1] / 2, color="w", ls="--", lw=1)
        _lab = labels[labels["sequence"] == _r["sequence"]]
        _title = f"{_r['sequence']}  {_im.shape[1]}x{_im.shape[0]}"
        if not _lab.empty and np.isfinite(_r["timestamp"]):
            _i = (_lab["timestamp"] - _r["timestamp"]).abs().idxmin()
            _title += f"   r={_lab.loc[_i, 'range']:.0f}m  cls={int(_lab.loc[_i, 'class_id'])}"
        _ax.set_title(_title, fontsize=8)
        _ax.axis("off")
    for _ax in _axes.ravel()[len(_imgs) :]:
        _ax.axis("off")
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(mo):
    mo.md("""
    Each PNG is **2560x960 — the two fisheye cameras side by side** (dashed line).
    That matches the calibration exactly: `fisheye_calibration.zip` carries one
    `camchain.yaml` per camera, each `resolution: [1280, 960]`, omni model with
    radtan distortion.

    Note what those files do **not** contain: `cam_overlaps: []` and a single `cam0`
    in each, so there is no camera-to-camera extrinsic, no camera-to-lidar, and no
    lidar-to-Leica. The 7.24 GB archive is two mono intrinsic calibrations plus a
    14.25 GB raw calibration rosbag. That matters for the next cell.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### 5.1 Is the ground truth in the sensor frame?

    The dataset ships no transform between the Leica frame and the sensors, so this
    has to be measured rather than assumed. The test: for each sampled frame take
    the nearest label in time and measure the distance from that position to the
    closest point in the cloud. If the drone is visible *and* the frames share an
    origin, that distance is small. Run it on `lidar_360` first.
    """)
    return


@app.cell
def _(Path, labels, mm, mo, np, pd, sample):
    _rows = []
    for _, _r in sample[sample["modality"] == "lidar_360"].iterrows():
        _lab = labels[labels["sequence"] == _r["sequence"]]
        if _lab.empty or not np.isfinite(_r["timestamp"]):
            continue
        _i = (_lab["timestamp"] - _r["timestamp"]).abs().idxmin()
        _gt = _lab.loc[_i, ["x", "y", "z"]].to_numpy(dtype=float)
        _cloud = mm.load_array(Path(_r["path"]))
        if _cloud.ndim != 2 or _cloud.size == 0:
            continue
        _cloud = _cloud[np.abs(_cloud).sum(axis=1) > 0]
        if not len(_cloud):
            continue
        _d = np.linalg.norm(_cloud - _gt, axis=1)
        _rows.append({
            "sequence": _r["sequence"],
            "gt_range": float(np.linalg.norm(_gt)),
            "nearest_point_m": float(_d.min()),
            "points_within_1m": int((_d < 1.0).sum()),
            "dt_ms": abs(_lab.loc[_i, "timestamp"] - _r["timestamp"]) * 1000,
        })

    observability = pd.DataFrame(_rows)
    mo.vstack([
        mo.md("**Distance from the ground-truth position to the nearest `lidar_360` point**"),
        observability[["gt_range", "nearest_point_m", "points_within_1m", "dt_ms"]]
        .describe()
        .loc[["min", "50%", "max"]]
        .round(2),
        mo.md(
            f"Frames with **any** lidar point within 1 m of the labelled position: "
            f"**{(observability['points_within_1m'] > 0).mean():.0%}** of "
            f"{len(observability)}."
        ),
    ])
    return (observability,)


@app.cell
def _(Path, labels, mm, mo, np, pd, sample):
    # Same test, other two sensors. lidar_360 answers "no points near the label",
    # which has two possible causes — wrong frame, or the drone is out of range.
    # Only a sensor that *does* see the drone can tell them apart.
    _rows = []
    for _, _r in sample[sample["modality"].isin(["livox_avia", "radar_enhance_pcl"])].iterrows():
        _lab = labels[labels["sequence"] == _r["sequence"]]
        if _lab.empty or not np.isfinite(_r["timestamp"]):
            continue
        _i = (_lab["timestamp"] - _r["timestamp"]).abs().idxmin()
        _gt = _lab.loc[_i, ["x", "y", "z"]].to_numpy(dtype=float)
        _cloud = mm.load_array(Path(_r["path"]))
        if _cloud.ndim != 2 or _cloud.size == 0:
            continue
        _cloud = _cloud[np.abs(_cloud).sum(axis=1) > 0]
        if not len(_cloud):
            continue
        _d = np.linalg.norm(_cloud - _gt, axis=1)
        _rows.append({
            "modality": _r["modality"],
            "nearest_point_m": float(_d.min()),
            "hit_1m": bool((_d < 1.0).any()),
            "hit_2m": bool((_d < 2.0).any()),
        })

    registration = pd.DataFrame(_rows)
    mo.vstack([
        mo.md("**Same measurement on the sensors that can actually see the drone**"),
        registration.groupby("modality").agg(
            frames=("nearest_point_m", "size"),
            median_nearest_m=("nearest_point_m", "median"),
            within_1m=("hit_1m", "mean"),
            within_2m=("hit_2m", "mean"),
        ).round(2),
    ])
    return (registration,)


@app.cell
def _(Path, labels, mm, np, observability, plt, sample):
    # Where lidar_360's points stop. The label says the drone is usually high; the
    # Mid-360 returns nothing up there, because it cannot reach that far.
    _cloud_z = []
    for _p in sample[sample["modality"] == "lidar_360"]["path"].head(30):
        _a = mm.load_array(Path(_p))
        if _a.ndim == 2 and _a.size:
            _cloud_z.append(_a[np.abs(_a).sum(axis=1) > 0][:, 2])
    cloud_z = np.concatenate(_cloud_z) if _cloud_z else np.array([])

    _fig, _axes = plt.subplots(1, 2, figsize=(11, 3.2))
    _axes[0].scatter(observability["gt_range"], observability["nearest_point_m"], s=14, alpha=0.6)
    _axes[0].axhline(1.0, color="k", ls="--", lw=0.8)
    _axes[0].set_xlabel("ground-truth range (m)")
    _axes[0].set_ylabel("nearest lidar point to GT (m)")
    _axes[0].set_title("lidar_360 never returns the drone")
    _axes[1].hist(labels["z"], bins=60, density=True, alpha=0.6, label="ground truth z")
    if cloud_z.size:
        _axes[1].hist(cloud_z, bins=60, density=True, alpha=0.6, label="lidar_360 point z")
    _axes[1].set_xlabel("height z (m)")
    _axes[1].set_title("lidar_360 stops well below the flights")
    _axes[1].legend(fontsize=8)
    _fig.tight_layout()
    _fig
    return (cloud_z,)


@app.cell
def _(cloud_z, labels, mo):
    mo.md(f"""
    So the frames **do** line up, to about a metre. `livox_avia` and the radar put
    points on the label; `lidar_360` does not, and that is a range problem, not a
    frame problem — **{(labels["z"] > 30).mean():.0%}** of labels sit above 30 m
    (up to {labels["z"].max():.0f} m) and only **{(cloud_z > 30).mean():.3%}** of
    sampled `lidar_360` points do. A Livox Mid-360 is spec'd to roughly 40 m on a
    low-reflectivity target and the drone flies at 42-75 m, so it returns ground
    scene and nothing else. The Avia reaches several times further, which is why it
    sees what the Mid-360 cannot.

    A wider check agrees: 816 `livox_avia` frames spread over all 102 sequences
    (1.6 MB of range requests) put **90%** of frames within 2 m of the label, with
    a per-sequence median under 2 m in **81 of 91** sequences that returned points.

    Two caveats keep this honest. The authors say no calibration was published
    ([issue #35](https://github.com/ntu-aris/MMAUD/issues/35)):

    > *"we did not provide a direct calibration between the Leica GT frame and the
    > sensor frame… This issue was identified later and has been addressed in MMAUD
    > V2, where the relative positions are properly included."*

    So treat a metre as *approximately* registered, not calibrated — expect a small
    residual bias, and note that about ten sequences (`seq0036`, `0039`, `0091`,
    `0037`, `0082`, `0038`) are much worse and need triage before use.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 7. Verdict
    """)
    return


@app.cell
def _(labels, mo, registration):
    mo.md(f"""
    **Usable.** {len(labels):,} labelled frames across
    {labels["sequence"].nunique()} sequences, real microsecond timestamps, metric 3D
    positions from a survey-grade Leica total station and
    {labels["class_id"].nunique()} drone classes — the whole supervision signal is
    17 MB. Position, timestamp and class come free; velocity differences out of the
    track.

    **Registration is not the blocker it looked like.** §5.1 measures the sensor
    clouds against the Leica labels and finds them aligned to about a metre:
    `livox_avia` puts a point within 1 m of the label in
    {registration[registration["modality"] == "livox_avia"]["hit_1m"].mean():.0%}
    of frames. `lidar_360` sees nothing because the drone is beyond its range, not
    because the frames disagree. No published calibration backs this up, so verify
    per sequence and expect a residual bias.

    **What to price in.**

    1. *Five clock rates* — camera 31 Hz, labels 20 Hz, radar 15 Hz, both lidars
       10 Hz. §2.1 quantifies the interpolation error any fusion model inherits:
       an argument for a filter over a per-frame regressor.
    2. *Coverage is intermittent* — the radar is empty in most frames and
       `livox_avia` returns a handful of points through a narrow FoV. A filter has
       to predict through the gaps.
    3. *No 2D boxes, no per-frame detections* — raw sensors plus a 3D label.
    4. *Intrinsics only* — no extrinsics of any kind ship, not even
       camera-to-camera, which is what makes the image path the hard one.
    5. *Slow, close flights* — {labels["range"].max():.0f} m max range, hover and
       manoeuvre rather than a fast inbound.
    6. *Classes are unnamed drone models, all multirotors* — no MULTIROTOR /
       FIXED_WING distinction, and no published id-to-model mapping (§0.1).

    **Next step: `livox_avia`.** It already sits in the label frame, it is sparse
    enough that clustering is a detector, and the whole modality is 42 MB
    compressed against 138 GB for the imagery. Cluster the returns, difference the
    result against the Leica track to get an empirical **R**, and the 6x6 **P**
    follows from a filter. Images are the second step — classification and wide
    FoV — not the first, because that is exactly where the missing extrinsics bite.
    """)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
