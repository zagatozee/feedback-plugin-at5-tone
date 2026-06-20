# AT5 Tone Switcher — feedBack Plugin
**v0.6.2**

Automatically switches AmpliTube 5 presets in sync with song playback in feedBack. When you load a song, the plugin extracts the guitar tone data, converts it to AT5 presets, and fires MIDI Program Change messages at the right moments — no manual switching needed.

---

## Installation

### Option A — Plugin Manager (recommended)

1. In feedBack, open **Plugins** in the nav bar
2. Click **Add from GitHub**
3. Enter: `zagatozee/feedback-plugin-at5-tone`
4. Click Install

### Option B — Manual

Download the zip, extract the `at5_tone` folder, and copy it to:

**Desktop app:**
```
C:\Users\<username>\AppData\Roaming\fee[dB]ack\plugins\at5_tone\
```

**Docker:**
```
<feedback_root>\plugins\at5_tone\
```
Then restart the container: `docker restart feedback-web-1`

---

## Setup — Desktop App

The plugin's Status tab will guide you through setup with buttons. Here's what happens:

### Step 1 — Link Presets folder
Click **Create Symlink** in the Status tab. This links feedBack and AT5 to the same Presets folder so converted presets are immediately visible to AT5.

> If the button fails, run feedBack Desktop as administrator (right-click → Run as administrator) and try again. The error message will also show the exact PowerShell command to run manually if needed.

### Step 2 — Populate live slots
Click **Run Setup**. This creates 8 preset slots (AT5_LIVE_00–07) and registers them in AT5's Program Change list. Restart AmpliTube 5 after this step.

### Step 3 — Configure AT5
In AmpliTube 5:
- **Options → Audio/MIDI → MIDI Input:** set to your audio interface or loopMIDI port
- **Options → Control → Program Change:** enable Preset Control, Receive Channel: All
- Restart AT5

### Step 4 — Select MIDI output
In the AT5 plugin Status tab, select your MIDI output from the dropdown:

| Your setup | Select |
|-----------|--------|
| AT5 loaded as VST in feedBack Desktop chain | Internal VST — no extra software needed |
| AT5 standalone + loopMIDI | Your loopMIDI port (e.g. "AT5 Bridge") |
| AT5 standalone + audio interface | Your interface (e.g. "AXE IO") — requires MIDI cable looped OUT→IN |

> **Simplest setup:** load AT5 as a VST inside feedBack Desktop's audio chain. No loopMIDI, no cable, no bridge script needed.

> **loopMIDI download:** https://www.tobias-erichsen.de/software/loopmidi.html — free, create one virtual port, leave it running in the system tray.

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

### Step 2 — Populate live slots
Run once from a terminal on the Windows host:
```
python plugins\at5_tone\generate_at5_pc_map.py
```
Restart AmpliTube 5 after running.

### Step 3 — Configure AT5
Same as Desktop Step 3 above.

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
| `cdlc_to_at5.py` | Tone converter |
| `at5_midi_bridge.py` | MIDI bridge script (Docker fallback) |
| `generate_at5_pc_map.py` | One-time PC map setup |
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

Effects with no CS equivalent are dropped rather than substituted wrongly. Dropped in CS: pitch shifter, whammy, octave, phaser, ring mod, bit crusher, acoustic/bass emulator, vibe. Everything else (wah, chorus, flanger, overdrive, compressor, delay, reverb, tremolo, noise gate, EQ) is remapped to the closest CS equivalent.

---

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

- [ ] Plugin appears in Plugins menu after install
- [ ] Status tab shows setup panel — "Presets folder not linked"
- [ ] Create Symlink button succeeds (run as administrator if it fails)
- [ ] Run Setup button completes — reports 8 live slots created
- [ ] Restart AT5 — presets appear in Program Change list (PC 121–128)
- [ ] AT5 MIDI Input set to your port, Program Change enabled
- [ ] MIDI output dropdown shows your port — hint text shown below it
- [ ] Test button fires PC 0 — AT5 switches to first preset
- [ ] Load a CDLC song — Live Slots section populates within ~1 second
- [ ] Play the song — AT5 switches presets at tone change events
- [ ] Tone Browser — search returns results, ▶ button auditions correct preset
- [ ] Noise gate — enable in Settings, reload song, open .at5p in text editor,
      confirm GUID `0455f997` appears at StompA1 slot 0
- [ ] Save-back — edit a tone in AT5, click 💾, reload song, confirm edits persist

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

- [ ] Diag button in Status tab shows correct _at5MidiOutput name and port ID
- [ ] Settings page (feedBack nav → Settings) shows AT5 section with tier
      selector, noise gate checkbox, MIDI offset slider
- [ ] Switching tier clears live slots — next song load re-converts
- [ ] Live Log tab captures every tone switch with timestamp

---

## Known issues

**Docker bridge window latency** — 100ms polling may add jitter on top of the prefire offset. If tone switches feel late, increase the MIDI Trigger Offset slider in Settings. A WebSocket upgrade is planned.

**AT5 as VST** — MIDI signalling confirmed working via `sendMidiToSlot`. Guitar audio routing through feedBack Desktop's chain is not yet fully validated. Use standalone AT5 for now.

**Browser tab suspension** — if the bridge window is backgrounded for a long time in a non-Electron browser, Chrome may throttle polling. Keep the window visible or use the Python bridge as fallback.

**Non-standard AT5 install paths** — if AT5 documents are not in Documents or OneDrive/Documents, path detection may fail. A text input field will appear in the setup panel — paste your AT5 Presets folder path there.

**Symlink requires admin** — Windows requires elevated privileges to create symbolic links. If the button fails, run feedBack Desktop as administrator or use the manual PowerShell command shown in the error message.

---

## Troubleshooting

**Setup panel shows "Presets folder not linked" after clicking Create Symlink**
Run feedBack Desktop as administrator and try again.

**Live slots not populating**
Make sure the Presets folder is linked first, then run Setup again.

**AT5 crashes on startup**
Delete `AT5_LIVE_*.at5p` from your AT5 Presets/Converted folder and let the plugin recreate them.

**No tone switches firing**
Check: AT5 MIDI Input is set correctly, Program Change is enabled in AT5 Control settings, correct MIDI output selected in plugin Status tab. Use the Diag button to inspect what _at5MidiOutput is set to.

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

Every CDLC song file contains the guitar tone settings from the original guitar game — amp model, cabinet, pedals, all knob positions. When you load a song, the plugin reads those settings and converts them to AT5 preset files using a mapping of CDLC gear to AT5 equivalents. It writes the presets to 8 reserved PC slots (120–127) and sends MIDI Program Change messages at the correct timestamps during playback.

The first load converts and seeds presets beside the song file in a tier-specific subfolder. Every subsequent load copies them directly — no extraction needed. If you edit a preset in AT5 and save it back, your version loads from then on.
