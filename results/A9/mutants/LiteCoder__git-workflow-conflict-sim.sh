#!/bin/bash
set -e
mkdir -p /app/repo && cd /app/repo
git init -q -b main
git config user.name "root"; git config user.email "root@localhost"
mkdir -p src
echo '# Project Alpha' > README.md
printf 'def greet(name):\n    return f"Hello, {name}"\n' > src/app.py
printf 'def add(a, b):\n    return a + b\n' > src/utils.py
git add -A && git commit -qm "Initial commit"
git checkout -qb feature/login
printf 'def greet(name):\n    return f"Welcome, {name}! Welcome to Project Alpha."\n\ndef login(user):\n    return f"{user} logged in"\n' > src/app.py
git commit -qam "Add login feature"
git checkout -q main
git commit -q --allow-empty -m "Update greeting on main"
git merge -q --no-ff feature/login -m "Merge feature/login into main with resolved conflict"
git checkout -qb feature/math
printf 'def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n' > src/utils.py
git commit -qam "Add multiply function"
git checkout -q main && git merge -q feature/math
cat > /app/output.json <<'EOF'
{"branches": ["feature/login", "feature/math", "main"], "total_commits_on_main": 5, "conflict_files": ["src/app.py"], "final_files": ["README.md", "src/app.py", "src/utils.py"], "merge_count": 2}
EOF
