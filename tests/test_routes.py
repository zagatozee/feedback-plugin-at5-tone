import json
import platform

import pytest

from conftest import write_feedpak_dir


# ── AmpliTube 5 folder resolution ─────────────────────────────────────────

def test_live_slots_are_created_in_the_resolved_at5_folder(make_plugin, at5_dir):
    mod, client = make_plugin(at5_docs=at5_dir)
    converted = at5_dir / "Presets" / "Converted"
    assert mod._live_presets_dir == converted
    assert len(list(converted.glob("AT5_LIVE_*.at5p"))) == mod.LIVE_SLOT_COUNT

    status = client.get("/api/plugins/at5_tone/setup/status").json()
    assert status["presets_linked"] is True
    assert status["at5_dir"] == str(at5_dir)
    assert status["at5_dir_source"] == "env"
    assert status["live_slots_exist"] is False   # not registered in the PC map yet


def test_config_dir_parent_is_never_used_as_the_at5_folder(make_plugin, config_dir):
    # The old code wrote live slots to <config_dir>/../Presets/Converted, which on
    # feedBack Desktop is %APPDATA%/feedback-desktop — a folder AT5 never reads.
    mod, client = make_plugin(at5_docs=None)
    assert mod._at5_dir is None and mod._live_presets_dir is None
    assert not (config_dir.parent / "Presets").exists()
    r = client.post("/api/plugins/at5_tone/live_convert", json={"filename": "x.feedpak"})
    assert r.status_code == 200 and r.json()["status"] == "error"
    status = client.get("/api/plugins/at5_tone/setup/status").json()
    assert status["presets_linked"] is False


def test_at5_path_setting_is_validated_persisted_and_applied(make_plugin, at5_dir, config_dir):
    mod, client = make_plugin(at5_docs=None)

    r = client.post("/api/plugins/at5_tone/setup/at5-path", json={"path": str(at5_dir / "nope")})
    assert r.json()["ok"] is False

    # The Presets folder itself is accepted and normalised to its parent
    r = client.post("/api/plugins/at5_tone/setup/at5-path", json={"path": str(at5_dir / "Presets")})
    body = r.json()
    assert body["ok"] is True and body["at5_dir"] == str(at5_dir) and body["at5_dir_source"] == "setting"
    assert mod._live_presets_dir == at5_dir / "Presets" / "Converted"
    saved = json.loads((config_dir / "at5_tone_settings.json").read_text(encoding="utf-8"))
    assert saved["at5_docs_path"] == str(at5_dir)

    # A fresh load (server restart) picks the saved folder back up
    mod2, _ = make_plugin(at5_docs=None)
    assert mod2._at5_dir == at5_dir and mod2._at5_dir_source == "setting"

    # Empty path clears the override
    r = client.post("/api/plugins/at5_tone/setup/at5-path", json={"path": ""})
    assert r.json()["ok"] is True and mod._at5_dir is None


def test_detection_is_inert_off_windows(monkeypatch):
    from conftest import _load_routes
    mod = _load_routes("at5_routes_detect")
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert mod._detect_at5_presets_path() is None   # used to raise ImportError (winreg)


# ── Settings ──────────────────────────────────────────────────────────────

def test_settings_persist_across_restart(make_plugin, at5_dir):
    _, client = make_plugin(at5_docs=at5_dir)
    r = client.post("/api/plugins/at5_tone/settings", json={"tier": "se", "noise_gate": True})
    assert r.json()["tier"] == "se"
    _, client2 = make_plugin(at5_docs=at5_dir)
    s = client2.get("/api/plugins/at5_tone/settings").json()
    assert s["tier"] == "se" and s["noise_gate"] is True


