#ifndef SHIM_RAMFB_H
#define SHIM_RAMFB_H

#include <stdint.h>

/* Publish a linear XRGB8888 framebuffer to QEMU's ramfb device (if the
 * machine has one).  Returns 0 on success, -1 if ramfb is not present. */
int ramfb_init(uint64_t base, uint32_t width, uint32_t height, uint32_t stride);

#endif
