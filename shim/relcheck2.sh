#!/bin/bash
cd /mnt/d/things/Merlin/ios-merlin/shim
echo '== .rodata of shim.o (bytes) =='
llvm-objdump -s -j .rodata out/shim.o 2>/dev/null | head -12
echo '== .rodata.str1.1 of shim.o (bytes) =='
llvm-objdump -s -j .rodata.str1.1 out/shim.o 2>/dev/null | head -8
