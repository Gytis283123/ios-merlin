#!/usr/bin/env bash
# One-time WSL environment for building + testing the merlin xnu image locally.
#
#   sudo bash tools/env-ubuntu.sh
#
# Installs: qemu-system-aarch64 (the test environment), the arm64 cross
# toolchain for shim/boot.img phone images later, unzip + cpio helpers.
# Every step prints what it does; on failure it prints an explicit marker.
set -u

fail() {
	echo "== ENV-UBUNTU FAILED at: $*"
	exit 1
}

E_UID=$(id -u)
echo "== env-ubuntu.sh: uid=$E_UID user=$(whoami) $(lsb_release -ds 2>/dev/null)"
[ "$E_UID" = 0 ] || echo "NOT ROOT: apt calls below will fail - run with sudo"

echo "== step 1/4: apt-get update"
apt-get update || fail "apt-get update"
echo "== step 2/4: apt-get install (qemu-system-arm gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu cpio unzip)"
DEBIAN_FRONTEND=noninteractive apt-get install -y \
	qemu-system-arm \
	gcc-aarch64-linux-gnu \
	binutils-aarch64-linux-gnu \
	cpio \
	unzip || fail "apt-get install"
echo "== step 3/4: verifying binaries"
command -v qemu-system-aarch64 || fail "qemu-system-aarch64 not found after install"
qemu-system-aarch64 --version | head -1
aarch64-linux-gnu-gcc --version | head -1
echo "== step 4/4: python checks (non-sudo parts)"
cd "$(dirname "$0")"
python3 mkadt.py /tmp/envcheck.adt >/dev/null 2>&1; rm -f /tmp/envcheck.adt
echo "== env-ubuntu.sh: ready."
