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


@pytest.mark.parametrize("stored", [99, -31, True, "x", None, [1], float("nan")])
def test_a_bad_persisted_output_level_loads_as_the_default(make_plugin, at5_dir, config_dir, stored):
    # json.dumps writes NaN as a bare NaN token, which Python's loader accepts.
    (config_dir / "at5_tone_settings.json").write_text(json.dumps({"output_db": stored}), encoding="utf-8")
    mod, client = make_plugin(at5_docs=at5_dir)
    assert client.get("/api/plugins/at5_tone/settings").json()["output_db"] == -10.0


def test_a_good_persisted_output_level_loads(make_plugin, at5_dir, config_dir):
    (config_dir / "at5_tone_settings.json").write_text(json.dumps({"output_db": -18}), encoding="utf-8")
    mod, client = make_plugin(at5_docs=at5_dir)
    assert client.get("/api/plugins/at5_tone/settings").json()["output_db"] == -18.0


def test_a_level_policy_failure_still_gives_the_tone_its_slot(make_plugin, at5_dir, dlc_dir, monkeypatch, caplog):
    pak = dlc_dir / "song.feedpak"
    write_feedpak_dir(dlc_dir)
    mod, client = make_plugin(at5_docs=at5_dir)

    def boom(*a, **k):
        raise RuntimeError("level policy broke")

    monkeypatch.setattr(mod._load_converter(), "apply_level_policy", boom)
    with caplog.at_level("WARNING"):
        r = client.post("/api/plugins/at5_tone/live_convert", json={"filename": pak.name}).json()
    # The tone keeps its slot (unleveled) instead of dropping to the PC table.
    assert r["status"] == "ok" and r["slots"] == {"Clean_Tone": mod.LIVE_SLOT_START}, r
    assert r["warnings"] == []
    slot = (at5_dir / "Presets" / "Converted" / "AT5_LIVE_00.at5p").read_text(encoding="utf-8")
    assert '<Output Output="1" />' in slot
    assert "level policy not applied" in caplog.text


SVT = "2aa0f50f-a6c9-4edd-97c2-df71a24087db"        # Ampeg SVT-VR: Volume1_AmpegSVTVR
MESA = "a91067a3-fd80-40a8-be35-0681da5c4f47"       # Volume_MesaMKIIIClean and Master_MesaMKIIIClean are different knobs
CHAMPION = "016a8c2a-489e-49da-81d7-5b72feb60f74"   # Volume, Loudness and Master are all Volume_Champion


