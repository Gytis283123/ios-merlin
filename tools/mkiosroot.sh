#!/bin/bash
# Build the SWEET iOS root: one case-sensitive HFS+ image holding an iOS OS
# root filesystem plus its cryptexes, for the userdata partition (rd=ufsroot0).
#
#   mkiosroot.sh OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.img [SIZE]     (SIZE default 16G)
#
# Pass - for SYSTEMOS.dmg/APPOS.dmg when the target has no cryptex volumes
# (A11 iOS builds ship everything inside the one OS volume; only A12+ split
# SystemOS/AppOS out).
#
# The IPSW images are raw APFS with LZBITMAP-compressed files: they are read
# through apfs-fuse (decompressing), so the HFS+ copy is uncompressed. On a
# device /private/preboot is its own volume holding the cryptexes, which
# /System/Cryptexes/{OS,App} link to; here they live inside the one volume.
# Owners, modes, symlinks and hard links are preserved (rsync -aH as root).
#
# The volume is journaled (XNU replays the journal after a panic; Linux only
# mounts it read-write with -o force and leaves the journal empty). SWEET
# additions: /System/Library/Caches/com.apple.dyld hard-links the SystemOS
# cryptex shared cache (ignition_level=1 looks there), and
# /private/var/keybags/systembag.kb is the plain-plist system keybag that
# keybagd reads with /defaults/no-effaceable-storage (tools/mkadt.py).
set -euo pipefail

