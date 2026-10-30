/*
 * ramfb.c - put the shim framebuffer on QEMU's display.
 *
 * QEMU -M virt maps the fw_cfg MMIO interface at 0x09020000:
 *   +0x00  data      byte reads/writes, advance the item offset
 *   +0x08  selector  16-bit big-endian item selector
 *   +0x10  dma       64-bit big-endian pointer to a DMA descriptor
 *
 * ramfb is configured through the writable fw_cfg file "etc/ramfb",
 * whose payload is a 28-byte big-endian struct:
 *   u64 addr; u32 fourcc; u32 flags; u32 width; u32 height; u32 stride;
 * The ramfb write callback only accepts the whole struct in a single
 * fw_cfg write, so the config has to go through the DMA interface
 * (28 byte-sized writes would arrive as 28 one-byte callbacks).
 *
 * The shim runs with the MMU off, so the descriptor and payload
 * addresses below are plain physical addresses in the shim image.
 */
#include <stdint.h>
#include "ramfb.h"

#define FW_CFG_BASE		0x09020000UL
#define FW_CFG_DATA		0x00
#define FW_CFG_SELECTOR		0x08
#define FW_CFG_DMA		0x10

#define FW_CFG_FILE_DIR		0x0019
#define FW_CFG_DMA_CTL_ERROR	0x01
#define FW_CFG_DMA_CTL_SELECT	0x08
#define FW_CFG_DMA_CTL_WRITE	0x10

#define RAMFB_FOURCC_XR24	0x34325258U	/* DRM 'XR24' = XRGB8888 */

struct fw_cfg_dma {
	uint32_t control;
	uint32_t length;
	uint64_t address;
} __attribute__((packed, aligned(8)));

static struct fw_cfg_dma dma;
static uint8_t cfg[28] __attribute__((aligned(8)));
static uint8_t dir[4 + 64 * 64];

static uint8_t fw_read8(void)
{
	return *(volatile uint8_t *)(FW_CFG_BASE + FW_CFG_DATA);
}

static void fw_select(uint16_t sel)
{
	*(volatile uint16_t *)(FW_CFG_BASE + FW_CFG_SELECTOR) =
		__builtin_bswap16(sel);
	__asm__ volatile("dsb sy" ::: "memory");
}

static int fw_dma_write(uint16_t sel, const void *buf, uint32_t len)
{
	unsigned spin;
	uint32_t c;

	dma.control = __builtin_bswap32(((uint32_t)sel << 16) |
					FW_CFG_DMA_CTL_SELECT |
					FW_CFG_DMA_CTL_WRITE);
	dma.length = __builtin_bswap32(len);
	dma.address = __builtin_bswap64((uint64_t)(uintptr_t)buf);
	__asm__ volatile("dsb sy" ::: "memory");
	*(volatile uint64_t *)(FW_CFG_BASE + FW_CFG_DMA) =
		__builtin_bswap64((uint64_t)(uintptr_t)&dma);

	for (spin = 0; spin < 10000000; spin++) {
		/* volatile: QEMU clears dma.control via DMA; a plain load may be
		 * hoisted out of this loop at -O2 and never see the store. */
		c = __builtin_bswap32(*(volatile uint32_t *)&dma.control);
		if (c == 0)
			return 0;
		if (c & FW_CFG_DMA_CTL_ERROR)
			return -1;
	}
	return -1;
}

static int name_is(const uint8_t *p, const char *s)
{
	for (; *s; p++, s++)
		if (*p != (uint8_t)*s)
			return 0;
	return *p == 0;
}

int ramfb_init(uint64_t base, uint32_t width, uint32_t height, uint32_t stride)
{
	uint32_t count, i;
	uint16_t sel = 0;

	/* FW_CFG_FILE_DIR: be32 count, then 64-byte entries:
	 * be32 size, be16 select, be16 reserved, char name[56]. */
	fw_select(FW_CFG_FILE_DIR);
	for (i = 0; i < 4; i++)
		dir[i] = fw_read8();
	count = ((uint32_t)dir[0] << 24) | ((uint32_t)dir[1] << 16) |
		((uint32_t)dir[2] << 8) | dir[3];
	if (count > 64)
		count = 64;
	for (i = 0; i < count; i++) {
		uint8_t *e = &dir[4 + 64 * i];
		unsigned j;
		for (j = 0; j < 64; j++)
			e[j] = fw_read8();
		if (name_is(e + 8, "etc/ramfb"))
			sel = (uint16_t)((e[4] << 8) | e[5]);
	}
	if (sel == 0)
		return -1;

	*(uint64_t *)(cfg + 0) = __builtin_bswap64(base);
	*(uint32_t *)(cfg + 8) = __builtin_bswap32(RAMFB_FOURCC_XR24);
	*(uint32_t *)(cfg + 12) = 0;
	*(uint32_t *)(cfg + 16) = __builtin_bswap32(width);
	*(uint32_t *)(cfg + 20) = __builtin_bswap32(height);
	*(uint32_t *)(cfg + 24) = __builtin_bswap32(stride);
	__asm__ volatile("dsb sy" ::: "memory");

	return fw_dma_write(sel, cfg, sizeof(cfg));
}
