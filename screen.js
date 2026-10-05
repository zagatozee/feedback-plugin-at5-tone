// AmpliTube 5 Tone Switcher — feedBack v3 / Desktop
// - Song lifecycle from feedBack events (song:ready / song:stop / song:ended)
// - setInterval + highway.getTime() (no setRenderer — doesn't interfere with visuals)
// - MIDI out, in order of preference:
//     1. AmpliTube 5 VST3 hosted in feedBack Desktop's signal chain (no extra software)
//     2. Web MIDI port → standalone AT5 (loopMIDI / hardware interface)
//     3. Docker: bridge window / at5_midi_bridge.py
// - Live tone log with per-song history, tone browser with manual trigger
// - All UI functions exposed as globals

(function () {
'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const AT5_PLUGIN_ID  = 'at5_tone';
const AT5_SCREEN_ID  = 'plugin-' + AT5_PLUGIN_ID;   // v3 mounts plugin screens as plugin-<id>
const AT5_BRIDGE_URL = 'http://localhost:37432';
const AT5_MIDI_CH    = 0;
const LOG_MAX        = 200;   // max log entries to keep
let AT5_PREFIRE_MS   = parseFloat(localStorage.getItem('at5_prefire_ms') ?? '0.2');   // seconds, despite the name

// Own HTML escaper (text and attribute safe) — core's global esc() survives
// only as a compatibility shim for older plugins.
function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ── Module state ───────────────────────────────────────────────────────────
let _at5Filename   = null;
let _at5PcTable    = {};
let _at5PcLoaded   = false;
let _at5BridgeOk   = false;
let _at5MidiAccess = null;
let _at5MidiOutput = null;

// Scheduler
let _at5Timer      = null;
let _at5Schedule   = [];
let _at5LastFired  = -1;
let _at5LastKey    = null;
let _at5LastT      = null;   // previous poll time — used to detect seeks

// ── Live convert state ────────────────────────────────────────────────────
const LIVE_SLOT_START = 120;
const LIVE_SLOT_COUNT = 8;
let _at5LiveSlots    = {};   // tone_key -> pc_number (from live convert)
let _at5LiveLastFile = null; // avoid re-converting same song
let _at5LiveEnabled  = true; // set false if backend says cdlc_to_at5 missing

// ── Live convert state ────────────────────────────────────────────────────
// Tone log — persists across screen navigations
// [{ts, toneKey, pc, presetName, songTitle, arrangement, firedAt}]
let _at5Log = [];

// ── Song lifecycle ────────────────────────────────────────────────────────
// song:ready fires once the highway has every chart message for the loaded
// song — tone_changes included — and again on each arrangement switch, so
// it is the one place to (re)build the schedule. feedBack.currentSong
// carries the library filename (set when song_info arrives).
// Library filenames reach us both raw (feedBack.currentSong) and URL-encoded
// (older playSong callers); decode once, tolerating a literal '%'.
function _at5Decode(s) {
    try { return decodeURIComponent(s); } catch { return s; }
}

function _at5CurrentFilename() {
    const cur = window.feedBack && window.feedBack.currentSong;
    return (cur && cur.filename) || _at5Filename;
}

(function () {
    const orig = typeof window.playSong === 'function' ? window.playSong : null;
    if (orig) {
        window.playSong = async function (filename, arrangement) {
            _at5Filename = filename;
            return await orig.apply(this, arguments);
        };
    }
    const bus = window.feedBack;
    if (!bus || typeof bus.on !== 'function') return;
    bus.on('song:ready', () => {
        const filename = _at5CurrentFilename();
        if (!filename) return;
        _at5Filename = filename;
        _at5InjectBadge();
        _at5StartScheduler(filename);
    });
    // Leaving the player mid-song emits song:stop (no pause/ended event).
    // song:ended keeps the scheduler alive: replaying from the start is a
    // backwards seek, which the poll loop already rescans for.
    bus.on('song:stop', () => _at5StopScheduler(true));
})();

// ── PC table ───────────────────────────────────────────────────────────────
async function _at5LoadPcTable() {
    if (_at5PcLoaded) return;
    try {
        const r = await fetch('/api/plugins/at5_tone/pc_table');
        if (!r.ok) return;
        const data = await r.json();
        const count = Object.keys(data).length;
        if (count > 0) {
            _at5PcTable = data;
            _at5PcLoaded = true;
            console.log(`[AT5] PC table loaded: ${count} tone keys`);
        }
    } catch (e) { console.warn('[AT5] PC table load failed:', e); }
}

function _at5Lookup(toneKey) {
    if (!toneKey) return null;
    // Live slots take priority — exact conversion of this song's actual tones
    const livePC = _at5LiveSlots[toneKey];
    if (livePC !== undefined) {
        return { pc: livePC, preset_name: `LIVE_${livePC}`, in_top128: false, cc_adjustments: [], live: true };
    }
    // Fall back to pre-baked PC table
    if (_at5PcTable[toneKey]) return _at5PcTable[toneKey];
    const lower = toneKey.toLowerCase();
    for (const [k, v] of Object.entries(_at5PcTable))
        if (k.toLowerCase() === lower) return v;
    return null;
}

// ── MIDI output routing ───────────────────────────────────────────────────
// localStorage.at5_output_id selects the route:
//   'internal'  → AmpliTube 5 VST3 in feedBack Desktop's signal chain
//   'bridge'    → Docker: at5_midi_bridge.py if it answers, else the bridge window
//   <port id>   → that Web MIDI output (standalone AT5 via loopMIDI / interface)
//   unset       → auto: Desktop AT5 slot if loaded, else first Web MIDI port,
//                 else (browser/Docker only) the bridge
let _at5LastRoute = null;   // { kind, detail } of the most recent send — shown in Status

function _at5DesktopAudio() {
    return (window.feedBackDesktop && window.feedBackDesktop.audio) || null;
}

function _at5IsAmpliTubeSlot(s) {
    // SignalChain::Type { VST = 0, NAM, IR, Empty }
    return s && s.type === 0 && /amplitube/i.test(`${s.name || ''} ${s.path || ''}`);
}

async function _at5AmpliTubeSlots() {
    const api = _at5DesktopAudio();
    if (!api || typeof api.getChainState !== 'function') return [];
    try {
        const chain = await api.getChainState();
        return Array.isArray(chain) ? chain.filter(_at5IsAmpliTubeSlot) : [];
    } catch { return []; }
}

async function _at5Ping() {
    try {
        const r = await fetch(`${AT5_BRIDGE_URL}/ping`, { signal: AbortSignal.timeout(500) });
        _at5BridgeOk = (await r.json()).ok;
    } catch { _at5BridgeOk = false; }
    return _at5BridgeOk;
}

async function _at5ResolveRoute() {
    const saved = localStorage.getItem('at5_output_id');
    const desktop = !!_at5DesktopAudio();
    if (saved === 'internal' || (!saved && desktop)) {
        const slots = await _at5AmpliTubeSlots();
        if (slots.length) return { kind: 'vst', slots };
        if (saved === 'internal') {
            return { kind: 'none', detail: 'AmpliTube 5 is not loaded in the Desktop signal chain' };
        }
    }
    if (saved === 'bridge') return { kind: 'bridge' };
    if (_at5MidiOutput) return { kind: 'webmidi', port: _at5MidiOutput };
    if (!desktop) return { kind: 'bridge' };
    return { kind: 'none', detail: 'No MIDI output — load AmpliTube 5 in the signal chain, or pick a MIDI port' };
}

const _at5Sleep = (ms) => new Promise(res => setTimeout(res, ms));

async function _at5SendVst(slots, ch, program, ccAdj) {
    const api = _at5DesktopAudio();
    // sendMidiToSlot(slotId, msgType 0=PC/1=CC, channel 1-16, data1, data2)
    let ok = true;
    for (const slot of slots) {
        ok = (await api.sendMidiToSlot(slot.id, 0, ch + 1, program & 0x7F)) !== false && ok;
    }
    if (ccAdj?.length) {
        await _at5Sleep(50);   // let AT5 finish loading the preset before nudging knobs
        for (const slot of slots) {
            for (const { cc, value } of ccAdj) {
                ok = (await api.sendMidiToSlot(slot.id, 1, ch + 1, cc & 0x7F, value & 0x7F)) !== false && ok;
            }
        }
    }
    return ok;
}

async function _at5SendWebMidi(port, ch, program, ccAdj) {
    port.send([0xC0 | (ch & 0x0F), program & 0x7F]);
    if (ccAdj?.length) {
        await _at5Sleep(50);
        for (const { cc, value } of ccAdj) port.send([0xB0 | (ch & 0x0F), cc & 0x7F, value & 0x7F]);
    }
    return true;
}

async function _at5PostJson(url, body, ms) {
    const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(ms),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
}

async function _at5SendBridge(ch, program, ccAdj) {
    // Python bridge script first (direct, lowest latency) …
    if (_at5BridgeOk || await _at5Ping()) {
        try {
            const d = await _at5PostJson(`${AT5_BRIDGE_URL}/pc`, { channel: ch, bank_msb: 0, bank_lsb: 0, program }, 1000);
            if (d.ok && ccAdj?.length) {
                await _at5Sleep(50);
                for (const { cc, value } of ccAdj) await _at5PostJson(`${AT5_BRIDGE_URL}/cc`, { channel: ch, cc, value }, 500);
            }
            return { ok: !!d.ok, detail: 'at5_midi_bridge.py' };
        } catch { _at5BridgeOk = false; }
    }
    // … else queue for the bridge window (a browser tab on the AT5 host)
    try {
        await _at5PostJson('/api/plugins/at5_tone/bridge-window/send', { type: 'pc', channel: ch, program }, 1000);
        if (ccAdj?.length) {
            await _at5Sleep(50);
            for (const { cc, value } of ccAdj) {
                await _at5PostJson('/api/plugins/at5_tone/bridge-window/send', { type: 'cc', channel: ch, cc, value }, 500);
            }
        }
        return { ok: true, detail: 'bridge window' };
    } catch (e) {
        return { ok: false, detail: `bridge window: ${e.message}` };
    }
}

async function _at5SendPC(program, ccAdj) {
    const ch = AT5_MIDI_CH;
    const route = await _at5ResolveRoute();
    let ok = false, detail = route.detail || '';
    try {
        if (route.kind === 'vst') {
            ok = await _at5SendVst(route.slots, ch, program, ccAdj);
            detail = route.slots.map(s => s.name).join(', ');
        } else if (route.kind === 'webmidi') {
            ok = await _at5SendWebMidi(route.port, ch, program, ccAdj);
            detail = route.port.name;
        } else if (route.kind === 'bridge') {
            ({ ok, detail } = await _at5SendBridge(ch, program, ccAdj));
        }
    } catch (e) {
        ok = false; detail = e.message;
    }
    _at5LastRoute = { kind: route.kind, ok, detail, program };
    if (!ok) console.warn(`[AT5] PC ${program} not delivered (${route.kind}): ${detail}`);
    return ok;
}

// ── MIDI init ──────────────────────────────────────────────────────────────
function _at5InitMidi() {
    if (!navigator.requestMIDIAccess) return;
    navigator.requestMIDIAccess({ sysex: false }).then(access => {
        _at5MidiAccess = access;
        // If user had 'bridge' saved but real Web MIDI ports exist, clear it
        // so they default to a real port rather than the Python bridge
        const saved = localStorage.getItem('at5_output_id');
        if (saved === 'bridge') {
            const ports = [];
            access.outputs.forEach(o => ports.push(o));
            if (ports.length) localStorage.removeItem('at5_output_id');
        }
        _at5PickOutput();
        access.onstatechange = _at5PickOutput;
    }).catch(() => {});
}

function _at5PickOutput() {
    const saved = localStorage.getItem('at5_output_id');
    if (!_at5MidiAccess) { _at5MidiOutput = null; return; }
    const outputs = [];
    _at5MidiAccess.outputs.forEach(o => outputs.push(o));
    // 'internal' = VST slot (handled in _at5SendPC), 'bridge' = Python bridge
    if (saved === 'internal' || saved === 'bridge') { _at5MidiOutput = null; return; }
    // Otherwise find the saved port, or default to first available
    _at5MidiOutput = outputs.find(o => o.id === saved) || outputs[0] || null;
}

// ── Tone log ───────────────────────────────────────────────────────────────
function _at5LogTone(toneKey, entry, firedAt) {
    const songInfo = highway?.getSongInfo?.() || {};
    _at5Log.unshift({
        ts:          Date.now(),
        firedAt:     firedAt?.toFixed(1) ?? '0.0',
        toneKey,
        pc:          entry?.pc ?? null,
        presetName:  entry?.preset_name ?? null,
        inTop128:    entry?.in_top128 ?? false,
        ccCount:     entry?.cc_adjustments?.length ?? 0,
        ccAdj:       entry?.cc_adjustments ?? [],
        song:        songInfo.title ?? _at5Filename ?? '',
        artist:      songInfo.artist ?? '',
        arrangement: songInfo.arrangement ?? '',
        filename:    _at5Filename ?? '',
    });
    if (_at5Log.length > LOG_MAX) _at5Log.length = LOG_MAX;
    _at5RefreshLogUI();
}

function _at5RefreshLogUI() {
    const el = document.getElementById('at5-log-list');
    if (!el) return;
    if (!_at5Log.length) {
        el.innerHTML = `<p class="text-xs text-gray-600 py-4 text-center">Play a song to see tone switches here.</p>`;
        return;
    }
    el.innerHTML = _at5Log.map((entry, i) => `
        <div class="flex items-center gap-3 py-2 border-b border-gray-800/50 hover:bg-dark-700/30 px-2 rounded group">
            <span class="text-xs text-gray-600 w-14 shrink-0 font-mono">${entry.firedAt}s</span>
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-xs font-semibold text-white truncate">${esc(entry.toneKey)}</span>
                    ${entry.pc !== null
                        ? `<span class="text-xs text-orange-400 font-mono shrink-0">PC ${entry.pc + 1}</span>`
                        : `<span class="text-xs text-red-500 shrink-0">not mapped</span>`}
                    ${entry.ccCount ? (() => {
                        const isWah = entry.ccAdj?.some(c => c.knob && (
                            c.knob.toLowerCase().includes('whammy') ||
                            c.knob.toLowerCase().includes('wah') ||
                            c.knob.toLowerCase().includes('position') ||
                            c.knob === 'default_heel'
                        ));
                        const tip = entry.ccAdj?.map(c=>`CC${c.cc}=${c.value} (${c.knob})`).join(', ') || '';
                        return `<span class="text-xs text-blue-400 shrink-0" title="${tip}">${isWah ? '〰 WAH' : entry.ccCount + ' CC'}</span>`;
                    })() : ''}
                    ${entry.inTop128 ? `<span class="text-xs text-green-600 shrink-0">●</span>` : ''}
                </div>
                <div class="text-xs text-gray-600 truncate">${esc(entry.presetName ?? '')} · ${esc(entry.song)}</div>
            </div>
            ${entry.pc !== null ? `
            <button onclick="_at5FireLogEntry(${i})"
                class="shrink-0 opacity-0 group-hover:opacity-100 text-xs border border-gray-700 hover:border-orange-500 text-gray-400 hover:text-orange-400 rounded-lg px-2 py-1 transition">
                ▶ Test
            </button>` : ''}
        </div>`).join('');
}

function _at5FireLogEntry(idx) {
    const entry = _at5Log[idx];
    if (!entry || entry.pc === null) return;
    console.log(`[AT5] Manual trigger: ${entry.toneKey} → PC ${entry.pc}`);
    _at5SendPC(entry.pc, entry.ccAdj || []);
}

// ── Live convert ──────────────────────────────────────────────────────────
async function _at5RequestLiveConvert(filename) {
    if (!_at5LiveEnabled || !filename) return;
    // Note: no cache check here — always reconvert so slots stay fresh per song
    _at5LiveLastFile = filename;
    Object.keys(_at5LiveSlots).forEach(k => delete _at5LiveSlots[k]);

    const decodedFilename = _at5Decode(filename);
    // Clear stale slots from previous song immediately so they can't fire incorrectly
    Object.keys(_at5LiveSlots).forEach(k => delete _at5LiveSlots[k]);
    console.log(`[AT5 Live] Converting ${decodedFilename}...`);
    try {
        const r = await fetch('/api/plugins/at5_tone/live_convert', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ filename: decodedFilename }),
            signal:  AbortSignal.timeout(15000),
        });
        const data = await r.json();
        if (!r.ok) {
            if (r.status === 503) { _at5LiveEnabled = false; }
            console.warn('[AT5 Live] Error:', data.message);
            return;
        }
        if (data.status === 'ok' && data.slots) {
            // Mutate in place so window._at5LiveSlots reference stays valid
            Object.keys(_at5LiveSlots).forEach(k => delete _at5LiveSlots[k]);
            Object.assign(_at5LiveSlots, data.slots);
            const n = Object.keys(_at5LiveSlots).length;
            const src = data.source === 'song-local' ? ' [song-local]' : data.cached ? ' [cached]' : ' [live-convert]';
        console.log(`[AT5 Live] ${n} tones in live slots (${data.elapsed_ms}ms)${src}`);
            if (data.warnings?.length) data.warnings.forEach(w => console.warn('[AT5 Live]', w));
            _at5RenderStatus(); // refresh UI to show live slot status
        }
    } catch(e) {
        console.warn('[AT5 Live] Fetch error:', e.message);
    }
}

