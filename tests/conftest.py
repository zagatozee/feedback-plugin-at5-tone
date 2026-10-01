"""Load routes.py as feedBack would — fresh module, FastAPI app, plugin context — per test."""
import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def _load_routes(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "routes.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def at5_dir(tmp_path):
    """A fake 'Documents/IK Multimedia/AmpliTube 5' folder."""
    d = tmp_path / "IK Multimedia" / "AmpliTube 5"
    (d / "Presets").mkdir(parents=True)
    return d


@pytest.fixture
def dlc_dir(tmp_path):
    d = tmp_path / "library"
    d.mkdir()
    return d


@pytest.fixture
def config_dir(tmp_path):
    d = tmp_path / "config"
    d.mkdir()
    return d


@pytest.fixture
def make_plugin(monkeypatch, config_dir, dlc_dir):
    """make_plugin(at5_docs=<path or None>) -> (module, TestClient).
    None means no AT5 folder anywhere (no env, no Docker mount, nothing detected)."""
    counter = {"n": 0}

    def _make(at5_docs=None):
        counter["n"] += 1
        mod = _load_routes(f"at5_routes_under_test_{counter['n']}")
        if at5_docs is None:
            monkeypatch.delenv("AT5_DOCS_DIR", raising=False)
        else:
            monkeypatch.setenv("AT5_DOCS_DIR", str(at5_docs))
        monkeypatch.setattr(mod, "_detect_at5_presets_path", lambda: None)
        app = FastAPI()
        context = {
            "config_dir": config_dir,
            "get_dlc_dir": lambda: dlc_dir,
            "log": logging.getLogger("test.at5_tone"),
            # no load_sibling → routes falls back to importlib for cdlc_to_at5
        }
        mod.setup(app, context)
        return mod, TestClient(app)

    return _make


def write_feedpak_dir(dlc_dir, name="song.feedpak", tone_key="Clean_Tone"):
    """A directory-form feedpak whose arrangement carries a legacy GearList tone."""
    pak = dlc_dir / name
    (pak / "arrangements").mkdir(parents=True)
    (pak / "manifest.yaml").write_text("title: Test\nartist: Test\n", encoding="utf-8")
    arr = {
        "name": "Lead",
        "tones": {
            "base": tone_key,
            "definitions": [{
                "name": tone_key, "id": tone_key,
                "gear": {
                    "Amp": {"Key": "Amp_TW22", "KnobValues": {"Amp_TW22_Gain": 40.0}},
                    "Cabinet": {"Key": "Cab_Marshall1960A", "KnobValues": {}},
                },
            }],
        },
    }
    (pak / "arrangements" / "lead.json").write_text(json.dumps(arr), encoding="utf-8")
    return pak
