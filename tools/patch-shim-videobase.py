#!/usr/bin/env python3
"""Patch the shim's boot_args Video base (loader.c FB_BASE) in a merlin
boot image, leaving the shim's own console framebuffer alone.

Why not just patch the FB_BASE literal: FB_BASE appears twice in the shim
binary.  The 8-byte literal at .data+0x4c48 is con_fb (the shim's early
console); moving it out of the mapped FB window resets the phone before the
loader prints anything.  The address the *loader* stores into
ba->Video.v_baseAddr is materialised as

    mov  w9, #0x5438
    movk w9, #0x7e60, lsl 16

in the boot_args builder (shim file offset 0x3860 in the fb270 build), found
here by its exact 8-byte encoding.  Patching that pair moves the iOS boot UI
(IOMobileFramebuffer, xnu patch 0046) without touching the early console.

The ADT `sweet-fbcon` reg (<base, 0x9a3f80> = base, 2340*4320) is what the
kernel text console maps; --adt-base moves it too (payload+0xfdbc48 in the
0098 images).  Image parts are laid out sequentially after the header page:
header, kernel (gzip shim + appended FDT), ramdisk (payload/ADT), dtb.  The
header's recovery_dtbo_offset is 0 in these images and must not be used as an
offset (doing so silently produced a broken ramdisk once).

  patch-shim-videobase.py IN OUT --dy ROWS [--dx PX] [--old-base HEX]
                         [--base HEX] [--adt-base HEX]

Prints the new base and sha256 of the result, then round-trips the image
through tools/unpack_bootv2.py.
"""
import argparse
import gzip
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRIDE = 4320
HEIGHT = 2340
# 0x7e605438 comes from an older FB_BASE and matches only the deployed
# in-flight image lineage (E1, repacked through 0105, see NOTES.md); shims
# freshly built from shim/console.h encode 0x7e605000 - pass
# --old-base 0x7e605000 for those (the assert below expects exactly 1 hit).
DEFAULT_OLD = 0x7E605438
ADT_SIZE = STRIDE * HEIGHT          # 0x9a3f80


def align(n, p):
    return (n + p - 1) // p * p


def movz_w9(imm):
    return 0x52800000 | ((imm & 0xFFFF) << 5) | 9


def movk_w9(imm):
    return 0x72A00000 | ((imm & 0xFFFF) << 5) | 9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--dy", type=int, default=0)
    ap.add_argument("--dx", type=int, default=0)
    ap.add_argument("--old-base", type=lambda s: int(s, 0), default=DEFAULT_OLD)
    ap.add_argument("--base", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--adt-base", type=lambda s: int(s, 0), default=None,
                    help="also move the ADT sweet-fbcon reg base (kernel fbcon)")
    a = ap.parse_args()

    new_base = a.base if a.base is not None else \
        a.old_base + a.dy * STRIDE + a.dx * 4
    if new_base == a.old_base:
        raise SystemExit("no change requested")
    if not 0 <= new_base <= 0xFFFFFFFF:
        raise SystemExit("base must fit in 32 bits (mov w9)")

    img = bytearray(Path(a.src).read_bytes())
    ks, ka, rs, ra, ss, sa, ta, ps, ver, osv = struct.unpack_from("<10I", img, 8)
    rds, rdo, hs = struct.unpack_from("<IQI", img, 1632)
    ds, da = struct.unpack_from("<IQ", img, 1648)
    assert ver == 2 and ps == 2048 and rds == 0, (ver, ps, rds)
    roff = ps + align(ks, ps)
    doff = roff + align(rs, ps)

    slot = bytes(img[ps:ps + ks])
    fdt = slot.find(b"\xd0\x0d\xfe\xed")
    assert fdt > 0, "no appended FDT in the kernel slot"
    gz, adtb = slot[:fdt], slot[fdt:]
    shim = bytearray(gzip.decompress(gz))

    old = struct.pack("<II", movz_w9(a.old_base & 0xFFFF),
                      movk_w9(a.old_base >> 16))
    hits = [i for i in range(len(shim) - 7) if shim[i:i + 8] == old]
    assert len(hits) == 1, f"expected 1 boot_args base pair, found {len(hits)}"
    at = hits[0]
    shim[at:at + 8] = struct.pack("<II", movz_w9(new_base & 0xFFFF),
                                  movk_w9(new_base >> 16))
    gz2 = gzip.compress(bytes(shim), 9, mtime=0)

    payload = bytearray(img[roff:roff + rs])
    dtb = bytes(img[doff:doff + ds])
    assert ds and len(payload) == rs and len(dtb) == ds
    assert payload[:4] != b"ANDROID!", "ramdisk slice looks like the header"

    if a.adt_base is not None:
        reg = struct.pack("<QQ", a.old_base, ADT_SIZE)
        hits = [i for i in range(len(payload) - 15) if payload[i:i + 16] == reg]
        assert len(hits) == 1, f"expected 1 ADT sweet-fbcon reg, found {len(hits)}"
        struct.pack_into("<Q", payload, hits[0], a.adt_base)
        print(f"ADT sweet-fbcon reg base {a.old_base:#x} -> {a.adt_base:#x} "
              f"at payload+{hits[0]:#x}")

    new_slot = gz2 + adtb
    ks2 = len(new_slot)
    out = bytearray(img[:ps])
    struct.pack_into("<I", out, 8, ks2)
    out += new_slot + b"\0" * (align(ks2, ps) - ks2)
    struct.pack_into("<I", out, 16, len(payload))
    out += payload
    out += b"\0" * (align(len(payload), ps) - len(payload))
    struct.pack_into("<IQI", out, 1632, 0, 0, hs)
    struct.pack_into("<IQ", out, 1648, len(dtb), da)
    out += dtb
    Path(a.out).write_bytes(bytes(out))
    print(f"boot_args Video base {a.old_base:#x} -> {new_base:#x} "
          f"(dy {a.dy:+d} rows, dx {a.dx:+d} px)")
    print(f"patched movz/movk at shim+{at:#x}; gzip {len(gz)} -> {len(gz2)} B")
    print(f"image {a.out}: {len(out)} bytes, sha256 "
          f"{hashlib.sha256(bytes(out)).hexdigest().upper()}")

    tmp = ROOT / "research" / "tmp-msdc-split" / "verify-shim"
    subprocess.run([sys.executable, str(ROOT / "tools" / "unpack_bootv2.py"),
                    a.out, str(tmp)], check=True, stdout=subprocess.DEVNULL)
    k = (tmp / "kernel").read_bytes()
    assert k[:2] == b"\x1f\x8b", k[:4]
    assert gzip.decompress(k[:len(gz2)]) == bytes(shim)
    assert (tmp / "ramdisk").read_bytes() == bytes(payload)
    assert (tmp / "dtb").read_bytes() == dtb
    print("verify: shim.gz + payload + dtb round-trip OK")


if __name__ == "__main__":
    main()