// ── Save-back ─────────────────────────────────────────────────────────────
async function _at5SaveBack(toneKey) {
    const key = toneKey || '*';
    try {
        const r = await fetch('/api/plugins/at5_tone/preset/save-back', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ tone_key: key }),
        });
        const data = await r.json();
        if (data.status === 'ok') {
            console.log('[AT5] Saved back:', data.saved, '->', data.song_dir);
            _at5RenderStatus();
            return data;
        } else {
            console.warn('[AT5] Save-back failed:', data.message);
        }
    } catch(e) {
        console.warn('[AT5] Save-back error:', e.message);
    }
}

// ── Scheduler ──────────────────────────────────────────────────────────────
function _at5StopScheduler(sendReset) {
    const firedThisSong = _at5LastKey !== null;
    if (_at5Timer) { clearInterval(_at5Timer); _at5Timer = null; }
    _at5StartGen++;   // abandon any _at5StartScheduler still awaiting
    _at5Schedule  = [];
    _at5LastFired = -1;
    _at5LastKey   = null;
    _at5LastT     = null;
    // Only reset if we actually fired a tone during this song
    if (sendReset && firedThisSong) {
        _at5SendPC(0, []);
        console.log('[AT5] Song stopped - reset to PC 0');
    }
}

let _at5StartGen = 0;   // bumps on every start/stop so a stale start can't arm a timer

