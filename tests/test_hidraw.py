"""Tests for the hidraw transport (no Home Assistant needed)."""
import importlib.util
import os
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "axpert_inverter"
spec = importlib.util.spec_from_file_location("hidraw", PKG / "hidraw.py")
hidraw = importlib.util.module_from_spec(spec)
sys.modules["hidraw"] = hidraw
spec.loader.exec_module(hidraw)


def _node(root, name, hid_id, phys="usb-3f980000.usb-1.2/input0", hid_name="HID 0665:5161"):
    d = root / name / "device"
    d.mkdir(parents=True)
    (d / "uevent").write_text(
        f"DRIVER=hid-generic\nHID_ID={hid_id}\nHID_NAME={hid_name}\nHID_PHYS={phys}\nHID_UNIQ=\n"
    )


def test_finds_only_matching_devices(tmp_path):
    _node(tmp_path, "hidraw0", "0003:00000665:00005161")
    _node(tmp_path, "hidraw1", "0003:0000046D:0000C52B", hid_name="Mouse")
    devices = hidraw.find_hidraw_devices(sys_root=tmp_path)
    assert [(d.path, d.phys) for d in devices] == [("/dev/hidraw0", "usb-3f980000.usb-1.2/input0")]
    assert "/dev/hidraw0" in devices[0].label


def test_unfiltered_lists_everything(tmp_path):
    _node(tmp_path, "hidraw0", "0003:00000665:00005161")
    _node(tmp_path, "hidraw1", "0003:0000046D:0000C52B")
    assert len(hidraw.find_hidraw_devices(None, None, sys_root=tmp_path)) == 2


def test_missing_or_broken_sysfs(tmp_path):
    assert hidraw.find_hidraw_devices(sys_root=tmp_path / "nope") == []
    (tmp_path / "hidraw0").mkdir()  # no device/uevent
    _node(tmp_path, "hidraw1", "garbage")
    assert hidraw.find_hidraw_devices(sys_root=tmp_path) == []


def test_read_until_drops_zero_padding():
    r, w = os.pipe()
    conn = hidraw.HidrawConnection("unused", timeout=1000)
    conn._fd = r
    # 18-byte frame delivered as three 8-byte reports, zero padded
    os.write(w, b"(9293200")
    os.write(w, b"7105447\xe7")
    os.write(w, b"\x01")
    os.write(w, b"\r\x00\x00\x00\x00\x00\x00\x00")
    out = conn.read_until(b"\r")
    assert out.endswith(b"\r") and b"\x00" not in out
    os.close(r)
    os.close(w)


def test_read_until_times_out_with_partial_data():
    r, w = os.pipe()
    conn = hidraw.HidrawConnection("unused", timeout=300)
    conn._fd = r
    os.write(w, b"(abc")
    assert conn.read_until(b"\r") == b"(abc"
    os.close(r)
    os.close(w)


def test_reset_input_buffer_drains():
    r, w = os.pipe()
    conn = hidraw.HidrawConnection("unused", timeout=300)
    conn._fd = r
    os.write(w, b"stale\r")
    conn.reset_input_buffer()
    assert conn.read_until(b"\r") == b""  # nothing left after draining
    os.close(r)
    os.close(w)


def test_resolve_by_phys_after_renumbering(tmp_path, monkeypatch):
    _node(tmp_path, "hidraw3", "0003:00000665:00005161")
    real = hidraw.find_hidraw_devices
    monkeypatch.setattr(hidraw, "find_hidraw_devices", lambda: real(sys_root=tmp_path))
    assert hidraw.resolve_hidraw_path("/dev/hidraw0", "usb-3f980000.usb-1.2/input0") == "/dev/hidraw3"


def test_resolve_raises_when_nothing_found(tmp_path, monkeypatch):
    real = hidraw.find_hidraw_devices
    monkeypatch.setattr(hidraw, "find_hidraw_devices", lambda: real(sys_root=tmp_path))
    monkeypatch.setattr(hidraw, "reattach_kernel_driver", lambda *a: False)
    try:
        hidraw.resolve_hidraw_path("/dev/does-not-exist", None)
    except FileNotFoundError as err:
        assert "replug" in str(err)
    else:
        raise AssertionError("expected FileNotFoundError")
