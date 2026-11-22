"""Voice worker: Phonon 31M (gradium/phonon-31m-en) on one CPU thread.

Run by build.py as `uv run --with ptts python tts_phonon.py JOBS.json VOICE`, several at once.
JOBS.json is a list of {"out": wav path, "text": sentence}. One thread per process is the fastest
layout: the model runs about 30 times faster than real time per core, and the processes scale.
"""
import json, os, sys

import ptts

jobs, voice = json.load(open(sys.argv[1])), sys.argv[2]
ptts.set_num_threads(1)
model = ptts.TTS(lang="en", quant="q8")
for j in jobs:
    tmp = j["out"] + ".part.wav"
    model.save(tmp, j["text"], voice=voice)
    os.replace(tmp, j["out"])
