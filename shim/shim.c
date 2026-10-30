/*
 * Milestone 2: one boot answers the questions that decide the XNU port.
 *   - CPU feature registers (16K granule, GIC sysreg interface)
 *   - PSCI/SMCCC version and which PSCI calls the Qualcomm TZ offers
 *   - SMP: PSCI CPU_ON for the 7 secondaries, each reports its MPIDR
 *   - GICv3 Group 1 IRQ from the virtual timer (INTID 19 on Qualcomm)
 * Any unexpected exception paints a blue panic screen.
 */
#include <stdint.h>
#include "console.h"
#include "mmu.h"
#include "loader.h"
#include "fdt.h"
#include "ufs.h"
#include "ramfb.h"

#define IMEM_RESTART_REASON	0x146aa65cUL	/* qcom,msm-imem restart_reason@65c */
#define RESTART_BOOTLOADER	0x77665500U
#define PSHOLD			0x0c264000UL

#define GICD_BASE		0x17a00000UL
#define GICR_BASE		0x17a60000UL
#define GICR_SIZE		0x100000UL
#define GICR_PE_SIZE		0x20000UL
#define GICR_TYPER		0x08
#define GICR_WAKER		0x14
#define GICR_SGI		0x10000
#define GICR_IGROUPR0		(GICR_SGI + 0x080)
#define GICR_ISENABLER0		(GICR_SGI + 0x100)
#define GICR_ICENABLER0		(GICR_SGI + 0x180)
#define GICR_IPRIORITYR		(GICR_SGI + 0x400)
#define GICR_ISPENDR0		(GICR_SGI + 0x200)
#define GICR_ISACTIVER0		(GICR_SGI + 0x300)
#define GICR_ICFGR1		(GICR_SGI + 0xc04)
#define VTIMER_INTID		19	/* DT: <GIC_PPI 3 ...>, not the usual 27 */
#define PTIMER_INTID		18	/* DT: <GIC_PPI 2 ...> */
#define SGI_INTID		1

#define PSCI_VERSION		0x84000000UL
#define PSCI_CPU_SUSPEND	0xc4000001UL
#define PSCI_CPU_OFF		0x84000002UL
#define PSCI_CPU_ON		0xc4000003UL
#define PSCI_MIGRATE_INFO_TYPE	0x84000006UL
#define PSCI_SYSTEM_RESET	0x84000009UL
#define PSCI_FEATURES		0x8400000aUL
#define PSCI_SYSTEM_SUSPEND	0xc400000eUL
#define PSCI_SYSTEM_RESET2	0xc4000012UL
#define SMCCC_VERSION		0x80000000UL

#define NR_CPUS			8

#define rsr(r) ({ uint64_t _v; __asm__ volatile("mrs %0, " r : "=r"(_v)); _v; })
#define wsr(r, v) __asm__ volatile("msr " r ", %0" : : "r"((uint64_t)(v)))
#define isb() __asm__ volatile("isb" ::: "memory")

static inline uint32_t rd32(uintptr_t a) { return *(volatile uint32_t *)a; }
static inline uint64_t rd64(uintptr_t a) { return *(volatile uint64_t *)a; }
static inline void wr32(uintptr_t a, uint32_t v) { *(volatile uint32_t *)a = v; }
static inline void wr8(uintptr_t a, uint8_t v) { *(volatile uint8_t *)a = v; }

extern char secondary_entry[];

static const char *stage;	/* set at runtime: no absolute pointers in data */
static volatile uint64_t sec_mpidr[NR_CPUS];
static volatile uint64_t sec_probe[4];	/* CPU1 redistributor write test */
static volatile uint32_t irq_count, irq_other, irq_last;
static volatile int irq_src;

/* ICC_SGI1R_EL1 value targeting the calling core only. */
static uint64_t sgi_self(unsigned id)
{
	uint64_t m = rsr("mpidr_el1");
	return ((m >> 16) & 0xff) << 32 |	/* Aff2 */
	       ((m >> 8) & 0xff) << 16 |	/* Aff1 */
	       (uint64_t)id << 24 |
	       (1U << (m & 0xf));		/* target list: Aff0 */
}