[[ $# -ge 4 ]] || { sed -n '2,12p' "$0"; exit 2; }
os=$1 sysos=$2 appos=$3 out=$4 size=${5:-16G}
[[ $os != - ]] && os=$(realpath "$os")
[[ $sysos != - ]] && sysos=$(realpath "$sysos")
[[ $appos != - ]] && appos=$(realpath "$appos")
[[ ! -e $out ]] || { echo "refusing to overwrite $out" >&2; exit 1; }

work=$(mktemp -d)
mounts=()
cleanup() {
	local busy=0
	for m in "${mounts[@]}"; do
		if mountpoint -q "$m"; then
			sudo umount "$m" 2>/dev/null || true
		fi
		mountpoint -q "$m" && busy=1
	done
	# Never recurse into a directory that is still mounted (the root is writable).
	if [[ $busy == 0 ]]; then
		rm -f "$work"/*.dmg
		rmdir "$work"/* "$work" 2>/dev/null || true
	else
		echo "still mounted under $work: left in place" >&2
	fi
}
trap cleanup EXIT

# apfs-fuse splits its options on ',' (e.g. in iPhone10,3 paths): use links.
# Keep the .dmg name: apfs-fuse only parses UDIF images (the OS one is UDIF,
# the cryptexes are raw APFS) when the file name ends in .dmg.
apfs_mount() {
	ln -s "$1" "$work/$2.dmg"
	mkdir "$work/$2"
	# As root: a user's FUSE mount is unreadable to the root rsync below.
	sudo "$(command -v apfs-fuse)" "$work/$2.dmg" "$work/$2"
	mounts+=("$work/$2")
}
apfs_mount "$os" os
if [[ $sysos != - ]]; then apfs_mount "$sysos" sysos; fi
if [[ $appos != - ]]; then apfs_mount "$appos" appos; fi

truncate -s "$size" "$out"
mkfs.hfsplus -s -J -v iOSRoot "$out"
mkdir "$work/root"
sudo mount -t hfsplus -o loop,force "$out" "$work/root"
mounts=("$work/root" "${mounts[@]}")

copy() {
	echo "copying $1 -> ${2#"$work/root"}"
	sudo mkdir -p "$2"
	sudo rsync -aH --numeric-ids "$1/" "$2/"
}
copy "$work/os/root" "$work/root"
if [[ $sysos != - ]]; then
	copy "$work/sysos/root" "$work/root/private/preboot/Cryptexes/OS"
fi
if [[ $appos != - ]]; then
	copy "$work/appos/root" "$work/root/private/preboot/Cryptexes/App"
fi

# Shared cache where dyld looks at ignition level 1: hard links, no extra space.
dsc=private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld
if [[ -d "$work/root/$dsc" ]]; then
	sudo mkdir -p "$work/root/System/Library/Caches/com.apple.dyld"
	for f in "$work/root/$dsc"/*; do
		sudo ln "$f" "$work/root/System/Library/Caches/com.apple.dyld/${f##*/}"
	done
	# The regular iOS 13+ location as well: dyld checks /System/Library/dyld
	# first, and dyld2.3+ reports "no dyld cache" from neither path.
	sudo mkdir -p "$work/root/System/Library/dyld"
	for f in "$work/root/$dsc"/*; do
		sudo ln "$f" "$work/root/System/Library/dyld/${f##*/}"
	done
fi

# dyld does not search the cryptexes at ignition level 1: hard-link every
# cryptex file that has no counterpart in the OS root (libobjc-trampolines,
# libffi-trampolines, libstdc++, ...) to its root path.
for c in OS App; do
	[[ -d "$work/root/private/preboot/Cryptexes/$c" ]] || continue
	(cd "$work/root/private/preboot/Cryptexes/$c" && sudo find . ! -type d ! -path './System/Library/Caches/com.apple.dyld/*') |
	while IFS= read -r f; do
		f=${f#./}
		if ! sudo test -e "$work/root/$f" && ! sudo test -L "$work/root/$f"; then
			sudo mkdir -p "$work/root/$(dirname "$f")"
			src="$work/root/private/preboot/Cryptexes/$c/$f"
			# Linux hfsplus cannot hard-link symlinks: copy those.
			if sudo test -L "$src"; then sudo cp -P "$src" "$work/root/$f"; else sudo ln "$src" "$work/root/$f"; fi
			echo "linked $c:/$f"
		fi
	done
done

# logd's log stores, normally made at restore: it checks owner _logd (272)
# and mode, plus a .migrated marker, else asks a helper and crashes
# ("BUG IN LIBTRACE: Failed to migrate directory").
# NOTE: coreutils install/chown reject bare numeric owners ("invalid user:
# 272"), so ownership goes through python os.chown.
db="$work/root/private/var/db"
python3 - "$db" <<'PYEOF'
import os, sys
db = sys.argv[1]
def d(p, mode):
    os.makedirs(p, exist_ok=True)
    os.chmod(p, mode)
    os.chown(p, 272, 272)
d(db + "/diagnostics", 0o751)
d(db + "/uuidtext", 0o755)
d(db + "/diagnostics/timesync", 0o755)
for f in (db + "/diagnostics/.migrated", db + "/uuidtext/.migrated",
          db + "/diagnostics/timesync/.migrated"):
    open(f, "w").close()
    os.chmod(f, 0o644)
    os.chown(f, 272, 272)
print("logd stores OK")
PYEOF

# System keybag for the built-in AppleKeyStore (no passcode).
kb="$work/root/private/var/keybags"
python3 - "$kb" <<'PYEOF'
import os, sys
kb = sys.argv[1]
os.makedirs(kb, exist_ok=True)
os.chmod(kb, 0o700)
data = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict><key>KeyBagKeys</key><data>U1dFRVQ=</data></dict></plist>\n')
open(kb + "/systembag.kb", "w").write(data)
os.chmod(kb + "/systembag.kb", 0o600)
print("keybag OK")
PYEOF

df -h "$work/root"
sudo umount "$work/root"
# Linux hfsplus decomposes some non-ASCII names (localized Shortcuts examples)
# differently from Apple's tables; let fsck_hfs rewrite them, then verify.
fsck.hfsplus -f -y "$out" | grep -v 'Illegal name' || true
fsck.hfsplus -f -n "$out"
