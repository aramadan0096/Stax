#!/usr/bin/env python3
"""
seq2gif.py

Scan a directory tree for image sequences and single images.
- Convert sequences (e.g. name.1001.exr, name.1002.exr, ...) into animated GIFs.
- Convert single images into PNGs.

Relies on ffmpeg being available (or pass --ffmpeg /path/to/ffmpeg).
"""

import os
import re
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

NUM_REGEX = re.compile(r"^(?P<prefix>.*?)(?P<frame>\d+)\.(?P<ext>[^.]+)$")

IMAGE_EXTS = {
    "exr", "png", "jpg", "jpeg", "tiff", "tif", "hdr", "bmp", "dpx", "tga"
}


def find_images(root: Path) -> Tuple[Dict[Tuple[Path, str, str], List[Tuple[str, int]]], List[Path]]:
    """
    Walk root and return:
      - sequence_groups: mapping (dirpath, prefix, ext) -> list of (frame_str, frame_int)
      - singles: list of file Paths that are not numeric-framed or are standalone
    """
    sequence_groups = {}
    singles = []

    for dirpath, _, files in os.walk(root):
        d = Path(dirpath)
        for fn in files:
            # ignore hidden files
            if fn.startswith("."):
                continue
            m = NUM_REGEX.match(fn)
            if m and m.group("ext").lower() in IMAGE_EXTS:
                prefix = m.group("prefix")
                frame_str = m.group("frame")
                ext = m.group("ext")
                key = (d, prefix, ext)
                sequence_groups.setdefault(key, []).append((frame_str, int(frame_str)))
            else:
                # non-numeric filename or not in known image ext -> treat as single
                # But still include known image extensions only
                ext = Path(fn).suffix.lower().lstrip(".")
                full = d / fn
                if ext in IMAGE_EXTS:
                    singles.append(full)
    return sequence_groups, singles


def ensure_ffmpeg(ffmpeg_path: str):
    """Return ffmpeg executable path or raise."""
    if ffmpeg_path:
        if Path(ffmpeg_path).exists():
            return ffmpeg_path
        else:
            raise FileNotFoundError(f"ffmpeg not found at {ffmpeg_path}")
    # search in PATH
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    raise FileNotFoundError("ffmpeg not found in PATH. Install ffmpeg or provide --ffmpeg path.")


def run(cmd: List[str]):
    """Run subprocess command, raise on non-zero return."""
    print("RUN:", " ".join(cmd))
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print("ffmpeg error output:\n", res.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return res.stdout


def convert_sequence_to_gif(ffmpeg_exe: str, dirname: Path, prefix: str, frames: List[Tuple[str, int]], ext: str,
                            outdir: Path, fps: int = 12, overwrite: bool = False):
    """
    Convert a sequence in dirname with given prefix/ext to an animated GIF.
    frames: list of (frame_str, frame_int)
    """
    # prepare
    pad = max(len(fstr) for fstr, _ in frames)
    frame_numbers = sorted(set(n for _, n in frames))
    start = min(frame_numbers)
    # pattern e.g. /path/v1.%04d.exr
    pattern = str(dirname / f"{prefix}%0{pad}d.{ext}")

    # prepare output name: safe prefix -> strip trailing dots/underscores
    safe_prefix = re.sub(r"[^\w\-_\.]", "_", prefix).rstrip("._")
    if not safe_prefix:
        safe_prefix = "sequence"
    outdir.mkdir(parents=True, exist_ok=True)
    out_gif = outdir / f"{safe_prefix}.gif"
    if out_gif.exists() and not overwrite:
        print(f"Skipping {out_gif} (exists). Use --overwrite to replace.")
        return str(out_gif)

    # two-pass palette generation for good GIF colors
    with tempfile.TemporaryDirectory() as td:
        palette = Path(td) / "palette.png"
        # 1) palettegen
        cmd1 = [
            ffmpeg_exe,
            "-y",
            "-start_number", str(start),
            "-i", pattern,
            "-vf", f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,palettegen",
            str(palette)
        ]
        run(cmd1)
        # 2) paletteuse -> gif
        cmd2 = [
            ffmpeg_exe,
            "-y",
            "-start_number", str(start),
            "-i", pattern,
            "-i", str(palette),
            "-lavfi", f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2[x];[x][1:v]paletteuse",
            str(out_gif)
        ]
        run(cmd2)
        print(f"Created GIF: {out_gif}")
    return str(out_gif)


def convert_single_to_png(ffmpeg_exe: str, infile: Path, outdir: Path, overwrite: bool = False):
    """Convert a single image (exr/png/jpg) to png using ffmpeg."""
    outdir.mkdir(parents=True, exist_ok=True)
    name = infile.stem
    out_png = outdir / f"{name}.png"
    if out_png.exists() and not overwrite:
        print(f"Skipping {out_png} (exists). Use --overwrite to replace.")
        return str(out_png)
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", str(infile),
        str(out_png)
    ]
    run(cmd)
    print(f"Created PNG: {out_png}")
    return str(out_png)


