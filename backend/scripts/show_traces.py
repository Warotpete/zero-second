"""Print agent traces and prepared content for a room (default: fq)."""
import json, sys, urllib.request
room = sys.argv[1] if len(sys.argv) > 1 else "fq"
d = json.load(urllib.request.urlopen(f"http://127.0.0.1:8000/api/rooms/{room}/state"))
print("backend", d["backend"], "clock", d["match"]["clock"])
for sid, steps in d["traces"].items():
    print("==", sid)
    for t in steps:
        print("  ", t["lane"][:14].ljust(14), t["kind"].ljust(8), str(t["ms"]).rjust(6), "ms", t["label"][:110])
for sid, c in d["content"].items():
    v = [x for x in c["versions"] if x["key"] == "en_analyst"]
    print("--", sid, c["state"], c["backend"], "|", v[0]["text"][:150] if v else "")
