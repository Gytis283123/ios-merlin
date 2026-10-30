/*
 * Milestone 4: act as iBoot for xnu.
 *
 * mkpayload.py already resolved the kernel's chained fixups and built the
 * ADT, so this only has to: find the payload in the ABL ramdisk, copy the
 * segments to phys_base + (vmaddr - virt_base), place the ADT and
 * boot_args behind the kernel, and jump to the entry point with the MMU
 * and caches off, x0 = boot_args (physical).
 */
#include <stdint.h>
#include "console.h"
#include "fdt.h"
#include "loader.h"

#define BOOT_LINE_LENGTH	608
#define PAGE_16K		0x4000UL

#define rsr(r) ({ uint64_t _v; __asm__ volatile("mrs %0, " r : "=r"(_v)); _v; })

struct payload_seg {
	uint64_t vmaddr, vmsize, file_off, file_size;
};

struct payload {
	char magic[8];
	uint32_t version, nsegs;
	uint64_t virt_base, entry_va, adt_off, adt_size, kernel_end;
	uint64_t phys_base, mem_size;
	char cmdline[BOOT_LINE_LENGTH];
	struct payload_seg segs[];
};

/* pexpert/pexpert/arm64/boot.h, Revision/Version 2 */
struct boot_video {
	uint64_t v_baseAddr, v_display, v_rowBytes, v_width, v_height, v_depth;
};

struct boot_args {
	uint16_t Revision, Version;
	uint64_t virtBase, physBase, memSize, topOfKernelData;
	struct boot_video Video;
	uint32_t machineType;
	uint64_t deviceTreeP;
	uint32_t deviceTreeLength;
	char CommandLine[BOOT_LINE_LENGTH];
	uint64_t bootFlags, memSizeActual;
};

_Static_assert(__builtin_offsetof(struct payload, segs) == 0x2a8, "payload header layout");
_Static_assert(__builtin_offsetof(struct boot_args, Video) == 40, "boot_args layout");
_Static_assert(__builtin_offsetof(struct boot_args, CommandLine) == 108, "boot_args layout");
_Static_assert(sizeof(struct boot_args) == 736, "boot_args layout");

/* MMU off: everything is Device memory, so copy in aligned 8-byte words. */
static void copy64(uintptr_t dst, uintptr_t src, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	volatile const uint64_t *s = (volatile const uint64_t *)src;
	for (uint64_t i = 0; i < (n + 7) / 8; i++)
		d[i] = s[i];
}

static void zero64(uintptr_t dst, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	for (uint64_t i = 0; i < n / 8; i++)
		d[i] = 0;
}

/* ---- ADT patching -----------------------------------------------------
 * Apple device tree blob: no header, node = {u32 nprops, u32 nchildren,
 * props..., children...}; prop = {char name[32], u32 size (bit31 =
 * placeholder), value padded to 4}.  The kernel reads /chosen's
 * dram-base/dram-size for the managed memory range, so a relocated
 * payload must rewrite dram-base in the copy we hand it. */
static uint32_t ld32(uintptr_t p)
{
	return *(const volatile uint32_t *)p;
}

static void st32(uintptr_t p, uint32_t v)
{
	*(volatile uint32_t *)p = v;
}

static int name_is(uintptr_t p, const char *s)
{
	const volatile char *n = (const volatile char *)p;

	for (int i = 0; i < 32; i++) {
		if (n[i] != s[i])
			return 0;
		if (!n[i])
			return 1;
	}
	return 0;
}

static int str_is(uintptr_t p, const char *s)
{
	const volatile char *v = (const volatile char *)p;

	for (; *s; s++, v++)
		if (*v != *s)
			return 0;
	return *v == 0;
}

static uintptr_t node_end(uintptr_t n)
{
	uint32_t np = ld32(n), nc = ld32(n + 4);
	uintptr_t p = n + 8;

	for (uint32_t i = 0; i < np; i++) {
		uint32_t len = ld32(p + 32) & 0x7fffffff;
		p += 36 + ((len + 3) & ~3UL);
	}
	for (uint32_t i = 0; i < nc; i++)
		p = node_end(p);
	return p;
}

