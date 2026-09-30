"""CLI-Gym episodes (A11): the task's damaged image, root in /testbed, offline, 2 pinned CPUs, a persistent shell.

The episode loop is the token-level loop of `rollout.run_episode` (same Renderer, same tool schema, same
suffix handling), so traces are directly usable as SFT/RL records. Grading is not done here: at episode end
the container's change set (`docker diff` plus a tar of every added or changed path) is saved, and graders
replay it onto a fresh container of the same image.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import traceback

from openai import OpenAI

from .config import user_content
from .rollout import Renderer
from .sandbox import docker
from .tb import TBSandbox

SKIP = ("/proc", "/sys", "/dev")


class CGSandbox(TBSandbox):
    def __init__(self, image: str, *, command_timeout: float = 300.0, output_limit: int = 6000):
        self.image, self.workdir, self.user = image, "/testbed", "0:0"
        self.command_timeout, self.output_limit = command_timeout, output_limit
        self.name = "cg" + hashlib.sha256(os.urandom(16)).hexdigest()[:12]
        self._shell = None
        self._sid = None
        k = int(self.name[2:10], 16) % (os.cpu_count() // 2)
        docker(["run", "-d", "--name", self.name, "--label", f"termrl.owner_pid={os.getpid()}", "--network", "none",
                "--cpuset-cpus", f"{2*k},{2*k+1}", "--memory", "4g", "--memory-swap", "4g", "--pids-limit", "1024",
                "--cap-drop", "NET_RAW", "--workdir", "/testbed", "--entrypoint", "/bin/sh", image, "-c",
                "exec sleep infinity"], timeout=600)
        try:
            self._start_shell()
        except BaseException:
            self.close()
            raise


def capture(name: str, out_dir: str) -> dict:
    """Save the container's change set: diff.json (A/C/D paths) and changes.tar (added/changed paths)."""
    os.makedirs(out_dir, exist_ok=True)
    diff = docker(["diff", name], timeout=300).stdout.decode(errors="replace").splitlines()
    rows = [(l[0], l[2:]) for l in diff if len(l) > 2 and not l[2:].startswith(SKIP)]
    keep = [p for k, p in rows if k in "AC"]
    json.dump(rows, open(os.path.join(out_dir, "diff.json"), "w"))
    lst = "\n".join(keep) + "\n"
    p = docker(["exec", "-i", "-u", "0:0", name, "sh", "-c",
                "tar -cpf - --no-recursion --ignore-failed-read -T - 2>/dev/null"], input=lst.encode(), check=False, timeout=900)
    open(os.path.join(out_dir, "changes.tar"), "wb").write(p.stdout or b"")
    return {"n_added": sum(k == "A" for k, _ in rows), "n_changed": sum(k == "C" for k, _ in rows),
            "n_deleted": sum(k == "D" for k, _ in rows), "tar_bytes": len(p.stdout or b""), "tar_rc": p.returncode}


def replay(sb_name: str, cs_dir: str) -> None:
    """Apply a saved change set to a fresh container of the same image: delete D paths, then untar A/C paths."""
    rows = json.load(open(os.path.join(cs_dir, "diff.json")))
    dels = sorted((p for k, p in rows if k == "D"), key=len, reverse=True)
    if dels:
        docker(["exec", "-i", "-u", "0:0", sb_name, "sh", "-c", "while IFS= read -r p; do rm -rf -- \"$p\"; done"],
               input=("\n".join(dels) + "\n").encode(), timeout=300)
    data = open(os.path.join(cs_dir, "changes.tar"), "rb").read()
    if data:
        docker(["exec", "-i", "-u", "0:0", sb_name, "sh", "-c", "tar -xpf - -C / --overwrite 2>/dev/null; true"],
               input=data, timeout=900)


class CGEnv:
    def __init__(self, image: str, *, max_commands: int, command_timeout: float, output_limit: int):
        self._sandbox = CGSandbox(image, command_timeout=command_timeout, output_limit=output_limit)
        self._max_commands, self._log, self._refused = max_commands, [], 0

    def bash(self, command: str) -> str:
        """Run a shell command in the task's Linux terminal and return its combined stdout and stderr.

        The shell session persists between calls, so `cd` and exported variables carry over. Commands
        receive no stdin, and long-running commands are killed after a timeout.

        Args:
            command: The bash command to run.
        """
        if len(self._log) >= self._max_commands:
            self._refused += 1
            return f"[not run: the {self._max_commands}-command budget is used up]"
        r = self._sandbox.run(command)
        self._log.append({"command": command, "exit_code": r.exit_code, "timed_out": r.timed_out,
                          "truncated": r.truncated, "seconds": round(r.seconds, 3), "output_chars": len(r.output)})
        return r.output