static uint64_t smc(uint64_t fn, uint64_t a1, uint64_t a2, uint64_t a3)
{
	register uint64_t x0 __asm__("x0") = fn;
	register uint64_t x1 __asm__("x1") = a1;
	register uint64_t x2 __asm__("x2") = a2;
	register uint64_t x3 __asm__("x3") = a3;
	__asm__ volatile("smc #0"
			 : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)
			 :
			 : "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11",
			   "x12", "x13", "x14", "x15", "x16", "x17", "memory");
	return x0;
}

static uint64_t now(void)
{
	isb();
	return rsr("cntpct_el0");
}

/* ---- MTK toprgu AP watchdog (merlin mt6768; wdt_v2 register map) ----
 * LK hands us the phone with the watchdog armed; if we neither feed nor
 * shut it down before it times out, toprgu resets the box mid-boot (seen
 * on the first phone boots: continuous reboots even with a do-nothing
 * shim).  Offsets/keys from the stock mt6768 kernel driver
 * (drivers/watchdog/mediatek/.../wdt_v2/mtk_wdt.h):
 *   MODE    +0x00  key 0x22000000, bit0 = enable
 *   LENGTH  +0x04  (armed timeout)
 *   RESTART +0x08  write 0x1971 to re-arm the counter
 *   STATUS  +0x0c  bit31 = last reset was this hw watchdog
 *   SWRST   +0x14  key 0x1209 = immediate reset (wrong key: no-op) */
#define MTK_RGU			0x10007000UL
#define RGU_WDT_MODE		0x00
#define RGU_WDT_LENGTH		0x04
#define RGU_WDT_RESTART		0x08
#define RGU_WDT_STATUS		0x0c
#define RGU_WDT_NONRST_REG	0x20
#define RGU_WDT_NONRST_REG2	0x24
static void wdt_pet(void);

static void delay_ms(unsigned ms)
{
	uint64_t end = now() + rsr("cntfrq_el0") / 1000 * ms;
	uint64_t pet = rsr("cntfrq_el0") / 8;	/* throttle: every ~125ms */
	uint64_t next = now() + pet;

	while (now() < end) {
		if (now() >= next) {
			wdt_pet();
			next += pet;
		}
	}
	wdt_pet();
}

static void wdt_pet(void)
{
#ifdef MERLIN
	wr32(MTK_RGU + RGU_WDT_RESTART, 0x1971);
#endif
}

static void __attribute__((noreturn)) reset(unsigned after_s)
{
	con_skip();
	con_str("RESET", after_s > 20 ? "in 40s" : "in 20s");
	delay_ms(after_s * 1000);
#ifndef MERLIN
	wr32(IMEM_RESTART_REASON, RESTART_BOOTLOADER);	/* qualcomm imem only */
#endif
	__asm__ volatile("dsb sy" ::: "memory");
	smc(PSCI_SYSTEM_RESET, 0, 0, 0);
#ifndef MERLIN
	wr32(PSHOLD, 0);				/* qualcomm pshold only */
#endif
	for (;;)
		__asm__ volatile("wfe");
}

/* ---- exceptions ---- */

static void irq_handler(void)
{
	uint64_t iar = rsr("icc_iar1_el1");
	uint32_t id = iar & 0xffffff;

	if (id >= 1020 && id <= 1023)
		return;	/* spurious */
	irq_last = id;
	if (id == (uint32_t)irq_src)
		irq_count++;
	else
		irq_other++;
	if (id == VTIMER_INTID)
		wsr("cntv_tval_el0", rsr("cntfrq_el0") / 100);	/* 10 ms */
	else if (id == PTIMER_INTID)
		wsr("cntp_tval_el0", rsr("cntfrq_el0") / 100);
	wsr("icc_eoir1_el1", iar);
	isb();
}

void exc_handler(uint64_t slot, uint64_t *regs)
{
	if (slot == 5) {	/* IRQ from current EL, SPx */
		irq_handler();
		return;
	}
#ifdef MERLIN
	/* Append below the diag facts: the screen is our only serial. */
	con_skip();
	con_str("PANIC", "exception");
#else
	con_clear(BLUE);
#endif
	uint32_t kind = slot & 3;
	static const char kindname[4][8] = {"SYNC", "IRQ", "FIQ", "SERROR"};
	con_str("PANIC", kindname[kind]);
	con_hex2("SLOT", "n=", slot, "cpu=", rsr("mpidr_el1"));
	con_str("STAGE", stage);
	con_hex("ESR", rsr("esr_el1"));
	con_hex("ELR", rsr("elr_el1"));
	con_hex("FAR", rsr("far_el1"));
	con_hex("SPSR", rsr("spsr_el1"));
	con_hex("X0", regs[0]);
	con_hex("X1", regs[1]);
	con_hex("X30", regs[29]);	/* interrupted lr, saved by exc_common */
	reset(40);
}