@pytest.mark.parametrize("body", [b"{not json", b"[1, 2]"])
def test_bad_bodies_are_400(make_plugin, at5_dir, body):
    _, client = make_plugin(at5_docs=at5_dir)
    for url in ("/api/plugins/at5_tone/live_convert", "/api/plugins/at5_tone/settings",
                "/api/plugins/at5_tone/bridge-window/send"):
        r = client.post(url, content=body, headers={"Content-Type": "application/json"})
        assert r.status_code == 400, url


def test_unknown_tier_is_400(make_plugin, at5_dir):
    _, client = make_plugin(at5_docs=at5_dir)
    assert client.post("/api/plugins/at5_tone/settings", json={"tier": "ultra"}).status_code == 400


# ── Bridge window queue (Docker path) ─────────────────────────────────────

def test_bridge_window_send_and_ack(make_plugin, at5_dir):
    # These handlers lacked the Request annotation, so FastAPI answered 422.
    _, client = make_plugin(at5_docs=at5_dir)
    r = client.post("/api/plugins/at5_tone/bridge-window/send", json={"type": "pc", "channel": 0, "program": 121})
    assert r.status_code == 200
    seq = r.json()["seq"]
    cmds = client.get("/api/plugins/at5_tone/bridge-window/poll?seq=0").json()["commands"]
    assert cmds[-1]["program"] == 121
    assert client.post("/api/plugins/at5_tone/bridge-window/ack", json={"seq": seq}).status_code == 200
    assert client.get("/api/plugins/at5_tone/bridge-window/poll?seq=0").json()["commands"] == []


def test_bridge_window_rejects_out_of_range_midi(make_plugin, at5_dir):
    _, client = make_plugin(at5_docs=at5_dir)
    r = client.post("/api/plugins/at5_tone/bridge-window/send", json={"type": "pc", "channel": 0, "program": 300})
    assert r.status_code == 400


# ── Live convert ──────────────────────────────────────────────────────────

def test_live_convert_fills_a_slot_and_seeds_the_song_folder(make_plugin, at5_dir, dlc_dir):
    pak = write_feedpak_dir(dlc_dir)
    mod, client = make_plugin(at5_docs=at5_dir)
    r = client.post("/api/plugins/at5_tone/live_convert", json={"filename": pak.name}).json()
    assert r["status"] == "ok", r
    assert r["slots"] == {"Clean_Tone": mod.LIVE_SLOT_START}
    assert (pak / "at5" / "max" / "Clean_Tone.at5p").exists()


def test_live_convert_cannot_escape_the_library(make_plugin, at5_dir, dlc_dir, tmp_path):
    outside = write_feedpak_dir(tmp_path, name="outside.feedpak")
    _, client = make_plugin(at5_docs=at5_dir)
    r = client.post("/api/plugins/at5_tone/live_convert", json={"filename": "../" + outside.name}).json()
    assert r["status"] == "error" and "not found" in r["message"]


# ── PC map setup ──────────────────────────────────────────────────────────

def test_run_pc_map_registers_live_slots(make_plugin, at5_dir):
    # Previously a 422 (unannotated request param) and pointed at a guessed folder.
    _, client = make_plugin(at5_docs=at5_dir)
    r = client.post("/api/plugins/at5_tone/setup/run-pc-map", json={})
    assert r.status_code == 200 and r.json()["ok"] is True, r.json()
    assert "AT5_LIVE" in (at5_dir / "ProgramChangePresetList.ik").read_text(encoding="utf-8")
    status = client.get("/api/plugins/at5_tone/setup/status").json()
    assert status["pc_map_exists"] is True and status["live_slots_exist"] is True


# ── Output level (tones loaded very loud) ────────────────────────────────

def test_output_level_setting_is_validated_and_persisted(make_plugin, at5_dir):
    mod, client = make_plugin(at5_docs=at5_dir)
    assert client.get("/api/plugins/at5_tone/settings").json()["output_db"] == -10.0
    assert client.post("/api/plugins/at5_tone/settings", json={"output_db": -18}).json()["output_db"] == -18.0
    for bad in (-31, 7, "loud", True, None):
        assert client.post("/api/plugins/at5_tone/settings", json={"output_db": bad}).status_code == 400
    mod2, client2 = make_plugin(at5_docs=at5_dir)          # restart
    assert client2.get("/api/plugins/at5_tone/settings").json()["output_db"] == -18.0


