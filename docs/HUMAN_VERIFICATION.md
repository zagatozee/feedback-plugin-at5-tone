# 0.8.0: what a human needs to verify

0.8.0 converts every Rocksmith knob into AmpliTube parameters, where earlier versions only set amp knobs. It was built and tested without AmpliTube running and without anyone listening, so everything below was checked against data and automated tests only:

- all 7,724 unique tones on the dev machine convert in three tiers with no errors and well-formed XML;
- 147 pytest tests pass;
- every model GUID exists in AmpliTube's GearInfo.

Two kinds of thing could still be wrong:

1. **How AmpliTube reads the file.** These are format assumptions that only loading a preset in AmpliTube can confirm.
2. **How it sounds.** These are mapping choices that only listening can confirm.

Items are ordered by how many tones they affect. Counts come from the dev machine's library: 6,739 unique Rocksmith 2014 tones and 985 unique Rocksmith+ tones, 35,867 gear uses in total. Each item names the code to change if it's wrong. Search the code for `VERIFY` to find every assumption.

How to test a tone: convert a song, play it in feedBack Desktop with the AmpliTube VST3 loaded, open the AmpliTube UI, and compare against the Rocksmith tone, by ear and against the knob values the plugin logs.

---

## A. Loading and routing (check these first)

### A1. AmpliTube loads presets whose effect slots carry parameters
Before 0.8, every effect slot was written as `<Slot0 Bypass="0" />`. Now slots carry values, e.g. `<Slot0 Bypass="0" Delay="480" Feedback="35" Level="3" />`.
- Load any converted tone. Check that AmpliTube doesn't crash or show a load error, and that the knobs show the written values. A good test is a Studio EQ tone: the 31-band rack EQ should show a curve.
- Affects every tone with an effect: 21,476 effect slots in the library.

### A2. The signal chain
`Chain11` is assumed to be the manual's "Single path" chain (§3.7: 12 effects before the amp, 4 in the loop, 2 after each cab, 6 on the master bus). On that basis:
- Rocksmith **pre-pedals** go to `StompA1`, before the amp.
- **Post-pedals** go to `LoopFxA`, the amp's loop FX between amp and cab. Before 0.8 they went to `StompB1`, which in a single-path chain is also *before* the amp.
- **Racks** go to `RackMaster`, the master bus. Before 0.8 they went to `RackA`/`RackB`, and RackB follows the muted cab B.
- Check in AmpliTube's chain view that a delay/reverb post-pedal appears after the amp and that racks are audible.
- Code: `build_preset()` in [cdlc_to_at5.py](../cdlc_to_at5.py).

### A3. Rack models in stomp slots, and the reverse
Each Rocksmith effect now uses its best AmpliTube model even if that is a rack placed in a stomp section. The manual says AmpliTube loads these as "rack-in-stomp / stomp-in-rack", and factory presets do it, but this converter hadn't done it before.
- Example: Rocksmith Studio Chorus → AmpliTube *Digital Chorus* (a rack), placed in `LoopFxA` as a post-pedal.

### A4. Tone volume → amp section level
Each Rocksmith tone's `Volume` (dB, median −20.5) now sets `AmpA OutputVolume` relative to a **−20 dB reference**, limited to ±12 dB. The master `<Output>` stays under the plugin's Output-level setting.
- Check: tones within one song should keep their relative loudness, and nothing should clip or vanish.
- Code: `TONE_VOLUME_REF_DB` in [tone_params.py](../tone_params.py).