/* ---- SMP ---- */

static uintptr_t find_gicr(void);

void secondary_main(uint64_t idx)
{
	sec_mpidr[idx] = rsr("mpidr_el1") | (1ULL << 63);
#ifndef MERLIN
	if (idx == 1) {
		uintptr_t r = find_gicr();
		if (r) {
			sec_probe[0] = rd32(r + GICR_IGROUPR0);
			wr32(r + GICR_IGROUPR0, 0xffffffff);
			sec_probe[1] = rd32(r + GICR_IGROUPR0);
			wr8(r + GICR_IPRIORITYR + 19, 0xa0);
			sec_probe[2] = rd32(r + GICR_IPRIORITYR + 16);
		}
		sec_probe[3] = r ? 1 : 0xdead;
	}
#endif
	__asm__ volatile("dsb sy" ::: "memory");
	smc(PSCI_CPU_OFF, 0, 0, 0);
}

static void __attribute__((unused)) test_smp(void)
{
	stage = "smp";
	uint64_t self = rsr("mpidr_el1") & 0xffffff;
	int64_t ret[NR_CPUS];

	for (int i = 1; i < NR_CPUS; i++)
		ret[i] = smc(PSCI_CPU_ON, (uint64_t)i << 8, (uintptr_t)secondary_entry, i);
	delay_ms(500);
	for (int i = 1; i < NR_CPUS; i++) {
		char label[] = "CPU0";
		label[3] = '0' + i;
		if (((uint64_t)i << 8) == self)
			con_str(label, "is boot cpu");
		else
			con_hex2(label, "ret=", (uint32_t)ret[i], "mpidr=",
				 (uint32_t)sec_mpidr[i] | (sec_mpidr[i] ? 0 : 0xdead0000));
	}
}

/* ---- GIC + timer ---- */

static uintptr_t find_gicr(void)
{
	uint64_t aff = rsr("mpidr_el1");
	uint32_t want = (aff & 0xffffff) | ((aff >> 8) & 0xff000000);

	for (uintptr_t off = 0; off < GICR_SIZE; off += GICR_PE_SIZE) {
		uint64_t typer = rd64(GICR_BASE + off + GICR_TYPER);
		if ((uint32_t)(typer >> 32) == want)
			return GICR_BASE + off;
		if (typer & (1 << 4))	/* Last */
			break;
	}
	return 0;
}

static void gicd_wait_rwp(void)
{
	for (int i = 0; i < 1000000 && (rd32(GICD_BASE) & (1U << 31)); i++)
		;
}

/* Run one interrupt source for ~300 ms and report what the GIC saw. */
static void irq_window(const char *label, uintptr_t r, int src)
{
	uint64_t f = rsr("cntfrq_el0");
	uint32_t pend = 0, act = 0, isr = 0, hppi = 0x3ff, ist = 0;

	irq_count = irq_other = 0;
	irq_last = 0x3ff;
	irq_src = src;
	if (src == VTIMER_INTID) {
		wsr("cntv_tval_el0", f / 100);
		wsr("cntv_ctl_el0", 1);
	} else if (src == PTIMER_INTID) {
		wsr("cntp_tval_el0", f / 100);
		wsr("cntp_ctl_el0", 1);
	}
	isb();
	/* sample state with IRQs still masked, after the first period */
	uint64_t t = now() + f / 50;
	while (now() < t)
		;
	if (src == SGI_INTID)
		wsr("icc_sgi1r_el1", sgi_self(SGI_INTID));
	isb();
	ist = src == PTIMER_INTID ? rsr("cntp_ctl_el0") : rsr("cntv_ctl_el0");
	pend = rd32(r + GICR_ISPENDR0);
	act = rd32(r + GICR_ISACTIVER0);
	isr = rsr("isr_el1");
	hppi = rsr("icc_hppir1_el1");

	__asm__ volatile("msr daifclr, #2" ::: "memory");
	t = now() + f * 3 / 10;
	/* SGI: one already sent above, send 9 more 10 ms apart -> expect 10 */
	uint64_t next = now() + f / 100;
	for (int sent = 1; now() < t;)
		if (src == SGI_INTID && sent < 10 && now() >= next) {
			wsr("icc_sgi1r_el1", sgi_self(SGI_INTID));
			isb();
			sent++;
			next += f / 100;
		}
	__asm__ volatile("msr daifset, #2" ::: "memory");
	wsr("cntv_ctl_el0", 0);
	wsr("cntp_ctl_el0", 0);
	isb();

	con_hex2(label, "irqs=", irq_count, "other=", irq_other);
	con_hex2(" pre", "pend=", pend, "act=", act);
	con_hex2(" pre", "isr=", isr, "hppi=", hppi);
	con_hex2(" pre", "tctl=", ist, "last=", irq_last);
}

