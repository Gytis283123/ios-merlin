/*
 * QEMU ramfb bootstrap for tools/qemu-merlin.py (the direct-loader path).
 *
 * Runs with the MMU off at QEMU_RAMFB_PA before the kernel entry.
 * x0..x3 are the framebuffer base, width, height and stride (set by the
 * generator stub); this tail-calls ramfb_init() from shim/ramfb.c, which
 * writes the "etc/ramfb" fw_cfg entry so QEMU's -device ramfb scans the
 * guest framebuffer.
 */
	.section .text
	.globl preboot
preboot:
	b	ramfb_init