async function _at5StartScheduler(filename) {
    _at5StopScheduler(false);
    const gen = ++_at5StartGen;
    // Live convert runs in parallel with the PC table load; both finish before
    // the schedule is built so lookups (and the first tone) see this song's live slots.
    const liveDone = _at5RequestLiveConvert(filename);
    await _at5LoadPcTable();
    await liveDone;
    if (gen !== _at5StartGen) return;

    // song:ready means the highway already holds this song's tone changes ([{t, name}])
    const hwChanges = highway.getToneChanges?.() || [];
    const hwBase    = highway.getToneBase?.() || '';

    if (hwChanges.length > 0 || hwBase) {
        // CDLC path — enrich with fallback matching for unmapped tones
        _at5Schedule = [];
        if (hwBase) _at5Schedule.push({ key: hwBase, startTime: 0 });
        for (const tc of hwChanges) _at5Schedule.push({ key: tc.name, startTime: tc.t });
        _at5Schedule.sort((a, b) => a.startTime - b.startTime);
        console.log(`[AT5] ${_at5Schedule.length} tone changes (highway) for ${filename}`);

        // Find unmapped tones and fetch CDLC fallback matches
        const unmapped = _at5Schedule.filter(t => !_at5Lookup(t.key)).map(t => t.key);
        if (unmapped.length > 0) {
            try {
                const decoded = _at5Decode(filename);
                const r = await fetch('/api/plugins/at5_tone/match-cdlc-tones/' + encodeURIComponent(decoded));
                if (r.ok) {
                    const d = await r.json();
                    // Inject fallback matches into PC table
                    for (const [key, match] of Object.entries(d.matches || {})) {
                        if (!_at5PcTable[key]) {
                            _at5PcTable[key] = {
                                pc:             match.pc,
                                preset_name:    match.preset + ` (${match.match_type})`,
                                cc_adjustments: match.cc_adjustments || [],
                                in_top128:      false,
                                fallback:       true,
                                match_type:     match.match_type,
                            };
                        }
                    }
                    console.log(`[AT5] CDLC fallback: ${Object.keys(d.matches||{}).length} tones matched`);
                }
            } catch (e) {
                console.warn('[AT5] CDLC match fetch failed:', e);
            }
        }
    } else {
        // RS+ scrape path: parse XML schedule
        const tones = await _at5FetchSchedule(filename);
        if (!tones.length) {
            // Last resort: if live slots were converted, use them as a single base tone
            const liveKeys = Object.keys(_at5LiveSlots);
            if (liveKeys.length) {
                console.log(`[AT5] No highway/XML schedule — using ${liveKeys.length} live slot(s) as base tone`);
                _at5Schedule = [{ key: liveKeys[0], startTime: 0 }];
            } else {
                console.log(`[AT5] No tone schedule for ${filename}`);
                return;
            }
        } else {
            _at5Schedule = tones.sort((a, b) => a.startTime - b.startTime);
            console.log(`[AT5] ${_at5Schedule.length} tone changes (XML) for ${filename}`);
        }
    }

    if (gen !== _at5StartGen || !_at5Schedule.length) return;

    // Fire initial tone
    const first = _at5Schedule[0];
    const entry = _at5Lookup(first.key);
    if (entry) {
        console.log(`[AT5] Initial tone: ${first.key} → PC ${entry.pc}`);
        _at5SendPC(entry.pc, entry.cc_adjustments || []);
        _at5LastFired = 0;
        _at5LastKey   = first.key;
        _at5UpdateBadge(first.key, entry);
        _at5LogTone(first.key, entry, 0);
    }

    // Poll every 100ms
    _at5Timer = setInterval(() => {
        let t;
        try { t = highway.getTime(); } catch { return; }
        if (t == null) return;

        // Seek detection — if time jumped > 2s, rescan from scratch
        if (_at5LastT !== null && Math.abs(t - _at5LastT) > 2.0) {
            console.log(`[AT5] Seek detected (${_at5LastT.toFixed(1)}→${t.toFixed(1)}s) — rescanning`);
            _at5LastFired = -1;
            _at5LastKey   = null;
        }
        _at5LastT = t;

        let idx = -1;
        for (let i = 0; i < _at5Schedule.length; i++) {
            if (_at5Schedule[i].startTime - AT5_PREFIRE_MS <= t) idx = i;
            else break;
        }
        if (idx < 0 || idx === _at5LastFired) return;

        const tone  = _at5Schedule[idx];
        if (tone.key === _at5LastKey) { _at5LastFired = idx; return; }

        const entry2 = _at5Lookup(tone.key);
        _at5LastFired = idx;
        _at5LastKey   = tone.key;

        if (entry2) {
            console.log(`[AT5] t=${t.toFixed(1)}s: ${tone.key} → PC ${entry2.pc}`);
            _at5SendPC(entry2.pc, entry2.cc_adjustments || []);
            _at5UpdateBadge(tone.key, entry2);
        } else {
            console.log(`[AT5] t=${t.toFixed(1)}s: ${tone.key} — not mapped`);
            _at5UpdateBadge(tone.key, null);
        }
        _at5LogTone(tone.key, entry2, t);
    }, 100);
}