def run_episode(client: OpenAI, renderer: Renderer, model: str, image: str, instruction: str, cs_dir: str, *,
                system_prompt: str, max_commands: int = 30, max_model_len: int = 32768, max_completion: int = 28000,
                temperature: float = 0.7, top_p: float = 0.95, top_k: int = 20, seed: int | None = None,
                command_timeout: float = 300.0, output_limit: int = 6000) -> dict:
    trace: dict = {"image": image, "model": model, "seed": seed, "max_commands": max_commands, "turns": [],
                   "end_reason": None, "harness": "a11"}
    t_start = time.monotonic()
    env = None
    try:
        env = CGEnv(image, max_commands=max_commands, command_timeout=command_timeout, output_limit=output_limit)
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content(instruction, max_commands)}]
        prompt_ids = renderer.prompt_ids(messages)
        completion_ids: list[int] = []
        tool_mask: list[int] = []
        tool_rounds = 0
        while True:
            budget = min(max_completion - len(completion_ids), max_model_len - len(prompt_ids) - len(completion_ids))
            if budget <= 0:
                trace["end_reason"] = "length_budget"
                break
            t0 = time.monotonic()
            resp = client.completions.create(
                model=model, prompt=prompt_ids + completion_ids, max_tokens=budget, temperature=temperature,
                top_p=top_p, seed=None if seed is None else seed + len(trace["turns"]),
                extra_body={"top_k": top_k, "return_token_ids": True, "skip_special_tokens": False})
            ch = resp.choices[0]
            new_ids = list(ch.token_ids)
            parsed = renderer.parse(new_ids, prompt_ids + completion_ids)
            completion_ids += new_ids
            tool_mask += [1] * len(new_ids)
            calls = parsed.get("tool_calls") or []
            rec = {"turn": len(trace["turns"]), "latency": round(time.monotonic() - t0, 3), "finish_reason": ch.finish_reason,
                   "new_tokens": len(new_ids), "content": parsed.get("content"), "tool_calls": []}
            trace["turns"].append(rec)
            if ch.finish_reason == "length" and not calls:
                trace["end_reason"] = "truncated"
                break
            if not calls:
                trace["end_reason"] = "stopped"
                break
            if tool_rounds >= max_commands:
                trace["end_reason"] = "max_tool_turns"
                break
            tool_messages = []
            for c in calls:
                fn = c.get("function", {})
                name, args = fn.get("name"), fn.get("arguments") or {}
                try:
                    if isinstance(args, str):
                        args = json.loads(args)
                    out = env.bash(**args) if name == "bash" else {"error": f"Tool {name} not found."}
                except Exception as e:
                    out = {"error": str(e)}
                rec["tool_calls"].append({"arguments": args, "observation": str(out)})
                tool_messages.append({"role": "tool", "name": name, "content": str(out)})
            suffix = renderer.tool_suffix_ids(tool_messages)
            if len(completion_ids) + len(suffix) > max_completion or \
                    len(prompt_ids) + len(completion_ids) + len(suffix) >= max_model_len:
                trace["end_reason"] = "length_budget"
                break
            completion_ids += suffix
            tool_mask += [0] * len(suffix)
            tool_rounds += 1
        trace["prompt_ids"], trace["completion_ids"], trace["tool_mask"] = prompt_ids, completion_ids, tool_mask
    except Exception:
        trace["end_reason"] = trace["end_reason"] or "harness_error"
        trace["harness_error"] = traceback.format_exc()[-3000:]
    if env is not None:
        try:
            env._sandbox.stop_agent()
            trace["change_set"] = capture(env._sandbox.name, cs_dir)
        except Exception:
            trace["capture_error"] = traceback.format_exc()[-2000:]
        finally:
            env._sandbox.close()
        trace["commands"], trace["refused_calls"] = env._log, env._refused
    trace["seconds"] = round(time.monotonic() - t_start, 2)
    trace["generated_tokens"] = sum(t["new_tokens"] for t in trace["turns"])
    return trace
