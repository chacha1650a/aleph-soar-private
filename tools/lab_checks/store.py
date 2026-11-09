"""Immutable, manifest-completed local bundles with bounded reads."""

import hashlib
from pathlib import Path, PurePosixPath
import re

from .models import LabError, MAX_BYTES, canonical, read_json

BUNDLE_FILES = {"card.json", "input.json", "receipt.json", "comparison.json", "report.md", "collection.json",
                "handoff.json", *(f"handoff-{seat}.md" for seat in "ABCD")}


def linked(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def contained(root, relative):
    root = Path(root).absolute()
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise LabError("Expected a safe relative path.")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in ("..", ".") for part in relative.split("/")):
        raise LabError("Path escapes the selected root.")
    target = root.joinpath(*pure.parts)
    for item in (root, *root.parents, target, *target.parents):
        if linked(item):
            raise LabError("Symlinks and junctions are not accepted.")
    if not target.resolve().is_relative_to(root.resolve()):
        raise LabError("Path escapes the selected root.")
    return target


def reserve(root, relative):
    target = contained(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = contained(root, relative)
    try:
        target.mkdir()  # Refuse an existing directory, including an unfinished attempt.
    except FileExistsError as error:
        raise LabError("Output already exists; choose a new attempt directory.") from error
    return target


def publish(root, relative, documents):
    if not documents or not set(documents) <= BUNDLE_FILES:
        raise LabError("Unsupported bundle contents.")
    target = reserve(root, relative)
    hashes = {}
    for name, value in documents.items():
        raw = value.encode("utf-8") if isinstance(value, str) else canonical(value) + b"\n"
        if len(raw) > MAX_BYTES:
            raise LabError("Output exceeds the local size limit.")
        with (target / name).open("xb") as stream:
            stream.write(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    manifest = {"format": "lab-check-bundle-v1", "files": hashes}
    with (target / "manifest.json").open("xb") as stream:
        stream.write(canonical(manifest) + b"\n")
    return target


def verified_document(directory, name):
    directory = Path(directory).absolute()
    manifest_path = contained(directory, "manifest.json")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or set(manifest) != {"format", "files"} or manifest["format"] != "lab-check-bundle-v1":
        raise LabError("Invalid completion manifest.")
    files = manifest["files"]
    if not isinstance(files, dict) or name not in files or not set(files) <= BUNDLE_FILES:
        raise LabError("Incomplete or unsupported bundle.")
    for filename, expected in files.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise LabError("Invalid manifest checksum.")
        path = contained(directory, filename)
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != expected:
            raise LabError("Bundle checksum mismatch.")
    return read_json(contained(directory, name))


def receipts_from_inbox(directory):
    directory = Path(directory).absolute()
    contained(directory, "manifest-check")
    receipts = []
    for child in sorted(directory.iterdir()):
        if linked(child):
            raise LabError("Linked inbox entries are not accepted.")
        if child.is_dir() and (child / "manifest.json").is_file():
            receipts.append(verified_document(child, "receipt.json"))
    return receipts