async function _at5FetchSchedule(filename) {
    if (!filename) return [];
    try {
        const decoded = _at5Decode(filename);
        const songInfo = highway?.getSongInfo?.() || {};
        const arrangement = songInfo.arrangement || '';
        const url = '/api/plugins/at5_tone/song-tone-schedule/' 
            + encodeURIComponent(decoded)
            + (arrangement ? `?arrangement=${encodeURIComponent(arrangement)}` : '');
        const r = await fetch(url);
        if (!r.ok) return [];
        const d = await r.json();
        return (d.tones || []).filter(t => t.key && t.key !== t.toneId);
    } catch { return []; }
}

// ── Badge ──────────────────────────────────────────────────────────────────
function _at5BadgeContainer() {
    // v3: the stable, always-reachable "Plugins" rail slot (docs/plugin-v3-ui.md)
    const ui = window.feedBack && window.feedBack.ui;
    if (window.feedBack?.uiVersion === 'v3' && ui && typeof ui.playerControlSlot === 'function') {
        try { const slot = ui.playerControlSlot(); if (slot instanceof Element) return slot; } catch {}
    }
    return document.getElementById('player-controls');
}

function _at5InjectBadge() {
    const container = _at5BadgeContainer();
    if (!container) return;
    const existing = document.getElementById('btn-at5');
    if (existing && container.contains(existing)) return;
    if (existing) existing.remove();
    const btn = document.createElement('button');
    btn.id = 'btn-at5';
    btn.className = 'px-3 py-1.5 bg-orange-900/40 hover:bg-orange-900/60 rounded-lg text-xs text-orange-300 transition';
    btn.textContent = 'AT5';
    btn.title = 'AmpliTube 5 Tone Switcher — click to open';
    btn.onclick = () => { if (typeof window.showScreen === 'function') window.showScreen(AT5_SCREEN_ID); };
    container.appendChild(btn);
}

function _at5UpdateBadge(toneKey, entry) {
    const btn = document.getElementById('btn-at5');
    if (!btn) return;
    if (entry) {
        btn.textContent = `AT5 #${entry.pc + 1}`;
        btn.title = `${toneKey} → ${entry.preset_name} (PC ${entry.pc}) — click to open`;
        btn.className = 'px-3 py-1.5 bg-orange-900/40 hover:bg-orange-900/60 rounded-lg text-xs text-orange-300 transition';
    } else {
        btn.textContent = 'AT5 ?';
        btn.title = `${toneKey} — not mapped`;
        btn.className = 'px-3 py-1.5 bg-dark-600 rounded-lg text-xs text-gray-500 transition';
    }
}

