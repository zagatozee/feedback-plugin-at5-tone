# Changelog

## 0.8.0: every knob converted (not yet human-validated)

Earlier versions set only amp knobs. Every effect loaded at AmpliTube's defaults, with `<Slot0 Bypass="0" />` and no values. 0.8.0 converts the **whole** Rocksmith 2014 / Rocksmith+ tone. See [docs/CONVERSION.md](docs/CONVERSION.md) for how, and [docs/HUMAN_VERIFICATION.md](docs/HUMAN_VERIFICATION.md) for what still needs ears and eyes.

### Added
- **Pedal and rack parameters.** All 100 Rocksmith pedal/rack models (and the 3 DI preamps) have a conversion recipe. Values are converted by unit: ms, Hz, dB, linear gain, %, enum, or position on range. Tones that omit a knob use the game's own default for it. Every knob without an AmpliTube equivalent is reported in the log with the reason.
- **EQ curve fitting.** Rocksmith EQs (graphic and parametric) are rebuilt as filter curves, and the AmpliTube EQ is fitted to that curve. The Studio Parametric EQ (the most-used Rocksmith rack) goes onto the 31-band GraphicEQ.
- **Amp knobs onto real parameter names** taken from AmpliTube's own presets, instead of `value / 10` onto guessed names. This adds channel-aware mapping for multi-channel amps, never puts a continuous knob on a switch, and rebuilds bass-amp graphic/semi-parametric EQs as a 10 Band Graphic after the amp.
- **Cab microphone and position** taken from the Rocksmith cab key (57/Condenser/Ribbon/Tube; Cone/Edge/Off-axis).
- **DI tones** keep their preamp settings: Tube Pre / Mixer Pre → Pre EQ 3, Bass Driver → AmpLess.
- **Tone volume.** Rocksmith's per-tone `Volume` sets the amp section level, so tones keep their relative loudness.
- **Data and tools.**
  - `data/rs_gear_defs.json`: the official Rocksmith knob definitions, from `gears.psarc`.
  - `data/at5_gear.json`: AmpliTube's GearInfo model list plus parameters learned from its presets.
  - `tools/extract_rs_gear.py` and `tools/extract_at5_gear.py` regenerate them.
- Command-line flags `--tier`, `--free` and `--noise-gate`.
- Tests: `tests/test_tone_params.py` and `tests/test_cache_upgrade.py`.

### Fixed
- **Post-amp pedals were placed before the amp.** Rocksmith's loop pedals (PostPedal1-4) went to `StompB1`, which in AmpliTube's single-path chain is *pre*-amp. They now go to the amp's loop FX (`LoopFxA`). Racks moved from `RackA`/`RackB` (RackB follows the muted second cab) to the master rack.
- **Free (CS) mode crashed** with `NameError: AT5_CS_NULL_EFFECT` on the first effect: the CS effect maps were never defined. They are now defined, from the gear AmpliTube's own CS presets use.
- **15 made-up GUIDs** in the SE/AT5 tier amp table and the Metal T/V cabs replaced with the real ones from GearInfo. Four CS cab entries pointed at the wrong cabinet (e.g. "2x12 Closed Vintage" was the 2x12 JP Jazz).
- **Rocksmith 2014 path:**
  - `convert_tone_rs2014` / `_xml` ignored the tier, free-mode and noise-gate settings.
  - Amp knobs were read from `Knobs`, while real manifests use `KnobValues`.
  - Real song manifests (`Entries → Attributes → Tones[]`) were not recognised.
  - All three are fixed. Tones are now found at any depth.
- The **Rocksmith+ path** dropped PrePedal3/4 and PostPedal3/4. Both paths now share one preset builder.
- **Amps.** Nine amps in a typical library resolved to *no amp*: Orange AD50/OR100/Jimmy Bean, Eden E300/WT800, Epiphone Zephyr, Gibson GA-8/GA-88, DI Mixer Pre. They now map to the closest AmpliTube model.
- **Cabs** missing from the map no longer fall back to a Marshall 4x12: the same cabinet at another mic position is used, or the speaker configuration in the key (98% of cab uses now match a real mapping).
- Converter output on a Windows console no longer crashes on the `⚠` character.

### Changed
- Converted presets carry `KeyWords="at5_tone converter 0.8.0"`. Song caches from older converters are moved to `at5/<tier>/superseded/` and re-converted. Presets saved back from AmpliTube are tagged `at5_tone user` and never replaced.
- `routes.py` writes empty live slots through `cdlc_to_at5.template_defaults()`, so it can't drift from the template again.
