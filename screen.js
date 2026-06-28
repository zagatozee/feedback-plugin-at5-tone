(function () {
'use strict';

// AmpliTube 5 Tone Switcher — v3
// - setInterval + highway.getTime() (no setRenderer — doesn't interfere with visuals)
// - Live tone log with per-song history
// - Tone browser with manual trigger
// - All UI functions exposed as globals

(function () {
'use strict';

// ── Config ─────────────────────────────────────────────────────────────────
const AT5_BRIDGE_URL = 'http://localhost:37432';
const AT5_MIDI_CH    = 0;
const LOG_MAX        = 200;
let AT5_PREFIRE_MS   = parseFloat(localStorage.getItem('at5_prefire_ms') ?? '0.2');   // max log entries to keep

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

// ── Filename capture (same as tabview) ────────────────────────────────────
(function () {
    const orig = typeof window.playSong === 'function' ? window.playSong : null;
    if (orig) {
        window.playSong = async function (filename, arrangement) {
            _at5Filename = filename;
            const result = await orig.call(this, filename, arrangement);
            _at5InjectBadge();
            // Don't start scheduler here — wait for highway ready event
            return result;
        };
    }
    // Hook highway ready event for reliable song + arrangement detection
    if (window.highway && typeof highway.addDrawHook === 'function') {
        let _lastScheduledFile = null;
        highway.addDrawHook(() => {
            const info = highway.getSongInfo?.();
            if (!info || !_at5Filename) return;
            const key = `${_at5Filename}|${info.arrangement}`;
            if (key !== _lastScheduledFile) {
                _lastScheduledFile = key;
                _at5StartScheduler(_at5Filename);
            }
        });
    } else {
        // Fallback: start from playSong with delay
        const origFallback = window.playSong;
        if (origFallback) {
            window.playSong = async function (filename, arrangement) {
                _at5Filename = filename;
                const result = await origFallback.call(this, filename, arrangement);
                _at5InjectBadge();
                _at5StartScheduler(filename);
                return result;
            };
        }
    }
    if (window.feedBack?.on) {
        window.feedBack.on('arrangement:changed', (e) => {
            if (e?.detail?.filename) _at5Filename = e.detail.filename;
        });
    }
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

// ── Bridge ─────────────────────────────────────────────────────────────────
async function _at5Ping() {
    try {
        const r = await fetch(`${AT5_BRIDGE_URL}/ping`, { signal: AbortSignal.timeout(500) });
        _at5BridgeOk = (await r.json()).ok;
    } catch { _at5BridgeOk = false; }
    return _at5BridgeOk;
}

async function _at5SendPC(program, ccAdj) {
    const ch = AT5_MIDI_CH;

    // 1. Internal VST (Desktop) — only if AT5 is loaded as a VST in the chain
    if (window.feedBackDesktop?.audio) {
        try {
            const api = window.feedBackDesktop.audio;
            const chain = await api.getChainState();
            const slots = chain.filter(s => s.type === 0);
            if (slots.length) {
                for (const slot of slots) {
                    api.sendMidiToSlot(slot.id, 1, ch+1, program & 0x7F, 0);
                    api.sendMidiToSlot(slot.id, 0, 0xC0|ch, program & 0x7F, 0);
                }
                return;
            }
            // No VST slots — AT5 is standalone, fall through to Web MIDI
        } catch {}
    }

    // 2. Web MIDI — preferred if user has selected a port
    if (_at5MidiOutput) {
        _at5MidiOutput.send([0xC0|(ch&0x0F), program & 0x7F]);
        if (ccAdj?.length) {
            await new Promise(res => setTimeout(res, 50));
            for (const { cc, value } of ccAdj) {
                _at5MidiOutput.send([0xB0|(ch&0x0F), cc & 0x7F, value & 0x7F]);
            }
        }
        return;
    }

    // 3. Bridge window (Docker) — push to queue for the host browser tab
    const savedId = localStorage.getItem('at5_output_id');
    if (savedId === 'bridge' || (!_at5MidiOutput && (_at5BridgeOk || await _at5Ping()))) {
        // Try bridge window queue first (no Python bridge needed)
        try {
            await fetch('/api/plugins/at5_tone/bridge-window/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: 'pc', channel: ch, program }),
                signal: AbortSignal.timeout(1000)
            });
            if (ccAdj?.length) {
                await new Promise(res => setTimeout(res, 50));
                for (const { cc, value } of ccAdj) {
                    await fetch('/api/plugins/at5_tone/bridge-window/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ type: 'cc', channel: ch, cc, value }),
                        signal: AbortSignal.timeout(500)
                    });
                }
            }
            return;
        } catch {}
        // Fallback: Python bridge script
        try {
            const r = await fetch(`${AT5_BRIDGE_URL}/pc`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel: ch, bank_msb: 0, bank_lsb: 0, program }),
                signal: AbortSignal.timeout(1000)
            });
            if ((await r.json()).ok && ccAdj?.length) {
                await new Promise(res => setTimeout(res, 50));
                for (const { cc, value } of ccAdj) {
                    await fetch(`${AT5_BRIDGE_URL}/cc`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ channel: ch, cc, value }),
                        signal: AbortSignal.timeout(500)
                    });
                }
            }
            return;
        } catch { _at5BridgeOk = false; }
    }
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

    const decodedFilename = decodeURIComponent(filename);
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
    if (_at5Timer) { clearInterval(_at5Timer); _at5Timer = null; }
    _at5Schedule  = [];
    _at5LastFired = -1;
    _at5LastKey   = null;
    _at5LastT     = null;
    // Only reset if we actually fired a tone during this song
    if (sendReset && _at5LastKey && typeof AT5_BRIDGE_URL !== 'undefined') {
        fetch(AT5_BRIDGE_URL + '/pc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ channel: 0, bank_msb: 0, bank_lsb: 0, program: 0 }),
        }).catch(() => {});
        console.log('[AT5] Song ended - reset to PC 0');
    }
}