### A5. Cab microphone
The Rocksmith cab key's mic and position (`_57_Cone`, `_Condenser_Edge`, `_Ribbon_OffAxis`, `_Tube_Cone`) now set mic 0, and mic 1 is muted (Rocksmith cabs are single-mic).
- Assumed mic models: 57 → Dynamic 57, Condenser → Condenser 87, Ribbon → Ribbon 121, Tube → Condenser 12. Rocksmith doesn't name its condenser or tube mics.
- Assumed positions: Cone = X 0, Edge = X 0.8, Off-axis = X 0.3 with Angle 1. AmpliTube's `Mic0XAxis`/`Angle` scales were inferred from factory presets.
- The room mics stay at the template's −34.5 dB. Check whether Rocksmith tones sound drier, and if so mute the room (`Cab1_Room_Mute`).
- Code: `RS_MIC_TO_AT5`, `RS_MIC_POSITION`, `cab_mic()`.

---

## B. High-use sound mappings (listen)

| # | Rocksmith gear (uses) | Converted to | Assumption to check |
|---|---|---|---|
| B1 | Studio Parametric EQ (6,387), Studio ParaGraphic EQ (115) | 31-band *GraphicEQ* rack, fitted to the EQ curve | Bass/Treble are treated as **shelves**, Low/High-Mid as peaks. "Wide/Narrow" Q is assumed to be **0.7 / 2.0** (not published). The GraphicEQ's `OutLevel` is assumed to be stored in dB. |
| B2 | MB Comp (2,495) | *Tube Compressor* rack | Compress → Drive (−6..+15 dB), Recovery → Release (1500→50 ms), Ratio fixed at 4. The multiband crossover can't be reproduced. Tube Compressor storage units (Drive linear, Attack/Release ms) were inferred. |
| B3 | 5-Band Graphic EQ (2,022), 8-Band EQ (683), 8-Band Bass EQ (423) | 7/10-band graphic, fitted | 7-band stored as **linear** gain (from factory presets), 10-band as **dB**. The 63 Hz band sits below the 7-band's range. |
| B4 | Spring Reverb (1,123) | '63 Reverb | Depth → Dwell, Mix → Mixer. Time has no equivalent. |
| B5 | Studio Chorus (739) | *Digital Chorus* rack | Rate in Hz copied (0.1–8 Hz). Stereo spread reduced to the Stereo/Mono switch. Delay, LoFilter and HiFilter have no equivalent. |
| B6 | Studio Compressor (724) | Tube Compressor | **Threshold → Drive** (no threshold control). Ratio by label (1.5:1 … 20:1). Attack/Release in ms. |
| B7 | DI Tube Pre (602) | *Pre EQ 3* stomp (amp muted) | The unitless 1..100 tone knobs are read as **±12 dB**. The mid-frequency selector is assumed to be 400/800/1600 Hz. |
| B8 | Studio Chamber (599) / Studio Plate (296) / Plate Reverb (24) | *Room* / *Plate Reverb* racks | Decay/Size/Color ranges for these T-RackS reverbs are only partly in presets. Diffusion → Size. |
| B9 | Studio Hall (371) / Digital Verb (66) | *Digital Reverb* rack | Decay 1..100 → 0.4–8 s on a log scale (the Rocksmith curve is unknown). Tone → Color 2–20 kHz. |
| B10 | Lo-Fi Filter (274), Bit Cruncher (10) | *Crusher* | Rocksmith keys "Mix" but labels it "Lo Cut", and Crusher has no high-pass. The Crusher output gain storage was inferred. |
| B11 | Studio Delay (168) | *Digital Delay* rack | Uses one delay time (left), with L/R mode when the times differ. Filter % → low-pass 20 k→1.5 kHz. |
| B12 | Octave Up (170) | Octa-V | Tone → Drive, and the octave amount isn't representable. |

## C. Amps

- **Knob scale.** Rocksmith amp knobs (1..100) land at the same position on AmpliTube's 0..10. AmpliTube amp parameter names come from its own factory presets. Rocksmith's `Gain` goes to the real gain knob, or to the volume on non-master amps (tweeds, Plexi, AC30).
- **Multi-channel amps.** The channel set is the one AmpliTube's own presets use most:
  - Dual Rectifier → Ch 2
  - German 34 → CH3
  - Satch VM → Clean
  - SVX-VR → Combine

  A high-gain Rocksmith tone on Satch VM in particular may want OD1/OD2. Code: `_amp_channel()`.
