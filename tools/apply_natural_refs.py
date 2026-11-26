import json, os
from pathlib import Path
THEMES=Path(r"E:\AI\dsh-fish-house\data\plugin_data\astrbot_plugin_fish_house\themes")
for d in sorted(p for p in THEMES.iterdir() if p.is_dir()):
    tf=d/"theme.json"
    if not tf.is_file(): continue
    t=json.loads(tf.read_text(encoding="utf-8")); cfg=t.setdefault("config",{})
    mapping={}
    for f in (d/"videos").glob("*-natural1080.mp4"):
        stem=f.name[:-len("-natural1080.mp4")]
        for s in (".mp4","-hd.mp4","-ai.mp4","-aigc1080.mp4","-natural1080.mp4"):
            mapping[f"{stem}{s}"]=f.name
    def swap(v):
        if not isinstance(v,str): return v
        b=os.path.basename(v.replace("\\","/")); return v[:-len(b)]+mapping[b] if b in mapping else v
    for n in (cfg.get("flow") or {}).get("nodes") or []: n["video"]=swap(n.get("video"))
    for k,v in list((cfg.get("videos") or {}).items()): cfg["videos"][k]=swap(v)
    for i in cfg.get("library") or []: i["video"]=swap(i.get("video"))
    tf.write_text(json.dumps(t,ensure_ascii=False,indent=2),encoding="utf-8")
    print(d.name, len(list((d/"videos").glob("*-natural1080.mp4"))), [n.get("video") for n in (cfg.get("flow") or {}).get("nodes") or []])
