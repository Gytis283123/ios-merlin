/*
 * Minimal text console on the ABL splash framebuffer. With the MMU off
 * every access is Device memory, so stay aligned (-mstrict-align).
 */
#include "console.h"
#include "font.h"

#ifdef MERLIN
#define SCALE		2		/* 1080x2340: 67 cols x 73 rows */
#else
#define SCALE		3
#endif
#define CH_W		(8 * SCALE)
#define CH_H		(16 * SCALE)
#define MARGIN		24
#define LABEL_COLS	8

volatile uint32_t *con_fb = (volatile uint32_t *)FB_BASE;
static uint32_t con_bg;
static int row;
static int big_scale;		/* 0 = normal SCALE, else 16*s pixel glyphs */

void con_clear(uint32_t bg)
{
	for (int y = 0; y < FB_H; y++) {
		volatile uint32_t *line = con_fb + y * (FB_STRIDE / 4);
		for (int x = 0; x < FB_W; x++)
			line[x] = bg;
	}
	con_bg = bg;
	row = 0;
}

static void put_char(int col, char ch, uint32_t fg)
{
	if (ch < 0x20 || ch > 0x7e)
		ch = '?';
	const unsigned char *g = font8x16[ch - 0x20];
	int s = big_scale ? big_scale : SCALE;
	int x0 = MARGIN + col * 8 * s, y0 = MARGIN + row * 16 * s;
	if (x0 + 8 * s > FB_W || y0 + 16 * s > FB_H)
		return;
	for (int gy = 0; gy < 16; gy++)
		for (int gx = 0; gx < 8; gx++) {
			uint32_t c = (g[gy] & (0x80 >> gx)) ? fg : con_bg;
			for (int sy = 0; sy < s; sy++) {
				volatile uint32_t *p = con_fb + (y0 + gy * s + sy) * (FB_STRIDE / 4)
						       + x0 + gx * s;
				for (int sx = 0; sx < s; sx++)
					p[sx] = c;
			}
		}
}

static int put_str(int col, const char *s, uint32_t fg)
{
	while (*s)
		put_char(col++, *s++, fg);
	return col;
}

static void fmt_hex(char *buf, uint64_t v, int digits)
{
	static const char hex[] = "0123456789ABCDEF";
	for (int i = 0; i < digits; i++)
		buf[i] = hex[(v >> (4 * (digits - 1 - i))) & 0xf];
	buf[digits] = 0;
}

void con_skip(void)
{
	row++;
}

void con_str(const char *label, const char *s)
{
	put_str(0, label, YELLOW);
	put_str(LABEL_COLS, s, WHITE);
	row++;
}

void con_hex(const char *label, uint64_t v)
{
	char buf[17];
	fmt_hex(buf, v, 16);
	con_str(label, buf);
}

void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb)
{
	char buf[9];
	int col = put_str(0, label, YELLOW);
	col = col < LABEL_COLS ? LABEL_COLS : col + 1;
	col = put_str(col, a, YELLOW);
	fmt_hex(buf, va, 8);
	col = put_str(col, buf, WHITE);
	if (b) {
		col = put_str(col + 1, b, YELLOW);
		fmt_hex(buf, vb, 8);
		put_str(col, buf, WHITE);
	}
	row++;
}

/* Big-font mode for phone-camera captures: glyphs are 8s x 16s pixels.
 * Screen geometry (1080 cols, 134 px row pitch at scale 8) means ~16
 * columns x ~16 rows - only for short fact lines, not the full diag. */
void con_big_mode(int s)
{
	big_scale = s;
}

/* "LABEL=XXXXXXXX" line, adjacent columns (no LABEL_COLS gap). */
void con_big_hex(const char *label, uint32_t v)
{
	char buf[9];

	fmt_hex(buf, v, 8);
	int col = put_str(0, label, YELLOW);
	put_str(col, "=", WHITE);
	put_str(col + 1, buf, WHITE);
	row++;
}

void con_big_str(const char *label, const char *s)
{
	int col = put_str(0, label, YELLOW);

	put_str(col, "=", WHITE);
	put_str(col + 1, s, WHITE);
	row++;
}
