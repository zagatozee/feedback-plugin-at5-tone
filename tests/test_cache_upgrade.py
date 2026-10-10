"""Song preset caches made by an older converter are re-converted; saved-back
user presets never are."""


def _write(d, name, text):
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.at5p"
    p.write_text(text, encoding="utf-8")
    return p


OLD_07 = ('<Preset><Chain Preset="Chain11" MonoChainDualCab="1" DIBeforeAmp="0" />'
          '<CabA IRDecimation="1"><Cab RoomType="Large Studio" RoomMicType="Condenser 87" Mic0Model="x" GUILoadComplete="0" /></CabA><AmpA><Amp Gain_X="5.0000"/></AmpA>'
          '<MetaInfo Song="s" Album="" KeyWords="" /></Preset>')


def test_old_and_new_markers(make_plugin, tmp_path):
    mod, _ = make_plugin(None)
    conv = mod._load_converter()
    d = tmp_path / "song" / "at5" / "max"
    old = _write(d, "OldTone", OLD_07)
    stale = _write(d, "Stale", '<MetaInfo KeyWords="at5_tone converter 0.0.1" />')
    fresh = _write(d, "Fresh", f'<MetaInfo KeyWords="{conv.CONVERTER_MARK}" />')
    user = _write(d, "Mine", '<MetaInfo KeyWords="at5_tone user" />')
    at5_saved = _write(d, "At5Saved", '<Preset><AmpA><Amp Gain_X="5" /></AmpA><MetaInfo KeyWords="" /></Preset>')

    assert mod._is_stale_generated(old)
    assert mod._is_stale_generated(stale)
    assert not mod._is_stale_generated(fresh)
    assert not mod._is_stale_generated(user)
    assert not mod._is_stale_generated(at5_saved)

    moved = mod._retire_stale_presets(d)
    assert sorted(moved) == ["OldTone", "Stale"]
    assert (d / "superseded" / "OldTone.at5p").exists()          # kept, never deleted
    assert sorted(p.stem for p in d.glob("*.at5p")) == ["At5Saved", "Fresh", "Mine"]


def test_save_back_marks_preset_as_user(make_plugin, tmp_path):
    mod, _ = make_plugin(None)
    conv = mod._load_converter()
    p = _write(tmp_path, "T", f'<MetaInfo KeyWords="{conv.CONVERTER_MARK}" />')
    mod._mark_user_preset(p)
    assert 'KeyWords="at5_tone user"' in p.read_text(encoding="utf-8")
    assert not mod._is_stale_generated(p)


def test_converted_preset_carries_current_marker(make_plugin):
    mod, _ = make_plugin(None)
    conv = mod._load_converter()
    xml, _ = conv.build_preset("K", "N", {"Amp": {"Key": "Amp_TW22"}})
    assert f'KeyWords="{conv.CONVERTER_MARK}"' in xml


def test_repeated_retirement_keeps_every_backup(make_plugin, tmp_path):
    mod, _ = make_plugin(None)
    d = tmp_path / "s" / "at5" / "max"
    _write(d, "T", '<MetaInfo KeyWords="at5_tone converter 0.0.1" />')
    mod._retire_stale_presets(d)
    _write(d, "T", '<MetaInfo KeyWords="at5_tone converter 0.0.2" />')
    mod._retire_stale_presets(d)
    assert sorted(p.name for p in (d / "superseded").iterdir()) == ["T.1.at5p", "T.at5p"]