static void test_gic(void)
{
	stage = "gic sre";
	uint64_t sre = rsr("icc_sre_el1");
	if (!(sre & 1)) {
		wsr("icc_sre_el1", sre | 1);
		isb();
	}
	if (!(rsr("icc_sre_el1") & 1)) {
		con_str("GIC", "no sysreg iface, skip");
		return;
	}

	stage = "gic dist";
	uint32_t dctlr = rd32(GICD_BASE);
	/* Non-secure view (DS=0): bit0 EnableGrp1, bit1 EnableGrp1A, bit4 ARE_NS; Linux writes 0x13 */
	wr32(GICD_BASE, dctlr | 0x13);
	gicd_wait_rwp();
	con_hex2("GICD", "was=", dctlr, "now=", rd32(GICD_BASE));

	stage = "gic redist";
	uintptr_t r = find_gicr();
	if (!r) {
		con_str("GICR", "not found");
		return;
	}
	uint32_t waker = rd32(r + GICR_WAKER);
	if (waker & 2) {
		wr32(r + GICR_WAKER, waker & ~2U);
		for (int i = 0; i < 100000 && (rd32(r + GICR_WAKER) & 4); i++)
			;
	}
	con_hex2("GICR", "base=", r, "waker=", rd32(r + GICR_WAKER));

	stage = "gic config";
	uint32_t grp = rd32(r + GICR_IGROUPR0);
	wr32(r + GICR_IGROUPR0, 0xffffffff);	/* NS view: secure bits are WI */
	uint32_t en_before = rd32(r + GICR_ISENABLER0);
	uint32_t pri_before = rd32(r + GICR_IPRIORITYR + 16);	/* INTIDs 16..19 */
	for (int id = 0; id < 32; id++)
		wr8(r + GICR_IPRIORITYR + id, 0xa0);
	wr32(r + GICR_ISENABLER0, (1U << VTIMER_INTID) | (1U << PTIMER_INTID) | (1U << SGI_INTID));
	con_hex2("ENABLE", "was=", en_before, "now=", rd32(r + GICR_ISENABLER0));
	(void)grp;
	(void)pri_before;

	uint64_t ctlr = rsr("icc_ctlr_el1");
	wsr("icc_ctlr_el1", ctlr & ~2ULL);	/* EOImode 0: EOIR also deactivates */
	wsr("icc_pmr_el1", 0xf0);
	wsr("icc_bpr1_el1", 0);
	wsr("icc_igrpen1_el1", 1);
	isb();
	con_hex2("ICC", "ctlr=", ctlr, "grpen1=", rsr("icc_igrpen1_el1"));

	stage = "gic vtimer";
	irq_window("VTIMER", r, VTIMER_INTID);
	stage = "gic sgi";
	irq_window("SGI1", r, SGI_INTID);
	wr32(r + GICR_ICENABLER0, 0xffffffff);
	isb();
}

/* ---- main ---- */

static void __attribute__((unused)) psci_line(const char *label, uint64_t fn)
{
	con_hex2(label, "feat=", smc(PSCI_FEATURES, fn, 0, 0), 0, 0);
}

static uint64_t scratch[8192];	/* 64KB, lives in our (later cacheable) image */

static uint64_t ticks_fill(uint32_t c)
{
	uint64_t t = now();
	con_clear(c);
	return now() - t;
}

static uint64_t ticks_mem(void)
{
	uint64_t t = now();
	for (int pass = 0; pass < 16; pass++)
		for (int i = 0; i < 8192; i++)
			scratch[i] = scratch[i] * 3 + i;
	return now() - t;
}

static uint32_t to_us(uint64_t ticks)
{
	return ticks * 10 / 192;	/* 19.2 MHz */
}

