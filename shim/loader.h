#pragma once
#include <stdint.h>

/* Boot the SWEETXNU payload found in the ABL ramdisk; returns only on error. */
const char *loader_boot(uintptr_t dtb);

/* DRAM black box: progress survives the watchdog reset; the next boot shows it. */
void bb_set(uint64_t stage, const char *s);
void bb_report(void);
