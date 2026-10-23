/*
 * FBCON_SCALE=1 replacement for the sweet framebuffer serial console
 * (xnu/patches/0003-sweet-framebuffer-serial-console.patch, compiled at
 * scale 2 in the CI kernel).  8x16 glyph cells instead of 16x32: 135
 * columns on the 1080-wide merlin panel instead of 67.
 *
 * Linked at the two original function VAs (tools/fbcon-1x.ld); every
 * global is an absolute address in __BOOTDATA.
 */
	.section .init,"ax",@progbits
	.globl fbcon_init_1x
fbcon_init_1x:
	stp	x29, x30, [sp, #-16]!
	mov	x29, sp
	adrp	x1, fbcon_width
	ldr	w2, [x1, #:lo12:fbcon_width]
	lsr	w2, w2, #3			// cols = width / 8
	adrp	x3, fbcon_cols
	str	w2, [x3, #:lo12:fbcon_cols]
	adrp	x4, fbcon_height
	ldr	w9, [x4, #:lo12:fbcon_height]
	lsr	w9, w9, #4			// rows = height / 16
	subs	w9, w9, #2			// keep 2 blank rows above the panel edge
	csel	w9, wzr, w9, lo			// height not set yet -> no rows
	adrp	x5, fbcon_rows
	str	w9, [x5, #:lo12:fbcon_rows]
	adrp	x6, fbcon_row
	str	wzr, [x6, #:lo12:fbcon_row]
	adrp	x7, fbcon_col
	str	wzr, [x7, #:lo12:fbcon_col]
	cbz	w9, 2f
	adrp	x8, fbcon_base
	ldr	x8, [x8, #:lo12:fbcon_base]
	cbz	x8, 2f				// fb not configured yet
	adrp	x8, fbcon_stride
	ldr	w8, [x8, #:lo12:fbcon_stride]
	cbz	w8, 2f
	mov	w10, #0
1:	adrp	x5, fbcon_rows		/* clear_row clobbers x5 */
	ldr	w9, [x5, #:lo12:fbcon_rows]
	cmp	w10, w9
	b.hs	2f
	mov	w0, w10
	bl	fbcon_clear_row_1x
	add	w10, w10, #1
	b	1b
2:	ldp	x29, x30, [sp], #16
	ret

	.section .tx,"ax",@progbits
	.globl fbcon_transmit_data_1x
fbcon_transmit_data_1x:
	stp	x29, x30, [sp, #-32]!
	mov	x29, sp
	str	w0, [sp, #16]			// char survives newline/clear
	adrp	x1, fbcon_base
	ldr	x1, [x1, #:lo12:fbcon_base]
	cbz	x1, .Lret			// framebuffer not configured yet
	adrp	x1, fbcon_stride
	ldr	w1, [x1, #:lo12:fbcon_stride]
	cbz	w1, .Lret
	adrp	x1, fbcon_cols
	ldr	w1, [x1, #:lo12:fbcon_cols]
	cbz	w1, .Lret
	cmp	w0, #0x0d			// '\r'
	b.eq	.Lcr
	cmp	w0, #0x0a			// '\n'
	b.eq	.Lnl
	adrp	x1, fbcon_col
	ldr	w2, [x1, #:lo12:fbcon_col]
	adrp	x3, fbcon_cols
	ldr	w3, [x3, #:lo12:fbcon_cols]
	cmp	w2, w3
	b.lo	.Lblit
	bl	fbcon_newline_1x
	adrp	x1, fbcon_col			// helpers clobber x1
	ldr	w2, [x1, #:lo12:fbcon_col]
.Lblit:
	ldr	w0, [sp, #16]
	adrp	x4, iso_font
	add	x4, x4, #:lo12:iso_font
	add	x4, x4, w0, uxtw #4		// glyph = iso_font + c*16
	lsl	w5, w2, #3			// x0 = col*8
	adrp	x6, fbcon_row
	ldr	w7, [x6, #:lo12:fbcon_row]
	lsl	w7, w7, #4			// y0 = row*16
	adrp	x8, fbcon_base
	ldr	x8, [x8, #:lo12:fbcon_base]
	adrp	x9, fbcon_stride
	ldr	w9, [x9, #:lo12:fbcon_stride]
	lsr	w9, w9, #2			// stride/4 pixels
	mov	w10, #16			// glyph rows
	mov	w11, #0xff000000		// bg
	mov	w12, #0xffffffff		// fg
.Lgy:
	ldrb	w13, [x4], #1
	madd	w14, w7, w9, w5
	add	x14, x8, w14, uxtw #2
	mov	w15, #1
	mov	w16, #8
.Lgx:
	tst	w13, w15
	csel	w17, w12, w11, ne
	str	w17, [x14], #4
	lsl	w15, w15, #1
	subs	w16, w16, #1
	b.ne	.Lgx
	add	w7, w7, #1
	subs	w10, w10, #1
	b.ne	.Lgy
	add	w2, w2, #1
	str	w2, [x1, #:lo12:fbcon_col]
	ldp	x29, x30, [sp], #32
	ret
.Lret:
	ldp	x29, x30, [sp], #32
	ret
.Lcr:
	adrp	x1, fbcon_col
	str	wzr, [x1, #:lo12:fbcon_col]
	ldp	x29, x30, [sp], #32
	ret
.Lnl:
	bl	fbcon_newline_1x
	ldp	x29, x30, [sp], #32
	ret

	.globl fbcon_newline_1x
fbcon_newline_1x:
	stp	x29, x30, [sp, #-16]!
	mov	x29, sp
	adrp	x1, fbcon_col
	str	wzr, [x1, #:lo12:fbcon_col]
	adrp	x4, fbcon_rows
	ldr	w4, [x4, #:lo12:fbcon_rows]
	cbz	w4, 9f				// height not set yet: no row to move to
	adrp	x2, fbcon_row
	ldr	w3, [x2, #:lo12:fbcon_row]
	add	w3, w3, #1
	adrp	x4, fbcon_rows
	ldr	w4, [x4, #:lo12:fbcon_rows]
	cmp	w3, w4
	b.lo	2f
	/* bottom row: scroll the text area up by one 16-px row */
	bl	fbcon_scroll_1x
	adrp	x2, fbcon_row
	adrp	x4, fbcon_rows
	ldr	w4, [x4, #:lo12:fbcon_rows]
	sub	w3, w4, #1
	str	w3, [x2, #:lo12:fbcon_row]
	mov	w0, w3
	bl	fbcon_clear_row_1x
	ldp	x29, x30, [sp], #16
	ret
2:	str	w3, [x2, #:lo12:fbcon_row]
	mov	w0, w3
	bl	fbcon_clear_row_1x
	adrp	x2, fbcon_row
	ldr	w3, [x2, #:lo12:fbcon_row]
	add	w0, w3, #1
	adrp	x4, fbcon_rows
	ldr	w4, [x4, #:lo12:fbcon_rows]
	cmp	w0, w4
	csel	w0, wzr, w0, eq
	bl	fbcon_clear_row_1x
9:	ldp	x29, x30, [sp], #16
	ret

/* shift rows [16, rows*16) up by 16 pixel rows (memmove down) */
fbcon_scroll_1x:
	adrp	x1, fbcon_base
	ldr	x1, [x1, #:lo12:fbcon_base]
	adrp	x2, fbcon_stride
	ldr	w2, [x2, #:lo12:fbcon_stride]
	lsl	x3, x2, #4			/* 16 rows in bytes */
	add	x8, x1, x3			/* src */
	adrp	x5, fbcon_rows
	ldr	w5, [x5, #:lo12:fbcon_rows]
	sub	w5, w5, #1
	lsl	w5, w5, #4			/* (rows-1)*16 pixel rows */
	mul	w6, w5, w2			/* bytes to copy */
	lsr	x6, x6, #4			/* 16-byte chunks */
	mov	x7, x1				/* dst */
5:	ldp	x9, x10, [x8], #16
	stp	x9, x10, [x7], #16
	subs	x6, x6, #1
	b.ne	5b
	ret

	.globl fbcon_clear_row_1x
fbcon_clear_row_1x:				// w0 = row
	lsl	w1, w0, #4			// y = row*16
	add	w2, w1, #16			// end y
	adrp	x3, fbcon_base
	ldr	x3, [x3, #:lo12:fbcon_base]
	adrp	x4, fbcon_stride
	ldr	w4, [x4, #:lo12:fbcon_stride]
	adrp	x5, fbcon_width
	ldr	w5, [x5, #:lo12:fbcon_width]
	mov	w6, #0xff000000
.Lrow:
	mul	w7, w1, w4
	add	x7, x3, w7, uxtw
	mov	w8, #0
.Lpx:
	str	w6, [x7, w8, uxtw #2]
	add	w8, w8, #1
	cmp	w8, w5
	b.ne	.Lpx
	add	w1, w1, #1
	cmp	w1, w2
	b.ne	.Lrow
	ret