#ifdef MERLIN
/* ---- boot 1: dump what LK actually passed us, before anything risky ---- */

static char pline[128];
static const char hexd[] = "0123456789abcdef";
static int ncpus;

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static void fmt32(char *d, uint32_t v)
{
	for (int i = 0; i < 8; i++)
		d[i] = hexd[(v >> (4 * (7 - i))) & 0xf];
	d[8] = 0;
}

/* One console row: "<prop>=<value>" with the node name in the label column. */
static void line_prop(const char *prop, uintptr_t val, uint32_t len)
{
	uint32_t i = 0;

	for (; prop[i] && i < 40; i++)
		pline[i] = prop[i];
	pline[i++] = '=';

	uint32_t printable = len && *(volatile char *)(val + len - 1) == 0;
	for (uint32_t j = 0; j < len && printable; j++) {
		char c = *(volatile char *)(val + j);
		if (c && (c < 0x20 || c > 0x7e))
			printable = 0;
	}

	if (printable) {
		for (uint32_t j = 0; j < len && i < sizeof pline - 1; j++) {
			char c = *(volatile char *)(val + j);
			pline[i++] = c ? c : '|';	/* NULs separate strings */
		}
	} else if (len == 4) {
		fmt32(pline + i, fdt_be32(val));
		i += 8;
	} else if (len == 8) {
		for (int k = 0; k < 16; k++)
			pline[i + k] = hexd[(fdt_be64(val) >> (4 * (15 - k))) & 0xf];
		i += 16;
	} else if (len % 4 == 0 && len <= 24) {
		for (uint32_t o = 0; o < len && i < sizeof pline - 10; o += 4) {
			if (o)
				pline[i++] = ',';
			fmt32(pline + i, fdt_be32(val + o));
			i += 8;
		}
	} else {
		pline[i++] = 'l';
		pline[i++] = 'e';
		pline[i++] = 'n';
		pline[i++] = '=';
		fmt32(pline + i, len);
		i += 8;
	}
	pline[i] = 0;
}

static int chosen_cb(const char *node, const char *prop, uintptr_t val,
		     uint32_t len, void *ctx)
{
	int *n = ctx;

	if (*n >= 26)
		return 1;	/* cap the dump */
	(*n)++;
	line_prop(prop, val, len);
	con_str(node, pline);
	return 0;
}

static int cpus_cb(const char *node, const char *prop, uintptr_t val,
		   uint32_t len, void *ctx)
{
	(void)node;
	(void)ctx;
	if (len == 4 && streq(prop, "reg")) {
		con_hex2("CPU", "mpidr=", fdt_be32(val), 0, 0);
		ncpus++;
	}
	return 0;
}

/* Values shown on the big-font facts page (see shim_main); diag_fdt fills. */
#define BG_MAX		4
static uint64_t bg_memb[BG_MAX], bg_msz[BG_MAX];
static int bg_nmem;
static uint64_t bg_ilo, bg_ihi, bg_fb;
static int bg_has_ilo, bg_has_fb;
static uint32_t bg_tirq[4];
static int bg_ntirq;

