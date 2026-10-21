import base64
import plistlib

root = plistlib.load(open('research/ipsw-x/blkx.plist', 'rb'))


def gather(mish):
    """UDIF mish: count @0xc8, entries @0xcc: type(4) comment(4)
    sect_no(8) sect_cnt(8) comp_off(8) comp_len(8) = 40 bytes."""
    n = int.from_bytes(mish[0xc8:0xcc], 'big')
    chunks = []
    o = 0xcc
    for _ in range(n):
        et = int.from_bytes(mish[o:o + 4], 'big')
        comment = int.from_bytes(mish[o + 4:o + 8], 'big')
        sect_no = int.from_bytes(mish[o + 8:o + 16], 'big')
        sect_cnt = int.from_bytes(mish[o + 16:o + 24], 'big')
        coff = int.from_bytes(mish[o + 24:o + 32], 'big')
        clen = int.from_bytes(mish[o + 32:o + 40], 'big')
        chunks.append((et, comment, sect_no, sect_cnt, coff, clen))
        o += 40
    return n, chunks


TYPES = {0: 'raw', 1: 'zero', 2: 'uue', 0x80000004: 'zlib', 0x80000005: 'adc',
         0x80000006: 'bzip2', 0x80000007: 'lzfse', 0x80000008: 'lzma'}
for ent in root['resource-fork']['blkx']:
    mish = ent['Data']
    name = ent['Name']
    if mish[:4] != b'mish':
        print(name, 'no mish:', mish[:4])
        continue
    declared = int.from_bytes(mish[0x10:0x18], 'big')
    n, chunks = gather(mish)
    hist = {}
    secs = 0
    ok_order = True
    for et, comment, sect_no, sect_cnt, coff, clen in chunks:
        secs += sect_cnt
        k = TYPES.get(et, hex(et))
        hist[k] = hist.get(k, 0) + 1
    print(f'{name}: chunks={n} declared_sectors={declared} summed={secs} '
          f'{"ORDER-OK" if secs == declared else "SECTOR MISMATCH"} '
          f'outGB={secs * 512 / 1e9:.3f}')
    print('   types:', hist)
    if name == 'Apple_APFS' and chunks:
        c = chunks[0]
        print('   first chunk:', hex(c[0]), 'sect', c[2], '+', c[3],
              '@', hex(c[4]), '+', hex(c[5]))