// ── Status panel ──────────────────────────────────────────────────────────
async function _at5RenderStatus() {
    const el = document.getElementById('at5-midi-status');
    if (!el) return;
    const isDesktop = !!_at5DesktopAudio();
    const vstSlots  = isDesktop ? await _at5AmpliTubeSlots() : [];
    const bridgeUp  = isDesktop ? false : await _at5Ping();   // no bridge on Desktop
    const pcCount = Object.keys(_at5PcTable).length;
    const savedId = localStorage.getItem('at5_output_id') || '';
    const outputs = [];
    if (_at5MidiAccess) _at5MidiAccess.outputs.forEach(o => outputs.push(o));
    const route = await _at5ResolveRoute();

    const card = 'background:rgba(55,65,81,0.3);border:1px solid rgba(31,41,55,0.5);border-radius:12px;padding:14px;margin-bottom:10px;';
    const row  = 'display:flex;align-items:center;gap:8px;margin-bottom:6px;';
    const dot  = (col) => `<span style="width:8px;height:8px;border-radius:50%;background:${col};flex-shrink:0;display:inline-block;"></span>`;
    const hint = (text) => `<div style="font-size:0.65rem;color:#4b5563;margin-top:2px;line-height:1.5;">${text}</div>`;
    let html = '';

    // ── Docker bridge window banner ───────────────────────────────────────
    const isDockerMode = !isDesktop && !outputs.length && !bridgeUp;
    if (isDockerMode && _at5ShouldShowBridgeBanner()) {
        html += `<div id="at5-bridge-banner"
            style="background:linear-gradient(135deg,rgba(249,115,22,0.15),rgba(249,115,22,0.05));
                   border:1px solid rgba(249,115,22,0.4);border-radius:12px;
                   padding:14px 16px;margin-bottom:10px;display:flex;align-items:center;gap:12px;">
            <span style="font-size:1.2rem;">⚡</span>
            <div style="flex:1;">
                <div style="font-size:0.8rem;font-weight:600;color:#f97316;margin-bottom:2px;">
                    Open the AT5 MIDI Bridge window
                </div>
                <div style="font-size:0.7rem;color:#9ca3af;line-height:1.5;">
                    Browser / Docker mode. Open this on the PC running AmpliTube 5 and leave it
                    in the background — it relays MIDI from feedBack to your MIDI port.
                </div>
            </div>
            <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0;">
                <button onclick="_at5OpenBridgeWindow()"
                    style="padding:6px 16px;background:#f97316;border:none;border-radius:8px;
                           color:#000;font-weight:700;font-size:0.8rem;cursor:pointer;white-space:nowrap;">
                    Open Bridge ↗
                </button>
                <button onclick="_at5DismissBridgeBanner()"
                    style="padding:4px 10px;background:transparent;border:1px solid #374151;
                           border-radius:6px;color:#6b7280;font-size:0.7rem;cursor:pointer;">
                    Dismiss
                </button>
            </div>
        </div>`;
    }

    // ── MIDI status + output selector ─────────────────────────────────────
    html += `<div style="${card}">`;

    const statusLine = (col, label, sub) => `<div style="${row}">
            ${dot(col)}
            <span style="font-size:0.75rem;font-weight:600;color:${col};">${label}</span>
            <span style="font-size:0.7rem;color:#4b5563;">${sub}</span>
        </div>`;
    if (route.kind === 'vst') {
        html += statusLine('#4ade80', 'AmpliTube 5 ready',
            `Desktop signal chain · ${esc(route.slots.map(s => s.name).join(', '))} · no extra software needed`);
    } else if (route.kind === 'webmidi') {
        html += statusLine('#4ade80', 'MIDI Ready', `Web MIDI · ${esc(route.port.name)}`);
    } else if (route.kind === 'bridge' && bridgeUp) {
        html += statusLine('#4ade80', 'Bridge Ready', 'at5_midi_bridge.py connected');
    } else if (route.kind === 'bridge') {
        html += statusLine('#eab308', 'Bridge window', 'MIDI is queued for the AT5 MIDI Bridge window — keep it open');
    } else {
        html += statusLine('#eab308', 'No MIDI output', esc(route.detail || ''));
    }
    if (isDesktop && !vstSlots.length) {
        html += `<div style="font-size:0.7rem;color:#6b7280;line-height:1.6;margin-bottom:8px;">
            <strong style="color:#9ca3af;">Recommended:</strong> add the <strong style="color:#d1d5db;">AmpliTube 5</strong>
            VST3 to the Signal Chain on feedBack's Audio screen. This plugin then switches its presets
            directly — no MIDI cable, virtual port or bridge.<br>
            <strong style="color:#9ca3af;">Standalone AmpliTube 5?</strong> Create a
            <a href="https://www.tobias-erichsen.de/software/loopmidi.html" target="_blank" style="color:#f97316;">loopMIDI</a>
            port, set it as AT5's MIDI input, and pick it below.
        </div>`;
    } else if (!isDesktop && !outputs.length && !bridgeUp) {
        html += `<div style="font-size:0.7rem;color:#6b7280;line-height:1.6;margin-bottom:8px;">
            No Web MIDI port in this browser. Open the
            <a href="/api/plugins/at5_tone/bridge-window" target="_blank" style="color:#f97316;font-weight:600;">AT5 MIDI Bridge window ↗</a>
            on the AmpliTube 5 PC, or run <code style="color:#9ca3af;">at5_midi_bridge.py</code> there.
            <strong style="color:#9ca3af;">feedBack Desktop</strong> needs neither.
        </div>`;
    }

    // Output picker — always shown so a choice can be changed or cleared
    html += `<div style="${row}">
        <span style="font-size:0.7rem;color:#6b7280;flex-shrink:0;">MIDI output</span>
        <select id="at5-device-select" onchange="_at5SelectOutput(this.value)"
            style="background:#1f2937;border:1px solid #374151;border-radius:6px;padding:3px 8px;font-size:0.75rem;color:#d1d5db;flex:1;">
            <option value="" ${!savedId ? 'selected' : ''}>Auto</option>`;
    if (isDesktop) html += `<option value="internal" ${savedId==='internal'?'selected':''}>AmpliTube 5 in Desktop signal chain${vstSlots.length ? '' : ' (not loaded)'}</option>`;
    if (!isDesktop) html += `<option value="bridge" ${savedId==='bridge'?'selected':''}>Bridge (window / at5_midi_bridge.py)</option>`;
    for (const o of outputs) html += `<option value="${esc(o.id)}" ${savedId===o.id?'selected':''}>${esc(o.name)}</option>`;
    html += `</select>
        <button onclick="_at5TestMidi(this)" style="font-size:0.7rem;padding:3px 10px;background:transparent;border:1px solid #374151;border-radius:6px;color:#9ca3af;cursor:pointer;" title="Send PC 0 to verify MIDI is reaching AT5">Test</button>
        <button onclick="_at5DiagMidi()" style="font-size:0.7rem;padding:3px 10px;background:transparent;border:1px solid #374151;border-radius:6px;color:#6b7280;cursor:pointer;" title="Show MIDI diagnostic info">Diag</button>
    </div>
    <pre id="at5-midi-diag" style="display:none;font-size:0.65rem;color:#9ca3af;background:#111827;border-radius:6px;padding:8px;margin-top:6px;white-space:pre-wrap;line-height:1.5;"></pre>`;

    if (route.kind === 'webmidi') {
        const isVirtual = /bridge|loop|virtual/i.test(route.port.name || '');
        html += hint(isVirtual
            ? 'Virtual MIDI port — no cable needed. Ensure AT5 MIDI Input matches this port name.'
            : 'Hardware port — ensure AT5 MIDI Input is set to match and MIDI cable is connected.');
    } else if (route.kind === 'vst') {
        html += hint('AT5 plugin: enable Program Change in its MIDI settings (Settings → MIDI) so it follows the preset list.');
    }
    if (_at5LastRoute && !_at5LastRoute.ok) {
        html += `<div style="font-size:0.65rem;color:#f87171;margin-top:4px;">Last send failed (${esc(_at5LastRoute.kind)}): ${esc(_at5LastRoute.detail || '')}</div>`;
    }

    // Manual PC send
    html += `<div style="${row};margin-top:8px;">
        <span style="font-size:0.7rem;color:#6b7280;flex-shrink:0;">Send PC</span>
        <input type="number" id="at5-test-prog" min="0" max="127" value="0"
            style="width:54px;background:#1f2937;border:1px solid #374151;border-radius:6px;padding:3px 6px;font-size:0.75rem;color:#d1d5db;text-align:center;">
        <span style="font-size:0.7rem;color:#4b5563;">(0–127)</span>
        <button onclick="at5TestSend()" style="font-size:0.7rem;padding:3px 10px;background:transparent;border:1px solid #374151;border-radius:6px;color:#9ca3af;cursor:pointer;">Send</button>
        <span style="font-size:0.7rem;color:#4b5563;">AT5 preset # = PC + 1</span>
    </div>`;
    html += `</div>`;

    // ── AmpliTube 5 folder + live slot setup ─────────────────────────────
    const setup = await _at5CheckSetup();
    if (setup) {
        const ready = setup.presets_linked && setup.live_slots_exist;
        html += `<div style="${card}">`;
        html += `<div style="font-size:0.75rem;font-weight:600;color:${ready ? '#9ca3af' : '#f97316'};margin-bottom:10px;">
            ${ready ? 'AmpliTube 5 setup' : '⚙ First-time Setup'}</div>`;

        // Step 1 — AmpliTube 5 documents folder
        if (setup.presets_linked) {
            const how = { setting: 'set manually', env: 'from AT5_DOCS_DIR', docker: 'Docker /at5docs mount', detected: 'auto-detected' }[setup.at5_dir_source] || '';
            html += `<div style="${row};margin-bottom:4px;">
                ${dot('#4ade80')}
                <span style="font-size:0.75rem;color:#6b7280;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(setup.at5_dir)}">
                    AmpliTube 5 folder: <code style="color:#9ca3af;">${esc(setup.at5_dir)}</code> ${how ? `· ${how}` : ''}</span>
                ${setup.mode !== 'docker' ? `<button onclick="document.getElementById('at5-folder-row').hidden=false;this.hidden=true"
                    style="font-size:0.65rem;padding:2px 8px;background:transparent;border:1px solid #374151;border-radius:6px;color:#6b7280;cursor:pointer;">Change…</button>` : ''}
            </div>`;
        } else {
            html += `<div style="${row};margin-bottom:6px;">
                ${dot('#f87171')}
                <span style="font-size:0.75rem;color:#d1d5db;flex:1;">AmpliTube 5 folder not found</span>
            </div>`;
        }
        if (setup.mode === 'docker') {
            if (!setup.presets_linked) {
                html += `<div style="font-size:0.65rem;color:#4b5563;margin-left:16px;margin-bottom:6px;">
                    Add to docker-compose.yml volumes:<br>
                    <code style="color:#9ca3af;">"C:/Users/&lt;username&gt;/Documents/IK Multimedia/AmpliTube 5:/at5docs"</code>
                </div>`;
            }
        } else {
            const suggested = setup.at5_docs_override || setup.at5_dir
                || (setup.detected_at5_presets ? setup.detected_at5_presets.replace(/[\\/]Presets[\\/]?$/i, '') : '');
            html += `<div id="at5-folder-row" ${setup.presets_linked ? 'hidden' : ''} style="margin-left:16px;margin-bottom:6px;">
                <div style="font-size:0.65rem;color:#6b7280;margin-bottom:4px;">
                    The folder AmpliTube 5 keeps its presets in — usually <code style="color:#9ca3af;">Documents\\IK Multimedia\\AmpliTube 5</code>
                    (OneDrive may move Documents). Leave empty to auto-detect.
                </div>
                <div style="display:flex;gap:6px;">
                    <input id="at5-presets-path-input" type="text" value="${esc(suggested)}"
                        placeholder="C:\\Users\\...\\Documents\\IK Multimedia\\AmpliTube 5"
                        style="flex:1;background:#1f2937;border:1px solid #374151;border-radius:6px;padding:4px 8px;font-size:0.7rem;color:#d1d5db;box-sizing:border-box;">
                    <button id="at5-setup-folder-btn" onclick="_at5SetAt5Folder()"
                        style="font-size:0.7rem;padding:4px 12px;background:#f97316;border:none;border-radius:6px;color:#000;cursor:pointer;font-weight:600;">Use folder</button>
                </div>
                <div id="at5-setup-folder-msg" style="font-size:0.65rem;color:#6b7280;margin-top:4px;"></div>
            </div>`;
        }

        // Step 2 — live slots registered in AT5's Program Change map
        if (setup.presets_linked && !setup.live_slots_exist) {
            html += `<div style="${row};margin-bottom:8px;">
                ${dot('#f87171')}
                <span style="font-size:0.75rem;color:#d1d5db;flex:1;">
                    Live slots not registered in AmpliTube 5's Program Change map
                    (${setup.live_slot_count}/${LIVE_SLOT_COUNT} slot files)
                </span>
                <button id="at5-setup-pcmap-btn" onclick="_at5DoPcMap()"
                    style="font-size:0.7rem;padding:4px 12px;background:#f97316;border:none;border-radius:6px;color:#000;cursor:pointer;font-weight:600;">
                    Run Setup
                </button>
            </div>
            <div id="at5-setup-pcmap-msg" style="font-size:0.65rem;color:#6b7280;margin-left:16px;margin-bottom:6px;"></div>
            <div style="font-size:0.65rem;color:#4b5563;margin-left:16px;">
                Close AmpliTube 5 (or remove it from the chain) first, then restart it to pick up the new PC map.
            </div>`;
        } else if (setup.presets_linked) {
            html += `<div style="${row};margin-bottom:4px;">
                ${dot('#4ade80')}
                <span style="font-size:0.75rem;color:#6b7280;">${setup.live_slot_count} live slots ready (PC ${LIVE_SLOT_START + 1}–${LIVE_SLOT_START + LIVE_SLOT_COUNT}) ✓</span>
            </div>`;
        }

        html += `</div>`;
    }

    // ── PC table status ───────────────────────────────────────────────────
    html += `<div style="font-size:0.7rem;color:${pcCount>0?'#6b7280':'#ca8a04'};margin-bottom:8px;">
        PC table: ${pcCount > 0 ? `${pcCount} tones mapped` : 'loading…'}
    </div>`;

    // ── Live slots ────────────────────────────────────────────────────────
    if (_at5LiveEnabled) {
        const liveSlots = Object.entries(_at5LiveSlots);
        const liveCount = liveSlots.length;
        html += `<div style="${card}">`;
        html += `<div style="font-size:0.7rem;font-weight:600;color:#9ca3af;margin-bottom:8px;">
            Live Slots
            <span style="font-weight:400;color:#4b5563;margin-left:6px;">
                ${liveCount > 0 ? `${liveCount} tones loaded` : (_at5LiveLastFile ? 'converting…' : 'idle — load a song')}
            </span>
        </div>`;

        if (liveCount > 0) {
            liveSlots.forEach(([toneKey, pc]) => {
                html += `<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid rgba(31,41,55,0.4);">
                    <span style="font-size:0.7rem;color:#f97316;font-family:monospace;flex-shrink:0;width:36px;">PC${pc+1}</span>
                    <span style="font-size:0.75rem;color:#d1d5db;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(toneKey)}">${esc(toneKey)}</span>
                    <button onclick="_at5SendPC(${pc}, []); this.textContent='✓'; setTimeout(()=>this.textContent='▶',1000);"
                        style="font-size:0.7rem;padding:2px 8px;background:transparent;border:1px solid #374151;border-radius:4px;color:#6b7280;cursor:pointer;flex-shrink:0;"
                        title="Audition this tone in AT5">▶</button>
                    <button onclick="_at5SaveBack('${esc(toneKey)}')"
                        style="font-size:0.7rem;padding:2px 8px;background:transparent;border:1px solid #374151;border-radius:4px;color:#6b7280;cursor:pointer;flex-shrink:0;"
                        title="Save this preset back to the song folder">💾</button>
                </div>`;
            });

            // Save-all button + explanation
            html += `<div style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(31,41,55,0.4);">
                <button onclick="_at5SaveBack('*')"
                    style="font-size:0.75rem;padding:5px 14px;background:transparent;border:1px solid #374151;border-radius:6px;color:#9ca3af;cursor:pointer;">
                    💾 Save all presets back to song
                </button>
                <div style="font-size:0.7rem;color:#4b5563;margin-top:6px;line-height:1.5;">
                    Copies the current AT5 preset files beside this song file so your edits
                    load automatically next time. Dial in a tone in AT5, then save it back here.
                    Individual 💾 buttons save one tone; the button above saves all.
                </div>
            </div>`;
        }
        html += `</div>`;
    }

    el.innerHTML = html;
}

