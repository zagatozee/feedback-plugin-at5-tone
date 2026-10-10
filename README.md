# AT5 Tone Switcher — feedBack Plugin
**v0.8.0** · requires feedBack 0.3.1-alpha.4 or newer

> ⚠️ **0.8.0 is not yet human-validated either.** It converts every pedal, rack, amp, cab-mic and tone-volume setting (earlier versions only set amp knobs), and was checked with automated tests and a conversion of 7,724 real tones, not by ear or in AmpliTube. [docs/HUMAN_VERIFICATION.md](docs/HUMAN_VERIFICATION.md) lists what to check, most important first; see [CHANGELOG.md](CHANGELOG.md) for the full list of changes.
>
> ⚠️ **Not yet human-validated.** The 0.7.0 update (feedBack v3 / Desktop) was prepared and shared by Claude (Claude Code in VS Code). Only automated checks have passed so far: the pytest suite, a smoke run against feedBack core 0.3.1-alpha.4, and a headless-browser run of the v3 UI with a *simulated* Desktop audio API. It has not yet been tried by a person with AmpliTube 5 loaded in feedBack Desktop — please report anything that doesn't work.

Automatically switches AmpliTube 5 presets in sync with song playback in feedBack. When you load a song, the plugin extracts the guitar tone data, converts it to AT5 presets, and fires MIDI Program Change messages at the right moments — no manual switching needed.

**feedBack Desktop is the primary target.** Load the AmpliTube 5 VST3 into Desktop's Signal Chain and the plugin drives it directly — no MIDI cable, virtual port, bridge script or symlink. Standalone AT5 (via loopMIDI) and Docker/browser setups (via the MIDI bridge) still work as secondary paths.

---

## Installation

Clone (or copy) the repo into feedBack's plugins folder as `at5_tone`, then restart feedBack:

**Desktop app (Windows):**
```
git clone <repo-url> "%APPDATA%\feedback-desktop\plugins\at5_tone"
```

**Docker / self-hosted:** clone anywhere and mount it with the included overlay:
```
AT5_TONE_PLUGIN_DIR=$(pwd) docker compose -f /path/to/feedBack/docker-compose.yml -f ./docker-compose.feedback.yml up -d
```

> The Desktop Plugin Manager can also install from a git URL, but a private repo needs git credentials available to it.

---

## Setup — Desktop App

Open **AT5** in the nav. The Status tab guides you through setup:

### Step 1 — AmpliTube 5 folder
The plugin finds `Documents\IK Multimedia\AmpliTube 5` on its own (OneDrive-redirected and relocated Documents folders included) and shows it in the **AmpliTube 5 setup** card. If it can't, paste the folder into the box and click **Use folder** — the choice is saved. Live slot files (`Presets\Converted\AT5_LIVE_00–07.at5p`) are created there automatically.

### Step 2 — Register the live slots
Click **Run Setup**. This registers the 8 live slots as PC 121–128 in AT5's Program Change list (`ProgramChangePresetList.ik`; any existing list is backed up with a timestamp first). Restart AmpliTube 5 — or remove and re-add it in the Signal Chain — afterwards.

### Step 3 — Load AmpliTube 5
**Recommended:** on feedBack's **Audio** screen, add the **AmpliTube 5** VST3 to the Signal Chain. In AT5's own settings enable Program Change (Preset Control). The Status tab shows **AmpliTube 5 ready · Desktop signal chain** and the MIDI output picker's **Auto** choice uses it.

**Standalone AT5 instead:** create a [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) port, set it as AT5's MIDI input (Options → Audio/MIDI), enable Program Change (Options → Control), and pick the port in the Status tab's **MIDI output** dropdown.

| Your setup | MIDI output |
|-----------|--------|
| AT5 VST3 in feedBack Desktop's Signal Chain | **Auto** or "AmpliTube 5 in Desktop signal chain" — nothing else needed |
| AT5 standalone + loopMIDI | Your loopMIDI port |
| AT5 standalone + audio interface | Your interface — requires a MIDI cable looped OUT→IN |

---

