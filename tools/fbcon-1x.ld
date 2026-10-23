OUTPUT_FORMAT(elf64-littleaarch64)
ENTRY(fbcon_init_1x)
SECTIONS
{
	. = 0xfffffe0007a7bae4;		/* _fbcon_init in the 0079+0082 kernel (nm) */
	.init : { *(.init) }
	. = 0xfffffe0007a7bbb0;		/* _fbcon_transmit_data (nm) */
	.tx : { *(.tx) }
}
fbcon_width  = 0xfffffe00080781b0;
fbcon_cols   = 0xfffffe00080781b4;
fbcon_height = 0xfffffe00080781b8;
fbcon_rows   = 0xfffffe00080781bc;
fbcon_row    = 0xfffffe00080781c0;
fbcon_col    = 0xfffffe00080781c4;
fbcon_base   = 0xfffffe00080781c8;
fbcon_stride = 0xfffffe00080781d0;
iso_font     = 0xfffffe0007b5fec0;
