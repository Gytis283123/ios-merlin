OUTPUT_FORMAT(elf64-littleaarch64)
ENTRY(fbcon_init_1x)
SECTIONS
{
	. = 0xfffffe0007a7aea4;		/* _fbcon_init in kernel.development.sweet.merlinfb */
	.init : { *(.init) }
	. = 0xfffffe0007a7af70;		/* _fbcon_transmit_data */
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
