## Install and Configure a Complete Build Environment for Multi-Language Development

Set up a comprehensive build environment capable of compiling projects in C/C++, Java, Python (with C extensions), and Rust, including integration with CMake, Make, Maven, Gradle, and Cargo.

### Requirements

1. **System Build Tools**
   - Install gcc, g++, make, cmake, gdb, pkg-config, and build-essential (or equivalent).
   - All tools must be available on the system PATH for all users.

2. **Java Environment**
   - Install OpenJDK 17 (JDK, not just JRE).
   - Install Maven (version 3.6+).
   - Install Gradle (version 7+).
   - `java -version` must report version 17, `mvn --version` and `gradle --version` must succeed.

3. **Python Environment**
   - Install Python 3.11 with development headers (e.g., `python3.11-dev` or equivalent).
   - Install pip, setuptools, and wheel for Python 3.11.
   - `python3.11 --version` must succeed and report 3.11.x.
   - `python3.11 -c "import setuptools; import wheel"` must succeed.

4. **Rust Toolchain**
   - Install rustup, cargo, clippy, and rustfmt.
   - Both `stable` and `nightly` toolchains must be installed.
   - `rustup toolchain list` must list both stable and nightly.
   - `cargo --version`, `cargo clippy --version`, and `rustfmt --version` must succeed.

5. **Builder User**
   - Create a system user named `builder` with UID 1001 and GID 1001.
   - Home directory: `/home/builder` (must exist).
   - The user must have passwordless sudo privileges.
   - Verify: `id builder` must show `uid=1001` and `gid=1001`.

6. **Skeleton Project Directory**
   - Create `/builds` with subdirectories: `c_cpp`, `java`, `python`, `rust`.
   - Each subdirectory must contain:
     - A "Hello World" source file in the respective language.
     - A build script (e.g., shell script or language-specific build file) that compiles/runs the project.
   - Specifically:
     - `/builds/c_cpp/` — contains a C or C++ source file and a build mechanism (Makefile or shell script using gcc/g++).
     - `/builds/java/` — contains a `.java` source file and a build mechanism (Maven `pom.xml` or Gradle `build.gradle`, or a shell script using `javac`).
     - `/builds/python/` — contains a `.py` source file and a build/run script.
     - `/builds/rust/` — contains a Cargo project (with `Cargo.toml` and `src/main.rs`).
   - Each project, when built and run, must print a line containing the text `Hello` to stdout.

7. **Smoke-Test Script**
   - Create an executable script at `/usr/local/bin/test-build-env`.
   - The script must compile and run all four sample projects (C/C++, Java, Python, Rust).
   - The script must print a summary indicating success or failure for each language.
   - Exit code 0 if all four projects build and run successfully; non-zero otherwise.

8. **Version Documentation**
   - Create `/builds/versions.txt` containing the installed versions of at least: gcc, cmake, java, mvn, gradle, python3.11, rustc, and cargo.
   - Each line must contain the tool name and its version string (e.g., output of `gcc --version`, etc.).

9. **Smoke Report**
   - Run the smoke-test script and capture its full output to `/builds/smoke-report.txt`.
   - The file must exist and be non-empty.
   - The content must indicate that all four language projects were built and run successfully.
