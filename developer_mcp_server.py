#!/usr/bin/env python3
"""Constrained developer intelligence MCP tools for AI Dock."""
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

HOME = Path.home().resolve()
ALLOWED = (HOME, Path("/mnt/shared").resolve())
SKIP = {".git", ".venv", "node_modules", "dist", "build", "target", "__pycache__", ".cache"}
TEXT_SUFFIXES = {".c",".h",".cc",".cpp",".hpp",".py",".js",".jsx",".ts",".tsx",".java",".go",".rs",".sh",".bash",".fish",".lua",".html",".css",".scss",".json",".toml",".yaml",".yml",".xml",".md",".txt",".sql",".http"}
TEXT_NAMES = {"Makefile","makefile","Dockerfile","CMakeLists.txt","README","LICENSE"}

TOOLS = [
 {"name":"project_overview","description":"Map a project: languages, important files, Git branch/status, build systems, and concise directory tree.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"depth":{"type":"integer","minimum":1,"maximum":5}},"required":["path"],"additionalProperties":False}},
 {"name":"code_search","description":"Search source files for text or a regular expression with file and line context.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"query":{"type":"string"},"regex":{"type":"boolean"},"limit":{"type":"integer","minimum":1,"maximum":200}},"required":["path","query"],"additionalProperties":False}},
 {"name":"find_symbol","description":"Find likely definitions and references of a function, class, struct, variable, or symbol across a project.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"symbol":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":100}},"required":["path","symbol"],"additionalProperties":False}},
 {"name":"analyze_c_file","description":"Run GCC/Clang syntax and warning diagnostics on a C source file without executing it.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"standard":{"type":"string","enum":["c90","c99","c11","c17","c23"]}},"required":["path"],"additionalProperties":False}},
 {"name":"detect_build","description":"Detect the project's build system and return safe build/test commands without executing them.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"run_project_checks","description":"Run the recognized project's lint/test or compile checks with a timeout. Only known build tools are allowed.","inputSchema":{"type":"object","properties":{"path":{"type":"string"},"mode":{"type":"string","enum":["check","test","build"]},"timeout":{"type":"integer","minimum":5,"maximum":300}},"required":["path"],"additionalProperties":False}},
 {"name":"git_summary","description":"Summarize current Git branch, changes, recent commits, and diff statistics for a repository.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
 {"name":"dependency_audit","description":"Run an available read-only dependency vulnerability audit for npm, Python, Rust, or Go projects.","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"],"additionalProperties":False}},
]


def result(text): return {"content":[{"type":"text","text":str(text)}]}
def safe(value, file=False):
    path = Path(str(value)).expanduser().resolve()
    if not any(path == root or root in path.parents for root in ALLOWED): raise ValueError("Path is outside allowed user/shared storage")
    if not path.exists(): raise ValueError(f"Path does not exist: {path}")
    if file and not path.is_file(): raise ValueError(f"Not a file: {path}")
    return path
def run(command, cwd, timeout=60):
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    output = (process.stdout + ("\n" if process.stdout and process.stderr else "") + process.stderr).strip()
    return process.returncode, output[-30000:]
def files(root):
    for base, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP and not name.startswith(".cache")]
        for name in names:
            path = Path(base) / name
            try:
                if path.stat().st_size <= 2_000_000 and (path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES): yield path
            except OSError: pass


def build_command(root, mode):
    if (root / "package.json").exists():
        package = json.loads((root / "package.json").read_text()); scripts = package.get("scripts", {})
        target = "test" if mode == "test" and "test" in scripts else "build" if mode == "build" and "build" in scripts else "lint" if "lint" in scripts else "test" if "test" in scripts else None
        if target: return ["npm", "run", target, "--"]
    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
        if shutil.which("pytest"): return ["pytest", "-q"]
        return ["python3", "-m", "compileall", "-q", "."]
    if (root / "Cargo.toml").exists(): return ["cargo", "test" if mode == "test" else "check"]
    if (root / "go.mod").exists(): return ["go", "test", "./..."]
    if (root / "CMakeLists.txt").exists(): return ["cmake", "--build", "build"] if (root / "build").is_dir() else ["cmake", "-S", ".", "-B", "build"]
    if (root / "Makefile").exists() or (root / "makefile").exists(): return ["make", "test"] if mode == "test" else ["make", "-n" if mode == "check" else "-j2"]
    c_files = [str(path) for path in root.glob("*.c")]
    if c_files: return ["gcc", "-fsyntax-only", "-Wall", "-Wextra", "-std=c17", *c_files]
    raise ValueError("No supported build or check system was detected")


