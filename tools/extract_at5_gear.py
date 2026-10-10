#!/usr/bin/env python3
"""Build data/at5_gear.json — AmpliTube 5 gear catalogue + parameter knowledge.

Two sources, both local to a machine with AmpliTube 5 installed:

1. GearInfo/{Amps,Cabs,Stomps,Racks,Mics,Speakers}.json, read out of
   "C:/Program Files/IK Multimedia/AmpliTube 5/AmpliTube 5.pak" (an IKMPAK
   archive; the GearInfo entries are plain JSON).  This is AmpliTube's own
   model list: the authoritative name <-> GUID table.

2. Every factory/user preset (*.at5p, *.at4p) under the AmpliTube presets
   folder.  For each model GUID found in an amp, cab or stomp/rack slot we
   record every parameter name the presets store and the values seen
   (numeric min/max/median, or the set of text values).  AmpliTube writes
   the model's full parameter set into a preset, so the parameter *names*
   are complete for every model that appears at least once.

The plugin's own output (Presets/Converted, AT5_LIVE_*) is skipped so the
learned ranges are never fed by converted presets.

Usage:
    python tools/extract_at5_gear.py [--pak PATH] [--presets DIR] [-o data/at5_gear.json]
"""
import argparse
import json
import re
import statistics
import struct
from collections import defaultdict
from pathlib import Path

DEFAULT_PAK = Path("C:/Program Files/IK Multimedia/AmpliTube 5/AmpliTube 5.pak")
DEFAULT_PRESETS = Path.home() / "Documents" / "IK Multimedia" / "AmpliTube 5" / "Presets"
NULL_GUID = "773b8ea7-b54a-4a3c-99df-ffbbf6d29271"
GEARINFO = ("Amps", "Cabs", "Stomps", "Racks", "Mics", "Speakers")


# ── IKMPAK reader ──────────────────────────────────────────────────────────
def read_ikmpak_index(path: Path):
    """[(name, offset, size)].  v1: u32 index_len @10, entries name\\0 u32 off
    u32 size.  v3: entries from byte 26, name\\0 u64 off u64 size."""
    with open(path, "rb") as f:
        head = f.read(26)
        if head[:6] != b"IKMPAK":
            raise ValueError(f"{path} is not an IKMPAK archive")
        ver = head[6]
        if ver >= 3:
            f.seek(26)
            raw, fmt, width = f.read(4 << 20), "<QQ", 17
        else:
            f.seek(10)
            raw = f.read(struct.unpack("<I", f.read(4))[0])
            fmt, width = "<II", 9
    entries, i = [], 0
    while i < len(raw):
        j = raw.find(b"\0", i)
        if j < 0 or j + width > len(raw):
            break
        name = raw[i:j].decode("utf-8", "replace")
        if ver >= 3 and (not name or not name.isprintable()):
            break
        off, size = struct.unpack_from(fmt, raw, j + 1)
        entries.append((name, off, size))
        i = j + width
    return entries


def read_gearinfo(pak: Path) -> dict:
    out = {}
    with open(pak, "rb") as f:
        for name, off, size in read_ikmpak_index(pak):
            m = re.fullmatch(r"GearInfo/(\w+)\.json", name)
            if m and m.group(1) in GEARINFO:
                f.seek(off)
                text = f.read(size).decode("utf-8")
                # IK's JSON has trailing commas in places
                out[m.group(1)] = json.loads(re.sub(r",\s*([}\]])", r"\1", text))
    return out


# ── preset corpus ──────────────────────────────────────────────────────────
ATTR = re.compile(r'(\w+)="([^"]*)"')
SECTION = re.compile(r"<((?:Stomp|Rack|LoopFx)\w*)\b([^>]*)>(.*?)</\1>", re.S)
SLOT = re.compile(r"<Slot(\d+)\b([^>]*?)/>")
AMP = re.compile(r"<Amp[A-C]\b([^>]*)>\s*<Amp\b([^>]*?)/>", re.S)
CAB = re.compile(r"<Cab[A-C]\b([^>]*)>\s*<Cab\b([^>]*?)/>", re.S)
SKIP_ATTRS = {"Bypass", "FullScreen", "GUILoadComplete"}


