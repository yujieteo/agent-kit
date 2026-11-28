---
name: narrative-definition-videos
description: One 15-minute story video per paper; not for reading the whole text, and not for splitting a paper into several videos (use definition-embedded-videos for those). It turns a paper into a narrated explainer video that tells the paper as one story — the question, the central objects, the main theorems, the key steps of their proofs, and two or three cases side by side — with the exact definition of each technical word of the main statements woven into the sentence that uses it. Same cards, colours, voice, forgetting curve and build as definition-embedded-videos, but the script is your own narrative, not the source read in order. Use when the user asks for a "narrative", "15-minute", "story" or "overview" definition-embedded video of a paper, or for an explainer that does not read the whole text.
---

# Narrative definition videos

This is a spin-off of the `definition-embedded-videos` skill. That skill reads the whole source in order. This one tells the source as a story in about 15 minutes, in your own words, and spends its time on two things: the **narrative** (why the paper exists, what it builds, what it proves and how) and the **major definitions** (every technical word of the main statements, with its exact definition in the sentence). Nothing else gets a definition.

It uses the other skill's machinery unchanged. Read these before you start, in this order:

1. `../definition-embedded-videos/SKILL.md` — the build, the memory model, the checks.
2. `../definition-embedded-videos/references/writing.md` — exact definitions. They are as strict here as there: a narrative video is short, not loose.
3. `../definition-embedded-videos/references/format.md` — the file formats and the marks.
4. `../definition-embedded-videos/references/design.md` — the colour tokens, typography and motion rules.
5. [references/narrative.md](references/narrative.md) — the story structure, the time budget and the cuts. This is the part that is new.

The scripts are `../definition-embedded-videos/scripts/build.py` (and its `frame.html`, `render.js`, voice worker). Do not copy them; call them from there. `prepare.py` is not used: you write the beats yourself.

## Steps

1. **Read the paper for its story**, not for its sentences. Use the transcription if one exists (a `.beats` file from the other skill is the fastest way in: strip the marks and read it), else the LaTeX source, else the PDF. Write down: the question, the central object and its definition, each main theorem with its exact statement, the one or two ideas in each proof, and the cases that the paper compares (or that its theorems split into). See "Find the story" in [narrative](references/narrative.md).
2. **Make the work folder** next to the source, `NAME-narrative/`: `glossary.txt` (shared exact words), `01.glossary.txt` (this paper), `01.preamble.tex` (the author's macros), `01-SLUG.beats`, `01.say.txt`.
3. **Write the beats** ([narrative](references/narrative.md), "Write the script"): numbered acts as `##` headings, one short sentence per line, the paper's own formulas in TeX with spoken forms, theorems stated in full. About 1100 to 1300 words of your own.
4. **Write the glossary**: only the words of the main statements, the central objects and the proof steps. Exact definitions, as in `writing.md`. If an exact glossary already exists for this paper or its field, copy it into the folder and prune it; never reuse a glossary written in plain words ("a rule", "like a mirror"), which some old folders hold.
5. **Lint** with `python3 ../definition-embedded-videos/scripts/build.py WORK --lint --formulas`. Fix the errors, fill `NAME.say.todo.txt` into `01.say.txt`, and read the spoken-word count. Cut to the budget ([narrative](references/narrative.md), "Fit 15 minutes").
6. **Optional context overrides**: if any beat needs shorter per-sentence wording than the glossary's definition or reminder, run with `--context-todo` to generate `NAME.context.todo.txt` and add overrides to `NAME.context.txt`. Aim for about 2350 spoken words in total.
7. **Read the narration** as the voice says it (the print-out in the other skill's "Check") and fix what reads badly ([narrative](references/narrative.md), "Read it once").
8. **Build** with `build.py WORK`. Measure the real length with `ffprobe` on `out/NAME.m4a`; if it is more than a minute off 15, cut or add and rebuild (the rebuild is fast: audio is cached by content).
9. **Look at stills** from a theorem beat, a proof beat, a "Words in the meanings" page and a heading before you say it is done. Send the `.mp4` to the user.

## The rules that differ from the reading skill

- **Your words, not the source's.** The ink text is your narrative. Do not retype the paper's paragraphs. A line that starts with `> ` is a short quotation of the source and shows "From the text"; use it at most once or twice, under about 15 words each, for a sentence whose exact wording matters. The `@intro` line says that this is a guide, not a reading.
- **Headings are your acts.** Number them ("## 6. The proof: the volume is quantized"). Name theorems by the paper's numbers ("Theorem 4.1 says this.") so the viewer can find them.
- **Every word of a main statement gets its exact definition; few others do.** The floor is a first-year graduate student in the field: those words have no entry at all (not `(base)`: no entry), so they are neither defined nor listed under other definitions. Side topics (physics context, history, motivations) get no entries either.
- **Statements are complete.** A theorem is stated with all its hypotheses and its conclusion, in one or two lines. The story may simplify the route between statements, never a statement.
- **Proofs are sketched by their key steps**, each step one or two lines, each a true step of the paper's proof (or of the proof it cites, said as such). Name the deep results that the proof uses and who proved them.
- **Cases are compared in parallel lines.** Two or three cases, each in one line of the same shape, then one line that names the single thing that changes from one case to the next.

## Worked example

`~/data/made/videos/connes-narrative` — "Geometry and the Quantum" (Connes, arXiv:1703.02470): ten acts, three cases (the circle, the one-sided equation and its spheres, the two-sided equation and every spin four-manifold), 96 beats, about 2400 spoken words. Its glossary started from the exact shared glossary of `~/data/made/videos/connes`, pruned to 15 shared words, plus about 70 entries of its own.