function _at5ShouldShowBridgeBanner() {
    // Show once for Docker users with no MIDI output, until they click it
    return !localStorage.getItem('at5_bridge_banner_dismissed');
}

function _at5DismissBridgeBanner() {
    localStorage.setItem('at5_bridge_banner_dismissed', '1');
    const el = document.getElementById('at5-bridge-banner');
    if (el) el.style.display = 'none';
}

function _at5OpenBridgeWindow() {
    window.open('/api/plugins/at5_tone/bridge-window', 'at5_bridge',
        'width=600,height=500,menubar=no,toolbar=no,location=no,status=no');
    _at5DismissBridgeBanner();
}

async function _at5CheckSetup() {
    try {
        const r = await fetch('/api/plugins/at5_tone/setup/status');
        if (!r.ok) return null;
        return await r.json();
    } catch { return null; }
}

function _at5SelectOutput(value) {
    if (value) localStorage.setItem('at5_output_id', value);
    else localStorage.removeItem('at5_output_id');   // Auto
    _at5PickOutput();
    _at5RenderStatus();
}

async function _at5SetAt5Folder() {
    const btn = document.getElementById('at5-setup-folder-btn');
    const msg = document.getElementById('at5-setup-folder-msg');
    const input = document.getElementById('at5-presets-path-input');
    if (btn) { btn.disabled = true; btn.textContent = 'Checking…'; }
    try {
        const r = await fetch('/api/plugins/at5_tone/setup/at5-path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: input ? input.value : '' }),
        });
        const d = await r.json();
        if (msg) {
            msg.style.color = d.ok ? '#4ade80' : '#f87171';
            msg.textContent = d.ok ? `✓ Using ${d.at5_dir}` : `✗ ${d.error || d.message || 'Failed'}`;
        }
        if (d.ok) {
            _at5PcLoaded = false;   // the PC table may come from the new folder
            setTimeout(() => _at5RenderStatus(), 800);
        }
    } catch (e) {
        if (msg) { msg.style.color = '#f87171'; msg.textContent = '✗ ' + e.message; }
    }
    if (btn) { btn.disabled = false; btn.textContent = 'Use folder'; }
}

async function _at5DoPcMap() {
    const btn = document.getElementById('at5-setup-pcmap-btn');
    const msg = document.getElementById('at5-setup-pcmap-msg');
    if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }
    try {
        const r = await fetch('/api/plugins/at5_tone/setup/run-pc-map', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
        const d = await r.json();
        if (msg) {
            msg.style.color = d.ok ? '#4ade80' : '#f87171';
            msg.textContent = d.ok ? '✓ Live slots populated' : '✗ ' + d.error;
        }
        if (d.ok) setTimeout(() => _at5RenderStatus(), 1500);
    } catch(e) {
        if (msg) { msg.style.color = '#f87171'; msg.textContent = '✗ ' + e.message; }
    }
    if (btn) { btn.disabled = false; btn.textContent = 'Run Setup'; }
}

async function _at5DiagMidi() {
    const el = document.getElementById('at5-midi-diag');
    if (!el) return;
    const savedId = localStorage.getItem('at5_output_id');
    const route = await _at5ResolveRoute();
    const lines = [`Saved output_id: ${savedId || '(auto)'}`];
    lines.push(`Route now: ${route.kind}${route.detail ? ' — ' + route.detail : ''}`);
    if (_at5LastRoute) lines.push(`Last send: PC ${_at5LastRoute.program} via ${_at5LastRoute.kind} — ${_at5LastRoute.ok ? 'ok' : 'FAILED'} ${_at5LastRoute.detail || ''}`);
    lines.push(`Web MIDI output: ${_at5MidiOutput ? _at5MidiOutput.name + ' [' + _at5MidiOutput.id + ']' : 'none'}`);
    lines.push(`Bridge script: ${_at5BridgeOk ? 'up' : 'not seen'}`);
    const desktop = _at5DesktopAudio();
    lines.push(`feedBack Desktop audio: ${!!desktop}`);
    if (desktop) {
        try {
            const chain = await desktop.getChainState();
            lines.push(`Signal chain (${chain.length}):`);
            chain.forEach(s => lines.push(`  #${s.id} type=${s.type} ${s.name}${_at5IsAmpliTubeSlot(s) ? '  ← AmpliTube' : ''}`));
        } catch (e) { lines.push(`Signal chain: ${e.message}`); }
    }
    if (_at5MidiAccess) {
        const ports = [];
        _at5MidiAccess.outputs.forEach(o => ports.push(`  ${o.id} — ${o.name} [${o.state}]`));
        lines.push(`Web MIDI outputs (${ports.length}):`);
        ports.forEach(p => lines.push(p));
    } else {
        lines.push('Web MIDI: not initialised');
    }
    el.textContent = lines.join('\n');
    el.style.display = '';
}

