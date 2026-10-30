/*
 * sweet boot shim entry: arm64 Linux Image header so Qualcomm ABL treats
 * us like a kernel. ABL enters at EL1, MMU/D-cache off, x0 = DTB pointer.
 */
	.section .text.head, "ax"
	.globl _head
_head:
	b	_start			/* code0 */
	.long	0			/* code1 */
	.quad	0			/* text_offset */
	.quad	_end			/* image_size (linked at 0) */
	.quad	0xa			/* flags: LE, 16K pages, place anywhere */
	.quad	0			/* res2 */
	.quad	0			/* res3 */
	.quad	0			/* res4 */
	.ascii	"ARM\x64"		/* magic */
	.long	0			/* res5 (PE offset) */

	.text
	.globl _start
_start:
	msr	daifset, #0xf
	mov	x19, x0			/* DTB pointer from ABL */
#ifdef MERLIN
#ifndef SHIM_QEMU
	/* merlin early life, BEFORE anything else touches the world.
	 * 1) pet the toprgu AP watchdog LK handed us armed (RESTART
	 *    register, key 0x1971): without a pet the 16s window runs out
	 *    and the box resets - exactly the bootloop signature with NO
	 *    red pixels ever seen.
	 * 2) paint a 96x48 RED block at the top-left of the LK splash:
	 *    the first MMIO the shim does.  It proves (a) we were
	 *    entered at all, (b) the splash fb base works.  If this
	 *    store fails exact-abort, we die here and NOTHING paints;
	 *    the pet gives +16s for the pilot to read a screenshot. */
	ldr	x20, =0x10007000
	movz	w21, #0x1971
	str	w21, [x20, #0x8]
	/* 3) the red splash paint below is the phone splash address
	 *    (0x7e605000), not console.h's SHIM_QEMU FB_BASE - on QEMU the
	 *    console is the only display, so skip the phone-plane paints. */
	ldr	x20, =0x7e605000
	movz	w22, #0xffff, lsl #16	/* RED (a8r8g8b8) */
	mov	w23, #48
1:	mov	w24, #96
2:	str	w22, [x20], #4
	subs	w24, w24, #1
	b.ne	2b
	add	x20, x20, #(4320 - 96 * 4)	/* next row after 96 cols */
	subs	w23, w23, #1
	b.ne	1b
#endif
#endif
	msr	spsel, #1
	adr	x1, _stack_top
	mov	sp, x1
	adr	x1, vectors
	msr	vbar_el1, x1
	isb
	/* zero .bss */
	adr	x1, _bss_start
	adr	x2, _bss_end
1:	cmp	x1, x2
	b.hs	2f
	str	xzr, [x1], #8
	b	1b
2:	mov	x0, x19
#ifdef MERLIN
#ifndef SHIM_QEMU
	/* GREEN proof block (rows 48..96) on the splash: survived bss zero
	 * + vectors setup; shim_main is next. */
	ldr	x20, =(0x7e605000 + 48 * 4320)
	movz	w22, #0xff00, lsl #16	/* GREEN (a8r8g8b8) */
	movk	w22, #0xff00
	mov	w23, #48
3:	mov	w24, #96
4:	str	w22, [x20], #4
	subs	w24, w24, #1
	b.ne	4b
	add	x20, x20, #(4320 - 96 * 4)
	subs	w23, w23, #1
	b.ne	3b
#endif
#endif
	bl	shim_main
3:	wfe
	b	3b

/* PSCI CPU_ON target. x0 = context id = cpu index (1..7). */
	.globl secondary_entry
secondary_entry:
	msr	daifset, #0xf
	msr	spsel, #1
	adr	x1, _sec_stacks
	add	x1, x1, x0, lsl #12
	add	x1, x1, #0x1000
	mov	sp, x1
	adr	x1, vectors
	msr	vbar_el1, x1
	isb
	bl	secondary_main
4:	wfe
	b	4b

/*
 * Exception vectors. Each slot stashes x29/x30, loads its slot number
 * and jumps to the common path, which saves x0-x28 plus the interrupted
 * lr and calls exc_handler(slot, regs). IRQs return; everything else
 * ends in the on-screen panic.
 */
.macro vent slot
	.balign	0x80
	stp	x29, x30, [sp, #-16]!
	mov	x29, #\slot
	b	exc_common
.endm

	.balign	0x800
	.globl vectors
vectors:
	vent 0
	vent 1
	vent 2
	vent 3
	vent 4
	vent 5
	vent 6
	vent 7
	vent 8
	vent 9
	vent 10
	vent 11
	vent 12
	vent 13
	vent 14
	vent 15

exc_common:
	sub	sp, sp, #(30 * 8)
	stp	x0, x1, [sp, #0]
	stp	x2, x3, [sp, #16]
	stp	x4, x5, [sp, #32]
	stp	x6, x7, [sp, #48]
	stp	x8, x9, [sp, #64]
	stp	x10, x11, [sp, #80]
	stp	x12, x13, [sp, #96]
	stp	x14, x15, [sp, #112]
	stp	x16, x17, [sp, #128]
	stp	x18, x19, [sp, #144]
	stp	x20, x21, [sp, #160]
	stp	x22, x23, [sp, #176]
	stp	x24, x25, [sp, #192]
	stp	x26, x27, [sp, #208]
	str	x28, [sp, #224]
	str	x30, [sp, #232]		/* interrupted lr, exc_handler reads regs[29] */
	mov	x0, x29
	mov	x1, sp
	bl	exc_handler
	ldp	x0, x1, [sp, #0]
	ldp	x2, x3, [sp, #16]
	ldp	x4, x5, [sp, #32]
	ldp	x6, x7, [sp, #48]
	ldp	x8, x9, [sp, #64]
	ldp	x10, x11, [sp, #80]
	ldp	x12, x13, [sp, #96]
	ldp	x14, x15, [sp, #112]
	ldp	x16, x17, [sp, #128]
	ldp	x18, x19, [sp, #144]
	ldp	x20, x21, [sp, #160]
	ldp	x22, x23, [sp, #176]
	ldp	x24, x25, [sp, #192]
	ldp	x26, x27, [sp, #208]
	ldr	x28, [sp, #224]
	ldr	x30, [sp, #232]
	add	sp, sp, #(30 * 8)
	ldp	x29, x30, [sp], #16
	eret
