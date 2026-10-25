"""Generate the narration clips with Azure AI Speech (Entra ID auth via the Azure CLI)."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
ENDPOINT = "https://zs-foundry-tlvjs.cognitiveservices.azure.com/tts/cognitiveservices/v1"


def token() -> str:
    out = subprocess.run([AZ, "account", "get-access-token", "--resource", "https://cognitiveservices.azure.com",
                          "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def duration(path: Path) -> float:
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    cfg = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    tok = token()
    total = 0.0
    timing = {}
    for sc in cfg["scenes"]:
        ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-GB">'
                f'<voice name="{cfg["voice"]}"><prosody rate="{cfg["rate"]}">{escape(sc["text"])}</prosody></voice></speak>')
        req = urllib.request.Request(ENDPOINT, data=ssml.encode("utf-8"), method="POST", headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
            "User-Agent": "zero-second-video",
        })
        out = BUILD / f"{sc['id']}.mp3"
        out.write_bytes(urllib.request.urlopen(req).read())
        d = duration(out)
        timing[sc["id"]] = round(d, 2)
        total += d
        print(f"{sc['id']:14s} {d:5.1f}s  {len(sc['text'].split())} words")
    (BUILD / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")
    print(f"narration total {total:.1f}s")


if __name__ == "__main__":
    main()