async function _at5TestMidi(btn) {
    // Send PC 0 as a quick connectivity check
    const ok = await _at5SendPC(0, []);
    if (btn) { btn.textContent = ok ? '✓ PC0 sent' : '✗ failed'; setTimeout(() => btn.textContent = 'Test', 1500); }
}

// ── Tone browser ───────────────────────────────────────────────────────────
async function at5SearchSongs() {
    const q = document.getElementById('at5-search')?.value.trim();
    if (!q) return;
    const fmt = document.getElementById('at5-search-format')?.value || '';
    const url = fmt
        ? `/api/library?q=${encodeURIComponent(q)}&page=0&size=20&sort=artist&format=${fmt}`
        : `/api/library?q=${encodeURIComponent(q)}&page=0&size=20&sort=artist`;
    const res = await fetch(url).then(r => r.json()).catch(() => ({ songs: [] }));
    const container = document.getElementById('at5-search-results');
    if (!container) return;
    if (!res.songs?.length) {
        container.innerHTML = `<p style="font-size:0.875rem;color:#6b7280;">No songs found.</p>`; return;
    }
    // Store song data in a map keyed by index to avoid inline JSON escaping issues
    window._at5SearchResults = res.songs;
    container.innerHTML = res.songs.map((s, i) => `
        <button data-song-index="${i}"
            style="display:block;width:100%;text-align:left;background:#374151;border:1px solid #1f2937;border-radius:12px;padding:10px 16px;margin-bottom:6px;cursor:pointer;">
            <span style="font-size:0.875rem;color:#fff;">${esc(s.title||s.filename)}</span>
            <span style="font-size:0.75rem;color:#6b7280;margin-left:8px;">${esc(s.artist||'')}</span>
            <span style="font-size:0.7rem;color:#9ca3af;float:right;background:#1f2937;padding:2px 6px;border-radius:4px;">${esc(s.format||s.filename.split('/')[0]||'')}</span>
        </button>`).join('');
    container.querySelectorAll('button[data-song-index]').forEach(btn => {
        btn.addEventListener('click', () => {
            const s = window._at5SearchResults[parseInt(btn.dataset.songIndex)];
            if (s) at5BrowseSong(s.filename, s.title||s.filename, s.artist||'');
        });
    });
}

async function at5BrowseSong(filename, title, artist) {
    document.getElementById('at5-search-results').innerHTML = '';
    const titleEl = document.getElementById('at5-editor-title');
    if (titleEl) titleEl.textContent = `${artist ? artist + ' — ' : ''}${title}`;
    const editorEl = document.getElementById('at5-editor');
    if (editorEl) editorEl.style.display = '';

    await _at5LoadPcTable();
    const container = document.getElementById('at5-mappings');
    if (!container) return;
    container.innerHTML = `<p style="font-size:0.875rem;color:#6b7280;padding:12px 0;">Loading...</p>`;

    // Try CDLC match first, fall back to RS+ scrape schedule
    const decoded = _at5Decode(filename);
    const isCdlc = decoded.toLowerCase().endsWith('.feedpak') || decoded.toLowerCase().endsWith('.sloppak');
    let tones = [];

    if (isCdlc) {
        // Use bundled midi_amp plugin's song-tones endpoint (always available)
        // Returns {tones: [{key, name, arrangement}]} — simpler and maintained by core
        try {
            const r = await fetch(`/api/plugins/midi_amp/song-tones/${encodeURIComponent(decoded)}`, {
                signal: AbortSignal.timeout(10000),
            });
            if (r.ok) {
                const d = await r.json();
                if (d.tones && d.tones.length) {
                    // Enrich each tone with AT5 PC table lookup
                    tones = d.tones.map(t => {
                        const entry = _at5Lookup(t.key);
                        const livePC = _at5LiveSlots[t.key];
                        return {
                            key: t.key,
                            startTime: null,
                            pc: livePC !== undefined ? livePC : entry?.pc,
                            preset_name: entry?.preset_name || '',
                            match_type: livePC !== undefined ? 'live'
                                      : entry ? (entry.in_top128 ? 'exact' : 'adjusted')
                                      : 'unmapped',
                            in_top128: entry?.in_top128 || false,
                            cc_adjustments: entry?.cc_adjustments || [],
                            arrangements: t.arrangement ? [t.arrangement] : [],
                        };
                    });
                }
            }
        } catch(e) {
            // midi_amp endpoint failed — fall through to scrape schedule fallback
        }
    }

    // Fallback: RS+ scrape schedule (for loose folder / sloppak songs)
    if (!tones.length) {
        tones = await _at5FetchSchedule(filename);
        tones = tones.map(t => {
            const entry = _at5Lookup(t.key);
            return { ...t, pc: entry?.pc, preset_name: entry?.preset_name || '',
                     match_type: entry ? (entry.in_top128 ? 'exact' : 'adjusted') : 'unmapped',
                     in_top128: entry?.in_top128, cc_adjustments: entry?.cc_adjustments || [] };
        });
    }

    if (!tones.length) {
        container.innerHTML = `<p style="font-size:0.875rem;color:#6b7280;padding:12px 0;">No tones found — song tones may not be readable, or this is a single-tone song with no explicit changes.</p>`;
        return;
    }

    // Deduplicate by key for display, keep timestamps
    const seen = new Set();
    const unique = [];
    for (const t of tones) {
        if (!seen.has(t.key)) { seen.add(t.key); unique.push(t); }
    }

    const hdStyle = 'display:grid;grid-template-columns:60px 1fr 80px 110px 70px 70px 50px;gap:0 8px;font-size:0.7rem;color:#6b7280;font-weight:600;padding:0 8px 6px 8px;';
    const rowStyle = 'display:grid;grid-template-columns:60px 1fr 80px 110px 70px 70px 50px;gap:0 8px;align-items:center;padding:8px;border-bottom:1px solid rgba(31,41,55,0.4);';
    container.innerHTML =
        `<div style="${hdStyle}"><span>Time</span><span>Tone Key</span><span>PC#</span><span>Preset</span><span>Arr.</span><span>Type</span><span></span></div>` +
        tones.map((tone, ti) => {
            // tones now have pc/match_type/preset_name directly (from cdlc endpoint)
            // or we fall back to _at5Lookup for RS+ scrape tones
            const livePC = _at5LiveSlots[tone.key];
            const pcNum = livePC !== undefined ? livePC + 1
                        : tone.pc !== undefined ? tone.pc + 1
                        : null;
            const isLive = livePC !== undefined;
            const matchType = tone.match_type || 'unknown';
            const type = isLive ? 'live'
                : matchType === 'exact' ? 'direct'
                : matchType === 'adjusted' || matchType === 'same_amp' ? 'CC adj'
                : matchType === 'unmapped' ? 'unmapped'
                : matchType;
            const typeColor = !pcNum ? '#ef4444'
                : isLive ? '#22c55e'
                : matchType === 'exact' ? '#22c55e'
                : '#60a5fa';
            const presetName = tone.preset_name || '';
            const ccAdj = tone.cc_adjustments || [];
            const playBtn = pcNum
                ? `<button data-pc="${pcNum-1}" data-cc='${JSON.stringify(ccAdj)}'
                    style="font-size:0.7rem;border:1px solid #374151;border-radius:4px;padding:2px 6px;background:transparent;color:#6b7280;cursor:pointer;">▶</button>`
                : '<span></span>';
            return `<div style="${rowStyle}">
                <span style="font-size:0.7rem;color:#6b7280;font-family:monospace;">${tone.startTime?.toFixed(1) ?? '0.0'}s</span>
                <span style="font-size:0.75rem;font-weight:600;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(tone.key)}">${esc(tone.key)}</span>
                <span style="font-size:0.75rem;color:#f97316;font-family:monospace;">${pcNum ? '#'+pcNum : '—'}</span>
                <span style="font-size:0.7rem;color:#6b7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(presetName)}</span>
                <span style="font-size:0.7rem;color:#6b7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc((tone.arrangements||[]).join(', '))}">${esc((tone.arrangements||[]).join(' / '))}</span>
                <span style="font-size:0.7rem;color:${typeColor};">${type}</span>
                ${playBtn}
            </div>`;
        }).join('');
    // Wire play buttons after render
    container.querySelectorAll('button[data-pc]').forEach(btn => {
        btn.addEventListener('click', () => {
            const pc = parseInt(btn.dataset.pc);
            const cc = JSON.parse(btn.dataset.cc || '[]');
            _at5SendPC(pc, cc);
            btn.textContent = '✓';
            setTimeout(() => btn.textContent = '▶', 1000);
        });
    });
}

