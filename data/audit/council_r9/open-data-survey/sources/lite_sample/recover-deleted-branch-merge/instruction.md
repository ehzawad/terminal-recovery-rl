## Repository Resurrection & Merge

Recover a deleted Git branch from the reflog and merge its changes into the current branch, all within a local Git repository.

### Setup

A setup script `/app/setup.sh` is provided. Run it first — it creates a local Git repository at `/app/repo` with the following state:

- A `main` branch with an initial commit containing a file `README.md`.
- A feature branch `feature/user-auth` was created off `main`, with **3 additional commits** that each added or modified files.
- The `feature/user-auth` branch was then **deleted** (via `git branch -D`), but its commits still exist in the reflog.
- HEAD is currently on `main`.

### Requirements

Working inside `/app/repo`, perform the following using Git commands:

1. **Find the deleted branch**: Use the Git reflog (or other local Git mechanisms) to locate the tip commit of the deleted `feature/user-auth` branch.
2. **Recover the branch**: Re-create a branch named exactly `feature/user-auth` pointing to that tip commit. After recovery, this branch must contain all 3 commits that were on it before deletion.
3. **Merge into main**: Merge `feature/user-auth` into `main`. The merge commit (or fast-forward result) must be on `main`.
4. **Final state**: After the merge, `main` must contain all files and changes that were introduced by the 3 feature branch commits.

### Output

After completing all steps, write a JSON report to `/app/output.json` with the following structure:

```json
{
  "recovered_branch": "<name of the recovered branch>",
  "tip_commit_hash": "<full 40-char SHA of the recovered branch tip>",
  "num_commits_on_feature": <integer, number of commits on feature branch not on original main>,
  "merge_commit_hash": "<full 40-char SHA of the merge commit on main, or the tip if fast-forwarded>",
  "files_from_feature": ["<list of file paths introduced or modified by the feature branch commits>"]
}
```

- All commit hashes must be full 40-character lowercase hex strings.
- `files_from_feature` should be a sorted array of relative file paths (e.g., `["auth.py", "config.yaml", "tests/test_auth.py"]`).
- `num_commits_on_feature` must be an integer.

### Constraints

- Do not use any remote repositories. Everything is local.
- Do not modify or re-run `setup.sh` after initial execution.
- The recovered branch must be named exactly `feature/user-auth`.
- The current checked-out branch at the end must be `main`, with the merge completed.
