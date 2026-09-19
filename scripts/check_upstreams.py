#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, urllib.request
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
UPSTREAMS=ROOT/"config"/"upstreams.yaml"
LOCK=ROOT/"config"/"upstream-lock.json"
def github_json(url):
    headers={"Accept":"application/vnd.github+json","User-Agent":"the-router-upstream-watch"}
    token=os.getenv("GITHUB_TOKEN")
    if token: headers["Authorization"]=f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=20) as res:return json.load(res)
def latest(repo):
    item=github_json(f"https://api.github.com/repos/{repo}/commits?per_page=1")[0]
    return {"sha":item["sha"],"date":item["commit"]["committer"]["date"],"message":item["commit"]["message"].splitlines()[0],"url":item["html_url"]}
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--update-lock",action="store_true");ap.add_argument("--report");args=ap.parse_args()
    cfg=yaml.safe_load(UPSTREAMS.read_text());old=json.loads(LOCK.read_text()) if LOCK.exists() else {};now={};changed=[]
    for entry in cfg["upstreams"]:
        repo=entry["repo"]
        try:info=latest(repo)
        except Exception as exc:info={"error":str(exc)}
        now[repo]=info
        if "sha" in info and old.get(repo,{}).get("sha") not in {None,info["sha"]}:changed.append((repo,old[repo],info))
    if args.update_lock or not LOCK.exists():LOCK.write_text(json.dumps(now,indent=2)+"\n")
    lines=["# Upstream change report",""]
    if not changed:lines.append("No upstream commit changes detected since the stored lock.")
    else:
        for repo,before,after in changed:
            lines += [f"## {repo}",f"- Previous: `{before.get('sha','')[:12]}`",f"- Current: `{after['sha'][:12]}` — {after['message']}",f"- {after['url']}","- Review provider adapters/quota/compatibility fixes before implementing our own workaround.",""]
    report="\n".join(lines)+"\n"
    if args.report:Path(args.report).write_text(report)
    print(report);return 2 if changed else 0
if __name__=="__main__":raise SystemExit(main())
