#pragma once
#include <stdint.h>

#ifdef MERLIN
/* Redmi Note 9 (MT6768): the LK splash framebuffer.  Base from the stock dts
 * atag "atag,videolfb-fb_base_l" (panel: hx83112b 1080x2340 DSI CMD); the
 * live-FDT dump on the first boot verifies both.  a8r8g8b8 assumed.
 * SHIM_QEMU runs the same shim on QEMU's virt board, whose sweet twin
 * console plane is 0x9c000000 1080x2400 - so the boot_args Video block the
 * loader hands xnu points at the same plane the QEMU ADT describes. */
#ifdef SHIM_QEMU
/* Overridable so the QEMU rig can also run with the phone's own splash
 * plane/geometry (see build-qemu.sh FB/FB_W/FB_H), which then matches the
 * phone ADT's sweet-fbcon node exactly. */
#ifndef SHIM_FB_BASE
#define SHIM_FB_BASE	0x9c000000UL
#endif
#ifndef SHIM_FB_W
#define SHIM_FB_W	1080
#endif
#ifndef SHIM_FB_H
#define SHIM_FB_H	2400
#endif
#define FB_BASE		SHIM_FB_BASE
#define FB_W		SHIM_FB_W
#define FB_H		SHIM_FB_H
#else
/* NOTE: the in-flight images (E1 lineage, repacked through 0105) carry
 * 0x7e605438 as the boot_args Video base from an older FB_BASE, so
 * tools/patch-shim-videobase.py's --old-base default matches only those;
 * shims rebuilt from these sources encode 0x7e605000 and need
 * --old-base 0x7e605000. */
#define FB_BASE		0x7e605000UL
#define FB_W		1080
#define FB_H		2340
#endif
#else
#define FB_BASE		0x9c000000UL	/* reserved-memory cont_splash_region */
#define FB_W		1080
#define FB_H		2400
#endif
#define FB_STRIDE	(FB_W * 4)	/* a8r8g8b8, matches mainline simplefb */

#define RED	0xffff0000U
#define BLUE	0xff0000a0U
#define WHITE	0xffffffffU
#define YELLOW	0xffffff00U
#define GREEN	0xff00ff00U

extern volatile uint32_t *con_fb;

void con_clear(uint32_t bg);
void con_skip(void);
void con_str(const char *label, const char *s);
void con_hex(const char *label, uint64_t v);
/* label, then "a=xxxxxxxx b=xxxxxxxx" style pairs of 32-bit values */
void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb);

/* Big-font phone-capture mode (see console.c). */
void con_big_mode(int s);
void con_big_hex(const char *label, uint32_t v);
void con_big_str(const char *label, const char *s);
