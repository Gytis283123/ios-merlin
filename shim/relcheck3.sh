#!/bin/bash
cd /mnt/d/things/Merlin/ios-merlin/shim
llvm-objdump -dr out/shim.o > /tmp/shim.dis 2>/dev/null
grep -n "rodata" /tmp/shim.dis | grep -v "str1" | head -20
echo "=== functions ==="
grep -n "^[0-9a-f]* <" /tmp/shim.dis | head -40
