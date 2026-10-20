#!/usr/bin/env python3
"""zipremote.py: list and fetch members of a remote zip via HTTP Range.

Lets us enumerate an IPSW on Apple's CDN (which serves 206 Partial Content)
without owning the whole file - used to pre-verify the rootfs pipeline while
the full download runs elsewhere.

    python zipremote.py URL                 # list members (EOCD/ZIP64)
    python zipremote.py URL BuildManifest.plist  # print that member
"""
import struct
import sys
import urllib.request


class RemoteZip:
    def __init__(self, url):
        self.url = url
        r = urllib.request.Request(self.url, headers={'Range': 'bytes=0-0'})
        with urllib.request.urlopen(r, timeout=30) as f:
            cr = f.headers.get('Content-Range')
        if cr is None:
            raise SystemExit('no Content-Range: server lacks Range support')
        self.size = int(cr.split('/')[-1])

    @staticmethod
    def _fetch(start, length):
        r = urllib.request.Request(
            __import__('sys').argv[1] if False else RemoteZip._url,
            headers={'Range': f'bytes={start}-{start + length - 1}'})
        with urllib.request.urlopen(r, timeout=60) as f:
            if f.getcode() != 206:
                raise SystemExit(f'HTTP {f.getcode()}, expected 206')
            return f.read(length)

    def members(self):
        """Parse EOCD (+ZIP64): [(name, data_offset, csize, method)]."""
        tail = self._fetch(self.size - 65536, 65536)
        pos = tail.rfind(b'PK\x05\x06')		# classic EOCD
        if pos < 0:
            raise SystemExit('no EOCD in tail 64K')
        n_tot, cd_size, cd_ofs = struct.unpack_from('<H', tail, pos + 10)[0], \
            struct.unpack_from('<I', tail, pos + 12)[0], \
            struct.unpack_from('<I', tail, pos + 16)[0]
        loc = tail.rfind(b'PK\x06\x07')		# ZIP64 EOCD locator
        if loc >= 0 and (cd_ofs == 0xFFFFFFFF or cd_size == 0xFFFFFFFF
                         or n_tot == 0xFFFF):
            lof = struct.unpack_from('<Q', tail, loc + 8)[0]
            rec = self._fetch(lof, 56)
            n_tot, cd_size, cd_ofs = struct.unpack_from('<QQQ', rec, 32)
            print(f'ZIP64: entries={n_tot} cd@{cd_ofs:#x}+{cd_size:#x}')
        out = []
        cd = self._fetch(cd_ofs, cd_size)	# one call for the whole table
        p = 0
        while p + 46 <= len(cd):
            if cd[p:p + 4] != b'PK\x01\x02':
                break
            sig, vm, vn, flags, mth, mt, md, crc, csz, usz, nlen, elen, \
                clen_, dsk, iat, eat, lho = struct.unpack_from(
                    '<IHHHHHHIIIHHHHHII', cd, p)
            p += 46
            name = cd[p:p + nlen].decode('utf-8', 'replace')
            extra = cd[p + nlen:p + nlen + elen]
            p += nlen + elen + clen_
            x = 0
            while x + 4 <= len(extra):
                idx, sz = struct.unpack_from('<HH', extra, x)
                if idx == 1 and sz:
                    v = struct.unpack_from(f'<{sz // 8}Q', extra, x + 4)
                    if len(v) > 0 and usz == 0xFFFFFFFF:
                        usz = v[0]
                    if len(v) > 1 and csz == 0xFFFFFFFF:
                        csz = v[1]
                    if len(v) > 2 and lho == 0xFFFFFFFF:
                        lho = v[2]
                x += 4 + sz
            if flags & 8:			# data descriptor: sizes unknown
                csz = None
            out.append((name, lho, csz, mth))
        return out

    def data_offset(self, lho):
        """True data offset from the member's own local header."""
        lf = self._fetch(lho, 30)
        if lf[:4] != b'PK\x03\x04':
            raise SystemExit(f'local header magic wrong at {lho:#x}')
        nl, xl = struct.unpack_from('<HH', lf, 26)
        return lho + 30 + nl + xl


def main():
    url = sys.argv[1]
    want = sys.argv[2] if len(sys.argv) > 2 else None
    RemoteZip._url = url
    z = RemoteZip(url)
    print(f'total size: {z.size / 1e9:.3f} GB')
    ms = z.members()
    print(f'{len(ms)} members (csize==None = streamed, size in local dd)')
    for name, dof, csz, mth in sorted(ms, key=lambda m: -(m[2] or 0))[:12]:
        print(f'  {(csz or 0) / 1e9:8.3f} GB  {name}  (method {mth})')
    if want:
        for name, lho, csz, mth in ms:
            if name == want:
                dof = z.data_offset(lho)
                print(f'\n--- fetching {name} ({csz} B) data@{dof:#x} ---')
                data = RemoteZip._fetch(dof, csz)
                if mth == 8:
                    import zlib
                    d = zlib.decompressobj(-15)
                    first = d.decompress(data)
                    first += d.flush()
                    data = first	# some Apple members pack extra streams
                sys.stdout.buffer.write(data)
                return
        print(f'{want}: not in archive')


main()
