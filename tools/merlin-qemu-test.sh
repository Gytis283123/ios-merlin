#!/usr/bin/env bash
# End-to-end local test of a merlin xnu image: kernel + merlin ADT + init
# RAM-disk root -> payload -> QEMU boot -> decoded framebuffer console.
#
#   tools/merlin-qemu-test.sh [KERNEL] [--secs N]
#
# Default KERNEL: newest kernel.development.* under xnu/out-*/ (see
# tools/fetch-kernel-artifact.py for getting one).  Exit codes: 0 or 3
# (blank/incomplete decode) = qemu ran; 2 = a visible panic was decoded.
set -o errexit
cd "$(dirname "$0")/.."

K_DEFAULT=$(find xnu -maxdepth 2 -name 'kernel.development.*' ! -path '*link*' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
K="$K_DEFAULT"
SECS=40
while [[ $# -gt 0 ]]; do
	case "$1" in
	-h|--help) sed -n 3,6p "$0"; exit 0;;
	--secs) SECS="$2"; shift 2;;
	--secs=*) SECS="${1#--secs=}"; shift;;
    *) K="$1"; shift;;
	esac
done

T=research/qtest-latest
mkdir -p "$T"

# 1. static init as PID 1 (the RAM disk itself, served by mockfs)
if [[ ! -s "$T/init" ]]; then
	clang -target arm64-apple-ios16.0 -c tools/merlin-init.S -o "$T/init.o"
	python3 tools/mkinit.py "$T/init.o" "$T/init"
fi

# 2. merlin ADT (QEMU twin: QEMU's GIC/CNTFRQ, merlin identity, iPhone X compat)
python3 tools/mkadt.py "$T/adt"

# 3. payload: kernel + ADT + boot-args + ramdisk (SWEETXNU v1, shared with shim)
CMD="debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress rd=md0"
python3 tools/mkpayload.py "$K" "$T/adt" "$T/payload.bin" --ramdisk "$T/init" --cmdline "$CMD"

# 4. boot in QEMU and decode the kernel framebuffer console
set +o errexit
python3 tools/qemu-merlin.py "$T/payload.bin" "$T/qemu" --secs "$SECS" --kernel "$K" --fail-on-panic
RC=$?
set -o errexit

echo
echo "== result: $(cat "$T/qemu/result.json") (exit $RC) =="
echo "console snapshot (fb.txt tail):"
tail -n 30 "$T/qemu/fb.txt" 2>/dev/null || true
exit $RC