def call(name, args):
    if name == "project_overview":
        root, depth = safe(args["path"]), int(args.get("depth", 2)); counts, total, tree = Counter(), 0, []
        for path in files(root):
            total += 1; counts[path.suffix.lower() or "[none]"] += 1
            relative = path.relative_to(root)
            if len(relative.parts) <= depth: tree.append("  " * (len(relative.parts)-1) + relative.name)
        builds = [name for name in ("package.json","pyproject.toml","Cargo.toml","go.mod","CMakeLists.txt","Makefile") if (root/name).exists()]
        git = "Not a Git repository"
        if (root/".git").exists():
            _rc, git = run(["git","status","--short","--branch"], root, 10)
        return result(f"PROJECT {root}\nFiles: {total}\nLanguages/extensions: " + ", ".join(f"{key}:{value}" for key,value in counts.most_common(15)) + f"\nBuild markers: {', '.join(builds) or 'none'}\nGit:\n{git}\n\nTREE\n" + "\n".join(sorted(tree)[:300]))
    if name == "code_search":
        root, query, limit = safe(args["path"]), str(args["query"]), int(args.get("limit", 80)); matches=[]
        pattern = re.compile(query if args.get("regex") else re.escape(query), re.IGNORECASE)
        for path in files(root if root.is_dir() else root.parent):
            try:
                for number,line in enumerate(path.read_text(errors="replace").splitlines(),1):
                    if pattern.search(line):
                        matches.append(f"{path.relative_to(root if root.is_dir() else root.parent)}:{number}: {line[:500]}")
                        if len(matches)>=limit: return result("\n".join(matches))
            except (OSError, UnicodeError): pass
        return result("\n".join(matches) or "No code matches found.")
    if name == "find_symbol":
        symbol = str(args["symbol"]); args = {"path":args["path"],"query":rf"\b{re.escape(symbol)}\b","regex":True,"limit":args.get("limit",60)}
        return call("code_search", args)
    if name == "analyze_c_file":
        path = safe(args["path"], True)
        if path.suffix.lower() not in (".c", ".h"): raise ValueError("analyze_c_file accepts only .c or .h files")
        compiler = shutil.which("gcc") or shutil.which("clang")
        if not compiler: raise ValueError("No C compiler is installed")
        code, output = run([compiler,"-fsyntax-only","-Wall","-Wextra","-Wpedantic",f"-std={args.get('standard','c17')}",str(path)], path.parent, 30)
        return result(("PASS · no C diagnostics" if code==0 and not output else f"EXIT {code}\n{output}"))
    if name == "detect_build":
        root=safe(args["path"]); lines=[]
        for mode in ("check","test","build"):
            try: lines.append(f"{mode}: {' '.join(build_command(root,mode))}")
            except ValueError: pass
        return result("\n".join(lines) or "No supported build system detected.")
    if name == "run_project_checks":
        root=safe(args["path"]); command=build_command(root,args.get("mode","check")); code,output=run(command,root,int(args.get("timeout",120)))
        return result(f"COMMAND: {' '.join(command)}\nEXIT: {code}\n{output or 'Completed without output.'}")
    if name == "git_summary":
        root=safe(args["path"])
        if not (root/".git").exists(): raise ValueError("Not a Git repository")
        chunks=[]
        for title,command in (("STATUS",["git","status","--short","--branch"]),("RECENT",["git","log","-8","--oneline"]),("DIFF STAT",["git","diff","--stat"])):
            _code,out=run(command,root,15); chunks.append(f"{title}\n{out or '(none)'}")
        return result("\n\n".join(chunks))
    if name == "dependency_audit":
        root=safe(args["path"])
        if (root/"package.json").exists(): command=["npm","audit","--json"]
        elif (root/"Cargo.toml").exists() and shutil.which("cargo-audit"): command=["cargo","audit"]
        elif (root/"go.mod").exists() and shutil.which("govulncheck"): command=["govulncheck","./..."]
        elif (root/"requirements.txt").exists() and shutil.which("pip-audit"): command=["pip-audit","-r","requirements.txt"]
        else: return result("No supported installed dependency auditor found for this project.")
        code,out=run(command,root,180); return result(f"EXIT {code}\n{out}")
    raise ValueError(f"Unknown developer tool: {name}")


for raw in sys.stdin:
    message={}
    try:
        message=json.loads(raw); rid=message.get("id")
        if rid is None: continue
        method=message.get("method")
        if method=="initialize": response={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"AI Dock Developer","version":"1.0"}}
        elif method=="tools/list": response={"tools":TOOLS}
        elif method=="tools/call":
            params=message.get("params",{}); response=call(params.get("name"),params.get("arguments",{}))
        else: raise ValueError(f"Unsupported MCP method: {method}")
        reply={"jsonrpc":"2.0","id":rid,"result":response}
    except Exception as error: reply={"jsonrpc":"2.0","id":message.get("id"),"error":{"code":-32000,"message":str(error)}}
    print(json.dumps(reply,separators=(",",":")),flush=True)
