#!/usr/bin/env python3
"""
Minimal AOSP boot image v2 packer (a mkbootimg replacement; the WSL box has
no mkbootimg and Windows has no adb/fastboot tooling beyond platform-tools).

The merlin LK reads kernel_addr as an ABSOLUTE address (stock boot header:
0x40080000); ramdisk/tags/dtb addresses are LK hints - our shim reads the
initrd location from the live FDT's /chosen instead.

Usage:
  python tools/mkbootimg.py --kernel shim/out/Image --ramdisk payload.bin \
      --dtb research/merlin-boot/merlin.dtb --output shim-boot-merlin.img \
      --cmdline "console=null merlin.shim-1"
"""
import argparse
import hashlib
import struct


def pad(data: bytes, page: int) -> bytes:
    n = (len(data) + page - 1) // page * page
    return data + b"\0" * (n - len(data))


def parse_os_version(v: str) -> int:
    a, b, c = (int(x) for x in v.split("."))
    return (a << 25) | (b << 18) | (c << 11)


def parse_os_patch(v: str) -> int:
    y, m = v.split("-")
    return ((int(y) - 2000) << 4) | int(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--ramdisk", default=None)
    ap.add_argument("--second", default=None)
    ap.add_argument("--dtb", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--kernel_addr", type=lambda x: int(x, 0), default=0x40080000)
    ap.add_argument("--ramdisk_addr", type=lambda x: int(x, 0), default=0x41000000)
    ap.add_argument("--second_addr", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--tags_addr", type=lambda x: int(x, 0), default=0x40000100)
    ap.add_argument("--dtb_addr", type=lambda x: int(x, 0), default=0x41F00000)
    ap.add_argument("--page_size", type=int, default=4096)
    ap.add_argument("--cmdline", default="")
    ap.add_argument("--extra_cmdline", default="")
    ap.add_argument("--name", default="merlin-shim")
    ap.add_argument("--os_version", default="17.0.0")
    ap.add_argument("--os_patch_level", default="2035-06")
    a = ap.parse_args()

    kernel = open(a.kernel, "rb").read()
    ramdisk = open(a.ramdisk, "rb").read() if a.ramdisk else b""
    second = open(a.second, "rb").read() if a.second else b""
    dtb = open(a.dtb, "rb").read() if a.dtb else b""

    os_version = parse_os_version(a.os_version) | parse_os_patch(a.os_patch_level)

    hdr = struct.pack(
        "<8sIIIIIIIIII",
        b"ANDROID!",
        len(kernel), a.kernel_addr,
        len(ramdisk), a.ramdisk_addr,
        len(second), a.second_addr,
        a.tags_addr, a.page_size,
        2, os_version,               # header_version = 2
    )
    hdr += a.name.encode()[:16].ljust(16, b"\0")
    hdr += a.cmdline.encode()[:512].ljust(512, b"\0")
    hdr += b"\0" * 32                # id: raw sha1 digest, filled below
    hdr += a.extra_cmdline.encode()[:1024].ljust(1024, b"\0")
    hdr += struct.pack("<I", 0)      # recovery_dtbo_size (v1)
    hdr += struct.pack("<Q", 0)      # recovery_dtbo_offset
    hdr += struct.pack("<I", 1660)   # header_size (v1+)
    hdr += struct.pack("<I", len(dtb))    # dtb_size (v2)
    hdr += struct.pack("<Q", a.dtb_addr)  # dtb_addr
    assert len(hdr) == 1660, len(hdr)

    img = bytearray(pad(hdr, a.page_size) + pad(kernel, a.page_size))
    if ramdisk:
        img += pad(ramdisk, a.page_size)
    if second:
        img += pad(second, a.page_size)
    if dtb:
        img += pad(dtb, a.page_size)

    # id = sha1 over the unpadded sections, in AOSP order (kernel, ramdisk,
    # second, recovery_dtbo, dtb); stored as the RAW 20-byte digest (not hex).
    h = hashlib.sha1()
    for part in (kernel, ramdisk, second, dtb):
        if part:
            h.update(part)
    # id[8] (32 bytes @576): the RAW 20-byte digest, zero-padded.
    img[0x240:0x260] = h.digest() + b"\0" * 12

    open(a.output, "wb").write(bytes(img))
    print(f"{a.output}: {len(img)} bytes (kernel {len(kernel)}, "
          f"ramdisk {len(ramdisk)}, dtb {len(dtb)}, page {a.page_size})")


main()