static void diag_fdt(uintptr_t dtb)
{
	uintptr_t v;
	uint32_t l;
	uint64_t u;
	int n;

	con_hex2("DTB", "at=", (uint32_t)dtb, "magic=", dtb ? fdt_be32(dtb) : 0);
	con_hex2("EL", "cur=", (uint32_t)(rsr("currentel") >> 2), "mpidr=",
		 (uint32_t)(rsr("mpidr_el1") & 0xffffff));
	con_hex2("FREQ", "cntfrq=", (uint32_t)rsr("cntfrq_el0"), "sctlr=",
		 (uint32_t)rsr("sctlr_el1"));
	if (!dtb || fdt_be32(dtb) != 0xd00dfeedUL) {
		con_str("DTB", "no valid FDT from LK!");
		return;
	}

	/* The live memory banks LK patched in (the stock dts has a stub). */
	if (fdt_top_prop(dtb, "memory", "reg", &v, &l))
		for (uint32_t o = 0; o + 16 <= l && bg_nmem < BG_MAX; o += 16) {
			bg_memb[bg_nmem] = fdt_be64(v + o);
			bg_msz[bg_nmem] = fdt_be64(v + o + 8);
			bg_nmem++;
			con_hex("MEMBASE", fdt_be64(v + o));
			con_hex("MEMSIZE", fdt_be64(v + o + 8));
		}
	else
		con_str("MEM", "no /memory reg!");

	if (fdt_chosen_u64(dtb, "linux,initrd-start", &u)) {
		uint64_t e = 0;

		fdt_chosen_u64(dtb, "linux,initrd-end", &e);
		bg_ilo = u;
		bg_ihi = e;
		bg_has_ilo = 1;
		con_hex("INITLO", u);
		con_hex("INITHI", e);
	} else
		con_str("INITRD", "absent in /chosen");
	if (fdt_chosen_u64(dtb, "atag,videolfb-fb_base_l", &u)) {
		bg_fb = u;
		bg_has_fb = 1;
		con_hex("ATAGFB", u);
	}

	/* Everything else LK merged into /chosen (atags live in a child). */
	n = 0;
	fdt_node_walk(dtb, "chosen", chosen_cb, &n);
	n = 0;
	fdt_node_walk(dtb, "psci", chosen_cb, &n);

	if (fdt_top_prop(dtb, "timer", "interrupts", &v, &l)) {
		/* First four raw cells (type,num@id...) for the facts page. */
		for (uint32_t o = 0; o + 4 <= l && bg_ntirq < 4; o += 4)
			bg_tirq[bg_ntirq++] = fdt_be32(v + o);
		for (uint32_t o = 0; o + 4 <= l; o += 8)
			con_hex2("TIRQ", "c=", fdt_be32(v + o), "c=",
				 o + 8 < l ? fdt_be32(v + o + 8) : 0);
	}

	ncpus = 0;
	fdt_node_walk(dtb, "cpus", cpus_cb, 0);
	con_hex2("CPUS", "n=", ncpus, "nr=", NR_CPUS);
}

/* Disable the AP watchdog reset generation, mirroring the stock
 * mtk_wdt_v2.c disable sequence (MODE_KEY | clear MODE_ENABLE).  Bring-up
 * prefers hangs that stay on screen over rebooting phones out from under
 * the operator; wdt_pet() keeps the counter restarted meanwhile as a
 * belt-and-braces residual for any mode bit that eats the disarm write. */
static void wdt_disarm(void)
{
	uint32_t mode = rd32(MTK_RGU + RGU_WDT_MODE);

	mode |= 0x22000000u;		/* MTK_WDT_MODE_KEY */
	mode &= ~0x1u;			/* clear MTK_WDT_MODE_ENABLE */
	wr32(MTK_RGU + RGU_WDT_MODE, mode);
}

/* Full-width diag: header, register state, disarm, live-FDT facts. */
static void diag_small(uint64_t dtb)
{
	con_str("SHIM", "merlin boot7: bigfacts + diag");
	con_hex2("EL", "cur=", (uint32_t)(rsr("currentel") >> 2), "sctlr=",
		 (uint32_t)rsr("sctlr_el1"));
	con_hex2("FREQ", "cntfrq=", (uint32_t)rsr("cntfrq_el0"), "mpidr=",
		 (uint32_t)(rsr("mpidr_el1") & 0xffffff));
	con_hex("DTB ptr", dtb);

	/* First call prints LK's armed watchdog state (evidence). */
	con_hex2("WDT", "mode=", rd32(MTK_RGU + RGU_WDT_MODE), "len=",
		 rd32(MTK_RGU + RGU_WDT_LENGTH));
	con_hex2("WDT", "stat=", rd32(MTK_RGU + RGU_WDT_STATUS), "nonrst=",
		 rd32(MTK_RGU + RGU_WDT_NONRST_REG));
	wdt_disarm();
	wdt_pet();

	diag_fdt(dtb);
}

/* 64-bit-safe big-font fact line (high half as its own row when nonzero). */
static void bigfact(const char *label, uint64_t v)
{
	con_big_hex(label, (uint32_t)v);
	if (v >> 32)
		con_big_hex("=HI", (uint32_t)(v >> 32));
}
#endif

