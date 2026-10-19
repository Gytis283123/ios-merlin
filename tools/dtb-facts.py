#!/usr/bin/env python3
"""Dump the interesting facts from a stock DTB (memory, reserved-memory,
chosen, cpus, timers, gic) so the MERLIN ADT constants come from the
device's own firmware files, not guesses.

  dtb-facts.py BOOT.dtb [--all]

Flattened device tree walk only: no libfdt dependency. Sources that produced
the constants in tools/mkadt.py: D:/things/Merlin/merlin_extracted.dtb (stock
boot.img v2 DTB) and the dts/ sources under android_kernel_xiaomi_mt6768.
"""
import struct, sys

FDT_BEGIN_NODE, FDT_END_NODE = 1, 2
FDT_PROP, FDT_NOP, FDT_END = 3, 4, 9

pad4 = lambda x: (x + 3) & ~3


def strlike(v):
    return v and v[-1] == 0 and all(32 <= b < 127 or b == 0 for b in v)


def hx(v):
    if v and len(v) % 4 == 0:
        return ' '.join(f'{c:#x}' for c in struct.unpack(f'>{len(v) // 4}I', v))
    return v.hex() + (f' ({len(v)}B)' if v else ' (empty)')


def strval(v):
    parts = v.rstrip(b'\0').split(b'\0')
    s = '|'.join(p.decode(errors='replace') for p in parts)
    return '"' + (s[:150] + ('...' if len(s) > 150 else '')) + '"'


def be_reg(v, ac, sc):
    """reg -> [(pa, sz)] using the parent's #address/#size-cells."""
    out, off, step = [], 0, (ac + sc) * 4
    while off + step <= len(v):
        c = struct.unpack_from(f'>{ac + sc}I', v, off)
        pa = 0
        for i in range(ac):
            pa = (pa << 32) | c[i]
        sz = 0
        for i in range(sc):
            sz = (sz << 32) | c[ac + i]
        out.append((pa, sz))
        off += step
    return out


def parse(path, dump_all):
    blob = open(path, 'rb').read()
    magic_, totalsize, off_struct, off_strings, off_rsv, version, *_ = \
        struct.unpack_from('>10I', blob, 0)
    assert magic_ == 0xd00dfeed, f'not a DTB (magic {magic_:#x})'
    print(f'{path}: {totalsize} bytes, FDT v{version}')

    off = off_rsv
    while True:
        pa, sz = struct.unpack_from('>QQ', blob, off)
        if pa == 0 and sz == 0:
            break
        print(f'/memreserve: {pa:#012x}..{pa + sz - 1:#012x} (size {sz:#x})')
        off += 16
    if off == off_rsv:
        print('/memreserve: empty (lk puts carve-outs in /reserved-memory)')

    stack = []  # [(name, path, props, ac, sc)]
    off = off_struct
    while True:
        tag, = struct.unpack_from('>I', blob, off)
        if tag == FDT_BEGIN_NODE:
            end = blob.index(b'\0', off + 4)
            name = blob[off + 4:end].decode()
            parent = stack[-1][1] if stack else ''
            pathstr = ('/' if not parent else parent.rstrip('/') + '/') + name
            stack.append([name, pathstr, {}, None, None])
            off = pad4(end + 1)
        elif tag == FDT_END_NODE:
            off += 4
            name, pathstr, props, ac, sc = stack.pop()
            parent = stack[-1] if stack else None
            pac, psc = (parent[3], parent[4]) if parent else (2, 2)
            pac = pac if pac is not None else 2
            psc = psc if psc is not None else 2
            keep = dump_all or pathstr in ('/', '/memory', '/chosen', '/cpus', '/psci') \
                or pathstr.startswith('/reserved-memory/') \
                or 'timer' in name or 'gic' in name or ('intpol' in pathstr) \
                or (parent and parent[1] == '/cpus')
            if keep:
                emit(pathstr, props, pac, psc)
            continue
        elif tag == FDT_PROP:
            rlen, nameoff = struct.unpack_from('>II', blob, off + 4)
            kname = blob[off_strings + nameoff:].split(b'\0')[0].decode()
            stack[-1][2][kname] = blob[off + 12:off + 12 + rlen]
            if kname == '#address-cells':
                stack[-1][3] = int.from_bytes(blob[off + 12:off + 16], 'big')
            elif kname == '#size-cells':
                stack[-1][4] = int.from_bytes(blob[off + 12:off + 16], 'big')
            off = pad4(off + 12 + rlen)
            continue
        elif tag == FDT_NOP:
            off += 4
        elif tag == FDT_END:
            break
        else:
            print(f'?? unknown FDT tag {tag:#x} at {off:#x}')
            break


def emit(pathstr, props, ac, sc):
    print(f'\n[{pathstr}]')
    for k, v in props.items():
        if k in ('phandle', 'linux,phandle', 'AAPL,phandle'):
            continue
        if k == 'reg':
            pairs = be_reg(v, ac, sc)
            if pairs and len(pairs) * (ac + sc) * 4 == len(v):
                print('  reg = ' + '  '.join(f'{pa:#x} sz={sz:#x}' for pa, sz in pairs))
            else:
                print(f'  reg = <{hx(v)}>')	# non-(ac,sc)-shaped reg: print raw cells
        elif strlike(v):
            print(f'  {k} = {strval(v)}')
        else:
            print(f'  {k} = <{hx(v)}>')


if __name__ == '__main__':
    parse(sys.argv[1], '--all' in sys.argv[2:])
