#!/bin/bash
# Build the shim for QEMU virt (-DSHIM_QEMU: no MTK MMIO pokes).
#
#   bash build-qemu.sh                       # QEMU twin plane 0x9c000000
#   FB=0x7e605000 FB_H=2340 OUT=out-qemu-phone bash build-qemu.sh
#                                            # phone splash plane/geometry
#
# The FB override matters for the phone payload: the ADT's sweet-fbcon
# node is 0x7e605000/1080x2340, and boot_args.Video comes from these
# constants, so both have to agree for a faithful phone-on-QEMU run.
set -euo pipefail
cd "$(dirname "$0")"
CC="clang --target=aarch64-linux-gnu -ffreestanding -fno-pic -fno-stack-protector -fno-builtin -mno-red-zone"
CFLAGS="-O2 -Wall -Wextra -mgeneral-regs-only -mstrict-align -DMERLIN -DSHIM_QEMU"
[ -n "${FB:-}" ] && CFLAGS="$CFLAGS -DSHIM_FB_BASE=$FB"
[ -n "${FB_W:-}" ] && CFLAGS="$CFLAGS -DSHIM_FB_W=$FB_W"
[ -n "${FB_H:-}" ] && CFLAGS="$CFLAGS -DSHIM_FB_H=$FB_H"
[ -n "${EXTRA:-}" ] && CFLAGS="$CFLAGS $EXTRA"
OUT=${OUT:-out-qemu}
mkdir -p "$OUT"
for f in start.S shim.c console.c mmu.c fdt.c loader.c ramfb.c; do
	$CC $CFLAGS -c $f -o $OUT/${f%.*}.o
done
ld.lld -nostdlib -T shim.ld --build-id=none -N -o $OUT/shim.elf \
	$OUT/start.o $OUT/shim.o $OUT/console.o $OUT/mmu.o \
	$OUT/fdt.o $OUT/loader.o $OUT/ramfb.o
llvm-objcopy -O binary $OUT/shim.elf $OUT/Image
size=$(llvm-nm $OUT/shim.elf | awk '$3=="_end"{print $1}')
truncate -s $((16#$size)) $OUT/Image
ls -l $OUT/Image