- **Bass-amp EQs.** Graphic and semi-parametric controls the AmpliTube amp lacks (e.g. Rocksmith CH350B's 7 bands, Eden WT Low-Mid/High-Mid with frequency) are rebuilt as a **10 Band Graphic right after the amp**. Check the placement. Real bass amps have the EQ in the preamp.
- **AC30 Presence** maps inversely onto `Cut` where an amp only has Cut.
- **Amp substitutions** for gear AmpliTube doesn't have:
  - Orange AD50 → AD 30
  - Orange OR100 → OR-120
  - Orange "Jimmy Bean" → Dual Terror
  - Eden E300/WT800 → New York B750
  - Epiphone Zephyr / Gibson GA-88 → Tube Vintage Combo
  - Gibson GA-8 → '57 Champ
  - DI Mixer Pre → DI, with the amp muted

## D. Cabinets

- About 98% of cab uses match a mapped cabinet: exact, or the same cabinet at a different mic position.
- 53 uses are matched by **speaker configuration** parsed from the key (`CH410BC` = 4x10 bass). The note says "matched by speaker configuration … VERIFY".
- Rocksmith's novelty cabs (jukebox, gramophone, radio, boombox, hi-fi) → *1x8 '57 Custom Champ*, the smallest AmpliTube cab.

## E. Free (CS) and other tiers

- Free mode used to crash with `NameError` on the first effect (`AT5_CS_STOMP_MAP` was never defined), so **free-mode conversion has effectively never worked with effects**.
- The CS effect set now follows what AmpliTube's own *AmpliTube 5 CS* presets use. Check that a CS-only install loads every effect in a converted free-mode preset.
- The free-tier flanger maps to *Digital Chorus*, because no flanger appears in CS presets.
- Tier amp/cab tables had **15 made-up GUIDs**. The amps' GUIDs had the right first 8 characters and invented tails, so SE/AT5-tier presets named amps AmpliTube doesn't have. They are now the real GUIDs. Four CS cab entries also pointed at the wrong cabinet. Check that SE/AT5-tier presets now load the intended amp/cab.

## F. Lower-use items (each under 100 uses)

Envelope filters (`Res` is keyed Resonance but labelled "Mix" in Rocksmith), Tape Echo "Lo Filter", Plate Reverb voice, Mixer DI tone, Oil-Can Echo (AmpliTube's *Oil Can Delay* parameters are undocumented, so *Tape Echo* is used), Ring Mod (*AM Modulator*'s parameter names are unknown, so it loads at its defaults), Amp EQ pedal frequency selectors, and the envelope tremolo/vibe pedals. Each is described by its `VERIFY` note in `tone_params.py`.

## G. Older open items (from before 0.8)

- **Wharmonator expression CC**: `gear_mapping_reference.md` lists it as "TBD — requires MIDI Learn in AT5". Someone needs to MIDI-learn the Wharmonator pedal in AmpliTube and enter the CC number. `routes.py` skips wah/whammy CC automation until then.
- **0.7.0 Desktop integration** is still marked "not yet human-validated" in the README.

## H. Upgrading existing song caches

Converted presets stored beside songs (`<song>/at5/<tier>/*.at5p`) are now tagged `KeyWords="at5_tone converter 0.8.0"`. When a song loads:

- Presets from an older converter are **moved to `at5/<tier>/superseded/`** (never deleted) and re-converted.
- Pre-0.8 presets are recognised by the old template's exact attribute sequences. On the dev machine this matched 12/12 real 0.7 files and **0/776** AmpliTube-written presets.
- Presets saved back from AmpliTube (💾) are tagged `at5_tone user` and never replaced.

**Check:** a song with a pre-0.8 save-back edit keeps that edit. If an edit was ever moved by mistake, it is in `superseded/`.
