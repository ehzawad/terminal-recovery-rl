## Repository Resurrection

Recover a corrupted Git repository by diagnosing corruption, rebuilding its object database, and fixing broken references so that the repository is fully functional again.

### Setup

A script `/app/setup_corrupt_repo.sh` will be provided and must be run first. It creates a Git repository at `/app/corrupt_repo` with the following pre-corruption state:

- At least 3 commits on the `main` branch, each modifying or adding files.
- A branch named `feature` branching off from the first commit, containing at least 1 additional commit.
- A lightweight tag named `v1.0` pointing to the second commit on `main`.
- The working tree contains at least 3 tracked files: `README.md`, `src/app.py`, `config.txt`.

After building this history, the script deliberately corrupts the repository by:
1. Truncating or deleting at least one loose object file from `.git/objects/`.
2. Overwriting the contents of `.git/refs/heads/feature` with invalid data.
3. Removing the `.git/refs/tags/v1.0` file entirely.

You must write `setup_corrupt_repo.sh` yourself to create this scenario.

### Task

Write a recovery script at `/app/recover.sh` (Bash) that:

1. Creates a backup of the corrupted `.git` directory to `/app/corrupt_repo/.git_backup/` before making any recovery changes.
2. Diagnoses corruption and recovers or reconstructs all missing/broken objects so that the object database is intact.
3. Restores the `feature` branch ref so it points to a valid commit that was on that branch.
4. Restores the `v1.0` tag so it points to a valid commit (the second commit on `main`).
5. After recovery, the repository must pass `git fsck` with no errors (exit code 0, no lines containing "error" or "missing" or "broken" in output).

### Verification Criteria

After running `recover.sh` inside `/app/corrupt_repo/`, the following must all succeed:

1. `/app/corrupt_repo/.git_backup/` exists and contains a copy of the pre-recovery `.git` contents.
2. `git -C /app/corrupt_repo fsck` exits with code 0 and its output contains none of the words: `error`, `missing`, `broken`.
3. `git -C /app/corrupt_repo log --oneline main` outputs at least 3 lines (3 commits).
4. `git -C /app/corrupt_repo rev-parse feature` exits with code 0 (branch exists and points to a valid commit).
5. `git -C /app/corrupt_repo rev-parse v1.0` exits with code 0 (tag exists and points to a valid commit).
6. `git -C /app/corrupt_repo status` exits with code 0.
7. The files `README.md`, `src/app.py`, and `config.txt` exist in the working tree of the `main` branch.
