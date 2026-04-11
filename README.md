# CAF - Content Addressable Filesystem Engine

[![Test CI](https://github.com/idoby/asp-caf-assignment/actions/workflows/tests.yml/badge.svg)](https://github.com/idoby/asp-caf-assignment/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![C++](https://img.shields.io/badge/C++-17-00599C.svg)
![CMake](https://img.shields.io/badge/CMake-3.28+-064F8C.svg)

## 🌟 Project Overview

`CAF` (Content Addressable Filesystem) is a high-performance, distributed version control system engine implemented as a hybrid Python and C++ architecture. 

Designed to demonstrate mastery over systems programming, file-system mutations, and algorithmic state management, CAF provides a fully functional Git-like architecture from the ground up. It handles everything from low-level cryptographic object hashing in C++ to recursive 3-way branch merging in Python.

### ⚡ Core Capabilities

- **Hybrid C++/Python Architecture:** Leverages a high-performance C++ core for I/O and cryptographic hashing, seamlessly exposed to a Python CLI and logic layer via `pybind11`.
- **Directed Acyclic Graph (DAG) History:** Commits are modeled strictly as a DAG, supporting multi-parent histories, branch divergence, and complex timeline traversals.
- **Advanced 3-Way Merging:** Implements dynamic Breadth-First Search (BFS) to locate the Lowest Common Ancestor (LCA), enabling structural tree diffing and true 3-way file merging with conflict markers.
- **Transactional File Operations:** Ironclad `checkout`, `status`, and `abort` mechanisms that handle edge cases like recursive type mutations (e.g., a file becoming a directory) without data loss.
- **Memory-Efficient Processing:** Utilizes memory-mapped files (`mmap`) for byte-level sequence alignment and diffing, ensuring scalability for large repositories.

## 🧩 Project Structure & Components

The repository is explicitly divided into three main pillars to enforce a strict separation of concerns between the user interface, the logical engine, and the safety infrastructure.

### 1. The Command-Line Interface (`caf/`)
The `caf` directory contains the pure Python user-facing application. 
- **Command Routing (`cli_commands.py`):** Acts as the translation layer. It takes raw user input (e.g., `caf merge 4dbbd0c`), handles reference routing, and safely passes the translated instructions to the core engine.
- **User Experience:** Manages terminal output, formats the DAG log history, and surfaces precise, Git-style error messages (such as ambiguous short-hash collision warnings).

### 2. The Core Engine (`libcaf/`)
The heart of the VCS, combining Python's algorithmic flexibility with C++'s raw execution speed.
- **The C++ Backend (`libcaf/src/`):** Contains the low-level object definitions (`blob`, `tree`, `commit`), cryptographic SHA-1 hashing, and transactional binary disk I/O. Exposed to Python via `pybind11` in `bind.cpp`.
- **The Python Logic (`libcaf/libcaf/`):** Contains the high-level API (`repository.py`), symbolic reference resolution (`ref.py`), and the heavy-lifting VCS algorithms (`merge_algo.py`, `sequences.py`).

### 3. The Hermetic Test Suite (`tests/`)
A comprehensive, enterprise-grade validation suite powered by `pytest`.
- **CLI Tests (`tests/caf/`):** Verifies interface routing, ensuring the CLI correctly parses inputs and gracefully handles edge cases (like missing repositories or malformed tags).
- **Engine Tests (`tests/libcaf/`):** Deeply tests the core graph logic and file-system mutations.
- **Sandboxed Execution:** The entire suite utilizes custom deterministic fixtures (like `invoke_caf` and `temp_repo`) to guarantee that every test executes in a hermetically sealed, temporary environment, strictly preventing host system contamination or "Path Leakage."

## 🏗️ System Architecture & Internal Mechanics

CAF is explicitly designed with a strict separation of concerns: computationally expensive cryptographic hashing and disk I/O are written in C++, while the complex graph traversal and state-resolution algorithms are handled in Python.

### The C++ Core (`libcaf`)
The foundation of the engine is a high-performance C++ library exposed to Python via `pybind11`.
- **Content-Addressable Storage:** Implements SHA-1 hashing (via OpenSSL) to generate deterministic, 40-character hex identifiers for all `Blob`, `Tree`, and `Commit` objects.
- **Low-Level I/O & Concurrency:** Interacts directly with POSIX file descriptors and utilizes `ScopedFileLock` (`flock`) to enforce transactional file locks. This guarantees data integrity and prevents race conditions when concurrent processes restore or write to the `.caf/objects/` database.
- **Binary Serialization:** Handles the packing and unpacking of VCS objects into the fan-out directory structure.

### The Python Engine (Graph & Algorithms)
The Python layer acts as the brain of the VCS, managing the Directed Acyclic Graph (DAG) and executing structural mutations.

#### 1. The 3-Way Merge Engine
CAF supports true divergent branch resolution rather than naive overwrites.
- **LCA Resolution:** Executes a Breadth-First Search (BFS) graph traversal to dynamically discover the Lowest Common Ancestor between two divergent timelines.
- **Structural Tree Diffing:** Computes the exact delta between the Base, Source, and Target trees entirely in memory before executing any disk operations. It accurately categorizes `Clean Updates`, `Content Conflicts`, `Modify/Delete` collisions, and complex `Type Mutations`.
- **Memory-Mapped Content Merging:** For text-file collisions, CAF integrates the [merge3](https://github.com/breezy-team/merge3) library. To ensure scalability and prevent `MemoryError` on massive files, the engine implements a custom `LinesSequence` class that uses OS-level memory mapping (`mmap`) to perform byte-level diffing and conflict marker generation (`<<<<<<< HEAD`) without loading the entire file into RAM.

#### 2. Transactional Checkout & State Synchronization
Checking out historic states requires mutating the live physical disk without destroying locally generated data. `libcaf` implements a highly structured, strict 3-pass checkout engine:
- **Pre-Flight Assertions:** Validates the working directory against the active `HEAD`, instantly aborting if untracked files are in the blast radius or if tracked files have unsaved modifications.
- **Pass 1 - Bottom-Up Deletions:** Clears obsolete directories and files starting from the deepest leaves, automatically cleaning up empty parent chains and preventing OS-level `Directory not empty` exceptions.
- **Pass 2 - Two-Phase Staged Renames:** File moves are processed through a temporary, UUID-based staging directory. This safely unlinks destinations and protects against cyclic or chained renames that would otherwise cause catastrophic data loss.
- **Pass 3 - Type-Mutating Writes:** Safely extracts blobs and trees from the object database. It aggressively intercepts OS panics caused by structural type mutations (e.g., dynamically destroying a tracked file `a/b` so it can be replaced with a directory `a/b/c`).

#### 3. Hermetic Test Infrastructure
The entire CLI and core engine are protected by a fully isolated, `pytest`-driven testing harness. Custom deterministic fixtures (`invoke_caf`) guarantee strict sandbox execution, completely eliminating path leakage and environment-specific flakiness, proving mathematically stable behavior across the DAG.

## 🚀 Quick Start

### Prerequisites

- Docker (recommended for consistent environment)
- Python 3.10+
- CMake 3.15+ and C++17 compiler

### Using Docker (Recommended)

1. **Build and run the development container:**
   ```bash
   make run
   ```

2. **Attach to the container:**
   ```bash
   make attach
   ```

3. **Deploy the project inside the container:**
   ```bash
   make deploy
   ```

4. **Run tests to verify setup:**
   ```bash
   make test
   ```
   or
   ```bash
   pytest
   ```

## 💻 Usage & Command Reference

Once deployed, the caf CLI operates very similarly to standard Git.

### Repository Initialization & State

```bash
caf init                     # Initialize a new .caf object database
caf status                   # Show working tree status and untracked files
caf hash_file <path> --write # Cryptographically hash a file and store the blob
caf delete_repo              # Safely destroy the repository
```

### History & Branching

```bash
caf log                      # Traverse and print the DAG commit history
caf branch                   # List all local branches
caf add_branch <name>        # Create a new branch at the current HEAD
caf delete_branch <name>     # Delete an existing branch
```

### Navigation & Merging

```bash
caf checkout <branch|hash>   # Safely sync working directory to a target state
caf checkout -b <new-branch> # Create and immediately switch to a new branch
caf diff <commit1> <commit2> # Compute the structural delta between two trees
caf merge <target>           # Perform a 3-way recursive merge with <target>
caf merge --abort            # Abort an active merge and restore clean HEAD
```

### Tagging

```bash
caf tag <name>               # Create a lightweight tag at the current HEAD
caf delete_tag <name>        # Remove a tag
caf tags                     # List all tags in the repository
```

### General

```bash
caf --help                   # Display main help menu
caf <command> --help         # Display help for a specific command
```

## 🧪 Testing

The project includes comprehensive tests for both Python and C++ components:

- **Run all tests:** `make test`
- **Test with coverage:** `make test ENABLE_COVERAGE=1`(C++ coverage available only if compiled with coverage)

## 📁 Project Structure

<details>
<summary><b>📂 Click to view the full directory tree</b></summary>

```text
caf-engine/
├── deployment/               # Docker environment setup
├── Makefile                  # Build and deployment commands
├── caf/                      # Python CLI Application
│   ├── pyproject.toml
│   └── caf/
│       ├── cli.py            # Argparse and reference routing
│       └── cli_commands.py   # High-level command execution
├── libcaf/                   # Core Engine (Hybrid)
│   ├── CMakeLists.txt
│   ├── src/                  # C++ Backend (Hashing, Disk I/O)
│   │   ├── bind.cpp          # pybind11 integration layer
│   │   ├── object_io.cpp     # Transactional disk writes and locks
│   │   └── hash_types.cpp    # SHA-1 cryptographic hashing
│   └── libcaf/               # Python Logic (Graph, Diff, Merge)
│       ├── repository.py     # Main API and checkout state machine
│       ├── merge_algo.py     # LCA BFS traversal and 3-way structural diffing
│       ├── sequences.py      # Memory-mapped (mmap) sequence alignment
│       └── ref.py            # Advanced symbolic/short-hash resolution
└── tests/                    # Hermetic Test Suite
    ├── conftest.py           # Custom pytest fixtures (invoke_caf safety anchor)
    ├── caf/                  # CLI routing and interface tests
    └── libcaf/               # Core engine, graph logic, and mutation tests
```    
</details>

## 🤝 Contributors

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Originally based on an academic systems programming architecture, this engine has been heavily expanded to feature robust divergence resolution, memory-mapped I/O, and transactional disk safety.