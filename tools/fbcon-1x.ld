OUTPUT_FORMAT(elf64-littleaarch64)
ENTRY(fbcon_init_1x)
SECTIONS
{
	/* Both addresses from xnu/out-dlildbg2's symtab (kernel.development.sweet,
	 * sha256 13789e21f7c90925158d30dfd2a09c3ef280ffc772cc20afd6516d81c2697cfc),
	 * NOT the 0083-era kernels; they move every kernel build - re-derive
	 * before reuse (see patch-fbcon1x.py). */
	. = 0xfffffe0007a7af24;		/* _fbcon_init (symtab) */
	.init : { *(.init) }
	. = 0xfffffe0007a7aff0;		/* _fbcon_transmit_data (symtab) */
	.tx : { *(.tx) }
}
fbcon_width  = 0xfffffe0008074150;
fbcon_cols   = 0xfffffe0008074154;
fbcon_height = 0xfffffe0008074158;
fbcon_rows   = 0xfffffe000807415c;
fbcon_row    = 0xfffffe0008074160;
fbcon_col    = 0xfffffe0008074164;
fbcon_base   = 0xfffffe0008074168;
fbcon_stride = 0xfffffe0008074170;
iso_font     = 0xfffffe0007b5fec0;
