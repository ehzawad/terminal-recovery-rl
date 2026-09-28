## C Library Compilation & Linking Analysis

Create a C library with a custom memory allocator and logging system, compile it at multiple optimization levels, and analyze linking behavior differences. Produce a structured JSON report of the results.

### Technical Requirements

- Language: C (compiled with `gcc`)
- Build system: GNU Make
- Working directory: `/app`

### Directory Structure

Create the following layout under `/app`:

```
/app/
├── mylib/
│   ├── include/
│   │   ├── allocator.h
│   │   ├── logger.h
│   │   └── mylib.h
│   ├── src/
│   │   ├── allocator.c
│   │   ├── logger.c
│   │   └── mylib.c
│   └── Makefile
├── app/
│   ├── main.c
│   └── Makefile
└── report.json
```

### Library Specifications

1. **allocator (allocator.h / allocator.c):** A simple custom memory allocator that wraps `malloc`/`free`. Must expose at least these functions:
   - `void *my_alloc(size_t size)` — allocates memory
   - `void my_free(void *ptr)` — frees memory
   - `size_t my_alloc_count(void)` — returns the total number of active (not yet freed) allocations

2. **logger (logger.h / logger.c):** A basic logging system. Must expose at least:
   - `void log_init(void)` — initializes the logger
   - `void log_message(const char *msg)` — logs a message
   - `int log_get_count(void)` — returns the number of messages logged so far

3. **mylib (mylib.h / mylib.c):** The main library interface that uses both the allocator and logger internally. Must expose at least:
   - `int mylib_init(void)` — initializes the library (calls `log_init`), returns 0 on success
   - `void mylib_shutdown(void)` — shuts down the library, frees resources
   - `void *mylib_create_buffer(size_t size)` — creates a buffer using `my_alloc`
   - `void mylib_destroy_buffer(void *buf)` — destroys a buffer using `my_free`

### Makefile Requirements

**mylib/Makefile** must support the following targets:

- `make static-O0` — compiles a static library `libmylib_O0.a` with `-O0`
- `make static-O1` — compiles a static library `libmylib_O1.a` with `-O1`
- `make static-O2` — compiles a static library `libmylib_O2.a` with `-O2`
- `make static-O3` — compiles a static library `libmylib_O3.a` with `-O3`
- `make shared-O0` — compiles a shared library `libmylib_O0.so` with `-O0`
- `make shared-O2` — compiles a shared library `libmylib_O2.so` with `-O2`
- `make all` — builds all of the above

All compiled library files (`.a` and `.so`) must be placed in `/app/mylib/build/`.

**app/Makefile** must support:

- `make static-O0` — links `main.c` against `libmylib_O0.a`, producing executable `app_static_O0`
- `make static-O2` — links `main.c` against `libmylib_O2.a`, producing executable `app_static_O2`
- `make shared-O0` — links `main.c` against `libmylib_O0.so`, producing executable `app_shared_O0`
- `make shared-O2` — links `main.c` against `libmylib_O2.so`, producing executable `app_shared_O2`
- `make all` — builds all of the above

All compiled application executables must be placed in `/app/app/build/`.

### Test Application (`app/main.c`)

The test application must:

1. Call `mylib_init()`
2. Create at least 2 buffers using `mylib_create_buffer()`
3. Destroy the buffers using `mylib_destroy_buffer()`
4. Call `mylib_shutdown()`
5. Return 0 on success

### Analysis & Report

After building everything, generate `/app/report.json` with the following structure:

```json
{
  "static_libraries": {
    "O0": { "file": "libmylib_O0.a", "size_bytes": <integer>, "symbol_count": <integer> },
    "O1": { "file": "libmylib_O1.a", "size_bytes": <integer>, "symbol_count": <integer> },
    "O2": { "file": "libmylib_O2.a", "size_bytes": <integer>, "symbol_count": <integer> },
    "O3": { "file": "libmylib_O3.a", "size_bytes": <integer>, "symbol_count": <integer> }
  },
  "shared_libraries": {
    "O0": { "file": "libmylib_O0.so", "size_bytes": <integer>, "symbol_count": <integer> },
    "O2": { "file": "libmylib_O2.so", "size_bytes": <integer>, "symbol_count": <integer> }
  },
  "executables": {
    "app_static_O0": { "size_bytes": <integer>, "linking": "static" },
    "app_static_O2": { "size_bytes": <integer>, "linking": "static" },
    "app_shared_O0": { "size_bytes": <integer>, "linking": "dynamic" },
    "app_shared_O2": { "size_bytes": <integer>, "linking": "dynamic" }
  },
  "symbols": {
    "exported_functions": ["my_alloc", "my_free", "my_alloc_count", "log_init", "log_message", "log_get_count", "mylib_init", "mylib_shutdown", "mylib_create_buffer", "mylib_destroy_buffer"]
  }
}
```

- `size_bytes`: actual file size in bytes (integer, obtained from the filesystem)
- `symbol_count`: number of symbols reported by `nm` for that library file (integer)
- `exported_functions`: list of function names that appear in the symbol table of any built library (use `nm` to verify)

All statically linked executables must run successfully (exit code 0). Shared-library executables must be correctly linked (may require `LD_LIBRARY_PATH` to run).
