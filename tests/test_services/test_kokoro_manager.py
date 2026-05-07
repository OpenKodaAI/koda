"""Tests for Kokoro asset root defaults."""

from __future__ import annotations

import importlib
import struct
import sys
import zipfile

import numpy as np


def test_kokoro_assets_default_to_state_root(monkeypatch, tmp_path):
    monkeypatch.delenv("CONTROL_PLANE_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("KOKORO_ASSET_ROOT", raising=False)
    monkeypatch.setenv("STATE_ROOT_DIR", str(tmp_path / "state"))

    sys.modules.pop("koda.services.kokoro_manager", None)
    module = importlib.import_module("koda.services.kokoro_manager")

    assert str(module._KOKORO_ROOT).startswith(str((tmp_path / "state").expanduser()))


def _write_minimal_torch_voice(path, values: list[float]) -> None:
    data_pickle = (
        b"\x80\x02"
        b"ctorch._utils\n_rebuild_tensor_v2\n"
        b"q\x00(("
        b"X\x07\x00\x00\x00storage"
        b"q\x01"
        b"ctorch\nFloatStorage\n"
        b"q\x02"
        b"X\x01\x00\x00\x000"
        b"q\x03"
        b"X\x03\x00\x00\x00cpu"
        b"q\x04"
        b"K\x06"
        b"tq\x05"
        b"Q"
        b"K\x00"
        b"K\x02K\x03\x86q\x06"
        b"K\x03K\x01\x86q\x07"
        b"\x89"
        b"ccollections\nOrderedDict\n"
        b"q\x08)Rq\x09"
        b"tq\x0a"
        b"Rq\x0b."
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("pf_test3/data.pkl", data_pickle)
        archive.writestr("pf_test3/byteorder", "little")
        archive.writestr("pf_test3/data/0", struct.pack("<6f", *values))
        archive.writestr("pf_test3/version", "3\n")


def test_rebuild_kokoro_voice_bank_without_torch(monkeypatch, tmp_path):
    from koda.services import kokoro_manager as module

    root = tmp_path / "kokoro"
    monkeypatch.setattr(module, "_KOKORO_ROOT", root)
    monkeypatch.setattr(module, "_KOKORO_MODEL_DIR", root / "model")
    monkeypatch.setattr(module, "_KOKORO_VOICES_DIR", root / "voices")
    monkeypatch.setattr(module, "_KOKORO_BANK_DIR", root / "voice_bank")
    monkeypatch.setattr(module, "_KOKORO_METADATA_PATH", root / "voices.json")
    monkeypatch.setattr(module, "_KOKORO_MODEL_PATH", root / "model" / "kokoro-v1.0.onnx")
    monkeypatch.setattr(module, "_KOKORO_VOICES_BANK_PATH", root / "voice_bank" / "voices-managed-v1.0.bin")
    monkeypatch.setitem(sys.modules, "torch", None)

    voice_path = module.kokoro_voice_file_path("pf_dora")
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    _write_minimal_torch_voice(voice_path, values)

    bank_path = module.rebuild_kokoro_voice_bank()

    with np.load(bank_path) as bank:
        np.testing.assert_array_equal(bank["pf_dora"], np.array(values, dtype=np.float32).reshape(2, 3))