static int adt_set_dram_base(uintptr_t adt, uint64_t base)
{
	uint32_t np = ld32(adt), nc = ld32(adt + 4);
	uintptr_t p = adt + 8;

	for (uint32_t i = 0; i < np; i++) {
		uint32_t len = ld32(p + 32) & 0x7fffffff;
		p += 36 + ((len + 3) & ~3UL);
	}
	for (uint32_t c = 0; c < nc; c++) {
		uintptr_t child = p;
		uint32_t cnp = ld32(child);
		uintptr_t q = child + 8;
		int chosen = 0;

		for (uint32_t i = 0; i < cnp; i++) {
			uint32_t len = ld32(q + 32) & 0x7fffffff;
			if (name_is(q, "name") && str_is(q + 36, "chosen"))
				chosen = 1;
			q += 36 + ((len + 3) & ~3UL);
		}
		if (chosen) {
			q = child + 8;
			for (uint32_t i = 0; i < cnp; i++) {
				uint32_t len = ld32(q + 32) & 0x7fffffff;
				if (name_is(q, "dram-base") && len == 8) {
					/* value is 4-byte aligned: two word stores */
					st32(q + 36, (uint32_t)base);
					st32(q + 40, (uint32_t)(base >> 32));
					__asm__ volatile("dsb sy" ::: "memory");
					return 0;
				}
				q += 36 + ((len + 3) & ~3UL);
			}
		}
		p = node_end(child);
	}
	return -1;
}

static int mem_writable(uintptr_t pa)
{
	volatile uint32_t *w = (volatile uint32_t *)pa;
	uint32_t save = *w;

	*w = 0x5a5a5a5a;
	__asm__ volatile("dsb sy" ::: "memory");
	uint32_t got = *w;
	*w = save;
	__asm__ volatile("dsb sy" ::: "memory");
	return got == 0x5a5a5a5a;
}

/* Some MTK DRAM windows are firewalled from the non-secure world
 * (0xB0000000 on merlin kept nothing we wrote).  Probe the entry, the
 * middle of the kernel image and the ADT landing spot; fall back to the
 * other aligned 256MB-ish bases until one holds.  The declared base is
 * always tried first, so a healthy phone behaves exactly as before. */
static uint64_t choose_base(const struct payload *p)
{
	static const uint64_t fallback[] = {
		0x90000000UL, 0xa0000000UL, 0x80000000UL, 0xb0000000UL,
	};
	uint64_t cand[1 + sizeof(fallback) / sizeof(fallback[0])];
	uint64_t eoff = p->entry_va - p->virt_base;
	uint64_t koff = p->kernel_end - p->virt_base;
	unsigned n = 0;

	cand[n++] = p->phys_base;
#ifdef SHIM_RELOC_TEST
	/* Test hook for the QEMU rig: pretend the declared base failed so the
	 * fallback path (copy + ADT dram-base patch) gets exercised. */
	cand[0] = SHIM_RELOC_TEST;
#endif
	for (unsigned i = 0; i < sizeof(fallback) / sizeof(fallback[0]); i++) {
		unsigned j;

		for (j = 0; j < n; j++)
			if (cand[j] == fallback[i])
				break;
		if (j == n)
			cand[n++] = fallback[i];
	}

	for (unsigned i = 0; i < n; i++) {
		uint64_t b = cand[i];

		if (mem_writable(b) && mem_writable(b + eoff) &&
		    mem_writable(b + koff / 2) && mem_writable(b + koff))
			return b;
	}
	return 0;
}

/* Commit dirty lines to the point of coherency (LK may have left EL2's
 * caches enabled, in which case our plain stores never reached DRAM). */
static void clean_dcache(uintptr_t start, uintptr_t end)
{
	start &= ~63UL;
	for (uintptr_t p = start; p < end; p += 64)
		__asm__ volatile("dc civac, %0" :: "r"(p) : "memory");
	__asm__ volatile("dsb sy" ::: "memory");
}

static int magic_ok(const char *m)
{
	static const char want[] = "SWEETXNU";
	for (int i = 0; i < 8; i++)
		if (m[i] != want[i])
			return 0;
	return 1;
}

typedef void (*xnu_entry_t)(uint64_t boot_args_pa);

/* Black box: one DRAM page above the payload copy.  The watchdog resets the
 * phone ~23 s after we stop petting it, so the next boot reads this page and
 * prints how far the previous one got - a post-mortem even when the screen
 * is ambiguous.  (0xBFFFF000 is the top of the 256MB bank we hand xnu.) */
#define BB_PA		0xBFFFF000UL
#define BB_MAGIC	0x424C4F4721UL		/* "BLOG!" */

struct bb_log {
	uint64_t magic, seq, stage;
	char text[64];
};

static volatile struct bb_log *const bb = (volatile struct bb_log *)BB_PA;

