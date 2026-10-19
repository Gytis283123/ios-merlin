#!/usr/bin/env bash
# One-time WSL environment for building + testing the merlin xnu image locally.
#
#   sudo bash tools/env-ubuntu.sh
#
# Installs: qemu-system-aarch64 (the test environment), the arm64 cross
# toolchain for shim/boot.img phone images later, cpio + mkbootimg helpers.
set -o errexit
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
	qemu-system-arm \
	gcc-aarch64-linux-gnu \
	binutils-aarch64-linux-gnu \
	cpio \
	unzip
echo
echo "qemu: $(qemu-system-aarch64 --version | head -1)"
echo
echo "Previous python checks that must already pass outside sudo:"
python3 mkadt.py /tmp/envcheck.adt >/dev/null 2>&1 && rm -f /tmp/envcheck.adt && echo "  mkadt.py: OK" || true
echo "ready."
