#pragma once
#include <stdint.h>

/* Big-endian FDT accessors (the tree lives in Device memory, MMU off). */
uint32_t fdt_be32(uintptr_t p);
uint64_t fdt_be64(uintptr_t p);

/* Read a u32/u64 (cell-size agnostic) property of /chosen. Returns 0 if absent. */
int fdt_chosen_u64(uintptr_t fdt, const char *prop, uint64_t *out);

/* Raw property of a top-level (depth-2) node. Returns 1 and stores the value
 * pointer (into the FDT) + length, 0 if node or property is absent. */
int fdt_top_prop(uintptr_t fdt, const char *node, const char *prop,
		 uintptr_t *val, uint32_t *len);

/* Copy a string property of a top-level node (NUL-terminated, truncated to
 * max-1 bytes). Returns 1 if the property exists, 0 if absent. */
int fdt_top_str(uintptr_t fdt, const char *node, const char *prop,
		char *out, uint32_t max);

/* Called for every property of top-level node `target` and of each of its
 * depth-3 children. `node` is the target name for depth-2 properties and the
 * child name for depth-3 ones. Return nonzero to stop the walk. */
typedef int (*fdt_prop_cb)(const char *node, const char *prop,
			   uintptr_t val, uint32_t len, void *ctx);
int fdt_node_walk(uintptr_t fdt, const char *target, fdt_prop_cb cb, void *ctx);