def _converter():
    import importlib.util
    from conftest import ROOT
    spec = importlib.util.spec_from_file_location("cdlc_to_at5_lp2", ROOT / "cdlc_to_at5.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _preset(model, knobs="", output='    <Output Output="1" />\n'):
    return ('<AmpA Bypass="0" Mute="0" OutputVolume="1" Model="' + model + '">\n'
            '        <Amp ' + knobs + '/>\n    </AmpA>\n' + output + '    <MidiAssignments />')


def _amp_attrs(xml_text):
    """The amp's attributes, parsed as XML (which rejects a duplicated attribute)."""
    import xml.etree.ElementTree as ET
    return ET.fromstring("<r>" + xml_text + "</r>").find("AmpA/Amp").attrib


def test_level_policy_adds_an_output_to_a_preset_that_has_none():
    m = _converter()
    out = m.apply_level_policy(_preset(SVT, 'Gain_AmpegSVTVR="3.0000"', output=""), -10)
    assert out.count("<Output ") == 1 and '<Output Output="0.31623" />' in out
    assert m.apply_level_policy(out, -10) == out


@pytest.mark.parametrize("model,knob", [
    (MESA, "Master_MesaMKIIIClean"),     # Master-named knobs exist on 19 models
    (SVT, "Volume1_AmpegSVTVR"),
    (SVT, "Output_X"),
    (SVT, "Loudness_X"),
])
def test_an_amp_that_sets_its_own_volume_is_left_alone(model, knob):
    # Each knob name starts with one of the volume prefixes; filling a default
    # on top would add a second Volume/Master attribute and break the XML.
    m = _converter()
    xml = _preset(model, knob + '="3.0000" ')
    assert m.apply_level_policy(xml, 0) == xml
    assert _amp_attrs(m.apply_level_policy(xml, -10)) == {knob: "3.0000"}


def test_level_policy_fills_both_the_volume_and_the_master_knob():
    # On the Mesa MKIII the two are different knobs; the SVT test above only
    # covers an amp whose Master is the same knob as its Volume.
    m = _converter()
    out = m.apply_level_policy(_preset(MESA, 'Gain_MesaMKIIIClean="3.0000" '), -10)
    attrs = _amp_attrs(out)
    assert attrs["Volume_MesaMKIIIClean"] == "5.0000" and attrs["Master_MesaMKIIIClean"] == "5.0000"
    assert attrs["Gain_MesaMKIIIClean"] == "3.0000"


@pytest.mark.parametrize("model,knob", [
    (CHAMPION, "Volume_Champion"),       # Volume, Loudness and Master are all this knob
    ("0265b273-d648-47c7-a5ef-579acba82a0a", "Master_AmpegV4B"),   # Volume and Master are the same knob
])
def test_level_policy_fills_a_shared_volume_and_master_knob_once(model, knob):
    # 43 of the 70 mapped amps use one knob for both roles; a duplicate attribute
    # is invalid XML, which AmpliTube may refuse to load.
    m = _converter()
    out = m.apply_level_policy(_preset(model), -10)
    assert out.count(knob + "=") == 1
    assert _amp_attrs(out) == {knob: "5.0000"}


def _settings_snapshot(mod, client, config_dir):
    saved = config_dir / "at5_tone_settings.json"
    return (client.get("/api/plugins/at5_tone/settings").json(), dict(mod._live_state),
            saved.read_bytes() if saved.exists() else None)


def _mixed_bodies():
    """Every combination of the accepted fields that includes a rejected one."""
    import itertools
    good = [("tier", "se"), ("free_mode", True), ("noise_gate", True), ("output_db", -20)]
    bad = [{"output_db": 7}, {"output_db": "x"}, {"output_db": True}, {"tier": "nope"},
           {"tier": "nope", "output_db": 7}]
    for n in range(len(good) + 1):
        for subset in itertools.combinations(good, n):
            for b in bad:
                yield {**dict(subset), **b}


def test_a_rejected_settings_post_changes_nothing(make_plugin, at5_dir, config_dir):
    mod, client = make_plugin(at5_docs=at5_dir)
    mod._live_state.update({"song": "keep.feedpak", "slots": {"Clean_Tone": 120}})
    # The exact request from the review, then every combination that has a bad field.
    bodies = [{"tier": "se", "noise_gate": True, "output_db": 7}, *_mixed_bodies()]
    for body in bodies:
        before = _settings_snapshot(mod, client, config_dir)
        r = client.post("/api/plugins/at5_tone/settings", json=body)
        assert r.status_code == 400, body
        assert _settings_snapshot(mod, client, config_dir) == before, body
        assert mod._live_state["song"] == "keep.feedpak", body      # live slots not cleared


def test_a_valid_mixed_settings_post_applies_every_field(make_plugin, at5_dir):
    mod, client = make_plugin(at5_docs=at5_dir)
    r = client.post("/api/plugins/at5_tone/settings",
                    json={"tier": "se", "noise_gate": True, "output_db": -20}).json()
    assert (r["tier"], r["free_mode"], r["noise_gate"], r["output_db"]) == ("se", False, True, -20.0)
    r = client.post("/api/plugins/at5_tone/settings", json={"free_mode": True}).json()
    assert (r["tier"], r["free_mode"]) == ("cs", True)