def test_live_slot_gets_the_output_level_set_not_stacked_and_the_stored_preset_keeps_its_seed(make_plugin, at5_dir, dlc_dir):
    pak = dlc_dir / "song.feedpak"
    write_feedpak_dir(dlc_dir)
    mod, client = make_plugin(at5_docs=at5_dir)
    client.post("/api/plugins/at5_tone/settings", json={"output_db": -20})
    r = client.post("/api/plugins/at5_tone/live_convert", json={"filename": pak.name}).json()
    assert r["status"] == "ok", r
    slot = (at5_dir / "Presets" / "Converted" / "AT5_LIVE_00.at5p").read_text(encoding="utf-8")
    assert '<Output Output="0.1" />' in slot                 # -20 dB
    # The preset seeded into the song is a copy of that leveled slot (-20 dB).
    stored = pak / "at5" / "max" / "Clean_Tone.at5p"
    assert '<Output Output="0.1" />' in stored.read_text(encoding="utf-8")
    # A second load of the stored (song-local) preset sets, not stacks, the level.
    client.post("/api/plugins/at5_tone/settings", json={"output_db": -6})
    r = client.post("/api/plugins/at5_tone/live_convert", json={"filename": pak.name}).json()
    assert r["status"] == "ok", r
    slot = (at5_dir / "Presets" / "Converted" / "AT5_LIVE_00.at5p").read_text(encoding="utf-8")
    assert '<Output Output="0.50119" />' in slot             # -6 dB, not -26
    # Loading it again set the slot only: the stored file still holds its seed.
    assert '<Output Output="0.1" />' in stored.read_text(encoding="utf-8")


def test_level_policy_fills_a_missing_amp_volume_and_respects_one_that_is_set():
    import importlib.util
    from conftest import ROOT
    spec = importlib.util.spec_from_file_location("cdlc_to_at5_lp", ROOT / "cdlc_to_at5.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    svt = "2aa0f50f-a6c9-4edd-97c2-df71a24087db"   # Ampeg SVT-VR: Volume1_AmpegSVTVR
    base = ('<AmpA Bypass="0" Mute="{mute}" OutputVolume="1" Model="' + svt + '">\n'
            '        <Amp {knobs}/>\n    </AmpA>\n    <Output Output="1" />\n    <MidiAssignments />')
    out = m.apply_level_policy(base.format(mute="0", knobs='Gain_AmpegSVTVR="3.0000"'), -10)
    assert 'Volume1_AmpegSVTVR="5.0000"' in out and '<Output Output="0.31623" />' in out
    assert m.apply_level_policy(out, -10) == out                                   # idempotent
    own = m.apply_level_policy(base.format(mute="0", knobs='Volume1_AmpegSVTVR="2.0000"'), -10)
    assert 'Volume1_AmpegSVTVR="2.0000"' in own and "5.0000" not in own           # user's volume kept
    di = m.apply_level_policy(base.format(mute="1", knobs=""), -10)
    assert "5.0000" not in di                                                      # DI tone: amp bypassed
    unknown = m.apply_level_policy(base.replace(svt, "00000000-0000-0000-0000-000000000000")
                                   .format(mute="0", knobs='Gain="3"'), 0)
    assert "5.0000" not in unknown and '<Output Output="1" />' in unknown        # unknown model left alone


def test_output_level_accepts_both_ends_of_the_slider(make_plugin, at5_dir):
    mod, client = make_plugin(at5_docs=at5_dir)
    for db in (-30, 6, -30.0, 6.0):
        r = client.post("/api/plugins/at5_tone/settings", json={"output_db": db})
        assert r.status_code == 200, db
        assert r.json()["output_db"] == float(db)