## Setup — Docker

### Step 1 — Docker volume
Add to your `docker-compose.yml` under `volumes:`:
```yaml
- "C:/Users/<username>/Documents/IK Multimedia/AmpliTube 5:/at5docs"
```
> If AT5 documents are in OneDrive use:
> `C:/Users/<username>/OneDrive/Documents/IK Multimedia/AmpliTube 5:/at5docs`
>
> Check the correct path in AT5 under Options → General.

Restart the container after changing docker-compose.yml.

### Step 2 — Register the live slots
Click **Run Setup** in the Status tab (it writes through the `/at5docs` mount), or run once on the Windows host:
```
python generate_at5_pc_map.py --presets-dir "C:/Users/<username>/Documents/IK Multimedia/AmpliTube 5/Presets"
```
Restart AmpliTube 5 after running.

### Step 3 — Configure AT5
Same as the standalone AT5 instructions in Desktop Step 3 above.

### Step 4 — AT5 MIDI Bridge window
Docker can't access Windows MIDI directly. On your first visit to the plugin's Status tab, an orange banner will appear — click **Open Bridge ↗** to open the AT5 MIDI Bridge window. Leave it open in the background. It handles MIDI directly from your host browser with no extra software needed.

The bridge window shows a live log of every MIDI command sent, with **📋 Copy Log**, **💾 Save Log**, and **🗑 Clear** buttons for troubleshooting.

> If you prefer the Python bridge script instead:
> ```
> python plugins\at5_tone\at5_midi_bridge.py --midi-port "Your Device Name"
> ```
> See Troubleshooting for how to find your device name.

---

## Files

| File | Purpose |
|------|---------|
| `plugin.json` | feedBack plugin descriptor |
| `routes.py` | Plugin backend |
| `screen.js` | Plugin frontend |
| `screen.html` | Plugin UI |
| `settings.html` | Settings panel (shown in feedBack Settings page) |
| `cdlc_to_at5.py` | Tone converter (gear selection, chain placement, preset assembly) |
| `tone_params.py` | Knob-accurate conversion of every Rocksmith knob to AmpliTube parameters |
| `data/rs_gear_defs.json` | Rocksmith knob definitions (units, ranges, defaults) |
| `data/at5_gear.json` | AmpliTube model list and preset-learned parameters |
| `tools/` | Scripts that regenerate `data/` from local Rocksmith 2014 / AmpliTube 5 installs |
| `docs/` | How conversion works; what still needs human verification |
| `at5_midi_bridge.py` | MIDI bridge script (Docker fallback) |
| `generate_at5_pc_map.py` | One-time PC map setup |
| `docker-compose.feedback.yml` | Compose overlay that mounts the plugin into a feedBack container |
| `tests/` | pytest suite (`python -m pytest tests`) |
| `gear_mapping_reference.md` | RS → AT5 gear mapping tables |

---

## AT5 Version Selector

In **Settings**, select your version of AT5:

| Version | Amps | Notes |
|---------|------|-------|
| CS — Free | 6 | Covers most rock/metal tones. Some effects dropped. |
| SE | 13 | Adds Peavey, Roland JC, Mesa family. Recommended minimum. |
| AT5 | 35 | Adds Bogner, Silver Jubilee, many more. |
| MAX | 107 | Full library — closest possible match for every tone. |

Each tier uses a separate preset cache (`at5/cs/`, `at5/se/`, `at5/at5/`, `at5/max/` beside each song file). Switching tiers re-converts all tones from scratch without touching your saved edits in other tiers.

### Amp mapping (CS tier example)

| CDLC amp family | Maps to |
|---------------------|---------|
| Marshall JCM/DSL/JVM, Orange | Brit 8000 |
| Peavey 5150, Mesa Rectifier, Soldano | SLD 100 |
| Fender clean, Mesa clean | American Tube Clean 1 |
| Roland JC-120 | American Tube Clean 2 |
| Marshall JTM45, Silver Jubilee, Bluesbreaker | British Tube Lead 1 |
| Bass amps (Ampeg, Aguilar) | Solid State Bass Preamp |