async function _at5StartScheduler(filename) {
    _at5StopScheduler(false);
    _at5RequestLiveConvert(filename);   // fire & forget — runs in parallel with scheduler startup
    await _at5LoadPcTable();

    // Wait for highway to load song data
    await new Promise(res => setTimeout(res, 800));
    if (_at5Filename !== filename) return;

    // Try highway.getToneChanges() first (CDLC: [{t, name}])
    // Retry a few times — highway may not be fully ready at 800ms
    let hwChanges = highway.getToneChanges?.() || [];
    let hwBase    = highway.getToneBase?.() || '';
    if (!hwChanges.length && !hwBase) {
        for (let attempt = 0; attempt < 5; attempt++) {
            await new Promise(r => setTimeout(r, 400));
            hwChanges = highway.getToneChanges?.() || [];
            hwBase    = highway.getToneBase?.() || '';
            if (hwChanges.length || hwBase) break;
        }
    }

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
                const decoded = decodeURIComponent(filename);
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
        const decoded = decodeURIComponent(filename);
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
function _at5InjectBadge() {
    if (document.getElementById('btn-at5')) return;
    const bar = document.getElementById('player-controls')
        || document.querySelector('[data-player-controls]')
        || document.querySelector('.player-controls');
    if (!bar) return;
    const btn = document.createElement('button');
    btn.id = 'btn-at5';
    btn.className = 'px-3 py-1.5 bg-orange-900/40 hover:bg-orange-900/60 rounded-lg text-xs text-orange-300 transition';
    btn.textContent = 'AT5';
    btn.title = 'AmpliTube 5 Tone Switcher — click to open';
    btn.onclick = () => { if (typeof showScreen === 'function') showScreen('at5-tone'); };
    const closeBtn = Array.from(bar.querySelectorAll('button')).find(b =>
        b.textContent.includes('Close') || b.textContent.includes('×') || b.title?.includes('Close')
    );
    try {
        if (closeBtn && closeBtn.parentNode === bar) bar.insertBefore(btn, closeBtn);
        else bar.appendChild(btn);
    } catch { bar.appendChild(btn); }
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
    const hasInternal = !!(window.feedBackDesktop?.audio);
    const hasDesktopMidi = hasInternal; // Desktop app has direct MIDI access
    const bridgeUp = hasDesktopMidi ? false : await _at5Ping(); // skip bridge ping on desktop
    const pcCount = Object.keys(_at5PcTable).length;
    const savedId = localStorage.getItem('at5_output_id');
    const outputs = [];
    if (_at5MidiAccess) _at5MidiAccess.outputs.forEach(o => outputs.push(o));

    const hasAnyMidi = hasInternal || outputs.length || bridgeUp;

    const card = 'background:rgba(55,65,81,0.3);border:1px solid rgba(31,41,55,0.5);border-radius:12px;padding:14px;margin-bottom:10px;';
    const row  = 'display:flex;align-items:center;gap:8px;margin-bottom:6px;';
    const dot  = (col) => `<span style="width:8px;height:8px;border-radius:50%;background:${col};flex-shrink:0;display:inline-block;"></span>`;
    let html = '';

    // ── Docker bridge window banner ───────────────────────────────────────
    const isDockerMode = !hasInternal && !outputs.length && !bridgeUp;
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
                    Docker mode detected. Open this once and leave it running in the background —
                    it handles MIDI directly from your browser, no extra software needed.
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

    if (hasDesktopMidi) {
        // Desktop app — direct MIDI, no bridge needed
        html += `<div style="${row}">
            ${dot('#4ade80')}
            <span style="font-size:0.75rem;font-weight:600;color:#4ade80;">MIDI Ready</span>
            <span style="font-size:0.7rem;color:#4b5563;">Desktop app · direct MIDI output · no bridge needed</span>
        </div>`;
    } else if (outputs.length && !bridgeUp) {
        // Web MIDI available, no bridge — loopMIDI or similar
        html += `<div style="${row}">
            ${dot('#4ade80')}
            <span style="font-size:0.75rem;font-weight:600;color:#4ade80;">MIDI Ready</span>
            <span style="font-size:0.7rem;color:#4b5563;">Web MIDI · ${outputs.length} port${outputs.length>1?'s':''} available</span>
        </div>`;
    } else if (bridgeUp) {
        // Docker + bridge running
        html += `<div style="${row}">
            ${dot('#4ade80')}
            <span style="font-size:0.75rem;font-weight:600;color:#4ade80;">Bridge Ready</span>
            <span style="font-size:0.7rem;color:#4b5563;">Docker mode · at5_midi_bridge.py connected</span>
        </div>`;
    } else {
        // Nothing available — show contextual setup help
        html += `<div style="${row}">
            ${dot('#eab308')}
            <span style="font-size:0.75rem;font-weight:600;color:#eab308;">No MIDI output</span>
        </div>
        <div style="font-size:0.7rem;color:#6b7280;line-height:1.6;margin-bottom:8px;">
            <strong style="color:#9ca3af;">Desktop app?</strong>
            Select your audio interface or a virtual port from the dropdown below.<br>
            No virtual port? Install
            <a href="https://www.tobias-erichsen.de/software/loopmidi.html" target="_blank"
               style="color:#f97316;">loopMIDI</a>,
            create a port, set AT5 MIDI Input to match, then select it here.<br>
            <strong style="color:#9ca3af;">Docker?</strong>
            Open the AT5 MIDI Bridge page in your browser — it handles MIDI directly
            from the host without needing any extra software:<br>
            <a href="/api/plugins/at5_tone/bridge-window" target="_blank"
               style="color:#f97316;font-weight:600;">Open AT5 MIDI Bridge window ↗</a>
            <span style="color:#4b5563;font-size:0.65rem;"> (leave this tab open in the background)</span>
        </div>`;
    }

    if (hasAnyMidi) {
        html += `<div style="${row}">
            <span style="font-size:0.7rem;color:#6b7280;flex-shrink:0;">MIDI output</span>
            <select id="at5-device-select" onchange="localStorage.setItem('at5_output_id',this.value);_at5PickOutput()"
                style="background:#1f2937;border:1px solid #374151;border-radius:6px;padding:3px 8px;font-size:0.75rem;color:#d1d5db;flex:1;">`;
        if (hasInternal) html += `<option value="internal" ${savedId==='internal'?'selected':''}>Internal VST (Desktop)</option>`;
        // Only offer bridge option if no Web MIDI ports and not on desktop
        if (bridgeUp && !hasInternal && !outputs.length) html += `<option value="bridge" ${savedId==='bridge'?'selected':''}>Bridge → AT5 (Docker)</option>`;
        for (const o of outputs) html += `<option value="${o.id}" ${savedId===o.id?'selected':''}>${esc(o.name)}</option>`;
        html += `</select>
            <button onclick="_at5TestMidi()" style="font-size:0.7rem;padding:3px 10px;background:transparent;border:1px solid #374151;border-radius:6px;color:#9ca3af;cursor:pointer;" title="Send PC 0 to verify MIDI is reaching AT5">Test</button>
            <button onclick="_at5DiagMidi()" style="font-size:0.7rem;padding:3px 10px;background:transparent;border:1px solid #374151;border-radius:6px;color:#6b7280;cursor:pointer;" title="Show MIDI diagnostic info">Diag</button>
        </div>
        <pre id="at5-midi-diag" style="display:none;font-size:0.65rem;color:#9ca3af;background:#111827;border-radius:6px;padding:8px;margin-top:6px;white-space:pre-wrap;line-height:1.5;"></pre>`;

        // Contextual hint below the dropdown
        const sel = savedId || (hasInternal ? 'internal' : (bridgeUp ? 'bridge' : (outputs[0]?.id || '')));
        if (hasInternal) {
            html += `<div style="font-size:0.65rem;color:#4b5563;margin-top:2px;">
                Desktop app: Internal VST sends MIDI directly — no cable or bridge needed.
            </div>`;
        } else if (bridgeUp) {
            html += `<div style="font-size:0.65rem;color:#4b5563;margin-top:2px;">
                Docker: MIDI routed via bridge → AXE IO OUT → cable → AXE IO IN → AT5.
            </div>`;
        } else if (outputs.length) {
            const portName = outputs.find(o => o.id === savedId)?.name || outputs[0]?.name || '';
            const isLoopMidi = /bridge|loop|virtual/i.test(portName);
            html += `<div style="font-size:0.65rem;color:#4b5563;margin-top:2px;">
                ${isLoopMidi
                    ? 'Virtual MIDI port — no cable needed. Ensure AT5 MIDI Input matches this port name.'
                    : 'Hardware port — ensure AT5 MIDI Input is set to match and MIDI cable is connected.'}
            </div>`;
        }
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

    // ── First-run setup panel ────────────────────────────────────────────
    const setup = await _at5CheckSetup();
    if (setup && (!setup.presets_linked || !setup.live_slots_exist)) {
        html += `<div style="${card}">`;
        html += `<div style="font-size:0.75rem;font-weight:600;color:#f97316;margin-bottom:10px;">⚙ First-time Setup</div>`;

        // Step 1 — Presets folder
        if (!setup.presets_linked) {
            const isDocker = setup.mode === 'docker';
            html += `<div style="${row};margin-bottom:8px;">
                <span style="width:8px;height:8px;border-radius:50%;background:#f87171;flex-shrink:0;display:inline-block;"></span>
                <span style="font-size:0.75rem;color:#d1d5db;flex:1;">Presets folder not linked to AmpliTube 5</span>
                ${isDocker
                    ? `<span style="font-size:0.7rem;color:#6b7280;">Add <code style="color:#d1d5db;">/at5docs</code> volume mount to docker-compose.yml</span>`
                    : `<button id="at5-setup-symlink-btn" onclick="_at5DoSymlink()"
                        style="font-size:0.7rem;padding:4px 12px;background:#f97316;border:none;border-radius:6px;color:#000;cursor:pointer;font-weight:600;">
                        Create Symlink
                       </button>`
                }
            </div>
            ${isDocker
                ? `<div style="font-size:0.65rem;color:#4b5563;margin-left:16px;margin-bottom:6px;">
                       Add to docker-compose.yml volumes:<br>
                       <code style="color:#9ca3af;">"C:/Users/&lt;username&gt;/Documents/IK Multimedia/AmpliTube 5:/at5docs"</code>
                   </div>`
                : `<div style="margin-left:16px;margin-bottom:6px;">
                       ${setup.detected_at5_presets
                           ? `<div style="font-size:0.65rem;color:#6b7280;margin-bottom:4px;">
                                  Detected AT5 Presets: <code style="color:#9ca3af;">${setup.detected_at5_presets}</code>
                              </div>`
                           : `<div style="font-size:0.65rem;color:#f87171;margin-bottom:4px;">
                                  Could not detect AT5 Presets folder. Enter path manually:
                              </div>
                              <input id="at5-presets-path-input" type="text" placeholder="C:\Users\...\IK Multimedia\AmpliTube 5\Presets"
                                  style="width:100%;background:#1f2937;border:1px solid #374151;border-radius:6px;padding:4px 8px;font-size:0.7rem;color:#d1d5db;box-sizing:border-box;margin-bottom:4px;">`
                       }
                       <div id="at5-setup-symlink-msg" style="font-size:0.65rem;color:#6b7280;"></div>
                   </div>`
            }`;
        } else {
            html += `<div style="${row};margin-bottom:4px;">
                <span style="width:8px;height:8px;border-radius:50%;background:#4ade80;flex-shrink:0;display:inline-block;"></span>
                <span style="font-size:0.75rem;color:#6b7280;">Presets folder linked ✓</span>
            </div>`;
        }

        // Step 2 — Live slots
        if (setup.presets_linked && !setup.live_slots_exist) {
            html += `<div style="${row};margin-bottom:8px;">
                <span style="width:8px;height:8px;border-radius:50%;background:#f87171;flex-shrink:0;display:inline-block;"></span>
                <span style="font-size:0.75rem;color:#d1d5db;flex:1;">
                    Live slots not populated
                    ${setup.live_slot_count > 0 ? `(${setup.live_slot_count}/8 found)` : '(0 found)'}
                </span>
                <button id="at5-setup-pcmap-btn" onclick="_at5DoPcMap()"
                    style="font-size:0.7rem;padding:4px 12px;background:#f97316;border:none;border-radius:6px;color:#000;cursor:pointer;font-weight:600;">
                    Run Setup
                </button>
            </div>
            <div id="at5-setup-pcmap-msg" style="font-size:0.65rem;color:#6b7280;margin-left:16px;margin-bottom:6px;"></div>
            <div style="font-size:0.65rem;color:#4b5563;margin-left:16px;">
                Restart AmpliTube 5 after running to pick up the new PC map.
            </div>`;
        } else if (setup.presets_linked) {
            html += `<div style="${row};margin-bottom:4px;">
                <span style="width:8px;height:8px;border-radius:50%;background:#4ade80;flex-shrink:0;display:inline-block;"></span>
                <span style="font-size:0.75rem;color:#6b7280;">${setup.live_slot_count} live slots ready ✓</span>
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

async function _at5DoSymlink() {
    const btn = document.getElementById('at5-setup-symlink-btn');
    const msg = document.getElementById('at5-setup-symlink-msg');
    if (btn) { btn.disabled = true; btn.textContent = 'Working...'; }
    // Include manual path override if user entered one
    const pathInput = document.getElementById('at5-presets-path-input');
    const body = pathInput?.value ? JSON.stringify({ at5_presets_path: pathInput.value }) : '{}';
    try {
        const r = await fetch('/api/plugins/at5_tone/setup/create-symlink', { method: 'POST', headers: {'Content-Type':'application/json'}, body });
        const d = await r.json();
        if (msg) {
            msg.style.color = d.ok ? '#4ade80' : '#f87171';
            if (d.ok) {
                msg.textContent = '✓ Symlink created — restart feedBack to apply';
            } else if (d.manual_cmd) {
                msg.innerHTML = '✗ ' + d.error +
                    '<br><span style="color:#9ca3af;">Or run this in PowerShell as admin:</span>' +
                    '<br><code style="color:#d1d5db;font-size:0.6rem;word-break:break-all;">' + d.manual_cmd + '</code>';
            } else {
                msg.textContent = '✗ ' + d.error;
            }
        }
        if (d.ok) setTimeout(() => _at5RenderStatus(), 1500);
    } catch(e) {
        if (msg) { msg.style.color = '#f87171'; msg.textContent = '✗ ' + e.message; }
    }
    if (btn) { btn.disabled = false; btn.textContent = 'Create Symlink'; }
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
    const lines = [`Saved output_id: ${savedId || '(none)'}`];
    lines.push(`_at5MidiOutput: ${window._at5MidiOutput ? window._at5MidiOutput.name + ' [' + window._at5MidiOutput.id + ']' : 'null'}`);
    lines.push(`_at5BridgeOk: ${window._at5BridgeOk}`);
    lines.push(`feedBackDesktop.audio: ${!!(window.feedBackDesktop?.audio)}`);
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

async function _at5TestMidi() {
    // Send PC 0 as a quick connectivity check
    await _at5SendPC(0, []);
    const btn = document.querySelector('button[onclick="_at5TestMidi()"]');
    if (btn) { btn.textContent = '✓ PC0 sent'; setTimeout(() => btn.textContent = 'Test', 1500); }
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
    const decoded = decodeURIComponent(filename);
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
    } catch(e) {}
    // Restore prefire slider from localStorage
    const prefireMs = Math.round(AT5_PREFIRE_MS * 1000);
    const slider = document.getElementById('at5-prefire-slider');
    const label  = document.getElementById('at5-prefire-label');
    if (slider) slider.value = prefireMs;
    if (label)  label.textContent = `${prefireMs} ms`;
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
_at5Ping();
_at5LoadPcTable();

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
window._at5SetPrefire    = (v) => { AT5_PREFIRE_MS = parseFloat(v) || 0; };
window._at5LiveSlots     = _at5LiveSlots;
window._at5RequestLiveConvert = _at5RequestLiveConvert;
window._at5SaveBack          = _at5SaveBack;
window._at5TestMidi          = _at5TestMidi;
window._at5DiagMidi          = _at5DiagMidi;
window._at5DoSymlink         = _at5DoSymlink;
window._at5OpenBridgeWindow  = _at5OpenBridgeWindow;
window._at5DismissBridgeBanner = _at5DismissBridgeBanner;
window._at5DoPcMap           = _at5DoPcMap;
window._at5LoadSettings      = _at5LoadSettings;
window.at5SetPrefire         = at5SetPrefire;
window.at5SetFreeMode        = at5SetFreeMode;
window.at5SetTier            = at5SetTier;
window.at5SetNoisegate       = at5SetNoisegate;

// Reset AT5 to PC 0 when song stops
(function() {
    const origStop = window.highway && window.highway.stop;
    if (origStop) {
        window.highway.stop = function() {
            _at5StopScheduler(true);
            return origStop.apply(this, arguments);
        };
    }
})();

// Hook showScreen
(function () {
    const orig = window.showScreen;
    if (orig) window.showScreen = function (id) {
        orig(id);
        if (id === 'at5-tone') {
            _at5RenderStatus();
            _at5RefreshLogUI();
        }
    };
})();

// Stub viz registration (harmless — prevents plugin manager warnings)
window.feedBackViz_at5tone = { init(){}, draw(){}, destroy(){} };

})();


})();