def main():
    parser = argparse.ArgumentParser(description="Scan folders and convert image sequences to GIFs (or single images to PNG).")
    parser.add_argument("root", help="Root folder to scan", type=Path)
    parser.add_argument("--out", help="Output folder (defaults to same folder as each sequence/file)", type=Path, default=None)
    parser.add_argument("--ffmpeg", help="Path to ffmpeg executable (optional)", default=None)
    parser.add_argument("--min-frames", type=int, default=3, help="Minimum number of frames to consider a sequence (default 3)")
    parser.add_argument("--fps", type=int, default=12, help="Frames per second for GIFs (default 12)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--dry-run", action="store_true", help="Do not run conversions; just print what would be done")
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.exists():
        raise SystemExit(f"Root folder {root} does not exist.")

    try:
        ffmpeg_exe = ensure_ffmpeg(args.ffmpeg)
    except FileNotFoundError as e:
        raise SystemExit(str(e))

    sequence_groups, singles = find_images(root)

    # Lists for decisions
    to_convert_sequences = []
    to_convert_singles = []

    # Decide sequence vs single based on counts
    for (dirname, prefix, ext), frames in sequence_groups.items():
        if len(frames) >= args.min_frames:
            to_convert_sequences.append((dirname, prefix, frames, ext))
        else:
            # treat as singles
            for fstr, _ in frames:
                fname = f"{prefix}{fstr}.{ext}"
                to_convert_singles.append(dirname / fname)

    # add previously found pure singles
    to_convert_singles.extend(singles)

    print("Summary:")
    print(f"  sequences detected (>= {args.min_frames} frames): {len(to_convert_sequences)}")
    print(f"  single files to convert to PNG: {len(to_convert_singles)}")
    print()

    if args.dry_run:
        print("Dry run mode. No conversions will be performed.")
        for dirname, prefix, frames, ext in to_convert_sequences:
            pad = max(len(fstr) for fstr, _ in frames)
            start = min(n for _, n in frames)
            pattern = dirname / f"{prefix}%0{pad}d.{ext}"
            outdir = args.out if args.out else dirname
            print(f"[SEQ] {pattern} -> {outdir}/{prefix.rstrip('.')}.gif  (start={start}, frames={len(frames)})")
        for sing in to_convert_singles:
            outdir = args.out if args.out else sing.parent
            print(f"[SNG] {sing} -> {outdir}/{sing.stem}.png")
        return

    # Perform conversions
    for dirname, prefix, frames, ext in to_convert_sequences:
        outdir = args.out if args.out else dirname
        try:
            convert_sequence_to_gif(ffmpeg_exe, dirname, prefix, frames, ext, outdir, fps=args.fps, overwrite=args.overwrite)
        except Exception as exc:
            print(f"Failed to convert sequence {prefix} in {dirname}: {exc}")

    for sing in to_convert_singles:
        outdir = args.out if args.out else sing.parent
        try:
            convert_single_to_png(ffmpeg_exe, sing, outdir, overwrite=args.overwrite)
        except Exception as exc:
            print(f"Failed to convert single file {sing}: {exc}")


if __name__ == "__main__":
    main()
