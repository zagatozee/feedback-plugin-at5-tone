"""
tone_params.py — Rocksmith 2014 / Rocksmith+ knob values -> AmpliTube 5 parameters.

Every Rocksmith gear knob is converted by *what it means*, not by its raw
number: the official Rocksmith knob definitions (data/rs_gear_defs.json, from
the game's gears.psarc) give each knob's unit, range and default, and the
AmpliTube side (data/at5_gear.json + PARAM_SPECS below, from AmpliTube's own
GearInfo, its factory presets and the Custom Shop Gear Models manual) gives
each AmpliTube parameter's unit, range and how the preset stores it.

Conversion kinds, in order of preference:
  * same physical unit  — ms->ms, Hz->Hz, dB->dB (or dB->linear gain), %->%.
  * frequency response  — Rocksmith EQs are rebuilt as filter curves and the
                          curve is sampled at the AmpliTube EQ's band centres.
  * position on range   — a "number" knob (1..100 etc.) lands at the same
                          relative position on the AmpliTube control's range.
  * enum / switch       — by label (Auto/On, LP/BP/HP, waveform, ratio...).

Knobs that are missing from a tone take the game's own default (Rocksmith
plays an unset knob at its DefaultValue, which is often not the middle).

Nothing is dropped silently: each conversion returns notes for any knob that
had to be approximated or has no AmpliTube counterpart, and tests check that
every knob of every recipe is either consumed or documented in its recipe.

This module is loaded by file path (feedBack's load_sibling / importlib), so
it only uses the standard library and finds its data next to itself.  No
`from __future__ import annotations`: dataclasses resolve string annotations
through sys.modules, which a by-path load may not have registered.
"""
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

DATA_DIR = Path(__file__).resolve().parent / "data"
NULL_GUID = "773b8ea7-b54a-4a3c-99df-ffbbf6d29271"


def _load(name: str) -> dict:
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


RS_GEAR: dict = _load("rs_gear_defs.json").get("gear", {})
AT5_DATA: dict = _load("at5_gear.json")
AT5_MODELS: dict = AT5_DATA.get("models", {})
AT5_BY_NAME: dict = {}
for _g, _m in AT5_MODELS.items():
    AT5_BY_NAME.setdefault((_m["kind"], _m["name"]), _g)
    AT5_BY_NAME.setdefault(("any", _m["name"]), _g)


def at5_guid(name: str, kind: str = "any") -> str | None:
    """AmpliTube model GUID by its GearInfo name (kind: stomp/rack/amp/cab/mic/any)."""
    return AT5_BY_NAME.get((kind, name))


def at5_kind(guid: str) -> str:
    return AT5_MODELS.get((guid or "").lower(), {}).get("kind", "")


def at5_name(guid: str) -> str:
    return AT5_MODELS.get((guid or "").lower(), {}).get("name", "")


# ─────────────────────────────────────────────────────────────────────────────
# UNIT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def db_to_lin(db: float) -> float:
    return 10.0 ** (db / 20.0)


def lin_to_db(lin: float) -> float:
    return 20.0 * math.log10(max(lin, 1e-12))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * clamp(t, 0.0, 1.0)


def log_pos(v: float, lo: float, hi: float) -> float:
    """Position of v on a logarithmic lo..hi scale (0..1)."""
    v = clamp(v, lo, hi)
    return math.log(v / lo) / math.log(hi / lo)