class ParamStats:
    def __init__(self):
        self.nums, self.texts = [], {}

    def add(self, v: str):
        try:
            self.nums.append(float(v))
        except ValueError:
            self.texts[v] = self.texts.get(v, 0) + 1

    def summary(self):
        d = {"n": len(self.nums) + len(self.texts)}
        if self.nums:
            d.update(min=min(self.nums), max=max(self.nums),
                     median=statistics.median(self.nums),
                     distinct=len(set(self.nums)))
        if self.texts:
            d["values"] = sorted(self.texts)
            d["counts"] = dict(sorted(self.texts.items(), key=lambda kv: -kv[1]))
        if self.nums:
            common = max(set(self.nums), key=self.nums.count)
            d["mode"] = common
        return d


def scan_presets(root: Path):
    params = defaultdict(lambda: defaultdict(ParamStats))
    uses = defaultdict(int)
    examples = defaultdict(list)
    files = 0
    for f in sorted(list(root.rglob("*.at5p")) + list(root.rglob("*.at4p"))):
        rel = f.relative_to(root).as_posix()
        if rel.startswith("Converted/") or f.name.startswith("AT5_LIVE"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files += 1

        def note(guid, attrs):
            uses[guid] += 1
            if len(examples[guid]) < 3:
                examples[guid].append(rel)
            for k, v in ATTR.findall(attrs):
                if k not in SKIP_ATTRS:
                    params[guid][k].add(v)

        for sec, attrs, body in SECTION.findall(text):
            guids = {k[5:]: v for k, v in ATTR.findall(attrs) if re.fullmatch(r"Stomp\d+", k)}
            for idx, sattrs in SLOT.findall(body):
                g = guids.get(idx)
                if g and g != NULL_GUID:
                    note(g, sattrs)
        for outer, inner in AMP.findall(text):
            g = dict(ATTR.findall(outer)).get("Model")
            if g and g != NULL_GUID:
                note(g, inner)
        for outer, inner in CAB.findall(text):
            o = dict(ATTR.findall(outer))
            g = o.get("CabModel")
            if g and g != NULL_GUID:
                uses[g] += 1
                for k, v in ATTR.findall(inner):
                    if k not in SKIP_ATTRS:
                        params["__cab_inner__"][k].add(v)
    return files, params, uses, examples


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pak", type=Path, default=DEFAULT_PAK)
    ap.add_argument("--presets", type=Path, default=DEFAULT_PRESETS)
    ap.add_argument("-o", "--output", type=Path,
                    default=Path(__file__).resolve().parent.parent / "data" / "at5_gear.json")
    args = ap.parse_args()

    info = read_gearinfo(args.pak)
    files, params, uses, examples = scan_presets(args.presets)

    models = {}
    for kind in GEARINFO:
        for m in info.get(kind, {}).get("Models", []):
            g = (m.get("Guid") or "").lower()
            if not g or g == NULL_GUID:
                continue
            entry = {"kind": kind[:-1].lower(), "name": m.get("Name", "")}
            for extra in ("ShortName", "Keywords", "Collection", "Family"):
                if m.get(extra):
                    entry[extra[0].lower() + extra[1:]] = m[extra]
            if g in params:
                entry["params"] = {k: s.summary() for k, s in sorted(params[g].items())}
                entry["presetUses"] = uses[g]
                entry["examples"] = examples[g]
            models[g] = entry
    # GUIDs seen in presets but not in GearInfo (legacy AT4 models etc.)
    orphans = {g: {"params": {k: s.summary() for k, s in p.items()}, "presetUses": uses[g],
                   "examples": examples[g]}
               for g, p in params.items() if g not in models and not g.startswith("__")}

    out = {
        "_source": {"pak": str(args.pak), "presets": str(args.presets), "presetFiles": files,
                    "note": "generated by tools/extract_at5_gear.py — do not hand-edit"},
        "models": models,
        "presetOnlyModels": orphans,
        "cabInnerParams": {k: s.summary() for k, s in sorted(params["__cab_inner__"].items())},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=1, sort_keys=False), encoding="utf-8")
    with_params = sum(1 for m in models.values() if "params" in m)
    print(f"{files} presets scanned; {len(models)} GearInfo models "
          f"({with_params} with learned params); {len(orphans)} preset-only GUIDs -> {args.output}")


if __name__ == "__main__":
    main()
