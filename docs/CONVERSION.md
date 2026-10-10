# How tones are converted (0.8.0)

This explains how a Rocksmith 2014 or Rocksmith+ tone becomes an AmpliTube 5 preset: which data the conversion uses, how each kind of setting is converted, and how to regenerate the data files.

## Sources of truth

| File | What it holds | Made by |
|---|---|---|
| `data/rs_gear_defs.json` | Every Rocksmith gear model (613: amps, cabs, pedals, racks) and **every knob's** key, display name, unit (`number`, `%`, `db`, `ms`, `hz`, `khz`, `enum`), min, max, default, step and enum labels. | `tools/extract_rs_gear.py`, from Rocksmith 2014's `gears.psarc` |
| `data/at5_gear.json` | AmpliTube's own model list (432 GUIDs and names, from `GearInfo/*.json` inside `AmpliTube 5.pak`), plus, for the 245 models that appear in any factory or user preset, every parameter name and the values AmpliTube stores (min/max/median/mode, or text values with counts). | `tools/extract_at5_gear.py` |
| `tone_params.py` | `PARAM_SPECS` (how each AmpliTube parameter is stored, taken from the *Custom Shop Gear Models* manual plus the preset values) and `RECIPES` (one per Rocksmith pedal/rack/DI). | hand-written |

The Rocksmith definitions matter for two reasons:

- **Units:** an EQ band in dB, a delay in ms and a rate in Hz each need a different conversion.
- **Defaults:** when a tone omits a knob, the game plays the knob's default, which is often not the middle. For example, the 5-band EQ's 63 Hz band defaults to −6 dB.

## Converting one value

`tone_params.Knobs` reads a slot's knob values. It accepts `KnobValues` or `Knobs` (dict or list), fills in the game's defaults, clamps values to the official range, converts kHz to Hz, and records which knobs a recipe used.

Each AmpliTube parameter has a spec saying how its value is stored:

| Spec | Panel range | Stored as |
|---|---|---|
| `knob lo hi` | e.g. 0..10 | the number |
| `pct` | 0..100 % | the number |
| `ms` / `hz` / `sec` | real unit | the number |
| `db lo hi` | dB | dB (e.g. the 10 Band Graphic) |
| `gain lo hi` | dB | **linear** `10^(dB/20)` (e.g. the 7 Band Graphic, rack OutLevels) |
| `vol` | −inf..0 dB | linear 0..1 (fuzz/vibe Volume, Dcomp Output) |
| `thresh` | dB | linear amplitude (Noise Gate threshold) |
| `enum` / `switch` | labels / 0-1 | text / 0-1 |

A recipe maps each AmpliTube parameter to one of:

- **`same(knob)`**: the same physical unit, copied and clamped (ms→ms, Hz→Hz, dB→dB or →linear gain, %→%).
- **`pos(knob)`**: the same *relative position* on both ranges, for unitless "number" knobs. Time and frequency ranges use a log taper.
- **A function**: enum labels (wah Auto/On, filter LP/BP/HP, compressor ratio, waveform), dry/wet laws (equal-power Mix → Direct/Octave levels), or the EQ fit below.
- **`const(value)`**: a parameter Rocksmith doesn't have (e.g. a drive pedal's output level), set to a neutral value.

`approx` lists every Rocksmith knob that cannot be represented exactly, with the reason. Every conversion returns these as notes, and they appear in the plugin log. A test checks that every knob of every recipe is either used or documented, so nothing is dropped silently.

## EQs: rebuilding the curve

A Rocksmith EQ is rebuilt as its actual frequency response, using RBJ cookbook biquads:

- **Graphic EQ bands** become constant-Q peaking filters (Q from the band spacing).
- **Studio Parametric EQ** becomes a low shelf, two peaks (Wide/Narrow Q) and a high shelf.

The AmpliTube EQ's band gains are then **fitted** to that curve: start from the response sampled at each AmpliTube band centre, then make 12 correction passes that account for the overlap between AmpliTube's own bands. So a Rocksmith 5-band EQ (63/250/750/2.2k/5.7k) onto a 7-band (100…6.4k), or a −9 dB narrow cut at 400 Hz onto a 31-band GraphicEQ, keeps its shape at the right frequencies. A band-1-to-band-1 copy would not.

## Placement (single-path chain, `Chain11`)

| Rocksmith | AmpliTube section | Position |
|---|---|---|
| PrePedal1-4 (+ optional noise gate first; a DI preamp before that) | `StompA1` | before the amp |
| PostPedal1-4 (+ an amp's leftover EQ first) | `LoopFxA` | amp loop, before the cab |
| Rack1-4 | `RackMaster` | master bus |

Any stomp or rack model may sit in any of these sections ("stomp-in-rack / rack-in-stomp" in the manual).

## Amps

`convert_amp()` maps each Rocksmith amp knob onto the target amp's **real** parameter names from `at5_gear.json`:

1. The hand-made `AMP_KNOB_MAP` (in `cdlc_to_at5.py`) is used first, when it names a real parameter on the chosen channel.
2. Otherwise **role patterns** apply, in order of preference. For example, Rocksmith *Gain* goes to `Gain`, `Drive` or `PreAmp`, or to `Volume` on non-master-volume amps.
3. **Channel handling** covers `Ch2Gain`, `GainCh3` and `OD1_Gain` naming. The channel AmpliTube's own presets use most is selected, and only that channel's knobs are set.
4. A continuous knob is never written to a switch.
5. Graphic or semi-parametric bass-amp EQ controls with no AmpliTube equivalent become a 10 Band Graphic placed right after the amp, fitted to their curve.

Values land at the same position on the range (1..100 → 0..10). dB bands go onto dB bands.

## Cabinets, mics, DI, volume

- **Cab:** exact `CAB_ENCLOSURE_MAP` entry → the same cabinet under another mic position → speaker configuration parsed from the key (`TW112C` 1x12, `CH410BC` 4x10 bass…) → old fuzzy match → default 4x12.
- **Mic:** taken from the key's `<mic>_<position>` suffix (see `RS_MIC_TO_AT5` and `RS_MIC_POSITION`). Mic 1 is muted.
- **DI tones** (`DI_Amp_*`): the amp is muted as before, and the DI preamp itself (gain + EQ) becomes the first pre-amp effect (*Pre EQ 3* or *AmpLess*).
- **Tone `Volume`:** sets `AmpA OutputVolume` relative to −20 dB (±12 dB at most). The master `<Output>` is still set by the plugin's Output-level setting when a preset goes into a live slot.

## Regenerating the data

You need Rocksmith 2014 and AmpliTube 5 installed. Pass the paths if they aren't the defaults:

```
python tools/extract_rs_gear.py  [--psarc ".../Rocksmith2014/gears.psarc"]
python tools/extract_at5_gear.py [--pak ".../AmpliTube 5/AmpliTube 5.pak"] [--presets ".../Documents/IK Multimedia/AmpliTube 5/Presets"]
python -m pytest tests
```

`extract_at5_gear.py` skips `Presets/Converted` and `AT5_LIVE_*`, so the plugin's own output never feeds its own data. Re-run it after installing new AmpliTube gear or presets: more presets mean more models with known parameter names.

Bump `CONVERTER_VERSION` in `cdlc_to_at5.py` whenever conversion output changes. Song caches from older versions are then re-converted, and user save-backs are kept (see `docs/HUMAN_VERIFICATION.md` §H).
