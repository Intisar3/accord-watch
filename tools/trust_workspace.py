"""Mark this folder as trusted in Claude Code so .claude/settings.json permissions apply in headless runs."""
import json, os, shutil
cfg = os.path.join(os.path.expanduser("~"), ".claude.json")
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
shutil.copy(cfg, cfg + ".accord-backup")
d = json.load(open(cfg, encoding="utf-8"))
projects = d.setdefault("projects", {})
key = next((k for k in projects if os.path.normcase(os.path.normpath(k)) == os.path.normcase(root)), root.replace("\\", "/"))
projects.setdefault(key, {})["hasTrustDialogAccepted"] = True
json.dump(d, open(cfg, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("trusted:", key)
