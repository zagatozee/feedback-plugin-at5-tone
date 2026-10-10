"""Knob-accurate conversion: tone_params.py + the cdlc_to_at5 preset builder."""
import importlib.util
import json
import re
import sys
import xml.dom.minidom
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load("c2a_under_test", "cdlc_to_at5.py")
TP = C.TP


def slot_attrs(xml_text, section, index=0):
    m = re.search(rf"<{section}\b([^>]*)>(.*?)</{section}>", xml_text, re.S)
    assert m, section
    guids = dict(re.findall(r'Stomp(\d)="([^"]+)"', m.group(1)))
    slot = re.search(rf"<Slot{index}\b([^>]*?)/>", m.group(2)).group(1)
    return guids.get(str(index)), dict(re.findall(r'(\w+)="([^"]*)"', slot))


# ── data ─────────────────────────────────────────────────────────────────────

def test_data_files_load():
    assert len(TP.RS_GEAR) > 600
    assert len(TP.AT5_MODELS) > 400
    assert TP.at5_guid("7 Band Graphic", "stomp") == "8d7ff76e-9273-46b6-95d5-3d7bd667fff2"


def test_every_rocksmith_pedal_and_rack_has_a_recipe():
    missing = [k for k, v in TP.RS_GEAR.items() if v["type"] in ("Pedals", "Racks") and k not in TP.RECIPES]
    assert missing == []


@pytest.mark.parametrize("rs_key", sorted(TP.RECIPES))
def test_recipe_is_complete(rs_key):
    """Target exists, writes only real parameters, and every Rocksmith knob is
    either converted or documented in the recipe (never silently dropped)."""
    r = TP.RECIPES[rs_key]
    guid = TP.at5_guid(r.target, r.kind)
    assert guid, f"{r.target} not in AmpliTube GearInfo"
    assert rs_key in TP.RS_GEAR
    specs = TP.at5_param_specs(guid)
    assert set(r.params) <= set(specs)
    for knob in r.approx:
        assert knob.startswith("__") or knob in TP.rs_knob_defs(rs_key)
    conv = TP.convert_effect(rs_key, {}, guid)
    assert not [n for n in conv.notes if "not carried over" in n or "could not" in n]


def test_every_guid_literal_is_a_real_amplitube_model():
    known = {g.replace("-", "") for g in TP.AT5_MODELS} | {TP.NULL_GUID.replace("-", "")}
    tuner = "354eca51457a41b7917dce6117586905"
    src = (ROOT / "cdlc_to_at5.py").read_text(encoding="utf-8")
    found = re.findall(r'"([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})"', src)
    bad = {g for g in found if g.replace("-", "") not in known | {tuner}}
    assert bad == set()


# ── value encoding ───────────────────────────────────────────────────────────

def test_encode_units():
    assert TP.encode(("gain", -15, 15), 0) == "1"
    assert float(TP.encode(("gain", -15, 15), -15)) == pytest.approx(0.177828, rel=1e-4)
    assert float(TP.encode(("gain", -15, 15), 40)) == pytest.approx(5.62341, rel=1e-4)   # clamped
    assert TP.encode(("vol",), -200) == "0"
    assert float(TP.encode(("vol",), -6)) == pytest.approx(0.501187, rel=1e-4)
    assert float(TP.encode(("thresh", -100, 0), -55)) == pytest.approx(0.00177828, rel=1e-4)
    assert TP.encode(("ms", 1, 2000), 5000) == "2000"
    assert TP.encode(("switch",), 0.7) == "1"


def test_missing_knob_takes_rocksmith_default():
    k = TP.Knobs("Pedal_EQ5", {})
    assert k.v("63") == -6.0           # the game's default, not the middle
    k = TP.Knobs("Rack_StudioEQ", {"Rack_StudioEQ_HiMidFreq": 2.0})
    assert k.v("HiMidFreq") == 2000.0  # kHz knob read as Hz


# ── EQ engine ────────────────────────────────────────────────────────────────

def test_flat_eq_stays_flat():
    bands = [("peak", f, 0.0, 1.4) for f in (100, 400, 1600)]
    assert all(abs(g) < 1e-6 for g in TP.fit_graphic(bands, [100, 200, 400, 800, 1600]))


def test_single_boost_lands_on_matching_band():
    gains = TP.fit_graphic([("peak", 800.0, 6.0, 1.4)], [100, 200, 400, 800, 1600, 3200, 6400])
    assert gains[3] == pytest.approx(6.0, abs=1.0)
    assert abs(gains[0]) < 1.0 and abs(gains[6]) < 1.0