SE and AT5 tiers route the same amps to closer matches where available (Peavey → Metal Lead V in SE+, Roland JC → Jazz Amp 120 in SE+, Bogner → German 34 in AT5+).

### Effects in constrained tiers

Effects with no CS equivalent are dropped rather than substituted wrongly. Dropped in CS: pitch shifter, whammy, octave, phaser, ring mod, bit crusher, acoustic/bass emulator, vibe. Everything else (wah, chorus, flanger, overdrive, compressor, delay, reverb, tremolo, noise gate, EQ) is remapped to the closest effect AmpliTube's own CS presets use. Before 0.8.0, free mode crashed on the first effect; see the changelog.

In MAX, every Rocksmith pedal and rack uses the AmpliTube model chosen so its controls have somewhere to go. In lower tiers, knobs are matched by name and unit onto whatever model the tier allows.

---

## Output Level

Every song loads a fresh preset into AmpliTube, so AT5's own **Output** knob resets each time. Set the level in the plugin's **Settings → Output level** instead (−30 to +6 dB, default **−10 dB**). It is written into the master output of every tone as it goes into a live slot — freshly converted and song-local presets alike — and applies from the next song. The level is *set* on the live slot each time a tone is loaded, never scaled, so it does not stack. A preset already stored with the song is not re-leveled by this, but one seeded from a fresh conversion is stored at the level in effect when it was converted (and is set again to your current level when it is loaded).

Most song tones carry no amp **Volume/Master** knob, which left AT5 on the amp model's own (loud) default. When a tone's amp sets no volume at all, the plugin now fills in a middle value (5) on that model's Volume/Master knobs. A volume the preset already sets — for example one you turned in AT5 and saved back to the song — is left alone. Note that the Output level setting owns each preset's master output: a different Output saved in a song preset is replaced at playback.

## Global Noise Gate

Enable in **Settings → Signal Chain**. Inserts the AT5 Noise Gate at pre-amp stomp slot 0 in every converted tone, shifting other effects down by one slot. Cuts hum and noise before the gain stage. Available in all AT5 versions.

> Changing this setting clears the live slot cache — the next song load will re-convert with the gate applied. Previously saved save-back presets are not affected.

---

## Save-back

Dial in a tone in AT5, then in the plugin Status tab click 💾 on a slot. Your edited preset is stored beside the song file and loads automatically on every subsequent play. Edits are stored per-tier — switching tiers generates a fresh conversion without touching edits in other tiers.

---

## Testing checklist

Work through these in order on a fresh install:

### Desktop app

- [ ] Plugin appears in the Plugins page / nav after install
- [ ] Status tab → AmpliTube 5 setup card shows the detected AT5 folder (or accepts one via **Use folder**)
- [ ] Run Setup completes — "8 live slots ready (PC 121–128)"
- [ ] Restart AT5 — live slots appear in its Program Change list
- [ ] AT5 VST3 added to the Signal Chain — Status shows "AmpliTube 5 ready · Desktop signal chain"
- [ ] Test button fires PC 0 — AT5 switches to its first mapped preset
- [ ] Load a song with tones — the AT5 badge in the player's Plugins rail shows the slot (e.g. "AT5 #121")
- [ ] Play the song — AT5 switches presets at tone change events; seeking back re-sends the earlier tone
- [ ] Tone Browser — search returns results, ▶ button auditions correct preset
- [ ] Noise gate — enable in Settings, reload song, open .at5p in text editor,
      confirm GUID `0455f997` appears at StompA1 slot 0
- [ ] Save-back — edit a tone in AT5, click 💾, reload song, confirm edits persist
- [ ] Restart feedBack — tier / noise gate / AT5 folder settings are kept

### Docker

- [ ] Plugin appears after container restart
- [ ] Status tab shows orange "Open AT5 MIDI Bridge window" banner
- [ ] Clicking Open Bridge ↗ opens bridge window popup
- [ ] Bridge window shows "MIDI Ready → [port name]" in green
- [ ] Banner dismissed — does not reappear on refresh
- [ ] Load a CDLC song — Live Slots populates
- [ ] Play song — bridge window log shows PC entries firing, AT5 switches
- [ ] Copy Log — content appears in clipboard
- [ ] Save Log — .txt file downloads with correct timestamp

