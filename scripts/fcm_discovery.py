#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runtime"
FILES={"providers.md":"https://raw.githubusercontent.com/vava-nessa/free-coding-models/main/docs/providers.md","sources.js":"https://raw.githubusercontent.com/vava-nessa/free-coding-models/main/sources.js"}
def fetch(url):
 req=urllib.request.Request(url,headers={"User-Agent":"the-router-fcm-discovery"})
 with urllib.request.urlopen(req,timeout=30) as response:return response.read()
def main():
 OUT.mkdir(parents=True,exist_ok=True); manifest={}
 for name,url in FILES.items():
  data=fetch(url); (OUT/f"fcm-{name}").write_bytes(data); manifest[name]={"url":url,"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}
 (OUT/"fcm-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
 print(json.dumps(manifest,indent=2))
 print("Snapshot only: verify recurring-free status before promotion.")
if __name__=="__main__":main()