def log_lerp(lo: float, hi: float, t: float) -> float:
    return lo * (hi / lo) ** clamp(t, 0.0, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# AMPLITUBE PARAMETER SPECS
# ─────────────────────────────────────────────────────────────────────────────
#
# Spec = how one AmpliTube parameter is stored in an .at5p file:
#   ("knob", lo, hi)     plain number, usually a 0..10 knob
#   ("pct",)             0..100 (%), stored as is
#   ("ms", lo, hi)       milliseconds
#   ("hz", lo, hi)       Hertz
#   ("sec", lo, hi)      seconds
#   ("db", lo, hi)       decibels, stored as dB
#   ("gain", lo, hi)     decibels on the panel, stored as LINEAR gain (10^(dB/20))
#   ("vol",)             "-inf .. 0 dB" volume, stored as linear 0..1
#   ("thresh", lo, hi)   threshold in dB, stored as linear amplitude
#   ("enum", [labels])   text value
#   ("switch",)          0 / 1
#
# Sources: AmpliTube 5 Custom Shop Gear Models manual (control ranges) +
# values AmpliTube itself writes into its factory presets (storage format:
# e.g. the 7 Band Graphic's "+/-15 dB" bands are stored 0.178..5.62 = linear,
# while the 10 Band Graphic stores the same +/-15 dB as plain dB).
# Specs marked  # VERIFY  are inferred from preset values only — see
# docs/HUMAN_VERIFICATION.md.

K10 = ("knob", 0.0, 10.0)
PCT = ("pct",)
SW = ("switch",)
VOL = ("vol",)
G15 = ("gain", -15.0, 15.0)
DB15 = ("db", -15.0, 15.0)

PARAM_SPECS: dict[str, dict[str, tuple]] = {
    # ── EQ ────────────────────────────────────────────────────────────────
    "7 Band Graphic": {**{f"Band{f}": G15 for f in (100, 200, 400, 800, 1600, 3200, 6400)}, "Level": G15},
    "10 Band Graphic": {**{f"Band{f}": DB15 for f in (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)},
                        "Level": DB15},
    "6 Band EQ": {f"Band{f}": G15 for f in (100, 200, 400, 800, 1600, 3200)},              # VERIFY
    "GraphicEQ": {**{f"Band{f}": DB15 for f in (20, 25, 31, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315,
                                                 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150,
                                                 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000)},
                  "OutLevel": DB15, "Mode_GraphicEQ": ("enum", ["Low", "Mid", "Hi"])},       # VERIFY OutLevel
    "Parametric EQ 3": {"BassGain": G15, "BassFreq": ("hz", 20, 20000), "BassQ": ("knob", 0.1, 8),
                        "MidGain": G15, "MidFreq": ("hz", 20, 20000), "MidQ": ("knob", 0.1, 8),
                        "HighGain": G15, "HighFreq": ("hz", 20, 20000), "HighQ": ("knob", 0.1, 8),
                        "OutLevel": G15, "Mode_ParametricEQ": ("enum", ["Low", "Mid", "Hi"])},
    # ── dynamics ──────────────────────────────────────────────────────────
    "Compressor": {"Comp": ("knob", 0, 100), "Level": G15},
    "Dcomp": {"Sensitivity": K10, "Output": VOL},
    "SVX Compressor": {"Sensitivity": K10, "Output": VOL},
    "Tube Compressor": {"Drive": G15, "Attack": ("ms", 0.5, 100), "Release": ("ms", 20, 2000),   # VERIFY
                        "Ratio": ("knob", 1.0, 20.0), "OutLevel": G15},
    "Noise Gate": {"Threshold": ("thresh", -100.0, 0.0), "Release": ("ms", 20, 2000), "Depth": ("db", -100, -20)},
    "Gate": {"TriggerLevel": K10, "Mode": ("enum", ["Full", "Mid", "Hiss"])},
    # ── drive ─────────────────────────────────────────────────────────────
    "Overdrive": {"Drive": K10, "Tone": K10, "Level": K10},
    "Diode Overdrive": {"Drive": K10, "Tone": K10, "Volume": K10},
    "OverScream": {"Drive": K10, "Tone": K10, "Level": K10},
    "Distortion": {"Distortion": K10, "Tone": K10, "Volume": K10},
    "Metal Distortion": {"Gain": K10, "Bass": ("db", -15, 15), "Mid": ("db", -15, 15), "Treble": ("db", -15, 15),
                         "Frequency": K10, "Volume": K10},                                       # VERIFY EQ units
    "BigPig": {"Sustain": K10, "Tone": K10, "Volume": K10},
    "Fuzz Age": {"Fuzz": K10, "Volume": VOL},
    "Fuzz Age 2": {"Fuzz": K10, "Volume": VOL},
    "FuzzOne": {"Attack": K10, "Volume": VOL},
    "Class Fuzz": {"Drive": K10, "Volume": VOL},
    "XS Fuzz": {"Drive": K10, "Volume": VOL},
    "Booster": {"Gain": ("db", 0, 20)},
    "Treble Booster": {"Level": K10, "Type": ("knob", 70, 90)},
    "SVX-OD": {"Texture": K10, "Balance": K10},
    "AmpLess": {"Drive": K10, "Bass": K10, "Treble": K10, "Presence": K10, "Blend": K10, "Level": K10},
    "PROdrive": {"Dist": K10, "Filter": K10, "Volume": K10},
    "Tube Overdrive": {"Drive": K10, "EqLo": K10, "EqHi": K10, "Level": K10},
    "Crusher": {"InputGain": ("db", -40, 40), "OutputGain": ("gain", -40, 40), "Cutoff": ("hz", 20, 20000),
                "Decimation": ("knob", 1, 16)},                                                 # VERIFY gain storage
    # ── modulation ────────────────────────────────────────────────────────
    "Chorus": {"Rate": K10, "Depth": K10, "Level": K10, "BPMSync": SW},
    "Chorus-1": {"Chorus": K10, "Level": G15, "Mode": ("enum", ["Chorus", "Vibrato"]),
                 "VibratoDepth": K10, "VibratoRate": K10},
    "Analog Chorus": {"Chorus": K10, "Level": G15, "Mode": ("enum", ["Chorus", "Vibrato"]),
                      "VibratoDepth": K10, "VibratoRate": K10},
    "Digital Chorus": {"Rate": ("hz", 0.1, 8.0), "Depth": ("knob", 0, 100), "Mix": PCT, "OutLevel": G15,
                       "Waveform": ("enum", ["Sine", "Triangle", "Square"]),
                       "StereoMode": ("enum", ["Mono", "Stereo"]), "BPMSync": SW},
    "Triangle Chorus": {"Rate": K10, "Depth": K10, "AvgDelay": K10, "ChorusLevel": K10, "Phase": K10,
                        "OutLevel": G15},                                                        # VERIFY
    "Flanger": {"Rate": K10, "Depth": K10, "Feedback": K10, "Level": K10, "BPMSync": SW},
    "Analog Flanger": {"Rate": K10, "Depth": K10, "Manual": K10, "Res": K10},
    "Metal Flanger": {"Speed": K10, "Width": K10, "Manual": K10, "Regen": K10},
    "Electric Flanger": {"Rate": K10, "Range": K10, "Color": K10},
    "Digital Flanger": {"Rate": ("hz", 0.1, 8.0), "Depth": ("knob", 0, 100), "Feedback": K10, "Mix": PCT,
                        "OutLevel": G15, "Waveform": ("enum", ["Sine", "Triangle", "Square"]),
                        "StereoMode": ("enum", ["Mono", "Stereo"])},
    "Phaze Nine": {"Speed": K10},
    "Small Phazer": {"Rate": K10, "Color": SW},
    "Phazer10": {"Speed": K10, "Intensity": ("knob", 0, 3)},
    "Uni-V": {"Rate": K10, "Intensity": K10, "Volume": VOL, "ChorusVibrato": ("enum", ["Chorus", "Vibrato"])},
    "Opto Tremolo": {"Rate": K10, "Depth": K10, "BPMSync": SW},
    "Tremolo": {"Speed": K10, "Intensity": K10, "BPMSync": SW},
    "Shape Shifter": {"Rate": K10, "Depth": K10, "Shape": K10, "Wave": K10},
    "Rotary Speaker": {"Speed": ("hz", 0.5, 7.8), "Drive": PCT, "Balance": ("knob", 0, 100), "Mix": PCT,
                       "OutLevel": G15},
    "Stereo Enhancer": {"WideNarrow": ("knob", 0, 100)},                                        # VERIFY
    # ── filter / wah ──────────────────────────────────────────────────────
    "Wah": {"Mode": ("enum", ["On", "Auto"]), "Wah": PCT},
    "Wah 46": {"Mode": ("enum", ["On", "Auto"]), "Wah": PCT},
    "Wah 47": {"Mode": ("enum", ["On", "Auto"]), "Wah": PCT},
    "Bass Wah": {"Mode": ("enum", ["On", "Auto"]), "Wah": PCT},                                # VERIFY names
    "Envelope Filter": {"Freq": ("hz", 40, 20480), "Resonance": ("knob", 0.3, 10), "Depth": PCT,
                        "BandMode": ("enum", ["LP", "BP", "HP"]), "PoleMode": ("knob", 12, 24)},
    "SVX Envelope Filter": {"Freq": ("hz", 40, 20480), "Resonance": ("knob", 0.3, 10), "Depth": PCT,
                            "BandMode": ("enum", ["LP", "BP", "HP"]), "PoleMode": ("knob", 12, 24)},
    "Nu-Tron III": {"FilterMode": ("enum", ["LP", "BP", "HP"]), "Peak": K10, "Gain": K10,
                    "Range": SW, "Drive": SW},
    # ── delay ─────────────────────────────────────────────────────────────
    "Delay": {"Delay": ("ms", 1, 2000), "Feedback": PCT, "Level": K10, "BPMSync": SW},
    "DDelay": {"Delay": ("ms", 1, 800), "Feedback": K10, "Level": K10},
    "Digital Delay": {"DelayTime": ("ms", 1, 2000), "Feedback": PCT, "Filter": ("hz", 200, 20000), "Mix": PCT,
                      "OutLevel": G15, "Mode": ("enum", ["ST", "LR", "Mono", "LCR", "Doubl"]), "BPMSync": SW},
    "Analog Delay": {"Delay": ("ms", 25, 500), "Feedback": PCT, "Blend": PCT, "ChVib": PCT,
                     "Mode": ("enum", ["Chorus", "Vibrato"]), "BPMSync": SW},
    "EchoMan": {"Delay": ("ms", 25, 500), "Feedback": PCT, "Blend": PCT, "ChVib": PCT,
                "Mode": ("enum", ["Chorus", "Vibrato"]), "BPMSync": SW},
    "Tape Echo": {"Time": ("ms", 60, 2000), "Feedback": K10, "EchoLevel": K10, "Brightness": K10,
                  "WowFilter": K10, "OutLevel": ("db", -15, 15), "BPMSync": SW},                # VERIFY ranges
    "EP Tape Echo": {"Delay": ("ms", 20, 750), "Sustain": K10, "Volume": K10},                  # VERIFY
    # ── reverb ────────────────────────────────────────────────────────────
    "'63 Reverb": {"Dwell": K10, "Mixer": K10, "Tone": K10},
    "Digital Reverb": {"DecayTime": ("sec", 0.6, 14.0), "Density": ("knob", 0, 99), "Color": ("hz", 2000, 20000),
                      "Mix": PCT, "OutLevel": G15},
    "Plate Reverb": {"Mix": PCT, "Decay": ("knob", 0, 100), "PreDelay": ("ms", 0, 250), "Color": ("knob", 0, 100),
                     "Size": ("knob", 0, 100), "Modulation": ("knob", 0, 100), "Hpf": ("knob", 0, 100)},  # VERIFY
    "Hall Reverb": {"Mix": PCT, "Decay": ("knob", 0, 100), "PreDelay": ("ms", 0, 250), "Color": ("knob", 0, 100),
                    "Size": ("knob", 0, 100), "Hpf": ("knob", 0, 100)},                         # VERIFY
    "Room Reverb": {"Mix": PCT, "Decay": ("knob", 0, 100), "PreDelay": ("ms", 0, 250), "Color": ("knob", 0, 100),
                    "Size": ("knob", 0, 100), "Modulation": ("knob", 0, 100), "Hpf": ("knob", 0, 100)},  # VERIFY
    # ── pitch ─────────────────────────────────────────────────────────────
    "Pitch Shifter": {"Coarse": ("knob", -24, 24), "Fine": ("knob", -50, 50), "Level": K10},
    "Pitch Shift": {"Pitch": ("knob", -12, 12), "Detune": ("knob", -50, 50), "PitchLevel": K10,
                    "Feedback": K10, "PreDelay": ("knob", 1, 100), "OutLevel": G15, "Stereo": SW},  # VERIFY
    "Octa-V": {"Drive": K10, "Volume": VOL},
    "Octav": {"Direct": VOL, "Oct1": VOL, "Oct2": VOL},
    "SVX-OCT": {"Direct": K10, "Octave": K10},
    "OctoBlue": {"Blend": K10, "Level": K10},
    "Wharmonator": {"Mode": ("enum", ["Harm", "Bend"]), "Pedal": PCT,
                    "Harm": ("enum", ["vOct ^Oct", "Deep", "Shallow", "^4th ^5th", "^5th ^7th"]),
                    "Bend": ("enum", ["v2Oct", "vOct", "^Oct", "^2Oct"])},                     # VERIFY labels
    # ── other ─────────────────────────────────────────────────────────────
    "Acoustic Sim": {"Mix": K10, "Bass": K10, "Treble": K10, "Body": ("knob", 1, 3), "Top": K10,
                     "BodyType": ("knob", 1, 3), "Pickup": ("enum", ["S", "H"]), "ABC": ("enum", ["A", "B", "C"])},  # VERIFY
    "Pre EQ 3": {"PreampGain": K10, "LowGain": ("gain", -99, 20), "LowFreq": ("hz", 25, 500),
                 "LowWidth": K10, "MidGain": ("gain", -99, 20), "MidFreq": ("hz", 150, 2500), "MidWidth": K10,
                 "HighGain": ("gain", -99, 20), "HighFreq": ("hz", 600, 10000), "HighWidth": K10,
                 "EQBypass": SW},
    "Volume": {"Volume": PCT, "MinLevel": K10},
    "Swell": {"Time": ("ms", 10, 2000), "Sens": K10, "Depth": ("db", -90, 0)},                  # VERIFY
    "Tape Cassette": {"Saturation": K10, "Wow": PCT, "Flutter": PCT, "Noise": PCT, "Erosion": PCT,
                      "Snaps": PCT},                                                             # VERIFY
}


def infer_spec(name: str, stats: dict) -> tuple:
    """Fallback spec from the values AmpliTube's own presets store."""
    if stats.get("values") and "min" not in stats:
        return ("enum", list(stats["values"]))
    lo, hi = stats.get("min", 0.0), stats.get("max", 10.0)
    n = name.lower()
    if {lo, hi} <= {0.0, 1.0} and stats.get("distinct", 2) <= 2:
        return SW
    if any(k in n for k in ("freq", "cutoff", "color")) and hi > 100:
        return ("hz", 20, 20000)
    if any(k in n for k in ("delay", "time")) and hi > 20:
        return ("ms", 1, 2000)
    if any(k in n for k in ("volume", "output", "level", "direct")) and 0 <= lo and hi <= 1.0001:
        return VOL
    if any(k in n for k in ("level", "gain", "band")) and lo >= 0.17 and hi <= 5.7 and hi > 1.0:
        return G15
    if lo < 0 and hi <= 15:
        return DB15
    if hi <= 10:
        return K10
    if hi <= 100:
        return ("knob", 0, 100)
    return ("knob", lo, hi)


def at5_param_specs(guid: str) -> dict[str, tuple]:
    """All known parameter specs for an AmpliTube model (curated, else inferred)."""
    m = AT5_MODELS.get((guid or "").lower(), {})
    specs = {k: infer_spec(k, s) for k, s in m.get("params", {}).items()}
    specs.update(PARAM_SPECS.get(m.get("name", ""), {}))
    return specs


def encode(spec: tuple, value) -> str:
    """Physical/panel value -> the string AmpliTube stores, clamped to the spec range."""
    kind = spec[0]
    if kind == "enum":
        return str(value)
    if kind == "switch":
        return "1" if value and float(value) >= 0.5 else "0"
    v = float(value)
    if kind == "pct":
        v = clamp(v, 0.0, 100.0)
    elif kind in ("knob", "ms", "hz", "sec", "db"):
        v = clamp(v, spec[1], spec[2])
    elif kind == "gain":
        v = db_to_lin(clamp(v, spec[1], spec[2]))
    elif kind == "vol":                       # value given in dB (-inf..0)
        v = 0.0 if v <= -90 else db_to_lin(min(v, 0.0))
    elif kind == "thresh":                    # value given in dB
        v = db_to_lin(clamp(v, spec[1], spec[2]))
    return f"{v:.6g}"


def spec_pos_value(spec: tuple, pos: float):
    """The panel value at relative position pos (0..1) of an AmpliTube control."""
    kind = spec[0]
    if kind == "pct":
        return lerp(0, 100, pos)
    if kind in ("knob", "db", "gain", "thresh"):
        return lerp(spec[1], spec[2], pos)
    if kind in ("ms", "hz", "sec"):
        return log_lerp(spec[1], spec[2], pos)
    if kind == "vol":                         # audio-taper volume: 0 -> -inf, 1 -> 0 dB
        return -200.0 if pos <= 0.001 else 40.0 * math.log10(pos)
    if kind == "switch":
        return 1 if pos >= 0.5 else 0
    if kind == "enum":
        labels = spec[1]
        return labels[min(len(labels) - 1, int(pos * len(labels)))]
    return pos


# ─────────────────────────────────────────────────────────────────────────────
# ROCKSMITH KNOB ACCESS
# ─────────────────────────────────────────────────────────────────────────────

def rs_knob_defs(rs_key: str) -> dict[str, dict]:
    """{short knob name: definition} for a Rocksmith gear key."""
    g = RS_GEAR.get(rs_key)
    if not g:
        return {}
    out = {}
    for k in g.get("knobs", []):
        short = k["key"][len(rs_key) + 1:] if k["key"].startswith(rs_key + "_") else k["key"]
        out[short] = k
    return out


class Knobs:
    """Rocksmith knob values for one gear slot, with the game's defaults filled
    in and access tracking (so unused knobs can be reported)."""

    def __init__(self, rs_key: str, values: dict | None):
        self.rs_key = rs_key
        self.defs = rs_knob_defs(rs_key)
        self.raw = {}
        for k, v in (values or {}).items():
            short = k[len(rs_key) + 1:] if k.startswith(rs_key + "_") else k
            try:
                self.raw[short] = float(v)
            except (TypeError, ValueError):
                pass
        self.used: set[str] = set()

    def names(self) -> list[str]:
        return list(self.defs) or list(self.raw)

    def has(self, name: str) -> bool:
        return name in self.defs or name in self.raw

    def given(self, name: str) -> bool:
        return name in self.raw

    def v(self, name: str, default: float | None = None) -> float:
        """Physical value (game unit; kHz is returned in Hz), default-filled."""
        self.used.add(name)
        d = self.defs.get(name, {})
        if name in self.raw:
            val = self.raw[name]
        elif "default" in d:
            val = d["default"]
        elif default is not None:
            val = default
        else:
            val = (d.get("min", 0.0) + d.get("max", 100.0)) / 2
        if "min" in d and "max" in d:
            val = clamp(val, d["min"], d["max"])
        if d.get("unit") == "khz":
            val *= 1000.0
        return val

    def pos(self, name: str) -> float:
        """Relative position 0..1 on the Rocksmith knob's own range."""
        val = self.v(name)
        d = self.defs.get(name, {})
        lo, hi = d.get("min", 0.0), d.get("max", 100.0)
        if d.get("unit") == "khz":
            lo, hi = lo * 1000.0, hi * 1000.0
        return 0.5 if hi == lo else clamp((val - lo) / (hi - lo), 0.0, 1.0)

    def label(self, name: str) -> str:
        """Enum label for an enum knob ('' if not an enum)."""
        val = self.v(name)
        for lbl, num in self.defs.get(name, {}).get("enum", {}).items():
            if abs(num - val) < 0.5:
                return lbl
        return ""

    def unit(self, name: str) -> str:
        return self.defs.get(name, {}).get("unit", "number")


# ─────────────────────────────────────────────────────────────────────────────
# EQ RESPONSE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
#
# RBJ "Audio EQ Cookbook" biquads, magnitude evaluated analytically.  A
# Rocksmith EQ becomes a list of bands (type, f0, gain dB, Q); its summed
# magnitude response is sampled at each AmpliTube band centre.  AmpliTube's
# graphic bands are themselves peaking filters, so sampling is an
# approximation, but it preserves boosts/cuts at the right frequencies, which
# a "band 1 -> band 1" copy does not when the band layouts differ.

FS = 48000.0


def _biquad_mag_db(b, a, f):
    w = 2 * math.pi * f / FS
    z1 = complex(math.cos(-w), math.sin(-w))
    z2 = z1 * z1
    num = b[0] + b[1] * z1 + b[2] * z2
    den = a[0] + a[1] * z1 + a[2] * z2
    return 20 * math.log10(max(abs(num / den), 1e-12))


def _band_coeffs(kind, f0, gain_db, q):
    A = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * min(f0, FS * 0.45) / FS
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2 * q)
    if kind == "peak":
        b = (1 + alpha * A, -2 * cw, 1 - alpha * A)
        a = (1 + alpha / A, -2 * cw, 1 - alpha / A)
    elif kind == "lowshelf":
        sa = 2 * math.sqrt(A) * alpha
        b = (A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sa))
        a = ((A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa)
    else:  # highshelf
        sa = 2 * math.sqrt(A) * alpha
        b = (A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sa))
        a = ((A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa)
    return b, a


def eq_response_db(bands, f: float) -> float:
    """Summed magnitude (dB) of a list of (kind, f0, gain_db, q) bands at f."""
    return sum(_biquad_mag_db(*_band_coeffs(k, f0, g, q), f) for k, f0, g, q in bands if abs(g) > 1e-6)


def graphic_q(centres: list[float]) -> float:
    """Constant-Q for a graphic EQ whose bands sit at `centres` (bandwidth =
    band spacing in octaves)."""
    if len(centres) < 2:
        return 1.0
    octs = [math.log2(b / a) for a, b in zip(centres, centres[1:])]
    n = sum(octs) / len(octs)
    return math.sqrt(2 ** n) / (2 ** n - 1)


def fit_graphic(bands, at5_centres: list[float], lo=-15.0, hi=15.0) -> list[float]:
    """AmpliTube graphic band gains (dB) whose own peaking bands best rebuild
    the Rocksmith response.  Starts from the sampled response and corrects the
    overlap between neighbouring AmpliTube bands with a few relaxation passes."""
    target = [eq_response_db(bands, f) for f in at5_centres]
    q = graphic_q(at5_centres)
    gains = [clamp(t, lo, hi) for t in target]
    for _ in range(12):
        rebuilt = [eq_response_db([("peak", c, g, q) for c, g in zip(at5_centres, gains)], f)
                   for f in at5_centres]
        gains = [clamp(g + 0.6 * (t - r), lo, hi) for g, t, r in zip(gains, target, rebuilt)]
    return gains


# ─────────────────────────────────────────────────────────────────────────────
# RECIPES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Recipe:
    """How to convert one Rocksmith gear model.

    target   AmpliTube model name (GearInfo name) — the closest model that can
             represent the Rocksmith controls.
    kind     "stomp" or "rack" (which AmpliTube catalogue the name is in).
    params   {AmpliTube param: fn(Knobs, specs) -> panel value}.
    approx   {Rocksmith knob: why it cannot be carried over exactly}; these are
             reported as notes on every conversion, never dropped silently.
    stomp_alt  AmpliTube *stomp* to use when this recipe's target is a rack
               model but the pedal sits before the amp (stomp-only slots).
    """
    target: str
    kind: str
    params: dict[str, Callable]
    approx: dict[str, str] = field(default_factory=dict)
    stomp_alt: str | None = None


def same(name: str, scale: float = 1.0, offset: float = 0.0):
    """Same physical unit (ms, Hz, dB, %), optional linear rescale."""
    return lambda k, s: k.v(name) * scale + offset


def pos(name: str, lo: float | None = None, hi: float | None = None, invert: bool = False):
    """Same relative position.  lo/hi narrow the AmpliTube range used."""
    def f(k, s, _spec=None):
        p = k.pos(name)
        p = 1 - p if invert else p
        return ("__pos__", p, lo, hi)
    return f


def const(value):
    return lambda k, s: value


def hz_to_knob(name: str, lo_hz: float, hi_hz: float):
    """A rate in Hz onto a 0..10 knob that spans lo_hz..hi_hz (log taper)."""
    return lambda k, s: 10.0 * log_pos(k.v(name), lo_hz, hi_hz)


def pct_of(name: str, lo: float = 0.0, hi: float = 10.0):
    """A Rocksmith % / 1..100 knob read as a percentage onto lo..hi."""
    return lambda k, s: lerp(lo, hi, k.v(name) / 100.0)


def mix_to_levels(mix_name: str):
    """Rocksmith Mix (wet %) -> (dry dB, wet dB) with an equal-power law."""
    def f(k):
        m = clamp(k.v(mix_name) / 100.0, 0.0, 1.0)
        dry = math.cos(m * math.pi / 2)
        wet = math.sin(m * math.pi / 2)
        return (lin_to_db(dry) if dry > 1e-4 else -200.0, lin_to_db(wet) if wet > 1e-4 else -200.0)
    return f


# ── EQ recipe builders ─────────────────────────────────────────────────────

def rs_graphic_bands(k: Knobs, centres: dict[str, float]):
    q = graphic_q(sorted(centres.values()))
    return [("peak", f, k.v(name), q) for name, f in centres.items()]


def graphic_recipe(target: str, kind: str, rs_bands: dict[str, float], at5_bands: dict[str, float],
                   level_param: str | None = None, extra=None, approx=None, stomp_alt=None):
    """Rocksmith graphic EQ -> AmpliTube graphic EQ via response fitting."""
    names = list(at5_bands)
    centres = [at5_bands[n] for n in names]

    def solve(k):
        if "_fit" not in k.__dict__:
            k._fit = dict(zip(names, fit_graphic(rs_graphic_bands(k, rs_bands), centres)))
        return k._fit

    params = {n: (lambda n: lambda k, s: solve(k)[n])(n) for n in names}
    if level_param:
        params[level_param] = const(0.0)
    params.update(extra or {})
    return Recipe(target, kind, params, approx or {}, stomp_alt)


def parametric_bands(k: Knobs, layout):
    """layout: list of (kind, gain knob, freq knob, q spec) where q spec is a
    number or an enum knob name with {label: Q}."""
    bands = []
    for kind, g, fq, qs in layout:
        if isinstance(qs, tuple):
            qname, table = qs
            q = table.get(k.label(qname), 0.7)
        else:
            q = qs
        bands.append((kind, k.v(fq), k.v(g), q))
    return bands


AT5_7BAND = {f"Band{f}": float(f) for f in (100, 200, 400, 800, 1600, 3200, 6400)}
AT5_10BAND = {f"Band{f}": float(f) for f in (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)}
AT5_31BAND = {f"Band{f}": float(f) for f in (20, 25, 31, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400,
                                             500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000,
                                             6300, 8000, 10000, 12500, 16000, 20000)}
WIDE_NARROW = {"Wide": 0.7, "Narrow": 2.0}       # VERIFY: Rocksmith Studio EQ Q values not published


def parametric_recipe(layout, approx=None):
    """Rocksmith parametric EQ -> AmpliTube 31-band GraphicEQ rack (fine
    enough to reproduce narrow bands), with a 10-band stomp fallback."""
    def solve(k, bands_map):
        key = "_fit" + str(len(bands_map))
        if key not in k.__dict__:
            names = list(bands_map)
            g = fit_graphic(parametric_bands(k, layout), [bands_map[n] for n in names])
            k.__dict__[key] = dict(zip(names, g))
        return k.__dict__[key]

    params = {n: (lambda n: lambda k, s: solve(k, AT5_31BAND)[n])(n) for n in AT5_31BAND}
    params["OutLevel"] = const(0.0)
    params["Mode_GraphicEQ"] = const("Mid")
    return Recipe("GraphicEQ", "rack", params, approx or {}, stomp_alt="10 Band Graphic")


def stomp_alt_params(rs_key: str, k: Knobs) -> dict | None:
    """Parameter functions for a recipe's stomp_alt target, when it needs
    something other than generic matching (EQs)."""
    r = RECIPES.get(rs_key)
    if not r or r.stomp_alt != "10 Band Graphic":
        return None
    layout = PARAMETRIC_LAYOUTS.get(rs_key)
    if layout:
        bands = parametric_bands(k, layout)
    else:
        return None
    names = list(AT5_10BAND)
    g = fit_graphic(bands, [AT5_10BAND[n] for n in names])
    out = {n: (lambda v: lambda k, s: v)(v) for n, v in zip(names, g)}
    out["Level"] = const(0.0)
    return out


SHELF_Q = 0.707
PARAMETRIC_LAYOUTS = {
    "Rack_StudioEQ": [("lowshelf", "Bass", "BassFreq", SHELF_Q),
                      ("peak", "LoMid", "LoMidFreq", ("LoMidQ", WIDE_NARROW)),
                      ("peak", "HiMid", "HiMidFreq", ("HiMidQ", WIDE_NARROW)),
                      ("highshelf", "Treble", "TrebleFreq", SHELF_Q)],
    "Rack_StudioGraphicEQ": [("lowshelf", "Bass", "BassFreq", SHELF_Q),
                             ("peak", "LoMid", "LoMidFreq", 1.0),
                             ("peak", "Mid", "MidFreq", 1.0),
                             ("peak", "HiMid", "HiMidFreq", 1.0),
                             ("highshelf", "Treble", "TrebleFreq", SHELF_Q)],
}


# ── wah / filter helpers ───────────────────────────────────────────────────

def wah_mode(k, s):
    """Rocksmith Auto-Mode ON -> AmpliTube Auto; OFF -> On (manual pedal)."""
    return "Auto" if k.label("Auto").upper() == "ON" else "On"


def wah_pedal(k, s):
    return k.v("Pedal")      # Rocksmith 1..100 pedal position -> AmpliTube 0..100 %


FILTER_TYPES = {"LP": "LP", "BP": "BP", "HP": "HP"}


def filter_mode(name):
    return lambda k, s: FILTER_TYPES.get(k.label(name).upper(), "BP")


def env_depth(k, s):
    """Rocksmith Sensitivity (1..100) -> envelope Depth (%)."""
    return k.v("Sens")


def env_freq(k, s):
    """Base cutoff — Rocksmith's auto-filters have no frequency knob; their
    range starts low.  A lower Mix/Res setting is not a frequency."""
    return 200.0          # VERIFY: Rocksmith filter base frequency unknown


# ── reverb helpers ─────────────────────────────────────────────────────────

def reverb_seconds(name, lo=0.6, hi=14.0):
    """Rocksmith reverb Time/Decay (1..100, unitless) -> seconds on a log scale."""
    return lambda k, s: log_lerp(0.4, 8.0, k.pos(name))      # VERIFY: Rocksmith decay curve unknown


def tone_to_hz(name, lo=2000.0, hi=20000.0):
    return lambda k, s: log_lerp(lo, hi, k.pos(name))


# ── recipes table ──────────────────────────────────────────────────────────
#
# Keys are Rocksmith gear keys.  Knobs listed in `approx` are reported as
# notes on each conversion.  Comments name the reasoning for non-obvious
# choices.

def _drive(target, drive, tone, level, gain_knob="Gain", tone_knob="Tone", approx=None, extra=None):
    p = {drive: pos(gain_knob)}
    if tone and tone_knob:
        p[tone] = pos(tone_knob)
    if level:
        p[level] = const(("__keep_unity__",))
    p.update(extra or {})
    return Recipe(target, "stomp", p, approx or {})


def _amp_eq_fit(k: Knobs) -> dict:
    """Rocksmith 'Amp EQ' pedal (3 unitless knobs + frequency selectors) ->
    7 Band Graphic gains, via the response fit."""
    if "_ampeq" not in k.__dict__:
        def db(name):
            return (k.v(name) - 50.5) / 49.5 * 12.0
        bands = [("lowshelf", {"One": 80.0, "Two": 160.0}.get(k.label("BassFreq"), 160.0), db("Bass"), SHELF_Q),
                 ("peak", {"One": 400.0, "Two": 800.0, "Three": 1600.0}.get(k.label("MidShift"), 800.0), db("Mid"), 0.9),
                 ("highshelf", {"One": 3200.0, "Two": 6400.0}.get(k.label("TrebleFreq"), 6400.0), db("Treble"), SHELF_Q)]
        names = list(AT5_7BAND)
        k._ampeq = dict(zip(names, fit_graphic(bands, [AT5_7BAND[n] for n in names])))
    return k._ampeq


def _di_db(k: Knobs, name: str) -> float:
    """Unitless 1..100 tone knob -> -12..+12 dB around the middle (VERIFY)."""
    return (k.v(name) - 50.5) / 49.5 * 12.0


LEVEL_NOTE = "Rocksmith drive pedals have no output-level knob (level is fixed); AmpliTube level set to unity-ish (5/10 or 0 dB)."

RECIPES: dict[str, Recipe] = {
    # ── EQ ────────────────────────────────────────────────────────────────
    "Rack_StudioEQ": parametric_recipe(PARAMETRIC_LAYOUTS["Rack_StudioEQ"]),
    "Rack_StudioGraphicEQ": parametric_recipe(PARAMETRIC_LAYOUTS["Rack_StudioGraphicEQ"]),
    "Pedal_EQ5": graphic_recipe("7 Band Graphic", "stomp",
                                {"63": 63.0, "250": 250.0, "750": 750.0, "2200": 2200.0, "5700": 5700.0},
                                AT5_7BAND, "Level",
                                approx={"63": "63 Hz sits below the 7-band's lowest band (100 Hz); it is reproduced by the curve fit, so very low boosts are softened."}),
    "Pedal_EQ8": graphic_recipe("10 Band Graphic", "stomp",
                                {str(f): float(f) for f in (50, 100, 200, 400, 800, 1600, 3200, 6400)},
                                AT5_10BAND, "Level"),
    "Bass_Pedal_BassEQ8": graphic_recipe("10 Band Graphic", "stomp",
                                         {str(f): float(f) for f in (30, 75, 185, 460, 1100, 2700, 6800, 16000)},
                                         AT5_10BAND, "Level"),
    # ── dynamics ──────────────────────────────────────────────────────────
    "Pedal_Compression": Recipe("Compressor", "stomp",
                                {"Comp": pos("Comp", 0, 100), "Level": const(0.0)},
                                {"Attack": "AmpliTube's Compressor stomp has fixed attack/release (only Comp and Level).",
                                 "Release": "AmpliTube's Compressor stomp has fixed attack/release (only Comp and Level)."}),
    "Pedal_Swole": Recipe("Dcomp", "stomp",
                          {"Sensitivity": pos("Smash"), "Output": const(-6.0)},
                          {"Rate": "Dcomp (Dynacomp) has no release/rate control."}),
    "Bass_Pedal_MBComp": Recipe("Tube Compressor", "rack",
                                {"Drive": lambda k, s: lerp(-6, 15, k.pos("Compress")),
                                 "Release": lambda k, s: log_lerp(1500, 50, k.pos("Rate")),
                                 "Attack": const(12.0), "Ratio": const(4.0), "OutLevel": const(0.0)},
                                {"Filter": "Multiband crossover (Transition Band) has no equivalent: AmpliTube has no multiband compressor; compressed full-band."},
                                stomp_alt="SVX Compressor"),
    "Rack_StudioCompressor": Recipe("Tube Compressor", "rack",
                                    {"Drive": lambda k, s: clamp(-k.v("Threshold") * 0.6 - 6, -15, 15),
                                     "Ratio": lambda k, s: {"1.5:1": 1.5, "2:1": 2, "4:1": 4, "8:1": 8, "20:1": 20}.get(k.label("Ratio"), 4),
                                     "Attack": lambda k, s: clamp(k.v("Attack"), 0.5, 100),
                                     "Release": same("Release"), "OutLevel": const(0.0)},
                                    {"Threshold": "Tube Compressor has no threshold; mapped to input Drive (lower threshold = more drive). VERIFY by ear."},
                                    stomp_alt="Compressor"),
    "Pedal_NoiseGate": Recipe("Noise Gate", "stomp",
                              {"Threshold": same("Thresh"),
                               "Release": lambda k, s: log_lerp(1000, 20, k.pos("Rate")),
                               "Depth": const(-60.0)}),
    # ── overdrive / distortion / fuzz ─────────────────────────────────────
    "Pedal_CustomDrive": _drive("Overdrive", "Drive", "Tone", "Level",
                                approx={"Voice": "UK/CA voicing switch has no equivalent on AmpliTube Overdrive.",
                                        "__level__": LEVEL_NOTE}),
    "Pedal_SuperDrive": _drive("Overdrive", "Drive", "Tone", "Level", approx={"__level__": LEVEL_NOTE}),
    "Pedal_MarshallGuvnorPlus": Recipe("The Ambass'dor", "stomp",          # AmpliTube's Guv'Nor model
                                       {"Gain": pos("Gain"), "Bass": pos("Bass"), "Mid": pos("Mid"),
                                        "Treble": pos("Treble"), "Level": const(5.0)},
                                       {"Deep": "the Guv'nor Plus 'Deep' (sub-bass) control is missing from The Ambass'dor (original Guv'Nor).",
                                        "__level__": LEVEL_NOTE}),
    "Pedal_LineDrive": Recipe("Booster", "stomp", {"Gain": lambda k, s: lerp(0, 20, k.pos("Gain"))},
                              {"Tone": "AmpliTube Booster has no tone control."}),
    "Pedal_Distortion": _drive("Distortion", "Distortion", "Tone", "Volume", approx={"__level__": LEVEL_NOTE}),
    "Pedal_VintageDistortion": _drive("Distortion", "Distortion", "Tone", "Volume", approx={"__level__": LEVEL_NOTE}),
    "Bass_Pedal_BassDistortion": _drive("Distortion", "Distortion", "Tone", "Volume",
                                        approx={"Filter": "Bass Distortion's low-end Filter (dry bass blend) has no knob on AmpliTube Distortion.",
                                                "__level__": LEVEL_NOTE}),
    "Pedal_ShredZone": Recipe("Metal Distortion", "stomp",
                              {"Gain": pos("Gain"), "Bass": same("Bass"), "Mid": same("Mid"),
                               "Treble": same("Treble"), "Frequency": const(5.0), "Volume": const(5.0)}),
    "Pedal_MetalDistortion": Recipe("Metal Distortion", "stomp",
                                    {"Gain": pos("Gain"),
                                     "Treble": lambda k, s: lerp(-9, 9, k.pos("Tone")),
                                     "Bass": const(0.0), "Mid": const(0.0), "Frequency": const(5.0),
                                     "Volume": const(5.0)},
                                    {"Tone": "single Tone knob mapped onto the Treble band (+/-9 dB)."}),
    "Pedal_GermaniumDrive": Recipe("Fuzz Age", "stomp", {"Fuzz": pos("Gain"), "Volume": const(-6.0)},
                                   {"Tone": "Fuzz Age (Fuzz Face) has no tone control — the original has none either."}),
    "Pedal_FuzzWasHe": Recipe("Fuzz Age 2", "stomp", {"Fuzz": pos("Gain"), "Volume": const(-6.0)},
                              {"Tone": "Fuzz Age 2 has no tone control."}),
    "Pedal_BuzzOne": Recipe("FuzzOne", "stomp", {"Attack": pos("Gain"), "Volume": const(-6.0)},
                            {"Tone": "FuzzOne (Tone Bender) has no tone control."}),
    "Pedal_BuzzToo": _drive("BigPig", "Sustain", "Tone", "Volume", approx={"__level__": LEVEL_NOTE}),
    "Pedal_CaptFuzzle": Recipe("BigPig", "stomp",
                               {"Sustain": lambda k, s: lerp(0, 10, k.v("Gain") / 150.0),
                                "Tone": pos("Tone"), "Volume": const(5.0)}),
    "Bass_Pedal_BassFuzz": _drive("BigPig", "Sustain", "Tone", "Volume",
                                  approx={"Filter": "Bass Fuzz Filter (dry low-end blend) has no BigPig equivalent.",
                                          "__level__": LEVEL_NOTE}),
    "Pedal_RangeBooster": Recipe("Treble Booster", "stomp",
                                 {"Level": pos("Boost"), "Type": const(70)}),
    "Bass_Pedal_BassOverdrive": Recipe("SVX-OD", "stomp",
                                       {"Texture": pos("Gain"), "Balance": lambda k, s: k.v("Blend") / 10.0},
                                       {"Tone": "SVX-OD has only Texture and Balance.",
                                        "Filter": "SVX-OD has only Texture and Balance."}),
    "Bass_Pedal_EdenWTDI": Recipe("AmpLess", "stomp",
                                  {"Drive": pos("Gain"),
                                   "Bass": lambda k, s: 5 + k.v("Bass") * 5 / 12,
                                   "Treble": lambda k, s: 5 + k.v("Treble") * 5 / 12,
                                   "Presence": lambda k, s: k.v("Enhance") / 10.0,
                                   "Blend": const(10.0), "Level": const(5.0)},
                                  {"Mid": "AmpLess has no mid control (its manual: bass/treble shape the mids).",
                                   "LoShift": "Bass Boost switch: no equivalent.", "MidShift": "Mid-Shift switch: no equivalent.",
                                   "Compression": "AmpLess has no compressor."}),
    # ── modulation ────────────────────────────────────────────────────────
    "Rack_StudioChorus": Recipe("Digital Chorus", "rack",
                                {"Rate": lambda k, s: clamp(k.v("Rate"), 0.1, 8.0),
                                 "Depth": same("Depth"), "Mix": same("Mix"),
                                 "StereoMode": lambda k, s: "Stereo" if k.v("Stereo") >= 50 else "Mono",
                                 "Waveform": const("Sine"), "OutLevel": const(0.0)},
                                {"Delay": "chorus base delay time has no Digital Chorus control.",
                                 "LoFilter": "chorus wet low-cut filter has no Digital Chorus control.",
                                 "HiFilter": "chorus wet high-cut filter has no Digital Chorus control.",
                                 "Stereo": "stereo spread reduced to the Stereo/Mono switch (>=50 % -> Stereo)."},
                                stomp_alt="Chorus"),
    "Pedal_DigitalChorus": Recipe("Digital Chorus", "rack",
                                  {"Rate": lambda k, s: clamp(k.v("Rate"), 0.1, 8.0), "Depth": same("Depth"),
                                   "Mix": same("Mix"), "Waveform": const("Sine"), "OutLevel": const(0.0)},
                                  {"LoFilter": "wet low-cut filter: no equivalent.",
                                   "HiFilter": "wet high-cut filter: no equivalent."},
                                  stomp_alt="Chorus"),
    "Pedal_Chorus": Recipe("Chorus", "stomp",
                           {"Rate": hz_to_knob("Rate", 0.1, 10), "Depth": pct_of("Depth"),
                            "Level": const(5.0)},
                           {"Mix": "AmpliTube Chorus stomp has no mix (fixed blend); Rocksmith Mix not representable — consider Digital Chorus rack."}),
    "Pedal_VintageChorus": Recipe("Chorus-1", "stomp",
                                  {"Chorus": pct_of("Depth"), "Mode": const("Chorus"), "Level": const(0.0),
                                   "VibratoRate": hz_to_knob("Rate", 0.1, 10)},
                                  {"Mix": "Chorus-1 (CE-1) has a fixed chorus blend.",
                                   "Rate": "CE-1 chorus speed is fixed; Rate set on the vibrato-rate control for reference only."}),
    "Pedal_Chorus20": Recipe("Chorus-1", "stomp",
                             {"Chorus": pct_of("Depth"), "Mode": const("Chorus"), "Level": const(0.0),
                              "VibratoRate": hz_to_knob("Rate", 0.1, 10)},
                             {"Mix": "Chorus-1 (CE-1) has a fixed chorus blend.",
                              "Rate": "CE-1 chorus speed is fixed; Rate set on the vibrato-rate control for reference only."}),
    "Bass_Pedal_BassChorus": Recipe("Digital Chorus", "rack",
                                    {"Rate": lambda k, s: clamp(k.v("Rate"), 0.1, 8.0), "Depth": same("Depth"),
                                     "Mix": same("Mix"), "Waveform": const("Sine"), "OutLevel": const(0.0)},
                                    {"LoFilter": "bass chorus low filter (keeps lows dry) has no equivalent."},
                                    stomp_alt="Analog Chorus"),
    "Pedal_ModernFlanger": Recipe("Flanger", "stomp",
                                  {"Rate": pos("Rate"), "Depth": pct_of("Depth"), "Feedback": pct_of("Regen"),
                                   "Level": const(5.0)},
                                  {"Mix": "AmpliTube Flanger stomp has no mix control."}),
    "Rack_StudioFlanger": Recipe("Digital Flanger", "rack",
                                 {"Rate": lambda k, s: clamp(k.v("Rate"), 0.1, 8.0), "Depth": same("Depth"),
                                  "Feedback": pct_of("Regen"), "Mix": same("Mix"), "Waveform": const("Sine"),
                                  "OutLevel": const(0.0)},
                                 {"Tone": "flanger tone filter has no Digital Flanger control."},
                                 stomp_alt="Flanger"),
    "Bass_Pedal_BassFlanger": Recipe("Flanger", "stomp",
                                     {"Rate": pos("Rate"), "Depth": pct_of("Depth"), "Feedback": const(5.0),
                                      "Level": const(5.0)},
                                     {"Mix": "AmpliTube Flanger stomp has no mix control.",
                                      "Filter": "bass flanger low filter has no equivalent."}),
    "Pedal_80sFlanger": Recipe("Metal Flanger", "stomp",
                               {"Speed": pos("Rate"), "Width": pct_of("Depth"), "Manual": const(5.0),
                                "Regen": const(5.0)},
                               {"Mix": "Metal Flanger (Electric Mistress-style) has no mix control."}),
    "Pedal_ClassicFlanger": Recipe("Analog Flanger", "stomp",
                                   {"Rate": pos("Rate"), "Depth": pct_of("Depth"), "Manual": const(5.0),
                                    "Res": const(5.0)},
                                   {"Mix": "Analog Flanger has no mix control."}),
    "Pedal_VintageFlanger": Recipe("Electric Flanger", "stomp",
                                   {"Rate": pos("Rate"), "Range": pct_of("Depth"), "Color": const(5.0)},
                                   {"Mix": "Electric Flanger has no mix control."}),
    "Pedal_Phaser": Recipe("Phaze Nine", "stomp", {"Speed": pos("Rate")}),
    "Pedal_ShaverPhaser": Recipe("Small Phazer", "stomp",
                                 {"Rate": pos("Rate"), "Color": lambda k, s: 1 if k.pos("Depth") >= 0.5 else 0},
                                 {"Depth": "Small Phazer depth is a two-position Color switch (>=50 % -> deep)."}),
    "Pedal_BakedRotatoe": Recipe("Uni-V", "stomp",
                                 {"Rate": pos("Rate"), "Intensity": pct_of("Depth"),
                                  "ChorusVibrato": lambda k, s: "Vibrato" if k.v("Mix") >= 90 else "Chorus",
                                  "Volume": const(-3.0)},
                                 {"Mix": "Uni-V has Chorus/Vibrato modes, not a mix: Mix >= 90 % -> Vibrato (wet only), otherwise Chorus.",
                                  "Balance": "rotor balance has no Uni-V equivalent."}),
    "Pedal_AmpTrem": Recipe("Opto Tremolo", "stomp", {"Rate": pos("Speed"), "Depth": pos("Depth")}),
    "Pedal_Tremolo": Recipe("Tremolo", "stomp", {"Speed": pos("Speed"), "Intensity": pct_of("Mix")}),
    "Pedal_MultiTrem": Recipe("Shape Shifter", "stomp",
                              {"Rate": pos("Speed"), "Depth": pct_of("Mix"),
                               "Wave": lambda k, s: {"Sine": 0.0, "Triangle": 5.0}.get(k.label("Waveform"), 10.0),
                               "Shape": lambda k, s: {"Square Short": 2.0, "Square Long": 8.0}.get(k.label("Waveform"), 5.0)}),
    "Rack_StereoTubeTrem": Recipe("Shape Shifter", "stomp",
                                  {"Rate": pos("Speed"), "Depth": pct_of("Mix"),
                                   "Wave": lambda k, s: {"Sine": 0.0, "Triangle": 5.0}.get(k.label("Waveform"), 10.0),
                                   "Shape": const(5.0)},
                                  {"__stereo__": "stereo (ping-pong) tremolo becomes mono on Shape Shifter."}),
    "Pedal_Enbiggenator": Recipe("Uni-V", "stomp",
                                 {"Rate": pos("Rate"), "Intensity": pct_of("Depth"),
                                  "ChorusVibrato": const("Chorus"), "Volume": const(-3.0)},
                                 {"Mix": "Uni-V chorus mode has a fixed blend."}),
    "Pedal_OmniMod": Recipe("Uni-V", "stomp",
                            {"Rate": pos("Rate"), "Intensity": pct_of("Depth"),
                             "ChorusVibrato": lambda k, s: "Vibrato" if k.v("Mix") >= 90 else "Chorus",
                             "Volume": const(-3.0)},
                            {"Mix": "mapped to Chorus/Vibrato mode (>=90 % wet -> Vibrato)."}),
    # ── filters / wah ─────────────────────────────────────────────────────
    "Pedal_ModernWah": Recipe("Wah", "stomp", {"Mode": wah_mode, "Wah": wah_pedal},
                              {"Sens": "AmpliTube auto-wah sensitivity is internal (no knob).",
                               "Speed": "AmpliTube auto-wah speed is internal (no knob)."}),
    "Pedal_USWah": Recipe("Wah 46", "stomp", {"Mode": wah_mode, "Wah": wah_pedal},
                          {"Sens": "AmpliTube auto-wah sensitivity is internal (no knob).",
                           "Speed": "AmpliTube auto-wah speed is internal (no knob)."}),
    "Pedal_UKWah": Recipe("Wah 47", "stomp", {"Mode": wah_mode, "Wah": wah_pedal},
                          {"Sens": "AmpliTube auto-wah sensitivity is internal (no knob).",
                           "Speed": "AmpliTube auto-wah speed is internal (no knob)."}),
    "Bass_Pedal_BassWah": Recipe("Bass Wah", "stomp", {"Mode": wah_mode, "Wah": wah_pedal},
                                 {"Sens": "AmpliTube auto-wah sensitivity is internal (no knob).",
                                  "Speed": "AmpliTube auto-wah speed is internal (no knob)."}),
    "Pedal_BobFilter": Recipe("Envelope Filter", "stomp",
                              {"Depth": env_depth, "BandMode": filter_mode("Filter"), "Freq": env_freq,
                               "Resonance": const(3.0), "PoleMode": const(12)},
                              {"Attack": "envelope attack time has no Envelope Filter knob.",
                               "Release": "envelope release time has no Envelope Filter knob.",
                               "Mix": "Envelope Filter is 100 % wet; Rocksmith Mix not representable."}),
    "Pedal_AutoFilter": Recipe("Envelope Filter", "stomp",
                               {"Depth": env_depth, "BandMode": filter_mode("FilterType"), "Freq": env_freq,
                                "Resonance": lambda k, s: lerp(0.3, 10, k.pos("Res")), "PoleMode": const(12)},
                               {"Attack": "envelope attack time has no Envelope Filter knob.",
                                "Release": "envelope release time has no Envelope Filter knob.",
                                "Res": "labelled 'Mix' in Rocksmith but keyed Res(onance): mapped to Resonance. VERIFY."}),
    "Bass_Pedal_BassAutoFilter": Recipe("SVX Envelope Filter", "stomp",
                                        {"Depth": env_depth, "BandMode": filter_mode("FilterType"),
                                         "Freq": const(150.0),
                                         "Resonance": lambda k, s: lerp(0.3, 10, k.pos("Res")), "PoleMode": const(12)},
                                        {"Attack": "envelope attack time has no knob.",
                                         "Release": "envelope release time has no knob.",
                                         "Res": "labelled 'Mix' in Rocksmith but keyed Res(onance): mapped to Resonance. VERIFY."}),
    # ── delay ─────────────────────────────────────────────────────────────
    "Rack_StudioDelay": Recipe("Digital Delay", "rack",
                               {"DelayTime": lambda k, s: (k.v("TimeL") + k.v("TimeR")) / 2
                                if abs(k.v("TimeL") - k.v("TimeR")) < 1 else k.v("TimeL"),
                                "Mode": lambda k, s: "Mono" if abs(k.v("TimeL") - k.v("TimeR")) < 1 else "LR",
                                "Feedback": same("Feedback"), "Mix": same("Mix"),
                                "Filter": lambda k, s: log_lerp(20000, 1500, k.pos("Filter")),
                                "OutLevel": const(0.0)},
                               {"TimeR": "Digital Delay has one time: Left time used, L/R mode set when the times differ (AmpliTube's LR mode offsets the right side itself).",
                                "Filter": "Rocksmith 'Filter' % read as darkening (higher = darker) onto the low-pass. VERIFY."},
                               stomp_alt="Delay"),
    "Pedal_NPNDelay": Recipe("Delay", "stomp",
                             {"Delay": same("Time"), "Feedback": same("Feedback"),
                              "Level": pct_of("Mix")}),
    "Pedal_AnalogueDelay": Recipe("Analog Delay", "stomp",
                                  {"Delay": same("Time"), "Feedback": same("Feedback"), "Blend": same("Mix"),
                                   "ChVib": const(0.0), "Mode": const("Chorus")},
                                  {"__range__": "Analog Delay tops out at 500 ms; longer Rocksmith times are clamped."}),
    "Pedal_CosmicEcho": Recipe("EchoMan", "stomp",
                               {"Delay": same("Time"), "Feedback": same("Feedback"), "Blend": same("Mix"),
                                "ChVib": const(0.0), "Mode": const("Chorus")},
                               {"__range__": "EchoMan tops out at 500 ms; longer Rocksmith times are clamped."}),
    "Pedal_ValveEcho": Recipe("Tape Echo", "stomp",
                              {"Time": same("Time"), "Feedback": pct_of("Feedback"), "EchoLevel": pct_of("Mix"),
                               "Brightness": const(5.0), "WowFilter": const(5.0), "OutLevel": const(0.0)}),
    "Rack_TapeEcho": Recipe("Tape Echo", "stomp",
                            {"Time": same("Time"), "Feedback": pct_of("Feedback"), "EchoLevel": pct_of("Mix"),
                             "Brightness": pct_of("Stereo"),
                             "WowFilter": lambda k, s: {"OFF": 5.0, "HI": 7.5, "LO": 2.5}.get(k.label("Filter").upper(), 5.0),
                             "OutLevel": const(0.0)},
                            {"Stereo": "keyed 'Stereo' but labelled 'Hi Filter' in Rocksmith: mapped to Brightness.",
                             "Filter": "'Lo Filter' OFF/HI/LO mapped onto WowFilter tone. VERIFY."}),
    "Pedal_ModDelay": Recipe("Delay", "stomp",
                             {"Delay": same("Time"), "Feedback": same("Feedback"), "Level": pct_of("Mix")},
                             {"Depth": "delay modulation depth: AmpliTube Delay has none (X-TIME parameters are unknown).",
                              "Rate": "delay modulation rate: AmpliTube Delay has none (X-TIME parameters are unknown)."}),
    "Pedal_NoFiEcho": Recipe("DDelay", "stomp",
                             {"Delay": same("Time"), "Feedback": pct_of("Feedback"), "Level": pct_of("Mix")},
                             {"__lofi__": "No-Fi Echo's lo-fi degradation has no AmpliTube delay equivalent (DDelay used)."}),
    "Bass_Pedal_BassFilterDelay": Recipe("Delay", "stomp",
                                         {"Delay": same("Time"), "Feedback": same("Feedback"), "Level": pct_of("Mix")},
                                         {"Filter": "delay low-cut filter (keeps bass dry) has no AmpliTube Delay control."}),
    # ── reverb ────────────────────────────────────────────────────────────
    "Pedal_SpringReverb": Recipe("'63 Reverb", "stomp",
                                 {"Dwell": pos("Depth"), "Mixer": pct_of("Mix"), "Tone": const(5.0)},
                                 {"Time": "the '63 spring has no decay knob (Dwell sets intensity); Time not representable."}),
    "Pedal_TubeSpring": Recipe("'63 Reverb", "stomp",
                               {"Dwell": pos("Depth"), "Mixer": pct_of("Mix"), "Tone": const(5.0)}),
    "Rack_StudioChamber": Recipe("Room Reverb", "rack",
                                 {"Mix": same("Mix"), "Decay": pos("Time", 5, 60), "Size": pos("Depth", 10, 60),
                                  "Color": pos("Tone", 20, 80), "PreDelay": const(0.0), "Modulation": const(0.0),
                                  "Hpf": const(0.0)},
                                 {"Depth": "Diffusion mapped onto room Size. VERIFY."},
                                 stomp_alt="'63 Reverb"),
    "Rack_StudioVerb": Recipe("Digital Reverb", "rack",
                              {"DecayTime": reverb_seconds("Time"), "Density": pos("Depth", 0, 99),
                               "Color": tone_to_hz("Tone"), "Mix": same("Mix"), "OutLevel": const(0.0)},
                              stomp_alt="'63 Reverb"),
    "Pedal_DigitalVerb": Recipe("Digital Reverb", "rack",
                                {"DecayTime": reverb_seconds("Time"), "Density": pos("Depth", 0, 99),
                                 "Color": tone_to_hz("Tone"), "Mix": same("Mix"), "OutLevel": const(0.0)},
                                stomp_alt="'63 Reverb"),
    "Rack_StudioPlate": Recipe("Plate Reverb", "rack",
                               {"Mix": same("Mix"), "Decay": pos("Time", 5, 80), "Size": pos("Depth", 10, 60),
                                "Color": pos("Tone", 20, 80), "PreDelay": const(0.0), "Modulation": const(0.0),
                                "Hpf": const(0.0)},
                               {"Depth": "Diffusion mapped onto plate Size. VERIFY."},
                               stomp_alt="'63 Reverb"),
    "Pedal_PlateVerb": Recipe("Plate Reverb", "rack",
                              {"Mix": same("Mix"), "Decay": pos("Time", 5, 80), "Size": pos("Depth", 10, 60),
                               "Color": lambda k, s: 40.0 if k.label("Voice") == "1" else 60.0,
                               "PreDelay": const(0.0), "Modulation": const(0.0), "Hpf": const(0.0)},
                              {"Voice": "two plate voicings mapped to darker (1) / brighter (2) Color. VERIFY."},
                              stomp_alt="'63 Reverb"),
    # ── pitch ─────────────────────────────────────────────────────────────
    "Pedal_OctaveUp": Recipe("Octa-V", "stomp", {"Drive": pct_of("Tone"), "Volume": const(-6.0)},
                             {"Mix": "Octa-V (Octavia) has no blend; octave-up amount not representable.",
                              "Tone": "Tone mapped to Drive (Octavia brightness rises with drive). VERIFY."}),
    "Pedal_Octavius": Recipe("Octav", "stomp",
                             {"Direct": lambda k, s: mix_to_levels("Mix")(k)[0],
                              "Oct1": lambda k, s: mix_to_levels("Mix")(k)[1],
                              "Oct2": const(-200.0)},
                             {"Tone": "Octav has no tone control."}),
    "Bass_Pedal_BassSubOctave": Recipe("SVX-OCT", "stomp",
                                       {"Direct": lambda k, s: 10 * math.cos(k.v("Mix") / 100 * math.pi / 2),
                                        "Octave": lambda k, s: 10 * math.sin(k.v("Mix") / 100 * math.pi / 2)},
                                       {"Tone": "SVX-OCT has no tone control."}),
    "Rack_StudioPitch": Recipe("Pitch Shifter", "stomp",
                               {"Coarse": lambda k, s: round(k.v("Pitch")), "Fine": const(0.0),
                                "Level": pct_of("Mix")},
                               {"Tone": "pitch-shifter tone filter: no equivalent.",
                                "Pan": "pitch voice pan: Pitch Shifter stomp is mono.",
                                "Mix": "Pitch Shifter stomp has no dry/wet mix: Mix sets the shifted Level (dry stays)."}),
    "Pedal_MultiPitch": Recipe("Pitch Shifter", "stomp",
                               {"Coarse": lambda k, s: round(k.v("Pitch1")), "Fine": const(0.0),
                                "Level": pct_of("Mix")},
                               {"Tone": "pitch tone filter: no equivalent.",
                                "Mix": "Pitch Shifter stomp has no dry/wet mix: Mix sets the shifted Level."}),
    "Pedal_BassEmulator": Recipe("SVX-OCT", "stomp",
                                 {"Octave": const(10.0), "Direct": lambda k, s: lerp(4.0, 0.0, k.pos("Body"))},
                                 {"Body": "Body sets how much dry guitar is removed (Direct level) under the full sub-octave. VERIFY.",
                                  "Tone": "SVX-OCT has no tone control."}),
    # ── more modulation (vibes, phasers, ring mod) ────────────────────────
    "Pedal_AmpVibe": Recipe("Uni-V", "stomp",
                            {"Rate": pos("Speed"),
                             "ChorusVibrato": lambda k, s: "Vibrato" if k.v("Mix") >= 90 else "Chorus",
                             "Intensity": const(5.0), "Volume": const(-3.0)},
                            {"Mix": "Uni-V has Chorus/Vibrato modes, not a mix: >=90 % -> Vibrato, else Chorus."}),
    "Pedal_AutoVibe": Recipe("Uni-V", "stomp",
                             {"Intensity": pos("Sens"),
                              "ChorusVibrato": lambda k, s: "Vibrato" if k.v("Mix") >= 90 else "Chorus",
                              "Rate": const(5.0), "Volume": const(-3.0)},
                             {"Sens": "envelope-driven vibe: Sensitivity mapped to Intensity (Uni-V has no envelope). VERIFY.",
                              "Attack": "envelope attack: Uni-V has no envelope follower.",
                              "Release": "envelope release: Uni-V has no envelope follower.",
                              "Mix": "mapped to Chorus/Vibrato mode."}),
    "Pedal_MarshallSupervibe": Recipe("Uni-V", "stomp",
                                      {"Rate": pos("Rate"), "Intensity": pct_of("Depth"),
                                       "ChorusVibrato": const("Vibrato"), "Volume": const(-3.0)},
                                      {"Wave": "Supervibe wave shape: Uni-V has a fixed photocell LFO.",
                                       "Mix": "keyed Mix but labelled 'Filter' in Rocksmith: no Uni-V equivalent."}),
    "Pedal_MultiVibe": Recipe("Uni-V", "stomp",
                              {"Rate": pos("Speed"),
                               "ChorusVibrato": lambda k, s: "Vibrato" if k.v("Mix") >= 90 else "Chorus",
                               "Intensity": const(6.0), "Volume": const(-3.0)},
                              {"Waveform": "selectable LFO waveform: Uni-V has a fixed LFO.",
                               "Mix": "mapped to Chorus/Vibrato mode."}),
    "Rack_StereoAnalogVibe": Recipe("Uni-V", "stomp",
                                    {"Rate": pos("Speed"),
                                     "ChorusVibrato": lambda k, s: "Vibrato" if k.v("Mix") >= 90 else "Chorus",
                                     "Intensity": const(6.0), "Volume": const(-3.0)},
                                    {"Waveform": "selectable LFO waveform: Uni-V has a fixed LFO.",
                                     "Mix": "mapped to Chorus/Vibrato mode.",
                                     "__stereo__": "stereo vibrato becomes mono."}),
    "Rack_RotaVibe": Recipe("Rotary Speaker", "rack",
                            {"Speed": lambda k, s: log_lerp(0.5, 7.8, k.pos("Rate")), "Mix": same("Mix"),
                             "Balance": same("Balance"), "Drive": const(0.0), "OutLevel": const(0.0)},
                            {"Depth": "rotor modulation depth is fixed by the Rotary Speaker's physics (no depth knob)."}),
    "Pedal_PlanePhase": Recipe("Small Phazer", "stomp",
                               {"Rate": pos("Rate"), "Color": lambda k, s: 1 if k.pos("Depth") >= 0.5 else 0},
                               {"Depth": "two-position Color switch (>=50 % -> deep).",
                                "Mix": "Small Phazer has no mix control."}),
    "Bass_Pedal_BassPhase": Recipe("Small Phazer", "stomp",
                                   {"Rate": pos("Rate"), "Color": lambda k, s: 1 if k.pos("Depth") >= 0.5 else 0},
                                   {"Depth": "two-position Color switch (>=50 % -> deep).",
                                    "Mix": "Small Phazer has no mix control.",
                                    "Filter": "bass phaser low filter (keeps lows dry): no equivalent."}),
    "Rack_StereoPhaser": Recipe("Phaze Nine", "stomp",
                                {"Speed": hz_to_knob("Rate", 0.1, 10.0)},
                                {"Depth": "Phaze Nine (Phase 90) has only Speed.",
                                 "Mix": "Phaze Nine (Phase 90) has only Speed.",
                                 "__stereo__": "stereo phaser becomes mono."}),
    "Pedal_SendInTheClones": Recipe("Digital Chorus", "rack",
                                    {"Depth": same("Depth"), "Mix": same("Mix"), "Rate": const(1.0),
                                     "Waveform": const("Triangle"), "OutLevel": const(0.0)},
                                    {"Clones": "'CLONES!' (voice/intensity) has no Digital Chorus control."}),
    "Bass_Pedal_BassEnbig": Recipe("Digital Chorus", "rack",
                                   {"Rate": lambda k, s: clamp(k.v("Rate"), 0.1, 8.0), "Depth": same("Depth"),
                                    "Mix": same("Mix"), "Waveform": const("Sine"), "OutLevel": const(0.0)},
                                   {"Filter": "bass chorus low filter (keeps lows dry): no equivalent."}),
    "Pedal_TremOle": Recipe("Opto Tremolo", "stomp",
                            {"Depth": pct_of("Mix"), "Rate": pos("Sens")},
                            {"Sens": "envelope-reactive tremolo: Sensitivity mapped to Rate. VERIFY.",
                             "Attack": "envelope attack: Opto Tremolo has no envelope.",
                             "Release": "envelope release: Opto Tremolo has no envelope."}),
    "Pedal_RingMod": Recipe("AM Modulator", "rack", {},
                            {"Attack": "AM Modulator parameter names are unknown (no AmpliTube preset uses it) — loaded at its defaults. VERIFY.",
                             "Depth": "AM Modulator parameter names are unknown — loaded at its defaults. VERIFY.",
                             "Sensitivity": "AM Modulator parameter names are unknown — loaded at its defaults. VERIFY.",
                             "Waveform": "AM Modulator parameter names are unknown — loaded at its defaults. VERIFY."}),
    "Rack_StudioWahFilter": Recipe("Wah", "stomp", {"Mode": wah_mode, "Wah": wah_pedal},
                                   {"Sens": "AmpliTube auto-wah sensitivity is internal (no knob).",
                                    "Attack": "auto-wah attack: no knob.", "Release": "auto-wah release: no knob."}),
    "Rack_SynthFilter": Recipe("Envelope Filter", "stomp",
                               {"Depth": env_depth, "BandMode": filter_mode("FilterType"), "Freq": env_freq,
                                "Resonance": lambda k, s: lerp(0.3, 10, k.pos("Res")), "PoleMode": const(24)},
                               {"Attack": "envelope attack: no Envelope Filter knob.",
                                "Release": "envelope release: no Envelope Filter knob.",
                                "Res": "labelled 'Mix' in Rocksmith but keyed Res(onance): mapped to Resonance. VERIFY."}),
    # ── more dynamics / EQ / delay ────────────────────────────────────────
    "Pedal_Limiter": Recipe("Compressor", "stomp",
                            {"Comp": lambda k, s: lerp(50, 100, k.pos("Limit")), "Level": const(0.0)},
                            {"Rate": "release speed: AmpliTube Compressor stomp has fixed timing."}),
    "Pedal_AmpEQ": Recipe("7 Band Graphic", "stomp",
                          {**{n: (lambda n: lambda k, s: _amp_eq_fit(k)[n])(n) for n in AT5_7BAND},
                           "Level": const(0.0)},
                          {"BassFreq": "frequency selector positions (One/Two) are not published; assumed 80/160 Hz. VERIFY.",
                           "MidShift": "frequency selector positions (One/Two/Three) are not published; assumed 400/800/1600 Hz. VERIFY.",
                           "TrebleFreq": "frequency selector positions (One/Two) are not published; assumed 3.2/6.4 kHz. VERIFY.",
                           "__range__": "Amp EQ knobs are unitless 1..100; read as -12..+12 dB around 50. VERIFY."}),
    "Pedal_OilCanEcho": Recipe("Tape Echo", "stomp",
                               {"Time": same("Time"), "Feedback": pct_of("Feedback"), "EchoLevel": pct_of("Mix"),
                                "Brightness": const(4.0), "WowFilter": const(6.0), "OutLevel": const(0.0)},
                               {"__model__": "Oil Can Delay exists in AmpliTube but its parameters are undocumented; Tape Echo used. VERIFY."}),
    "Bass_Pedal_BassFilterEcho": Recipe("Digital Delay", "rack",
                                        {"DelayTime": same("Time"), "Feedback": same("Feedback"), "Mix": same("Mix"),
                                         "Mode": const("Mono"), "Filter": const(20000.0), "OutLevel": const(0.0)},
                                        {"Filter": "'Low Filter' (high-pass on the repeats) has no Digital Delay control (its Filter is a low-pass)."}),
    # ── DI preamps (Rocksmith "DI_Amp_*": the amp is muted, the DI preamp
    #    becomes the first pre-amp effect) ───────────────────────────────
    "DI_Amp_TubePre": Recipe("Pre EQ 3", "stomp",
                             {"PreampGain": pos("Gain"),
                              "LowGain": lambda k, s: _di_db(k, "Bass"), "LowFreq": const(100.0),
                              "MidGain": lambda k, s: _di_db(k, "Mid"),
                              "MidFreq": lambda k, s: {0: 400.0, 1: 800.0, 2: 1600.0}.get(int(round(k.v("MidFreq"))), 800.0),
                              "HighGain": lambda k, s: _di_db(k, "Treble"), "HighFreq": const(4000.0),
                              "LowWidth": const(7.0), "MidWidth": const(6.0), "HighWidth": const(7.0),
                              "EQBypass": const(0)},
                             {"MidFreq": "mid-frequency selector positions are not published; assumed 400/800/1600 Hz. VERIFY.",
                              "__range__": "DI tone knobs are unitless 1..100; read as -12..+12 dB around 50. VERIFY."}),
    "DI_Amp_MixerPre": Recipe("Pre EQ 3", "stomp",
                              {"PreampGain": pos("Gain"),
                               "LowGain": lambda k, s: _di_db(k, "Bass"), "LowFreq": const(100.0),
                               "MidGain": lambda k, s: _di_db(k, "Mid"), "MidFreq": const(800.0),
                               "HighGain": lambda k, s: _di_db(k, "Treble") + (k.pos("Tone") - 0.76) * 12.0,
                               "HighFreq": const(5000.0),
                               "LowWidth": const(7.0), "MidWidth": const(6.0), "HighWidth": const(7.0),
                               "EQBypass": const(0)},
                              {"Tone": "mixer Tone (default 76) added to the high band as a tilt. VERIFY.",
                               "__range__": "DI tone knobs are unitless 1..100; read as -12..+12 dB around 50. VERIFY."}),
    "DI_Amp_BassDriver": Recipe("AmpLess", "stomp",                   # SansAmp Bass Driver DI
                                {"Drive": pos("Gain"), "Bass": pos("Bass"), "Treble": pos("Treble"),
                                 "Presence": pos("Pres"), "Blend": lambda k, s: k.v("Blend") / 10.0,
                                 "Level": const(5.0)}),
    # ── other ─────────────────────────────────────────────────────────────
    "Pedal_AcousticEmulator": Recipe("Acoustic Sim", "stomp",
                                     {"Mix": const(10.0), "Bass": pos("Body"), "Treble": pos("Tone"),
                                      "BodyType": const(1), "Pickup": const("S")},
                                     {"Mid": "mid-range level: Acoustic Sim has only Bass/Treble.",
                                      "MidShift": "mid frequency: Acoustic Sim has no mid EQ."}),
    "Pedal_LoFiFilter": Recipe("Crusher", "stomp",
                               {"Cutoff": lambda k, s: log_lerp(20000, 1000, k.pos("FilterType")),
                                "Decimation": const(1), "InputGain": const(0.0), "OutputGain": const(0.0)},
                               {"Mix": "keyed Mix but labelled 'Lo Cut' in Rocksmith: Crusher has no high-pass. VERIFY."}),
    "Pedal_BitCruncher": Recipe("Crusher", "stomp",
                                {"Decimation": lambda k, s: clamp(1 + k.v("Release") / 2, 1, 16),
                                 "Cutoff": lambda k, s: log_lerp(20000, 2000, k.pos("Attack")),
                                 "InputGain": lambda k, s: lerp(0, 24, k.pos("Sens")), "OutputGain": const(-6.0)},
                                {"FilterType": "Bit Depth (2..8 bits): Crusher reduces sample rate only, not bit depth.",
                                 "Mix": "Crusher is 100 % wet.",
                                 "Sens": "Rectify mapped onto input gain (both add harshness). VERIFY."}),
}


# ─────────────────────────────────────────────────────────────────────────────
# GENERIC MATCHING (any target without a recipe — e.g. tier fallbacks)
# ─────────────────────────────────────────────────────────────────────────────

ROLE_SYNONYMS = {
    "gain": ("Gain", "Drive", "Distortion", "Dist", "Fuzz", "Sustain", "Attack", "Overdrive", "Texture", "Boost"),
    "tone": ("Tone", "Filter", "Color", "Brightness", "Treble"),
    "mix": ("Mix", "Mixer", "Blend", "Balance", "EchoLevel", "Level"),
    "rate": ("Rate", "Speed", "LFOSpeed", "VibratoRate", "VibRate"),
    "depth": ("Depth", "Intensity", "Width", "Range", "Chorus", "Dwell"),
    "feedback": ("Feedback", "Regen", "Res", "Sustain", "Repeat"),
    "time": ("Delay", "DelayTime", "Time", "DecayTime", "Decay"),
    "level": ("Level", "Volume", "Output", "OutLevel"),
    "comp": ("Comp", "Sensitivity", "Drive"),
    "sens": ("Sens", "Sensitivity", "Depth"),
    "pedal": ("Wah", "Pedal"),
    "pitch": ("Coarse", "Pitch"),
    "threshold": ("Threshold", "TriggerLevel"),
}

RS_ROLE = {
    "Gain": "gain", "Boost": "gain", "Smash": "comp", "Comp": "comp", "Compress": "comp", "Compression": "comp",
    "Tone": "tone", "Filter": "tone", "Mix": "mix", "Blend": "mix", "Rate": "rate", "Speed": "rate",
    "Depth": "depth", "Regen": "feedback", "Feedback": "feedback", "Time": "time", "TimeL": "time",
    "Sens": "sens", "Pedal": "pedal", "Pitch": "pitch", "Pitch1": "pitch", "Thresh": "threshold",
    "Threshold": "threshold",
}


def generic_params(k: Knobs, specs: dict[str, tuple]) -> dict[str, Callable]:
    """Best-effort knob -> parameter assignment by role and unit."""
    out: dict[str, Callable] = {}
    taken = set()
    for knob in k.names():
        role = RS_ROLE.get(knob)
        if not role:
            continue
        for cand in ROLE_SYNONYMS[role]:
            if cand in specs and cand not in taken:
                spec = specs[cand]
                unit = k.unit(knob)
                if spec[0] == "ms" and unit == "ms":
                    out[cand] = same(knob)
                elif spec[0] == "pct" and unit == "%":
                    out[cand] = same(knob)
                elif spec[0] in ("db", "gain", "thresh") and unit == "db":
                    out[cand] = same(knob)
                elif spec[0] == "hz" and unit in ("hz", "khz"):
                    out[cand] = same(knob)
                else:
                    out[cand] = pos(knob)
                taken.add(cand)
                break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# EFFECT CONVERSION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Converted:
    guid: str                   # AmpliTube model GUID
    attrs: dict[str, str]       # slot attributes (excluding Bypass)
    notes: list[str]            # approximations / unrepresentable knobs
    kind: str = ""              # "stomp" / "rack"


def _resolve(fn, k: Knobs, specs, name):
    val = fn(k, specs)
    spec = specs.get(name, K10)
    if isinstance(val, tuple) and val and val[0] == "__pos__":
        _, p, lo, hi = val
        if lo is not None and hi is not None:
            return lerp(lo, hi, p) if spec[0] not in ("ms", "hz", "sec") else log_lerp(lo, hi, p)
        return spec_pos_value(spec, p)
    if isinstance(val, tuple) and val and val[0] == "__keep_unity__":
        return {"knob": 5.0, "pct": 50.0, "gain": 0.0, "db": 0.0, "vol": -6.0}.get(spec[0], 5.0)
    return val


def recipe_target_guid(rs_key: str) -> str | None:
    """AmpliTube GUID of the recipe's target.  Any AmpliTube stomp or rack can
    sit in any effect slot (the manual: "loaded as it is or as a
    stomp-in-rack/rack-in-stomp"; factory presets do both), so the target
    does not depend on where the effect lands."""
    r = RECIPES.get(rs_key)
    return at5_guid(r.target, r.kind) if r else None


def convert_effect(rs_key: str, knob_values: dict | None, target_guid: str) -> Converted:
    """Convert one Rocksmith pedal/rack onto the AmpliTube model `target_guid`.
    Uses the recipe when its target matches, generic matching otherwise."""
    k = Knobs(rs_key, knob_values)
    specs = at5_param_specs(target_guid)
    notes: list[str] = []
    r = RECIPES.get(rs_key)
    tname = at5_name(target_guid)
    params = None
    approx = {}
    if r and tname == r.target:
        params, approx = r.params, r.approx
    elif r and tname == r.stomp_alt:
        params = stomp_alt_params(rs_key, k)
        if params is None:
            params = generic_params(k, specs)
        notes.append(f"{rs_key}: placed before the amp, so the stomp '{tname}' is used instead of the rack '{r.target}'.")
    else:
        params = generic_params(k, specs)
        if r:
            notes.append(f"{rs_key}: tier/slot forced '{tname}' instead of '{r.target}'; knobs matched by name.")
    attrs: dict[str, str] = {}
    for name, fn in params.items():
        spec = specs.get(name)
        if spec is None:
            continue
        try:
            attrs[name] = encode(spec, _resolve(fn, k, specs, name))
        except Exception as e:   # never let one knob break a preset
            notes.append(f"{rs_key}: could not convert {name} ({e})")
    for knob in k.names():
        if knob in approx:
            notes.append(f"{rs_key}.{knob}: {approx[knob]}")
        elif knob not in k.used:
            notes.append(f"{rs_key}.{knob}: no matching control on {tname or target_guid} — not carried over.")
    for key, why in approx.items():
        if key.startswith("__"):
            notes.append(f"{rs_key}: {why}")
    return Converted(target_guid, attrs, notes, at5_kind(target_guid))


# ─────────────────────────────────────────────────────────────────────────────
# AMP KNOBS
# ─────────────────────────────────────────────────────────────────────────────
#
# Rocksmith amp knobs are 1..100 (or 0..100) "number" knobs; AmpliTube amp
# knobs are 0..10.  The value lands at the same position on the range.  The
# AmpliTube parameter names come from the target model's own preset data, so
# only real parameters are written.

# Role -> base-name patterns (the parameter name before "_<Model>"), in
# preference order.  "Gain" falls back to volume-type knobs because
# non-master-volume amps (tweeds, Plexi, AC30) have no gain knob: their
# volume IS the gain stage, which is what Rocksmith's Gain knob represents.
AMP_ROLE_PATTERNS = {
    "Gain": [r"Gain1?", r"Drive", r"PreAmp", r"PreNormal", r"LeadDrive", r"Distortion", r"Overdrive",
             r"Volume1", r"NormalVol", r"VolNormal", r"InstVol", r"VolInst", r"Volume", r"Vol", r"Loudness1?"],
    "Bass": [r"Bass1?", r"R1R2Bass", r"Low", r"Lo", r"EqLow?"],
    "Mid": [r"Middle", r"Mid", r"MidRange1?", r"Mids", r"EqMid"],
    "Treble": [r"Treble1?", r"R1Treble", r"High", r"Hi", r"EqHi(gh)?", r"Tone"],
    "Pres": [r"Presence", r"Pres"],
    "Master": [r"Master1?", r"MasterVol(ume)?", r"MasterNormal", r"Output", r"LeadMaster"],
    "Loudness1": [r"Volume1", r"NormalVol", r"VolNormal", r"InstVol", r"VolInst", r"Volume", r"Loudness1"],
    "Loudness2": [r"BrillantVol", r"VolBright", r"BrightVolume", r"Volume2", r"Loudness2"],
    "Tone": [r"Tone", r"Treble1?", r"Cut"],
    "Bright": [r"Bright1?", r"BrightSwitch", r"TopBoostSwitch"],
    "HiShift": [r"UltraHi1?", r"Bright1?", r"TrebleShift"],
    "LoShift": [r"UltraLo2?", r"Deep", r"BassShift"],
    "Deep": [r"Deep", r"UltraLo2?", r"BassShift"],
    "Enhance": [r"Contour", r"UltraHi1?", r"Enhance"],
    "MidFreq": [r"Freq", r"Frequency", r"MidFreq(uency)?"],
    "Res": [r"Resonance", r"Depth"],
    "Punch": [r"Punch", r"Contour"],
    "Compression": [r"Compression", r"Comp", r"Limit"],
    "Blend": [r"Blend", r"Ch12Mix"],
    "Lo": [r"Bass1?", r"Low", r"Lo"], "Hi": [r"Treble1?", r"High", r"Hi"],
    "LoMid": [r"LowMid", r"Middle", r"Mid"], "HiMid": [r"HighMid", r"Middle", r"Mid"],
    "LoFreq": [r"LowFreq", r"BassFreq"], "HiFreq": [r"HighFreq", r"TrebleFreq"],
}
_CHANNEL_PREFIX = re.compile(r"^(Ch\d|Clean\d?|Crunch|OD\d|Lead|Rhy\d?|R\d)(?=[A-Z])")
_CHANNEL_SUFFIX = re.compile(r"(?<=[a-z])(Ch\d|CH\d)$")
SWITCH_ROLES = {"Bright", "HiShift", "LoShift", "Deep"}
INVERTED = {("Pres", "Cut")}          # AC30-style Cut = inverse presence


def _is_switch(stats: dict) -> bool:
    return (stats.get("distinct", 3) <= 2 and {stats.get("min"), stats.get("max")} <= {0.0, 1.0}) \
        or bool(stats.get("values") and "min" not in stats)


_CHANNEL_TOKEN = re.compile(r"^(Clean\d?|Crunch|OD\d|Master\d|Lead|Rhythm\d?|Ch\d)$")


def _param_core(name: str):
    """(channel tag, role core) of an AmpliTube amp parameter name:
    Ch2Gain_X / GainCh2_X / OD1_Gain_X  ->  ('Ch2'|'OD1', 'Gain')."""
    tokens = name.split("_")
    if len(tokens) >= 3 and _CHANNEL_TOKEN.match(tokens[0]):
        return tokens[0], tokens[1]
    return _split_channel(tokens[0])


def _split_channel(base: str):
    """('Ch2', 'Gain') for Ch2Gain / GainCh2; ('', base) without a channel."""
    m = _CHANNEL_PREFIX.match(base)
    if m:
        return m.group(1), base[m.end():]
    m = _CHANNEL_SUFFIX.search(base)
    if m:
        return "Ch" + m.group(1)[2:], base[: m.start()]
    return "", base


def _amp_channel(params: dict):
    """(channel select param, value to write, channel tag) — the channel
    AmpliTube's own presets use most for this amp."""
    tags = {_param_core(n)[0] for n in params} - {""}
    for name, s in params.items():
        sel = name.split("_")[0]
        if sel not in ("Channel", "Channele", "Mode"):
            continue
        if sel == "Mode" and not set(s.get("values") or []) & tags:
            continue
        if s.get("values") and "min" not in s:
            counts = s.get("counts") or {v: 1 for v in s["values"]}
            choice = max(counts, key=counts.get)
        elif "mode" in s or "median" in s:
            choice = str(int(round(s.get("mode", s.get("median", 0)))))
        else:
            continue
        compact = choice.replace(" ", "")
        cands = [compact]
        if compact.upper().startswith("CH"):
            cands.append("Ch" + compact[2:])
        if choice.isdigit():
            cands.append(f"Ch{int(choice) + 1}")
        tag = next((c for c in cands if c in tags), None)
        return name, choice, tag
    return None, None, None


def _amp_param_for(role: str, params: dict, used: set, prefer_tag):
    """Best AmpliTube amp parameter for a Rocksmith knob role: (name, inverted)."""
    pats = list(AMP_ROLE_PATTERNS.get(role, [re.escape(role)]))
    if role == "Pres":
        pats.append("Cut")
    names = [n for n in params if not n.startswith("AmpFlexi") and n not in used]
    for pat in pats:
        rx = re.compile(rf"^(?:{pat})$")
        hits = []
        for n in names:
            base = n.split("_")[0]
            tag, core = _param_core(n)
            if not tag and rx.match(base):
                hits.append((1, n))
            elif tag and rx.match(core):
                hits.append((0 if tag == prefer_tag else 2, n))
        if hits:
            hits.sort()
            return hits[0][1], (role, pat) in INVERTED
    return None, False


def _amp_band_param(freq_hz: float, params: dict, used: set):
    """Amp graphic band (Eq125Hz / Band240Hz / Band80 ...) nearest to freq_hz."""
    best = None
    for n in params:
        m = re.match(r"^(?:Eq|Band)(\d+(?:\.\d+)?)(k?)Hz?$", n.split("_")[0])
        if not m or n in used:
            continue
        f = float(m.group(1)) * (1000.0 if m.group(2) else 1.0)
        d = abs(math.log2(f / freq_hz))
        if d <= 0.75 and (best is None or d < best[0]):
            best = (d, n)
    return best[1] if best else None


def _amp_value(k: "Knobs", knob: str, stats: dict, inverted: bool = False) -> str:
    d = k.defs.get(knob, {})
    p = 1.0 - k.pos(knob) if inverted else k.pos(knob)
    if _is_switch(stats):
        if stats.get("values") and "min" not in stats:
            vals = stats["values"]
            return vals[-1] if p >= 0.5 else vals[0]
        return "1" if p >= 0.5 else "0"
    hi = 10.0 if stats.get("max", 10.0) <= 10.5 else stats["max"]
    lo = 0.0 if stats.get("min", 0.0) >= 0.0 else stats["min"]
    if d.get("unit") == "db" and lo < 0:          # dB band onto a dB band
        return f"{clamp(k.v(knob), lo, hi):.4f}"
    return f"{lerp(lo, hi, p):.4f}"


@dataclass
class AmpConverted:
    attrs: dict
    notes: list
    eq_bands: list            # leftover amp EQ as (kind, f0, gain dB, q) filter bands


# Rocksmith amp EQ gain knobs that come with a real frequency knob, so they
# can be rebuilt as a filter curve when the AmpliTube amp has no match.
_SEMI_PARAM = {"Lo": "LoFreq", "Hi": "HiFreq", "Mid": "MidFreq"}


def convert_amp(rs_amp_key: str, knob_values: dict | None, at5_amp_guid: str,
                curated: dict | None = None) -> AmpConverted:
    """Rocksmith amp knobs -> AmpliTube amp parameters (+ leftover EQ bands).

    Parameter names come from the AmpliTube amp's own preset data.  `curated`
    is cdlc_to_at5.AMP_KNOB_MAP[guid] (hand-made role -> param), used first
    when it names a real parameter on the chosen channel."""
    k = Knobs(rs_amp_key, knob_values)
    params = AT5_MODELS.get((at5_amp_guid or "").lower(), {}).get("params", {})
    tname = at5_name(at5_amp_guid) or "the AmpliTube amp"
    attrs, notes, used, eq = {}, [], set(), []
    if not params:
        notes.append(f"{rs_amp_key}: no parameter data for AmpliTube amp {at5_amp_guid}; amp knobs not set.")
        return AmpConverted(attrs, notes, eq)
    ch_param, ch_value, ch_tag = _amp_channel(params)
    if ch_param:
        attrs[ch_param] = ch_value
        used.add(ch_param)
        if ch_tag:
            notes.append(f"{rs_amp_key}: multi-channel AmpliTube amp '{tname}' — channel '{ch_value}' "
                         f"(the one its factory presets use most) selected and its knobs set. VERIFY.")
    rebuilt_freqs = set()
    primary = ("Gain", "Bass", "Mid", "Treble", "Pres", "Master", "Loudness1", "Loudness2", "Tone")
    order = sorted(k.names(), key=lambda n: (primary.index(n) if n in primary else len(primary)))
    for knob in order:
        if knob in rebuilt_freqs:
            continue
        unit = k.unit(knob)
        target, inverted = None, False
        cur = curated.get(knob) if curated else None
        if cur in params and cur not in used and not _is_switch(params[cur]):
            ctag = _param_core(cur)[0]
            if not ctag or not ch_tag or ctag == ch_tag:
                target = cur
        if target is None and re.fullmatch(r"\d+", knob):            # graphic band in Hz
            target = _amp_band_param(float(knob), params, used)
            if target is None and unit == "db":
                eq.append(("peak", float(knob), k.v(knob), 1.0))
                notes.append(f"{rs_amp_key}.{knob}: amp graphic band rebuilt in a 10 Band Graphic after the amp.")
                continue
        if target is None:
            target, inverted = _amp_param_for(knob, params, used, ch_tag)
        if target is not None and _is_switch(params[target]) and unit != "enum" and knob not in SWITCH_ROLES:
            target = None                                            # never put a knob on a switch
        if target is None and knob in _SEMI_PARAM and unit == "db":
            fk = _SEMI_PARAM[knob]
            if k.has(fk) and k.unit(fk) in ("hz", "khz"):
                eq.append(("peak", k.v(fk), k.v(knob), 0.9))
                rebuilt_freqs.add(fk)
                notes.append(f"{rs_amp_key}.{knob}: amp {knob} band (at {k.v(fk):.0f} Hz) rebuilt in a 10 Band Graphic after the amp.")
                continue
        if target is None:
            k.used.add(knob)
            notes.append(f"{rs_amp_key}.{knob}: no matching control on {tname} — not carried over.")
            continue
        used.add(target)
        attrs[target] = _amp_value(k, knob, params[target], inverted)
        if inverted:
            notes.append(f"{rs_amp_key}.{knob}: mapped inversely onto {target.split('_')[0]} (a cut control). VERIFY.")
    # a frequency knob handled before its gain knob reported "no control": drop that note
    notes = [n for n in notes if not any(n.startswith(f"{rs_amp_key}.{fk}: no matching") for fk in rebuilt_freqs)]
    return AmpConverted(attrs, notes, eq)


def convert_amp_knobs(rs_amp_key: str, knob_values: dict | None, at5_amp_guid: str,
                      curated: dict | None = None):
    """(attrs, notes) — see convert_amp."""
    r = convert_amp(rs_amp_key, knob_values, at5_amp_guid, curated)
    return r.attrs, r.notes


def amp_eq_effect(eq_bands: list):
    """A 10 Band Graphic carrying an amp's leftover EQ bands (None if none)."""
    if not eq_bands:
        return None
    guid = at5_guid("10 Band Graphic", "stomp")
    names = list(AT5_10BAND)
    gains = fit_graphic(eq_bands, [AT5_10BAND[n] for n in names])
    attrs = {n: f"{g:.4g}" for n, g in zip(names, gains)}
    attrs["Level"] = "0"
    return Converted(guid, attrs, [], "stomp")


# ─────────────────────────────────────────────────────────────────────────────
# CABINET MIC
# ─────────────────────────────────────────────────────────────────────────────
#
# Rocksmith cab keys end in <mic>_<position>: mic = 57 / Condenser / Ribbon /
# Tube (also Dynamic in a few), position = Cone / Edge / OffAxis.  AmpliTube's
# cab has a free-placement mic: XAxis -1..1 across the speaker (0 = centre of
# the cone), Angle 0..1 (0 on-axis, 1 = fully angled), Distance 0..1.

RS_MIC_TO_AT5 = {
    "57": "Dynamic 57",          # Shure SM57
    "Dynamic": "Dynamic 57",
    "Condenser": "Condenser 87",  # VERIFY: Rocksmith does not name its condenser
    "Ribbon": "Ribbon 121",       # Royer R-121 — the usual guitar-cab ribbon
    "Tube": "Condenser 12",       # AKG C12 tube condenser. VERIFY
    "121": "Ribbon 121",
    "421": "Dynamic 421",
}
RS_MIC_POSITION = {               # VERIFY: AmpliTube mic coordinates
    "Cone": {"XAxis": 0.0, "YAxis": 0.0, "Angle": 0.0, "Distance": 0.0},
    "Edge": {"XAxis": 0.8, "YAxis": 0.0, "Angle": 0.0, "Distance": 0.0},
    "OffAxis": {"XAxis": 0.3, "YAxis": 0.0, "Angle": 1.0, "Distance": 0.0},
}


def cab_mic(rs_cab_key: str) -> tuple[dict[str, str], list[str]]:
    """Cab inner attributes for mic 0 (model + placement) from a Rocksmith cab key."""
    parts = (rs_cab_key or "").split("_")
    notes = []
    pos_name = parts[-1] if parts and parts[-1] in RS_MIC_POSITION else None
    mic_name = parts[-2] if len(parts) >= 2 and parts[-2] in RS_MIC_TO_AT5 else None
    if not mic_name or not pos_name:
        return {}, ([f"{rs_cab_key}: no mic/position in the cab key — AmpliTube default mic kept."]
                    if rs_cab_key else [])
    guid = at5_guid(RS_MIC_TO_AT5[mic_name], "mic") or ""
    if not guid:
        notes.append(f"{rs_cab_key}: AmpliTube mic '{RS_MIC_TO_AT5[mic_name]}' not found.")
        return {}, notes
    p = RS_MIC_POSITION[pos_name]
    attrs = {"Mic0Model": guid, "Mic0XAxis": f"{p['XAxis']:g}", "Mic0YAxis": f"{p['YAxis']:g}",
             "Mic0Angle": f"{p['Angle']:g}", "Mic0Distance": f"{p['Distance']:g}", "Mic0Speaker": "0"}
    return attrs, notes


# ─────────────────────────────────────────────────────────────────────────────
# TONE VOLUME
# ─────────────────────────────────────────────────────────────────────────────
#
# Each Rocksmith tone carries a "Volume" in dB (Rocksmith+: -35..0, median
# -20.5; Rocksmith 2014 manifests similar).  The game uses it to level tones
# against each other.  It becomes the amp section's OutputVolume, relative to
# a reference, so loud and quiet tones of one song keep their balance.  The
# master <Output> stays under the plugin's Output-level setting.

TONE_VOLUME_REF_DB = -20.0          # VERIFY: Rocksmith reference loudness
TONE_VOLUME_MAX_OFFSET_DB = 12.0


def tone_volume_gain(volume_db) -> str | None:
    try:
        v = float(volume_db)
    except (TypeError, ValueError):
        return None
    off = clamp(v - TONE_VOLUME_REF_DB, -TONE_VOLUME_MAX_OFFSET_DB, TONE_VOLUME_MAX_OFFSET_DB)
    return f"{db_to_lin(off):.5g}"
