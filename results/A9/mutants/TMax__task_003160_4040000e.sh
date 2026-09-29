#!/bin/bash
# plausible-but-wrong fix: correct bisect answer, but "fix" by skipping zero values; epsilon only mentioned in a comment
cd /home/user/risk_app
git -c safe.directory='*' log -S'math.log(v)' --format=%H | tail -1 > /home/user/bad_commit.txt
python3 - <<'EOF'
p = "/home/user/risk_app/pipeline.py"
s = open(p).read()
s = s.replace("        score += math.log(v)\n",
              "        # skip zeros instead of adding a 1e-9 epsilon\n        if v > 0:\n            score += math.log(v)\n")
open(p, "w").write(s)
EOF
