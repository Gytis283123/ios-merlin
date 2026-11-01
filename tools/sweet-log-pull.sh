#!/bin/sh
# Read the SWEET console log (kernel patch 0047) from a phone booted into
# OrangeFox recovery (fastboot boot recovery/recovery.img; adb root shell).
#   tools/sweet-log-pull.sh OUT.txt
# Only reads: the last 4097 4-KiB blocks (16 MiB + 4 KiB) of userdata.
# The decoder locates the SWEETLOG header from its size field, so this also
# accepts a 4-MiB ring at the end of the larger read area.
set -eu
out=${1:?usage: sweet-log-pull.sh OUT.txt}
block_size=4096
blocks=4097
read_bytes=$((block_size * blocks))
dev=$(adb shell 'for d in /dev/block/by-name/userdata /dev/block/bootdevice/by-name/userdata; do [ -e $d ] && readlink -f $d && break; done' | tr -d '\r')
[ -n "$dev" ] || { echo "userdata block device not found" >&2; exit 1; }
bytes=$(adb shell blockdev --getsize64 "$dev" | tr -d '\r')
[ $((bytes % block_size)) -eq 0 ] || { echo "userdata size is not 4-KiB aligned" >&2; exit 1; }
skip=$((bytes / block_size - blocks))
[ "$skip" -ge 0 ] || { echo "userdata is smaller than the SWEETLOG read area" >&2; exit 1; }
[ ! -e "$out.bin" ] && [ ! -e "$out" ] || {
	echo "refusing to overwrite an existing log capture" >&2
	exit 1
}
adb exec-out "dd if=$dev bs=$block_size skip=$skip count=$blocks 2>/dev/null" > "$out.bin"
actual=$(stat -c %s "$out.bin")
[ "$actual" -eq "$read_bytes" ] || {
	echo "short read: expected $read_bytes bytes, got $actual; raw capture kept at $out.bin" >&2
	exit 1
}
echo "$dev: $bytes bytes, read blocks $skip..$((skip + blocks - 1)) ($actual bytes)" >&2
python3 "$(dirname "$0")/sweet-log.py" "$out.bin" "$out"