function at5TestSend() {
    const prog = parseInt(document.getElementById('at5-test-prog')?.value) || 0;
    _at5SendPC(prog, []);
}

// ── Tab switcher ───────────────────────────────────────────────────────────
// ── Settings ──────────────────────────────────────────────────────────────
function at5SetPrefire(ms) {
    const val = Math.max(0, Math.min(1000, parseInt(ms) || 0));
    AT5_PREFIRE_MS = val / 1000;  // convert ms to seconds for internal use
    localStorage.setItem('at5_prefire_ms', AT5_PREFIRE_MS);
    const label = document.getElementById('at5-prefire-label');
    if (label) label.textContent = `${val} ms`;
    const slider = document.getElementById('at5-prefire-slider');
    if (slider) slider.value = val;
}

async function _at5LoadSettings() {
    try {
        const r = await fetch('/api/plugins/at5_tone/settings');
        if (!r.ok) return;
        const data = await r.json();
        const tier = data.tier || (data.free_mode ? 'cs' : 'max');
        const radio = document.getElementById(`at5-tier-${tier}`);
        if (radio) radio.checked = true;
        const cb = document.getElementById('at5-free-mode-checkbox');
        if (cb) cb.checked = (tier === 'cs');
        const ngCb = document.getElementById('at5-noise-gate-checkbox');
        if (ngCb) ngCb.checked = !!data.noise_gate;
        if (typeof data.output_db === 'number') {
            const os = document.getElementById('at5-output-slider');
            const ol = document.getElementById('at5-output-label');
            if (os) os.value = data.output_db;
            if (ol) ol.textContent = `${data.output_db > 0 ? '+' : ''}${data.output_db} dB`;
        }
    } catch(e) {}
    // Restore prefire slider from localStorage
    const prefireMs = Math.round(AT5_PREFIRE_MS * 1000);
    const slider = document.getElementById('at5-prefire-slider');
    const label  = document.getElementById('at5-prefire-label');
    if (slider) slider.value = prefireMs;
    if (label)  label.textContent = `${prefireMs} ms`;
}

// Master output of every tone loaded into AT5 (dB). Applied to the live slot
// preset on the next song load (apply_level_policy in cdlc_to_at5.py).
async function at5SetOutputLevel(db) {
    try {
        const r = await fetch('/api/plugins/at5_tone/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ output_db: db }),
        });
        const data = await r.json();
        console.log(`[AT5] Output level: ${data.output_db} dB`);
        Object.keys(_at5LiveSlots).forEach(k => delete _at5LiveSlots[k]);
        _at5LiveLastFile = null;
    } catch(e) {
        console.warn('[AT5] Output level error:', e.message);
    }
}

async function at5SetNoisegate(enabled) {
    try {
        const r = await fetch('/api/plugins/at5_tone/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ noise_gate: enabled }),
        });
        const data = await r.json();
        console.log(`[AT5] Noise gate: ${data.noise_gate}`);
        // Clear slots so next song re-converts with gate applied
        Object.keys(_at5LiveSlots).forEach(k => delete _at5LiveSlots[k]);
        _at5LiveLastFile = null;
    } catch(e) {
        console.warn('[AT5] Noise gate error:', e.message);
    }
}

async function at5SetTier(tier) {
    try {
        const r = await fetch('/api/plugins/at5_tone/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tier }),
        });
        const data = await r.json();
        console.log(`[AT5] Tier: ${data.tier}`);
        Object.keys(_at5LiveSlots).forEach(k => delete _at5LiveSlots[k]);
        _at5LiveLastFile = null;
        _at5RenderStatus();
    } catch(e) {
        console.warn('[AT5] Settings error:', e.message);
    }
}

async function at5SetFreeMode(enabled) {
    return at5SetTier(enabled ? 'cs' : 'max');
}

function at5ShowTab(tab) {
    ['status', 'browser', 'log'].forEach(t => {
        const tabEl = document.getElementById(`at5-tab-${t}`);
        const btnEl = document.getElementById(`at5-tabbtn-${t}`);
        if (tabEl) tabEl.style.display = (t === tab) ? '' : 'none';
        if (btnEl) {
            btnEl.style.borderBottomColor = (t === tab) ? '#f97316' : 'transparent';
            btnEl.style.color = (t === tab) ? '#fff' : '#6b7280';
        }
    });
    if (tab === 'log') _at5RefreshLogUI();
    if (tab === 'status') _at5RenderStatus();
}

// ── Init ───────────────────────────────────────────────────────────────────
_at5InitMidi();
if (!_at5DesktopAudio()) _at5Ping();   // the bridge script is a browser/Docker-only helper
_at5LoadPcTable();

function _at5ClearLog() {
    _at5Log.length = 0;
    _at5RefreshLogUI();
}

// Expose globals
window.at5SearchSongs    = at5SearchSongs;
window.at5BrowseSong     = at5BrowseSong;
window.at5TestSend       = at5TestSend;
window.at5ShowTab        = at5ShowTab;
window._at5PickOutput    = _at5PickOutput;
window._at5RenderStatus  = _at5RenderStatus;
window._at5SendPC        = _at5SendPC;
window._at5FireLogEntry  = _at5FireLogEntry;
window._at5Log           = _at5Log;
window._at5RefreshLogUI  = _at5RefreshLogUI;
window._at5ClearLog      = _at5ClearLog;
window._at5SetPrefire    = (v) => { AT5_PREFIRE_MS = parseFloat(v) || 0; };
window._at5LiveSlots     = _at5LiveSlots;
window._at5RequestLiveConvert = _at5RequestLiveConvert;
window._at5SaveBack          = _at5SaveBack;
window._at5TestMidi          = _at5TestMidi;
window._at5DiagMidi          = _at5DiagMidi;
window._at5SetAt5Folder      = _at5SetAt5Folder;
window._at5SelectOutput      = _at5SelectOutput;
window._at5OpenBridgeWindow  = _at5OpenBridgeWindow;
window._at5DismissBridgeBanner = _at5DismissBridgeBanner;
window._at5DoPcMap           = _at5DoPcMap;
window._at5LoadSettings      = _at5LoadSettings;
window.at5SetPrefire         = at5SetPrefire;
window.at5SetFreeMode        = at5SetFreeMode;
window.at5SetTier            = at5SetTier;
window.at5SetNoisegate       = at5SetNoisegate;
window.at5SetOutputLevel     = at5SetOutputLevel;

// Refresh status + log whenever our screen is shown (per-visit re-init)
function _at5OnScreenShown() {
    _at5RenderStatus();
    _at5RefreshLogUI();
}
if (window.feedBack?.on) {
    // core's showScreen emits screen:changed with { id, from }
    window.feedBack.on('screen:changed', (e) => {
        if (e?.detail?.id === AT5_SCREEN_ID) _at5OnScreenShown();
    });
}

})();