### Both

- [ ] Diag button shows the active route, last send result, Web MIDI ports and (Desktop) the Signal Chain
- [ ] Settings page (feedBack nav → Settings) shows AT5 section with tier
      selector, noise gate checkbox, MIDI offset slider
- [ ] Switching tier clears live slots — next song load re-converts
- [ ] Live Log tab captures every tone switch with timestamp

---

## Known issues

**Docker bridge window latency** — 100ms polling may add jitter on top of the prefire offset. If tone switches feel late, increase the MIDI Trigger Offset slider in Settings. A WebSocket upgrade is planned.

**AT5 as VST** — Program Change / CC go straight to the AmpliTube slot via Desktop's `sendMidiToSlot` (versions before 0.7.0 sent malformed messages here). Only Signal Chain slots whose name or path contains "AmpliTube" receive them.

**Browser tab suspension** — if the bridge window is backgrounded for a long time in a non-Electron browser, Chrome may throttle polling. Keep the window visible or use the Python bridge as fallback.

**Non-standard AT5 install paths** — if detection fails, paste the AT5 documents folder (or its Presets folder) into the setup card and click **Use folder**. It can also be forced with the `AT5_DOCS_DIR` environment variable.

---

## Troubleshooting

**Setup card says "AmpliTube 5 folder not found"**
Paste the folder that contains AT5's `Presets` folder (usually `Documents\IK Multimedia\AmpliTube 5`) and click **Use folder**.

**Live slots not populating**
Make sure the AT5 folder is set first, then click Run Setup again.

**AT5 crashes on startup**
Delete `AT5_LIVE_*.at5p` from your AT5 Presets/Converted folder and let the plugin recreate them.

**No tone switches firing**
Check: AT5 MIDI Input is set correctly, Program Change is enabled in AT5 Control settings, correct MIDI output selected in plugin Status tab. Use the Diag button to see which route the plugin picked and whether the last send succeeded.

**Tone Browser shows no results**
The bundled MIDI plugin (`midi_amp`) is required and should always be present. If missing, reinstall feedBack.

**Docker: finding your MIDI device name**
```powershell
python -c "
import ctypes
class MIDIOUTCAPS(ctypes.Structure):
    _fields_ = [('wMid',ctypes.c_uint16),('wPid',ctypes.c_uint16),
                ('vDriverVersion',ctypes.c_uint32),('szPname',ctypes.c_wchar*32),
                ('wTechnology',ctypes.c_uint16),('wVoices',ctypes.c_uint16),
                ('wNotes',ctypes.c_uint16),('wChannelMask',ctypes.c_uint16),
                ('dwSupport',ctypes.c_uint32)]
winmm = ctypes.windll.winmm
for i in range(winmm.midiOutGetNumDevs()):
    caps = MIDIOUTCAPS()
    winmm.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
    print(f'{i}: {caps.szPname}')
"
```

**Opening the plugin screen pauses playback**
This is a feedBack core behaviour affecting all plugins. Use the Live Log tab to review what happened after resuming.

---

## How it works

Every CDLC song file contains the guitar tone settings from the original guitar game — amp model, cabinet, pedals, all knob positions. When you load a song, the plugin reads those settings and converts them to AT5 preset files using a mapping of CDLC gear to AT5 equivalents. Every knob is converted by its real unit (ms, Hz, dB, %), EQs are rebuilt as curves, and the cab mic, DI preamp and tone volume carry over; see [docs/CONVERSION.md](docs/CONVERSION.md). It writes the presets to 8 reserved PC slots (120–127) and sends MIDI Program Change messages at the correct timestamps during playback.

The first load converts and seeds presets beside the song file in a tier-specific subfolder. Every subsequent load copies them directly — no extraction needed. If you edit a preset in AT5 and save it back, your version loads from then on.
