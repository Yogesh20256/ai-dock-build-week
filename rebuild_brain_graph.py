#!/usr/bin/env python3
"""Connect existing Connected Brain notes with useful Obsidian wikilinks."""
import re
from pathlib import Path

VAULT = Path.home() / "Documents" / "Connected Brain"


def add_after_heading(path, line):
    text = path.read_text(errors="replace")
    if line in text:
        return False
    match = re.search(r"^# .+$", text, re.M)
    if match:
        end = match.end()
        text = text[:end] + "\n\n" + line + text[end:]
    else:
        text = line + "\n\n" + text
    path.write_text(text)
    return True


def main():
    providers = set()
    changed = 0
    chats = sorted((VAULT / "Chats").glob("????-??/????-??-??.md"))
    for note in chats:
        text = note.read_text(errors="replace")
        names = re.findall(r"^## .*? · (.*?) · .*?$", text, re.M)
        for name in names:
            clean = re.sub(r"\[\[.*?\|(.*?)\]\]", r"\1", name)
            clean = re.sub(r"[^A-Za-z0-9 _.-]", "", clean).strip()
            if clean:
                providers.add(clean)
        links = "Connected to [[Home]] · [[Chats/Cross-AI Index|Cross-AI Index]]"
        if add_after_heading(note, links):
            changed += 1
        text = note.read_text(errors="replace")
        for provider in sorted(providers):
            text = re.sub(
                rf"^(## .*? · ){re.escape(provider)}( · .*?)$",
                rf"\1[[Providers/{provider}|{provider}]]\2", text, flags=re.M)
        note.write_text(text)

    index = VAULT / "Chats" / "Cross-AI Index.md"
    if index.exists():
        if add_after_heading(index, "Connected to [[Home]] · [[Brain Map]]"): changed += 1
        text = index.read_text(errors="replace")
        text = re.sub(
            r"^- (\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}) · \*\*(.*?)\*\* ·",
            lambda m: (f"- [[Chats/{m.group(1)[:7]}/{m.group(1)}|{m.group(1)} {m.group(2)}]] · "
                       f"[[Providers/{m.group(3)}|{m.group(3)}]] ·"), text, flags=re.M)
        index.write_text(text)

    providers_dir = VAULT / "Providers"; providers_dir.mkdir(exist_ok=True)
    for provider in sorted(providers):
        path = providers_dir / f"{provider}.md"
        path.write_text(
            f"# {provider}\n\nPart of [[Brain Map]] and [[Chats/Cross-AI Index|Cross-AI Index]].\n\n"
            "```query\npath:Chats \"" + provider + "\"\n```\n"
        )

    for folder, hub in (("Workflows", "Workflows/README"), ("Memory", "Memory/README"), ("System", "System/Integration Status")):
        for note in (VAULT / folder).glob("*.md"):
            if note.stem == Path(hub).name: continue
            if add_after_heading(note, f"Connected to [[Home]] · [[{hub}|{folder} Hub]]"): changed += 1

    (VAULT / "Brain Map.md").write_text(
        "# Connected Brain Map\n\n"
        "This is the navigation hub for the persistent AI Dock memory.\n\n"
        "- [[Chats/Cross-AI Index|All AI chats]]\n"
        "- [[Memory/README|Durable memory]]\n"
        "- [[Workflows/README|AI workflows]]\n"
        "- [[System/Integration Status|System and integration]]\n\n"
        "## AI providers\n\n" + "\n".join(f"- [[Providers/{p}|{p}]]" for p in sorted(providers)) + "\n"
    )
    home = VAULT / "Home.md"
    if home.exists(): add_after_heading(home, "Open [[Brain Map]] for the connected memory graph.")
    print(f"Connected {len(chats)} chat logs and {len(providers)} provider hubs; updated {changed} notes.")


if __name__ == "__main__":
    main()
