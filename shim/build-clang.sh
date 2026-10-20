#!/bin/bash
# Build the merlin shim with WSL clang+lld (no aarch64-linux-gnu-gcc needed):
#   wsl -d Ubuntu -- bash -lc "/mnt/d/things/Merlin/ios-merlin/shim/build-clang.sh"
# Same layout as build.sh; -DMERLIN selects the mt6768 build (merlin fb, no
# qcom GIC/IMEM pokes, diag-first main).  The payload ramdisk is NOT included
# here: the boot image is packed on the Windows side (tools/mkbootimg.py).
set -euo pipefail
cd "$(dirname "$0")"
CC="clang --target=aarch64-linux-gnu -ffreestanding -fno-pic -fno-stack-protector -fno-builtin -mno-red-zone"
CFLAGS="-O2 -Wall -Wextra -mgeneral-regs-only -mstrict-align -DMERLIN"
mkdir -p out
for f in start.S shim.c console.c mmu.c fdt.c loader.c; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
done
# ufs.c (the qualcomm UFS probe) is not linked on merlin: the phone is eMMC
# and the probe would poke a wrong address.
abs=$(llvm-readelf -r out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o | grep -c R_AARCH64_ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
ld.lld -nostdlib -T shim.ld --build-id=none -N -o out/shim.elf \
	out/start.o out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o
llvm-objcopy -O binary out/shim.elf out/Image
size=$(llvm-nm out/shim.elf | awk '$3=="_end"{print $1}')
truncate -s $((16#$size)) out/Image
ls -l out/Image
