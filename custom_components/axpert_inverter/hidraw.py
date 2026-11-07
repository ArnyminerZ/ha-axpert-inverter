"""hidraw transport for Axpert/Voltronic inverters.

The kernel's usbhid driver stays bound to the device and exposes it as
/dev/hidrawN, so no libusb, interface claiming or driver detaching is needed.
"""
from __future__ import annotations

import logging
import os
import select
import time
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

AXPERT_VID = 0x0665
AXPERT_PID = 0x5161

SYSFS_HIDRAW = Path("/sys/class/hidraw")


@dataclass(frozen=True)
class HidrawDevice:
    """A hidraw node found in sysfs."""

    path: str  # /dev/hidrawN
    vid: int
    pid: int
    name: str
    phys: str  # e.g. usb-3f980000.usb-1.2/input0; stable across renumbering

    @property
    def label(self) -> str:
        return f"{self.path} - {self.name or 'HID device'}" + (f" ({self.phys})" if self.phys else "")


def _parse_uevent(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()
    return values


def find_hidraw_devices(
    vid: int | None = AXPERT_VID,
    pid: int | None = AXPERT_PID,
    sys_root: Path = SYSFS_HIDRAW,
) -> list[HidrawDevice]:
    """List hidraw devices, optionally filtered by USB vendor/product ID (blocking)."""
    devices: list[HidrawDevice] = []
    try:
        nodes = sorted(sys_root.iterdir())
    except OSError:
        return devices

    for node in nodes:
        try:
            info = _parse_uevent((node / "device" / "uevent").read_text())
            # HID_ID=<bus>:<vid>:<pid>, hex, zero padded
            _bus, dev_vid, dev_pid = info["HID_ID"].split(":")
            dev_vid, dev_pid = int(dev_vid, 16), int(dev_pid, 16)
        except (OSError, KeyError, ValueError):
            continue

        if (vid is not None and dev_vid != vid) or (pid is not None and dev_pid != pid):
            continue

        devices.append(
            HidrawDevice(
                path=f"/dev/{node.name}",
                vid=dev_vid,
                pid=dev_pid,
                name=info.get("HID_NAME", ""),
                phys=info.get("HID_PHYS", ""),
            )
        )
    return devices


def reattach_kernel_driver(vid: int = AXPERT_VID, pid: int = AXPERT_PID) -> bool:
    """Best effort: give the device back to usbhid after the legacy pyusb backend detached it."""
    try:
        import usb.core  # noqa: PLC0415 - optional, only used by the legacy backend

        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if dev is None:
            return False
        if not dev.is_kernel_driver_active(0):
            dev.attach_kernel_driver(0)
            _LOGGER.info("Re-attached kernel HID driver to %04x:%04x", vid, pid)
            return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not re-attach kernel driver: %s", err)
    return False


def discover_hidraw_devices() -> list[HidrawDevice]:
    """List inverters, recovering a node the legacy pyusb backend had detached (blocking)."""
    devices = find_hidraw_devices()
    if not devices and reattach_kernel_driver():
        time.sleep(1.5)  # let udev create the node
        devices = find_hidraw_devices()
    return devices


def resolve_hidraw_path(path: str | None, phys: str | None = None) -> str:
    """Find the current /dev/hidrawN for a configured device (blocking).

    Prefers the stable physical USB path, then the configured path, and finally
    tries to recover a node that disappeared because the legacy backend had
    detached the kernel driver.
    """
    for attempt in range(2):
        devices = find_hidraw_devices()
        if phys:
            for dev in devices:
                if dev.phys == phys:
                    return dev.path
        if path and os.path.exists(path):
            return path
        if attempt == 0 and reattach_kernel_driver():
            time.sleep(1.5)  # let udev create the node
            continue
        break

    if len(devices) == 1 and not phys:
        return devices[0].path
    raise FileNotFoundError(
        f"No hidraw device found for {path or phys}. Unplug and replug the inverter's USB cable, "
        "or reboot the host if it was previously used with the USB (pyusb) backend."
    )


class HidrawConnection:
    """Context manager with the same interface as USBConnection."""

    def __init__(self, path: str, timeout: int = 5000):
        self.path = path
        self.timeout = timeout
        self._fd: int | None = None

    def __enter__(self):
        self._fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    def write(self, data: bytes):
        for offset in range(0, len(data), 8):
            os.write(self._fd, data[offset : offset + 8])
            time.sleep(0.01)

    def read_until(self, terminator: bytes = b"\r") -> bytes:
        """Read until the terminator, dropping the zero padding hidraw adds to 8-byte reports."""
        buf = b""
        end = time.monotonic() + self.timeout / 1000.0
        while time.monotonic() < end:
            if not select.select([self._fd], [], [], 0.2)[0]:
                continue
            buf += os.read(self._fd, 64)
            idx = buf.find(terminator)
            if idx != -1:
                return buf[: idx + len(terminator)]
        return buf

    def reset_input_buffer(self):
        """Drain stale reports left over from a previous exchange."""
        while self._fd is not None and select.select([self._fd], [], [], 0)[0]:
            if not os.read(self._fd, 64):
                break

    def reset_output_buffer(self):
        pass
