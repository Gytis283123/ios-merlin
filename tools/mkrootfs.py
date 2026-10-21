#!/usr/bin/env python3
"""mkrootfs.py: pull the OS filesystem DMG out of an iPhone restore IPSW.

iOS 16.7.16 (build 20H392, iPhone10,3/iPhone10,6) is the rootfs base for the
merlin port: our kernel is xnu-8796 (Darwin 22.6), matching that userland.
The restore IPSW is an ordinary zip; the system rootfs is its largest ".dmg"
member (a LZFSE-compressed UDIF image, unencrypted for iPhone restores).

Usage:
    python tools/mkrootfs.py IPW_PATH           # show manifest + dmg info
    python tools/mkrootfs.py IPW_PATH OUT_DIR   # extract to artifacts
"""
import os
import plistlib
import struct
import sys
import zipfile

UDIF_KOLY = b'koly'


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    ipsw = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.isfile(ipsw) and outdir is None:
        # Still downloading / partial: list what we can from the head
        # (local file headers), then bail out politely.
        print(f'{ipsw} not found or still partial (no OUT_DIR: info-only)')
        return

    zf = zipfile.ZipFile(ipsw) if os.path.isfile(ipsw) else None
    if zf is None:
        raise SystemExit(f'{ipsw}: not readable yet')

    dmgs = [(i.file_size, i.filename) for i in zf.infolist()
            if i.filename.endswith('.dmg')]
    dmgs.sort(reverse=True)
    total_dmg = sum(s for s, _ in dmgs)
    print(f'{ipsw}: {len(zf.infolist())} members; {len(dmgs)} dmg(s), '
          f'{total_dmg / 1e9:.2f} GB total')
    for s, n in dmgs:
        print(f'  {n}: {s / 1e9:.3f} GB')

    # BuildManifest: device identity + build + exact image names.
    bys = {}
    for n in ('BuildManifest.plist', 'Restore.plist'):
        try:
            bys[n] = zf.read(n)
        except KeyError:
            pass
    for n, b in bys.items():
        if b[:2] == b'\xff\xfe':		# Apple quirk: UTF-16 content
            b = b.decode('utf-16').encode('utf-8')
        e = b.find(b'</plist>')
        if e != -1:
            b = b[:e + 8]
        try:
            p = plistlib.loads(b)
        except Exception as ex:
            print(f'{n}: not parsed ({ex})')
            continue
        prod = p.get('ProductType') or p.get('DeviceClass')
        print(f'\n{n}: build {p.get("ProductBuildVersion")} '
              f'{prod} buildId={p.get("ProductVersion")}')
        for pers in p.get('BuildIdentities') or []:
            comp = {k: v.get('Info', {}).get('Path')
                    for k, v in pers.get('Manifest', {}).items()}
            fs = comp.get('OS', '')
            if fs:
                print(f'  OS identity: {fs} '
                      f'(class {pers.get("Info", {}).get("LatestBuildType")})')

    if not outdir:
        print('\n(no OUT_DIR: not extracting)')
        return

    big = dmgs[0][1]
    dest = os.path.join(outdir, os.path.basename(big))
    os.makedirs(outdir, exist_ok=True)
    print(f'\nextracting {big} -> {dest}')
    with zf.open(big) as src, open(dest, 'wb') as dst:
        copied = 0
        while True:
            chunk = src.read(64 << 20)
            if not chunk:
                break
            copied += len(chunk)
            dst.write(chunk)
            print(f'  {copied / 1e9:.2f} GB', flush=True)
    with open(dest, 'rb') as f:
        head = f.read(512)
        print('dmg head:', head[:32].hex())
        magic = head[:4]
        if magic == b'koly':
            blkx_ofs, blkx_len = struct.unpack_from('>qq', head, 0x22c)
            print(f'koly: block tables at {hex(blkx_ofs)}+{hex(blkx_len)}')
        else:
            f.seek(-512, 2)
            koly = f.read(512)
            print('dmg tail koly?', koly[:4])
    print(f'done: {os.path.getsize(dest) / 1e9:.3f} GB')


main()
