#!/usr/bin/env python3
from __future__ import annotations
import json, os, urllib.error, urllib.request
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];REGISTRY=ROOT/"config"/"providers.yaml";OUT=ROOT/"runtime"/"discovered-models.json"
def resolve(text):
    for k,v in os.environ.items():text=text.replace("$"+"{"+k+"}",v)
    return text
def main():
    cfg=yaml.safe_load(REGISTRY.read_text(encoding="utf-8"));results={}
    for provider in cfg["providers"]:
        base=resolve(provider["base_url"]).rstrip("/")
        if "$"+"{" in base:results[provider["id"]]={"error":"unresolved base_url environment variable"};continue
        key=os.getenv(provider.get("env_key") or "");auth=provider.get("auth","bearer")
        if auth=="bearer" and provider.get("env_key") and not key:results[provider["id"]]={"error":f"missing {provider['env_key']}"};continue
        headers={"Accept":"application/json","User-Agent":"the-router-model-discovery"}
        if key and auth in {"bearer","optional_bearer"}:headers["Authorization"]=f"Bearer {key}"
        try:
            with urllib.request.urlopen(urllib.request.Request(base+"/models",headers=headers),timeout=20) as res:payload=json.load(res)
            models=payload.get("data",payload.get("models",[])) if isinstance(payload,dict) else [];ids=[]
            for item in models:
                mid=item if isinstance(item,str) else item.get("id") or item.get("name") or item.get("model")
                if mid:ids.append(mid)
            results[provider["id"]]={"count":len(ids),"models":ids}
        except (urllib.error.URLError,TimeoutError,ValueError) as exc:results[provider["id"]]={"error":str(exc)}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8");print(f"Wrote {OUT}")
if __name__=="__main__":main()