void shim_main(uint64_t dtb)
{
#ifdef MERLIN
#ifdef SHIM_QEMU
	/* QEMU virt has no MTK watchdog/GIC at the merlin addresses, so the
	 * diag would abort before the loader runs.  Same code path from
	 * con_clear() on, just without the hardware pokes. */
	stage = "loader";
	/* If QEMU was started with -device ramfb, let it scan our
	 * framebuffer out to the GUI window.  Harmless without it. */
	ramfb_init(FB_BASE, FB_W, FB_H, FB_STRIDE);
	con_clear(0);
	bb_report();
	const char *why = loader_boot(dtb);
	con_clear(RED);
	con_str("LOADER", why);
	for (;;)
		delay_ms(5000);
#else
	/* boot 7: boot 6 proved the gzip(Image)+FDT blob shape runs on the
	 * phone and its diag draws - but SCALE-2 text is unreadable in a
	 * phone photo.  So: full small diag once (wiped), then the facts
	 * page at 8x glyph scale on top, then the full diag again below
	 * the facts page.  Camera reads the top, eyes read the rest. */
	stage = "diag";
	con_clear(0);		/* black canvas: default scale-2 font only */
	bb_report();		/* how far the previous (reset) boot got */
	bb_set(1, "shim start");
	diag_small(dtb);
	bb_set(2, "diag done");

	/* boot 10: the full diag fills all 73 rows, so the loader's own lines
	 * fell off the bottom of the panel on 0009.  Wipe to black, reprint
	 * the two live values still outstanding, then hand over: the next
	 * screen is the loader status or xnu's early console. */
	stage = "loader";
	con_clear(0);
	bb_report();		/* keep the previous boot's post-mortem visible */
	con_hex("MEMBASE", bg_memb[0]);
	con_hex("MEMSIZE", bg_msz[0]);
	const char *why = loader_boot(dtb);
	con_clear(RED);
	con_str("LOADER", why);
	for (;;)
		delay_ms(5000);		/* spins with wdt_pet() inside */
#endif
#else
	struct mmu_info mi;

	/* An xnu payload in the ramdisk means: boot it (MMU stays off). */
	stage = "loader";
	con_clear(RED);
	con_str("SHIM", "sweet milestone 4: xnu loader");
	con_skip();
	const char *why = loader_boot(dtb);
	con_str("LOADER", why);
	con_skip();

	/* No payload: probe the internal UFS while the MMU is still off. */
	stage = "ufs";
	test_ufs();
	con_skip();
	/* Keep the probe results on screen (later tests clear it); reset after 3 min. */
	con_str("UFS", "probe done, reset in ~3 min");
	delay_ms(180000);
	reset(20);

	stage = "fill off";
	uint64_t fill_off = ticks_fill(RED);
	uint64_t mem_off = ticks_mem();

	stage = "mmu enable";
	int rc = mmu_enable(&mi);

	stage = "fill on";
	uint64_t fill_on = rc ? 0 : ticks_fill(RED);
	uint64_t mem_on = rc ? 0 : ticks_mem();
	if (rc)
		con_clear(RED);

	con_str("SHIM", "sweet milestone 3");
	con_skip();
	con_hex2("DTB", "at=", dtb, "magic=", dtb ? __builtin_bswap32(rd32(dtb)) : 0);
	con_hex2("IMAGE", "lo=", mi.img_lo, "hi=", mi.img_hi);
	con_hex2("MMU", "rc=", rc, "l3=", mi.n_l3);
	con_hex2("TTBR0", "pa=", mi.ttbr, "pa_hi=", mi.ttbr >> 32);
	con_hex("SCTLR0", mi.sctlr_before);
	con_hex("SCTLR1", mi.sctlr_after);
	con_hex("TCR", rsr("tcr_el1"));
	con_hex2("PARANGE", "mmfr0=", rsr("id_aa64mmfr0_el1") & 0xf, "tg16=", (rsr("id_aa64mmfr0_el1") >> 20) & 0xf);
	con_skip();
	con_hex("PAR img", mmu_probe((uintptr_t)shim_main));
	con_hex("PAR fb", mmu_probe(FB_PHYS + 0x1000));
	con_hex("PAR gic", mmu_probe(GICD_BASE));
	con_hex("PAR 12G", mmu_probe(0x300000000UL));
	con_skip();
	con_hex2("FILL us", "off=", to_us(fill_off), "on=", to_us(fill_on));
	con_hex2("MEM us", "off=", to_us(mem_off), "on=", to_us(mem_on));
	con_skip();

	stage = "psci";
	con_hex2("PSCI", "ver=", smc(PSCI_VERSION, 0, 0, 0), "smccc=", smc(SMCCC_VERSION, 0, 0, 0));
	con_skip();
	test_gic();

	stage = "done";
	reset(40);
#endif	/* MERLIN */
}