void bb_set(uint64_t stage, const char *s)
{
	if (bb->magic != BB_MAGIC) {
		bb->seq = 0;
		bb->magic = BB_MAGIC;
	}
	bb->seq++;
	bb->stage = stage;
	int i;
	for (i = 0; i < 63 && s[i]; i++)
		bb->text[i] = s[i];
	bb->text[i] = 0;	/* terminate past a shorter previous boot's text */
	bb->text[63] = 0;
	__asm__ volatile("dsb sy" ::: "memory");
}

void bb_report(void)
{
	/* Snapshot on first call: after that bb_set() overwrites the page with
	 * the current run's progress, but we keep showing the previous run. */
	static int taken, valid;
	static uint64_t seq, stage;
	static char text[64];

	if (!taken) {
		taken = 1;
		if (bb->magic == BB_MAGIC) {
			valid = 1;
			seq = bb->seq;
			stage = bb->stage;
			for (int i = 0; i < 64; i++)
				text[i] = bb->text[i];
		}
	}
	if (!valid) {
		con_str("BBOX", "empty (first boot)");
		return;
	}
	con_hex2("BBOX", "n=", (uint32_t)seq, "stage=", (uint32_t)stage);
	con_str("BBOX", text);
}

/* LK on mt6768 runs at EL2 and boots Linux, whose head.S drops to EL1
 * itself - so it hands "the kernel" control at EL2.  xnu expects EL1: its
 * first instruction is `msr OSLAR_EL1` and its MMU setup programs
 * SCTLR_EL1, so at EL2 it faults before start.s can even draw its
 * stage-0 band.  Drop the CPU to EL1 here, iBoot-style. */
static void drop_to_el1(void)
{
	uint64_t el;

	__asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
	if ((el >> 2) != 2)
		return;

	__asm__ volatile(
		"mov	x0, #(1 << 31)\n"	/* HCR_EL2.RW: EL1 is AArch64 */
		"msr	hcr_el2, x0\n"
		"mov	x1, #0x33ff\n"		/* CPTR_EL2: no FP/SIMD traps */
		"msr	cptr_el2, x1\n"
		"mov	x1, #3\n"		/* CNTHCTL_EL2: EL1PCTEN|EL1PCEN */
		"msr	cnthctl_el2, x1\n"
		"mov	x1, sp\n"		/* EL1h eret keeps this stack */
		"msr	sp_el1, x1\n"
		"isb\n"
		"mov	x0, #0x3c5\n"		/* DAIF masked, EL1h */
		"msr	spsr_el2, x0\n"
		"adr	x0, 1f\n"
		"msr	elr_el2, x0\n"
		"eret\n"
		"1:\n"
		:
		:
		: "x0", "x1", "memory");
}