def test_parametric_cut_reaches_graphic_eq():
    c = TP.convert_effect("Rack_StudioEQ", {"Rack_StudioEQ_LoMid": -9, "Rack_StudioEQ_LoMidFreq": 400,
                                            "Rack_StudioEQ_LoMidQ": 1},
                          TP.recipe_target_guid("Rack_StudioEQ"))
    assert float(c.attrs["Band400"]) == pytest.approx(-9.0, abs=1.5)
    assert abs(float(c.attrs["Band4000"])) < 1.5


# ── recipes ──────────────────────────────────────────────────────────────────

def test_delay_keeps_milliseconds_and_percent():
    c = TP.convert_effect("Pedal_NPNDelay", {"Pedal_NPNDelay_Time": 480, "Pedal_NPNDelay_Feedback": 35,
                                             "Pedal_NPNDelay_Mix": 30},
                          TP.recipe_target_guid("Pedal_NPNDelay"))
    assert c.attrs["Delay"] == "480" and c.attrs["Feedback"] == "35" and c.attrs["Level"] == "3"


def test_wah_manual_vs_auto():
    g = TP.recipe_target_guid("Pedal_USWah")
    assert TP.convert_effect("Pedal_USWah", {"Pedal_USWah_Auto": 0, "Pedal_USWah_Pedal": 60}, g).attrs \
        == {"Mode": "On", "Wah": "60"}
    assert TP.convert_effect("Pedal_USWah", {"Pedal_USWah_Auto": 1}, g).attrs["Mode"] == "Auto"


def test_noise_gate_threshold_is_linear():
    c = TP.convert_effect("Pedal_NoiseGate", {"Pedal_NoiseGate_Thresh": -60},
                          TP.recipe_target_guid("Pedal_NoiseGate"))
    assert float(c.attrs["Threshold"]) == pytest.approx(10 ** (-60 / 20), rel=1e-4)


def test_unrepresentable_knob_is_reported():
    c = TP.convert_effect("Pedal_CustomDrive", {"Pedal_CustomDrive_Voice": 0},
                          TP.recipe_target_guid("Pedal_CustomDrive"))
    assert any("Voice" in n for n in c.notes)


# ── amps ─────────────────────────────────────────────────────────────────────

def test_amp_knob_never_lands_on_a_switch():
    guid, _ = C.lookup_amp("Amp_TW22")
    attrs, _ = TP.convert_amp_knobs("Amp_TW22", {"Amp_TW22_Gain": 80}, guid, C.AMP_KNOB_MAP.get(guid))
    assert not any(k.startswith("Input_") for k in attrs)
    assert float(attrs["InstVol_Fender57CustomDeluxe"]) > 7


def test_multichannel_amp_uses_one_channel():
    guid, _ = C.lookup_amp("Amp_CA100")
    attrs, _ = TP.convert_amp_knobs("Amp_CA100", {}, guid, C.AMP_KNOB_MAP.get(guid))
    chans = {re.match(r"(Ch\d)", k).group(1) for k in attrs if re.match(r"Ch\d", k)}
    assert len(chans) == 1


def test_bass_amp_graphic_eq_becomes_an_eq_effect():
    guid, _ = C.lookup_amp("Bass_Amp_CH350B")
    amp = TP.convert_amp("Bass_Amp_CH350B", {"Bass_Amp_CH350B_800": -8}, guid, C.AMP_KNOB_MAP.get(guid))
    assert amp.eq_bands
    eq = TP.amp_eq_effect(amp.eq_bands)
    assert TP.at5_name(eq.guid) == "10 Band Graphic"
    assert float(eq.attrs["Band1000"]) < -3


# ── preset assembly ──────────────────────────────────────────────────────────

GEAR = {
    "Amp": {"Key": "Amp_MarshallJCM800", "KnobValues": {"Amp_MarshallJCM800_Gain": 70}},
    "Cabinet": {"Key": "Cab_Marshall1960AV_57_Cone"},
    "PrePedal1": {"Key": "Pedal_CustomDrive", "KnobValues": {"Pedal_CustomDrive_Gain": 40}},
    "PostPedal1": {"Key": "Pedal_NPNDelay", "KnobValues": {"Pedal_NPNDelay_Time": 400}},
    "Rack1": {"Key": "Rack_StudioVerb", "KnobValues": {"Rack_StudioVerb_Mix": 25}},
}


