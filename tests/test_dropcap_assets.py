from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

import cli
from engine.dropcap_assets import analyze_dropcap_alpha_bounds


def _chunk(kind: bytes, payload: bytes) -> bytes:
    import binascii

    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def _write_rgba_png(path: Path, width: int, height: int, alpha_points: set[tuple[int, int]]) -> None:
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            alpha = 255 if (x, y) in alpha_points else 0
            row.extend([10, 20, 30, alpha])
        rows.append(bytes(row))
    payload = b"".join(rows)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(payload))
        + _chunk(b"IEND", b"")
    )


def test_analyze_dropcap_alpha_bounds_reports_transparent_margins(tmp_path):
    png = tmp_path / "dropcap.png"
    _write_rgba_png(png, 5, 4, {(1, 1), (2, 1), (1, 2), (2, 2)})

    report = analyze_dropcap_alpha_bounds(png)

    assert report["status"] == "ok"
    assert report["width_px"] == 5
    assert report["height_px"] == 4
    assert report["alpha_bbox_px"] == {"left": 1, "top": 1, "right": 2, "bottom": 2}
    assert report["visible_width_px"] == 2
    assert report["visible_height_px"] == 2
    assert report["transparent_margins_px"] == {"left": 1, "right": 2, "top": 1, "bottom": 1}
    assert report["recommended_crop_box_px"] == "1,1,3,3"
    assert report["needs_crop_attention"] is True


def test_cli_initial_inspect_reports_dropcap_crop_diagnostics(tmp_path, monkeypatch, capsys):
    png = tmp_path / "dropcap.png"
    _write_rgba_png(png, 3, 3, {(1, 1)})
    monkeypatch.setattr(sys, "argv", ["foundry", "initial", "inspect", str(png)])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["recommended_crop_box_px"] == "1,1,2,2"


def test_cli_initial_recipes_lists_named_tuning_recipes(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["foundry", "initial", "recipes"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert "codex0_a5_default" in payload["recipes"]
    assert payload["recipes"]["codex0_a5_default"]["width"] == ".72in"
