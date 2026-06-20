"""
generate_at5_pc_map.py
─────────────────────────────────────────────────────────────────────────────
Generates the AmpliTube 5 ProgramChangePresetList.ik file from presets
in the Converted folder.

PC slots 120-127 are always reserved for live conversion (AT5_LIVE_00..07).
Run this once after first install, and again if you add presets or change
the live slot count.

Usage:
    python generate_at5_pc_map.py

Optional args:
    --presets-dir   Path to AT5 Presets folder (auto-detected if omitted)
    --output        Path to write ProgramChangePresetList.ik
    --folder        Subfolder within Presets to use (default: Converted)
    --max-presets   Maximum presets to map, not counting live slots (default: 120)
"""

import argparse
import os
import sys
from pathlib import Path
from xml.etree.ElementTree import Element, tostring
from xml.dom import minidom


def find_at5_presets_dir():
    """Try to find the AT5 Presets folder automatically."""
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Documents" / "IK Multimedia" / "AmpliTube 5" / "Presets",
        Path(os.environ.get("USERPROFILE", "")) / "Documents" / "IK Multimedia" / "AmpliTube 5" / "Presets",
        Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Documenten" / "IK Multimedia" / "AmpliTube 5" / "Presets",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def find_pc_map_file(presets_dir):
    """Try to find where AT5 stores ProgramChangePresetList.ik"""
    # It's often next to Presets.db in the parent folder
    parent = presets_dir.parent
    candidates = [
        parent / "ProgramChangePresetList.ik",
        presets_dir / "ProgramChangePresetList.ik",
    ]
    # Also search AppData
    appdata = Path(os.environ.get("APPDATA", "")) / "IK Multimedia" / "AmpliTube 5"
    candidates.append(appdata / "ProgramChangePresetList.ik")
    localappdata = Path(os.environ.get("LOCALAPPDATA", "")) / "IK Multimedia" / "AmpliTube 5"
    candidates.append(localappdata / "ProgramChangePresetList.ik")

    for c in candidates:
        if c.exists():
            return c
    # Return the most likely location even if it doesn't exist yet
    return parent / "ProgramChangePresetList.ik"


LIVE_SLOT_START  = 120
LIVE_SLOT_COUNT  = 8
LIVE_SLOT_PREFIX = "AT5_LIVE"


def generate_pc_map(presets_dir, folder, output_path, max_presets=848):
    """Generate the ProgramChangePresetList.ik file.
    Slots 120-127 are always reserved for live conversion (AT5_LIVE_00..07).
    """
    target_dir = presets_dir / folder
    if not target_dir.exists():
        print(f"ERROR: Folder not found: {target_dir}")
        print(f"Make sure your converted presets are in: {target_dir}")
        sys.exit(1)

    # Collect all .at5p files, sorted alphabetically — exclude AT5_LIVE files
    all_presets = sorted(target_dir.rglob("*.at5p"))
    presets = [p for p in all_presets if LIVE_SLOT_PREFIX not in p.stem]
    live_files = [p for p in all_presets if LIVE_SLOT_PREFIX in p.stem]

    if not presets:
        print(f"ERROR: No .at5p files found in {target_dir}")
        sys.exit(1)

    print(f"Found {len(presets)} presets in {target_dir} (+ {len(live_files)} live slot files)")

    # Cap at LIVE_SLOT_START so live slots never get overwritten
    effective_max = min(max_presets, LIVE_SLOT_START) if max_presets else LIVE_SLOT_START
    if len(presets) > effective_max:
        presets = presets[:effective_max]
        print(f"Limiting to {effective_max} presets (slots 0-{effective_max-1})")

    # Build the XML attrs
    attrs = {}
    for i, preset in enumerate(presets):
        relative = preset.relative_to(presets_dir)
        rel_str = str(relative).replace("\\", "/")
        attrs[f"PC{i}"] = rel_str

    # Reserve slots LIVE_SLOT_START..LIVE_SLOT_START+LIVE_SLOT_COUNT-1
    print(f"\nReserving PC {LIVE_SLOT_START}-{LIVE_SLOT_START+LIVE_SLOT_COUNT-1} for live slots:")
    for i in range(LIVE_SLOT_COUNT):
        slot_name = f"{LIVE_SLOT_PREFIX}_{i:02d}.at5p"
        slot_path = target_dir / slot_name
        if not slot_path.exists():
            print(f"  WARNING: {slot_name} not found — start Slopsmith once to create it")
        rel_str = str(slot_path.relative_to(presets_dir)).replace("\\", "/")
        attrs[f"PC{LIVE_SLOT_START + i}"] = rel_str
        print(f"  PC{LIVE_SLOT_START + i} -> {slot_name}")

    # Generate XML
    # AT5 uses a single element with all PCs as attributes
    # Format: <ProgramChangeMap PC0="Folder/Name.at5p" PC1="..." />
    xml_lines = ['<?xml version="1.0" ?>']
    xml_lines.append('<ProgramChangeMap')
    for key, val in sorted(attrs.items(), key=lambda x: int(x[0][2:])):
        # Escape & in preset names
        safe_val = val.replace('&', '&amp;')
        xml_lines.append(f'  {key}="{safe_val}"')
    xml_lines.append('/>')
    xml_content = '\n'.join(xml_lines)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_content, encoding='utf-8')
    print(f"\n✓ Written to: {output_path}")
    print(f"  Total presets mapped: {len(presets)}")
    print(f"  Banks needed: {(len(presets) + 127) // 128}")
    print()
    print("Bank/PC reference:")
    for bank in range((len(presets) + 127) // 128):
        start = bank * 128
        end = min(start + 128, len(presets))
        start_preset = presets[start]
        end_preset = presets[end - 1]
        print(f"  Bank {bank}: PC0-PC{end-start-1}  "
              f"({start_preset.stem} → {end_preset.stem})")

    print()
    print("To use bank 0 (PC 0-127): just send PC messages")
    print("To use bank 1 (PC 128-255): send CC#0=1 then PC")
    print("To use bank 2 (PC 256-383): send CC#0=2 then PC")
    print("etc.")
    print()
    print("Restart AmpliTube 5 to load the new mapping.")

    return len(presets)


def main():
    parser = argparse.ArgumentParser(description="Generate AT5 PC preset map")
    parser.add_argument("--presets-dir", type=str, default=None,
                        help="Path to AmpliTube 5 Presets folder")
    parser.add_argument("--output", type=str, default=None,
                        help="Path to write ProgramChangePresetList.ik")
    parser.add_argument("--folder", type=str, default="Converted",
                        help="Subfolder to map (default: Converted)")
    parser.add_argument("--max-presets", type=int, default=120,
                        help="Max presets to map excluding live slots (default: 120)")
    args = parser.parse_args()

    # Find presets dir
    if args.presets_dir:
        presets_dir = Path(args.presets_dir)
    else:
        presets_dir = find_at5_presets_dir()
        if not presets_dir:
            print("ERROR: Could not find AT5 Presets folder.")
            print("Specify it with --presets-dir")
            sys.exit(1)
    print(f"Presets folder: {presets_dir}")

    # Find output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = find_pc_map_file(presets_dir)
    print(f"Output file:    {output_path}")
    print()

    # Backup existing file if present
    if output_path.exists():
        backup = output_path.with_suffix(".ik.bak")
        import shutil
        shutil.copy2(output_path, backup)
        print(f"Backed up existing file to: {backup}")

    max_p = args.max_presets if args.max_presets else None
    generate_pc_map(presets_dir, args.folder, output_path, max_p)


if __name__ == "__main__":
    main()
