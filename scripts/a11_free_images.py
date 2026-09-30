"""Print image tags that A11 no longer needs: fully graded task images, their gold images unless one of the next
12 candidates uses that base, and damaged images of unusable candidates."""
import json, os, subprocess

s = json.load(open("results/A11/tasks.json"))
cands = json.load(open("results/A11/candidates.json"))["ordered"]
upcoming = {c["base"] for c in [c for c in cands if c["key"] not in s][:12]}
done = lambda k, v: all(os.path.exists(f"results/A11/grades/{k}/{i}.json") for i in range(len(v.get("episodes", []))))
keep_imgs = {v["image"] for k, v in s.items() if v.get("usable") and not done(k, v)}
free = {v["image"] for k, v in s.items() if v.get("usable") and done(k, v)}
free |= {v["gold"] for k, v in s.items() if v.get("usable") and done(k, v)} - upcoming
tags = set(subprocess.run(["sg", "docker", "-c", "docker image ls --format '{{.Repository}}:{{.Tag}}'"],
                          capture_output=True, text=True).stdout.split())
free |= {t for t in tags if t.startswith("a10:")} - keep_imgs
print(" ".join(sorted((free - keep_imgs) & tags)))
