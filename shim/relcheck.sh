#!/bin/bash
for f in shim console mmu fdt loader ufs; do
	n=$(llvm-readelf -r out/$f.o 2>/dev/null | grep -c ABS64)
	echo "$f.o: $n"
done
echo '---- ABS64 detail ----'
llvm-readelf -r out/*.o 2>/dev/null | grep -B20 ABS64 | grep -E '^(out|Relocation|00)' | head -30