def test_effects_land_in_the_right_chain_sections():
    xml_text, _ = C.build_preset("K", "Name", GEAR, volume=-14.0)
    xml.dom.minidom.parseString(xml_text)
    g, a = slot_attrs(xml_text, "StompA1")
    assert TP.at5_name(g) == "Overdrive" and "Drive" in a           # before the amp
    g, a = slot_attrs(xml_text, "LoopFxA")
    assert TP.at5_name(g) == "Delay" and a["Delay"] == "400"        # after the amp (loop)
    g, a = slot_attrs(xml_text, "RackMaster")
    assert TP.at5_name(g) == "Digital Reverb" and a["Mix"] == "25"
    g, _ = slot_attrs(xml_text, "StompB1")
    assert g == C.NULL_GUID                                         # no longer used for post pedals


def test_tone_volume_and_cab_mic():
    xml_text, _ = C.build_preset("K", "Name", GEAR, volume=-14.0)
    amp = re.search(r'<AmpA [^>]*OutputVolume="([^"]+)"', xml_text).group(1)
    assert float(amp) == pytest.approx(10 ** (6 / 20), rel=1e-3)     # -14 dB vs -20 reference
    cab = re.search(r"<CabA\b.*?<Cab ([^>]*)/>", xml_text, re.S).group(1)
    assert 'Mic0Model="1e41acc4-85af-4e84-bee4-eabc0be5fef1"' in cab  # SM57 for a "_57_" cab
    assert 'Mic1Mute="1"' in cab
    assert 'Cab1_Mic2_Mute="1"' in xml_text


def test_noise_gate_is_first_and_configured():
    xml_text, _ = C.build_preset("K", "Name", GEAR, noise_gate=True)
    g, a = slot_attrs(xml_text, "StompA1")
    assert g == C.NOISE_GATE_GUID and float(a["Threshold"]) > 0
    g, _ = slot_attrs(xml_text, "StompA1", 1)
    assert TP.at5_name(g) == "Overdrive"


def test_free_mode_converts_without_error_and_uses_free_gear():
    xml_text, _ = C.build_preset("K", "Name", GEAR, free_mode=True)
    xml.dom.minidom.parseString(xml_text)
    for section in ("StompA1", "LoopFxA", "RackMaster"):
        g, _ = slot_attrs(xml_text, section)
        assert g in C.AT5_CS_EFFECT_GUIDS


def test_knobs_and_knobvalues_both_accepted():
    a, _ = C.build_preset("K", "N", {"PostPedal1": {"Key": "Pedal_NPNDelay", "Knobs": {"Pedal_NPNDelay_Time": 250}}})
    b, _ = C.build_preset("K", "N", {"PostPedal1": {"Key": "Pedal_NPNDelay",
                                                    "KnobValues": {"Pedal_NPNDelay_Time": 250}}})
    assert slot_attrs(a, "LoopFxA")[1]["Delay"] == slot_attrs(b, "LoopFxA")[1]["Delay"] == "250"


def test_rocksmith_plus_extra_pedal_slots_are_converted():
    gear = {f"PrePedal{i}": {"Key": "Pedal_CustomDrive"} for i in range(1, 5)}
    xml_text, _ = C.build_preset("K", "N", gear)
    assert sum(1 for i in range(4) if slot_attrs(xml_text, "StompA1", i)[0] != C.NULL_GUID) == 4


# ── RS2014 file parsing + CLI pass-through ───────────────────────────────────

def test_parse_real_manifest_layout(tmp_path):
    manifest = {"Entries": {"ABC": {"Attributes": {"Tones": [
        {"Key": "T1", "Name": "Tone 1", "Volume": -18.0,
         "GearList": {"Amp": {"Key": "Amp_TW22", "KnobValues": {"Amp_TW22_Gain": 30}}}}]}}}}
    f = tmp_path / "song_lead.json"
    f.write_text(json.dumps(manifest), encoding="utf-8")
    tones = C._parse_rs2014_json(f)
    assert [(t["key"], t["volume"]) for t in tones] == [("T1", -18.0)]


def test_rs2014_entry_points_pass_settings(tmp_path, monkeypatch):
    seen = {}

    def spy(*a, **kw):
        seen.update(kw)
        return []

    monkeypatch.setattr(C, "_convert_tone_from_gearlist", spy)
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"Key": "T", "GearList": {"Amp": {"Key": "Amp_TW22"}}}), encoding="utf-8")
    C.convert_tone_rs2014(f, tmp_path, free_mode=True, tier="se", noise_gate=True)
    assert seen["free_mode"] is True and seen["tier"] == "se" and seen["noise_gate"] is True


def test_empty_template_defaults_render():
    xml.dom.minidom.parseString(C.AT5P_TEMPLATE.format(**C.template_defaults()))