const char *loader_boot(uintptr_t dtb)
{
	uint64_t rd_start, rd_end;

	bb_set(3, "loader entry");
	if (!fdt_chosen_u64(dtb, "linux,initrd-start", &rd_start) ||
	    !fdt_chosen_u64(dtb, "linux,initrd-end", &rd_end))
		return "no initrd in /chosen";
	con_hex2("INITRD", "lo=", rd_start, "hi=", rd_end);

	const struct payload *p = (const struct payload *)rd_start;
	if (!magic_ok(p->magic))
		return "no SWEETXNU payload";
	if (p->version != 1 || (p->adt_off & 7) || (rd_start & 7))
		return "bad payload header";
	bb_set(4, "payload header ok");

	uint64_t base = choose_base(p);
	if (!base) {
		con_big_mode(4);
		con_clear(RED);
		con_big_str("HOLD", "no writable kernel base");
		con_big_hex("WANT", (uint32_t)p->phys_base);
		con_big_str("NEXT", "power-cycle, reflash");
		for (;;)
			__asm__ volatile("wfi");
	}
	uint64_t pa_of_va_base = base - p->virt_base;	/* pa = va + this */
	con_hex2("PHYS", "base=", (uint32_t)base, "size=", (uint32_t)p->mem_size);
	if (base != p->phys_base)
		con_hex("RELOC", base);
	con_hex("VIRT", p->virt_base);
	con_hex("ENTRY", p->entry_va);

	/* The payload must not overlap where the kernel goes. */
	if (rd_end > base && rd_start < base + p->mem_size)
		return "ramdisk overlaps kernel memory";

	/* Locate the entry in the payload before copying, so the source bytes
	 * the copy will use can be inspected. */
	uint64_t entry_off = 0;
	for (uint32_t i = 0; i < p->nsegs; i++) {
		const struct payload_seg *s = &p->segs[i];
		if (p->entry_va >= s->vmaddr && p->entry_va < s->vmaddr + s->vmsize)
			entry_off = s->file_off + (p->entry_va - s->vmaddr);
	}
	con_hex2("ESRC", "off=", entry_off, "pa=", p->entry_va + pa_of_va_base);

	/* LK ran with its caches on and then turned them off before jumping to
	 * us, so the ramdisk may still be dirty in its cache: our uncached
	 * reads would then see stale DRAM.  Read the entry word before and
	 * after committing the source, then copy from the clean version. */
	uint32_t s0 = *(volatile uint32_t *)(rd_start + entry_off);
	clean_dcache(rd_start, rd_start + ((p->adt_off + p->adt_size + 63) & ~63UL));
	uint32_t s1 = *(volatile uint32_t *)(rd_start + entry_off);
	con_hex2("SRCWORD", "s0=", s0, "s1=", s1);

	uintptr_t dst_entry = 0;
	for (uint32_t i = 0; i < p->nsegs; i++) {
		const struct payload_seg *s = &p->segs[i];
		uintptr_t dst = s->vmaddr + pa_of_va_base;
		if (p->entry_va >= s->vmaddr && p->entry_va < s->vmaddr + s->vmsize)
			dst_entry = dst + (p->entry_va - s->vmaddr);
		copy64(dst, rd_start + s->file_off, s->file_size);
		if (s->vmsize > s->file_size)
			zero64(dst + ((s->file_size + 7) & ~7UL), s->vmsize - ((s->file_size + 7) & ~7UL));
	}
	con_hex2("SEGS", "n=", p->nsegs, "end=", p->kernel_end + pa_of_va_base);
	con_hex("EDST", dst_entry);
	bb_set(5, "segments copied");

	/* ADT, then boot_args, behind the kernel; everything below topOfKernelData is ours. */
	uintptr_t adt_pa = p->kernel_end + pa_of_va_base;
	copy64(adt_pa, rd_start + p->adt_off, p->adt_size);
	if (base != p->phys_base && adt_set_dram_base(adt_pa, base)) {
		con_big_mode(4);
		con_clear(RED);
		con_big_str("HOLD", "cannot patch ADT dram-base");
		con_big_hex("PHYS", (uint32_t)base);
		con_big_str("NEXT", "power-cycle, reflash");
		for (;;)
			__asm__ volatile("wfi");
	}
	uintptr_t ba_pa = (adt_pa + p->adt_size + PAGE_16K - 1) & ~(PAGE_16K - 1);
	uintptr_t top = ba_pa + PAGE_16K;

	zero64(ba_pa, PAGE_16K);
	volatile struct boot_args *ba = (volatile struct boot_args *)ba_pa;
	ba->Revision = 2;
	ba->Version = 2;
	ba->virtBase = p->virt_base;
	ba->physBase = base;
	ba->memSize = p->mem_size;
	ba->topOfKernelData = top;
	ba->Video.v_baseAddr = FB_BASE;
	ba->Video.v_display = 1;
	ba->Video.v_rowBytes = FB_STRIDE;
	ba->Video.v_width = FB_W;
	ba->Video.v_height = FB_H;
	ba->Video.v_depth = 32;
	ba->deviceTreeP = adt_pa - pa_of_va_base;	/* xnu reads it with the MMU on: a VA */
	ba->deviceTreeLength = (uint32_t)p->adt_size;
	for (int i = 0; i < BOOT_LINE_LENGTH; i++)
		ba->CommandLine[i] = p->cmdline[i];
	ba->memSizeActual = p->mem_size;
	con_hex2("BOOTARG", "pa=", ba_pa, "top=", top);
	bb_set(6, "bootargs ready");

	uintptr_t entry_pa = p->entry_va + pa_of_va_base;
	uint64_t el;
	__asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
	con_hex2("MODE", "el=", (uint32_t)(el >> 2), 0, 0);
	if ((el >> 2) == 2) {
		con_hex("HCR_EL2", rsr("hcr_el2"));
		con_hex("CPTR_EL2", rsr("cptr_el2"));
		con_hex("SCTLR_EL2", rsr("sctlr_el2"));
	}
	con_hex("JUMP", entry_pa);
	con_str("XNU", "jumping (fbcon clears screen)");
	bb_set(7, "dropping to EL1");

	drop_to_el1();

	__asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
	con_hex2("POSTEL", "el=", (uint32_t)(el >> 2), 0, 0);
	con_hex("SCTLR_EL1", rsr("sctlr_el1"));
	con_hex("TTBR0_EL1", rsr("ttbr0_el1"));
	con_hex("TCR_EL1", rsr("tcr_el1"));
	bb_set(8, "at EL1, checking entry");

	/* The entry word as *this* translation regime sees it.  If this is not
	 * the `b _start_first_cpu` instruction, the kernel never got a chance:
	 * either the copies sat in a cache LK left enabled (below), or the PA
	 * is not where we think it is. */
	{
		uint32_t w0 = *(volatile uint32_t *)entry_pa;
		uint32_t w1 = *(volatile uint32_t *)(entry_pa + 4);
		con_hex2("WORD0", "w0=", w0, "w1=", w1);
	}

	/* LK may run at EL2 with its caches on; commit everything we wrote to
	 * DRAM before EL1 fetches it with the MMU off. */
	clean_dcache(base, top);
	{
		uint32_t w0 = *(volatile uint32_t *)entry_pa;
		uint32_t w1 = *(volatile uint32_t *)(entry_pa + 4);
		con_hex2("WORD1", "w0=", w0, "w1=", w1);
	}

	/* Is the destination writable at all from this translation regime? */
	{
		volatile uint32_t *ep = (volatile uint32_t *)entry_pa;
		uint32_t save = ep[0];
		ep[0] = 0xdeadbeef;
		__asm__ volatile("dsb sy" ::: "memory");
		uint32_t got = ep[0];
		ep[0] = save;
		__asm__ volatile("dsb sy" ::: "memory");
		con_hex2("WRTEST", "set=", (uint32_t)0xdeadbeef, "got=", got);
	}

	/* Map which parts of DRAM actually accept writes: some MTK regions
	 * (TEE/modem carve-outs) are firewalled from the non-secure world, and
	 * the kernel must not be placed inside one.  Write, read back, restore.
	 * Bit i of MEMOK = probe[i] held the pattern. */
	uint64_t memok = 0;
	{
		static const uintptr_t probe[] = {
			0x47c90000UL, 0x80000000UL, 0x90000000UL, 0xa0000000UL,
			0xa8000000UL, 0xb0000000UL, 0xb0400000UL, 0xb0800000UL,
			0xb0c00000UL, 0xb1000000UL, 0xb148b488UL, 0xb1800000UL,
			0xb1c00000UL, 0xb2000000UL, 0xb2400000UL, 0xb2800000UL,
			0xb3000000UL, 0xb8000000UL, 0xbc000000UL, 0xbfffe000UL,
		};
		const unsigned n = sizeof(probe) / sizeof(probe[0]);
		uint32_t g_b0 = 0, g_ent = 0, g_top = 0;

		for (unsigned i = 0; i < n; i++) {
			volatile uint32_t *p = (volatile uint32_t *)probe[i];
			uint32_t save = *p;
			*p = 0xdeadbeef;
			__asm__ volatile("dsb sy" ::: "memory");
			uint32_t got = *p;
			*p = save;
			__asm__ volatile("dsb sy" ::: "memory");
			if (got == 0xdeadbeef)
				memok |= 1ULL << i;
			if (probe[i] == 0xb0000000UL)
				g_b0 = got;
			else if (probe[i] == 0xb148b488UL)
				g_ent = got;
			else if (probe[i] == 0xbfffe000UL)
				g_top = got;
		}
		con_hex("MEMOK", memok);
		con_hex2("MEMB0", "r=", g_b0, "ent=", g_ent);
		con_hex2("MEMTOP", "r=", g_top, "n=", n);
	}

	/* The destination must hold the source's entry word; if it does not,
	 * the copy never reached DRAM (a firewalled MTK carve-out, or LK cache
	 * state) and jumping would fault at EL1 with no way to see why.  Hold a
	 * big-font page instead, so one photo names the bad base and the MEMOK
	 * map around it.  (0x80000000 is the current phone base; the previous
	 * 0xB0000000 band failed exactly here.) */
	if (*(volatile uint32_t *)entry_pa != s1) {
		con_big_mode(4);
		con_clear(BLUE);
		con_big_str("HOLD", "destination not writable");
		con_big_hex("PHYS", (uint32_t)p->phys_base);
		con_big_hex("ENTRY", (uint32_t)entry_pa);
		con_big_hex("WANT", s1);
		con_big_hex("GOT", *(volatile uint32_t *)entry_pa);
		con_big_hex("MEMOK", (uint32_t)memok);
		con_big_str("NEXT", "power-cycle, reflash");
		for (;;)
			__asm__ volatile("wfi");
	}

	/* Everything was written with the MMU and caches off; drop any stale
	 * I-cache lines too - now at EL1, where the flush actually counts. */
	__asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
	bb_set(9, "xnu entry");
	((xnu_entry_t)entry_pa)(ba_pa);
	return "xnu returned";
}
