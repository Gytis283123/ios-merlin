/*
 * Just enough flattened-device-tree parsing for the boot diagnostics:
 * properties of top-level nodes (/memory, /chosen, /psci, /timer) and of
 * the children of /cpus. Big-endian, 4-byte aligned tokens, byte loads
 * only where Device memory allows them.
 */
#include "fdt.h"

#define FDT_MAGIC	0xd00dfeed
#define FDT_BEGIN_NODE	1
#define FDT_END_NODE	2
#define FDT_PROP	3
#define FDT_NOP		4
#define FDT_END		9

uint32_t fdt_be32(uintptr_t a)
{
	return __builtin_bswap32(*(volatile uint32_t *)a);
}

uint64_t fdt_be64(uintptr_t a)
{
	return (uint64_t)fdt_be32(a) << 32 | fdt_be32(a + 4);
}

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static uintptr_t align4(uintptr_t a)
{
	return (a + 3) & ~3UL;
}

static uintptr_t skip_str(uintptr_t p)
{
	/* byte loads are fine on Device memory as long as they are aligned to 1 */
	while (*(volatile char *)p)
		p++;
	return p + 1;
}

int fdt_chosen_u64(uintptr_t fdt, const char *prop, uint64_t *out)
{
	uintptr_t val;
	uint32_t len;

	if (!fdt_top_prop(fdt, "chosen", prop, &val, &len))
		return 0;
	if (len == 4) {
		*out = fdt_be32(val);
		return 1;
	}
	if (len == 8 || len == 16) {
		*out = fdt_be64(val);
		return 1;
	}
	return 0;
}

int fdt_top_prop(uintptr_t fdt, const char *node, const char *prop,
		 uintptr_t *val, uint32_t *len)
{
	if (!fdt || fdt_be32(fdt) != FDT_MAGIC)
		return 0;
	uintptr_t p = fdt + fdt_be32(fdt + 8);		/* off_dt_struct */
	uintptr_t strings = fdt + fdt_be32(fdt + 12);	/* off_dt_strings */
	int depth = 0, in_target = 0;

	for (;;) {
		uint32_t tok = fdt_be32(p);
		p += 4;
		switch (tok) {
		case FDT_BEGIN_NODE:
			depth++;
			in_target = in_target ||
				    (depth == 2 && streq((const char *)p, node));
			p = align4(skip_str(p));
			break;
		case FDT_END_NODE:
			if (in_target && depth == 2)
				return 0;	/* target done, prop not found */
			depth--;
			break;
		case FDT_PROP: {
			uint32_t plen = fdt_be32(p), nameoff = fdt_be32(p + 4);
			uintptr_t pv = p + 8;
			if (in_target && depth == 2 &&
			    streq((const char *)(strings + nameoff), prop)) {
				*val = pv;
				*len = plen;
				return 1;
			}
			p = align4(pv + plen);
			break;
		}
		case FDT_NOP:
			break;
		default:	/* FDT_END or garbage */
			return 0;
		}
	}
}

int fdt_top_str(uintptr_t fdt, const char *node, const char *prop,
		char *out, uint32_t max)
{
	uintptr_t val;
	uint32_t len;

	if (!max)
		return 0;
	if (!fdt_top_prop(fdt, node, prop, &val, &len))
		return 0;
	if (len > max - 1)
		len = max - 1;
	for (uint32_t i = 0; i < len; i++)
		out[i] = *(volatile char *)(val + i);
	out[len] = 0;
	return 1;
}

int fdt_node_walk(uintptr_t fdt, const char *target, fdt_prop_cb cb, void *ctx)
{
	if (!fdt || fdt_be32(fdt) != FDT_MAGIC)
		return 0;
	uintptr_t p = fdt + fdt_be32(fdt + 8);		/* off_dt_struct */
	uintptr_t strings = fdt + fdt_be32(fdt + 12);	/* off_dt_strings */
	int depth = 0, in_target = 0;
	const char *child_name = "";

	for (;;) {
		uint32_t tok = fdt_be32(p);
		p += 4;
		switch (tok) {
		case FDT_BEGIN_NODE: {
			const char *name = (const char *)p;
			depth++;
			if (!in_target && depth == 2 && streq(name, target))
				in_target = 1;
			if (in_target && depth == 3)
				child_name = name;
			p = align4(skip_str(p));
			break;
		}
		case FDT_END_NODE:
			depth--;
			if (in_target && depth < 2)
				return 1;	/* target done */
			break;
		case FDT_PROP: {
			uint32_t plen = fdt_be32(p), nameoff = fdt_be32(p + 4);
			uintptr_t pv = p + 8;
			const char *pname = (const char *)(strings + nameoff);
			if (in_target && depth >= 2 && depth <= 3) {
				const char *node = depth == 2 ? target : child_name;
				if (cb(node, pname, pv, plen, ctx))
					return 1;	/* cb asked to stop */
			}
			p = align4(pv + plen);
			break;
		}
		case FDT_NOP:
			break;
		default:	/* FDT_END or garbage */
			return 0;
		}
	}
}
