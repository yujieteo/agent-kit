---
name: definition-embedded-videos
description: Turn a paper or monograph into a video that reads the text in order, where each technical word and symbol gets its exact definition, cut to what matters in that sentence, put into the same sentence. A forgetting curve decides when the listener needs the meaning again. The words inside each definition get their own meanings straight after the sentence. Terms are circled and colour-matched to their meanings (teoyujie.org colours, Emil Kowalski design rules), and the narration is smooth enough to listen to in bed with the screen off. Use when the user asks for a "definition-embedded", "repeated definitions" or "every word defined" explainer video or audio of a paper, chapter or book. The text must already be transcribed. It does not summarise the source and does not audit it.
---

# Definition-embedded videos

The video is the source read aloud, in order, in the source's own words. The only addition is that a technical word or symbol is followed, in the same sentence, by its definition: the exact one that a textbook gives, written in simple sentences and cut to what matters in that sentence. Straight after the sentence, the technical words inside those definitions get their meanings too, two layers down. A model of the listener's memory decides when: the first time, and then again each time the listener is about to forget. The listener never needs to look at the screen.

The definitions are exact, not simplified. "A space that looks flat near each point" is not a definition of a manifold. Simple Technical English controls the sentence form, not the precision. Read [rules for definitions](references/writing.md) before you write one entry.

You write the glossary. Scripts do the rest.

- `scripts/prepare.py` copies the sentences out of the transcription into `NN-name.beats`, one per line, with each formula kept as TeX. You do not retype the source, and you must not: a paper is someone's copyrighted text, and a model that retypes 3000 pages is slow and makes mistakes. The script moves the user's own file from one format to another on their machine.
- `glossary.txt` holds each term once, with its exact definition. This is your main work.
- `NAME.context.txt` holds, for each place where the video gives a meaning, the words for that sentence. You write these last, when the script is final.
- `PREFIX.say.txt` holds the spoken form of each formula that the script cannot say by itself.
- `scripts/build.py` finds the terms in every sentence, puts each definition in place, cuts a sentence that has too many terms, says the simple formulas, and makes the voice, the frames, the captions and the video.

The cost of the definitions is one glossary. The cost of the sentences is zero. That is what makes a 3000-page monograph possible.

## Steps

1. **Get the text.** Work from the transcription the user gives you. Use the LaTeX source for formulas where it exists, so each formula is the author's. Do not read or re-transcribe the PDF if a transcription exists.
2. **Make the work folder** in the user's project: `glossary.txt`, one `.beats` file per video (per paper, or per chapter of a book), and `preamble.tex` if the formulas need the author's macros.
3. **Write the glossary** ([format](references/format.md), [rules for definitions](references/writing.md)). One term per line. Each definition is the exact definition, in ASD-STE100 sentence form, 40 spoken words or fewer, with each expression as a formula between `$`. Put `!depth 3` at the top so a definition can use other glossary terms. Give each technical word that a definition uses its own entry.
4. **Make the beats with the script.** `python3 scripts/prepare.py paper.tex --out WORK/01-name.beats --source "arXiv:..."` for LaTeX, or the same with a `.md` or `.txt` transcription that has `$...$` formulas. It resolves theorem, section and equation numbers, and leaves out citations, labels, figures and the reference list. Then edit the file only to annotate it: take out front matter that is not content (key words, subject codes, addresses), add `@scope` lines, add `[-key]` where a sentence introduces a symbol, and put a `~` line where a figure or table was. Do not rewrite sentences.
5. **Lint, then fix.** `python3 scripts/build.py WORK --lint --formulas`. Fix every error. Lint writes `NAME.say.todo.txt`, the formulas with no spoken form: fill them in and move the lines to `PREFIX.say.txt`. Lint also names the lines that still have more than 4 terms after the automatic cut: break those lines by hand at a clause boundary (a line break only; the words stay).
6. **Read the narration once** as the voice will say it (see "Check" below). Fix a clumsy sentence with the placement marks in [format](references/format.md), not by rewriting the source.
7. **Finalise.** Lint writes `NAME.context.todo.txt`: each place where the video gives a meaning, with its sentence and the exact definition. Write the meaning for each sentence ("Finalise" in [rules for definitions](references/writing.md)) and move the lines to `NAME.context.txt`. Run lint again until the list is empty.
8. **Build.** `python3 scripts/build.py WORK`. Output is in `WORK/out`: `.mp4` (video, captions, chapters), `.m4a` (audio only, for the bed), `.srt`.
9. **Look at stills** from a formula beat, a long beat and a heading before you say it is done.

## The rules that make it work

- **Verbatim.** The ink-coloured words on screen are the source's words. Anything you add that is not a definition goes on a `~` line and shows as "Not in the text". Use these rarely: for code, a figure, or a table that cannot be read aloud.
- **A meaning when the listener needs it.** The build keeps a model of the listener's memory for each term, on the clock of the narration. It uses the forgetting curve of FSRS, R = (1 + 19/81 · t/S)^(-1/2), where S is the time until 90% is left, and the recall ladder of Pimsleur: each recall multiplies S by 5. A new term gets its definition. While R is 0.9 or more, the term stands alone, in a grey outline. Below 0.9 the term gets a short reminder, at about 2 minutes, 10 minutes, 52 minutes and 4.3 hours after the first time, for a term that stays in use. This is what keeps a video short: a term that the text uses 80 times gets about 5 meanings, not 80. `!memory 0` in the glossary gives each term its meaning each time.
- **Equations on the screen, words for the voice.** In a meaning, as in the source, an expression is TeX between `$` and shows as an equation, with its spoken form in `[[...]]`. Never write an expression out in words ("minus the trace of rho times the logarithm of rho"): it is hard to read on the screen.
- **Exact in the glossary, short in the video.** The glossary's definition is the exact one. The video gives the part of it that matters in the sentence: you write these words last, in `NAME.context.txt`. They must be a true part of the definition, never an analogy.
- **Exact definitions, three layers.** With `!depth 3` (the user's standing choice), a definition uses the technical words it needs. The build puts the term's meaning in the sentence, and puts the meanings of the words inside it, and of the words inside those, on a page straight after the sentence ("Here, Hilbert space means ..."), for each word that the listener does not know at that time. It stops there. A definition must never come back to its own term: the lint finds loops. Mark words below the floor `(base)` so they are not repeated under every definition.
- **The sentence that introduces a thing is its definition.** In "Let $p$ be a prime number", do not also explain $p$: mark the line `[-p]`.
- **At most 4 terms and about 120 spoken words in a beat.** Four colours come from the site. The build cuts a longer sentence at a comma or a conjunction by itself, and reads the parts with a short gap. A fifth and sixth colour exist for what is left; past six the colours repeat and lint names the line.
- **A formula is said in words.** The build says simple formulas itself ("X sub Q", "f of x", "p squared") and uses each glossary symbol's spoken name. The rest need a spoken form from you, in `PREFIX.say.txt` or as `[[...]]` after the formula. Symbols get their meanings in a "where" clause after the sentence, not in the middle of the formula.
- **Scopes for symbols.** The same letter means different things in different sections. Give symbol entries a `@scope` and switch with `@scope name` lines in the beats.

## Check

Print what the voice will say, and read it:

```
python3 - <<'E'
import sys; sys.path.insert(0, "SKILL_DIR/scripts")
import build; from pathlib import Path
G = build.Glossary(Path("glossary.txt"))
for b in build.read_beats(Path("01-name.beats"), G)[1]:
    print(build.for_voice(build.spoken(b)[0], G), "\n")
E
```

Look for: a definition that is a loose description and not the definition, a common word that the build took for a glossary term, a definition that lands in the middle of a noun phrase, two definitions in a row, a symbol read as "C underscore 1", a citation key read aloud. Each has a one-mark fix in [format](references/format.md).

## Speed and scale

Measured on an M5. A 3 h 33 min video (875 beats, 919 meanings in the sentences, 356 lines on pages, 1132 formulas): voice 3 min 53 s, frames 37 s, mux 86 s, so 6 minutes in all, 36 times faster than real time. A 1 h 42 min video (451 beats): 3 minutes. A second build after an edit takes seconds for the voice, because audio, formulas and frames are cached by content; the mux runs again each time. For length, plan on about 2 to 4 times the time it takes to read the source alone: the memory model, not the number of terms, sets it.

- **Voice** is Phonon 31M (`gradium/phonon-31m-en`, through the `ptts` package, run by `uv`), voice "Everly". It is the fastest good voice on this machine: about 30 times faster than real time. It does not go faster with more processes (the performance cores are the limit), so the script uses 3. Supertonic 3 was 10 times slower here. `--engine say` uses the macOS voice with no install; it is faster but sounds flat.
- **How the voice says letters.** Phonon reads some Greek names wrongly as written (xi as "she", psi as "see", phi as "fee", chi as "chee") and swallows a variable of one small letter ("zeta of s"). The build respells them for the voice only: xi, psi, phi, chi, pi and tau become "zye", "sigh", "fie", "kye", "pie" and "tao", and a small single letter becomes a capital. The screen and the captions keep the usual spelling. A glossary line such as `>> xi => ksee` overrides the table. If you change the voice or the engine, test the letters again: synthesise each name between unrelated words ("Table. Xi. Window.") and transcribe it with a speech recogniser.
- **Captions** come from the script's own text and timings. Nothing is transcribed from audio.
- **Frames** are screenshots from the installed Chrome, driven by `bun` with no packages. The video stores one frame per change, not 30 per second, so encode time depends on the number of beats, not the length.
- **Formulas** are set by `pdflatex` in one batch and cut into SVG, so the author's macros and diagrams work.
- **Finalising at scale.** The per-sentence meanings are the slow part for a model, not for the machine. For a long file, let lint write the places, split them into worksheets of about 300 places (line, sentence, exact definition, present text), give each worksheet to one subagent, and merge the lines back into `NAME.context.txt`. The plan of places does not move when the wording changes, so the parts can be done at the same time.
- **A monograph.** One `.beats` file per chapter, one shared glossary (plus `PREFIX.glossary.txt` for the terms and symbols of one chapter), `build.py WORK --only '07-*'` to build one. Files over 400 beats drop the fades by default (`--motion steps`); `--motion none` makes one frame per beat. Plan for about 2 minutes of voice time per hour of narration. Write the glossary first and lint it before any chapter: a change to a definition re-voices every beat that uses it.
- Use subagents to write beats for chapters in parallel only after the shared glossary is fixed. Each one reads this file, the two reference files and the shared glossary, writes its own `.beats` and `PREFIX.glossary.txt`, and runs `--lint --formulas`. Agents do not build: the voice step does not go faster when shared, so build the chapters one after another yourself.

## Design

Tokens and motion rules are in [design](references/design.md). Do not add colours, shadows or decoration. The look is teoyujie.org: light warm grey, Inter, one hairline, and colour only where it carries meaning.

## Files

- `scripts/prepare.py`: transcription (LaTeX, or text with `$` formulas) to draft beats. Standard library only.
- `scripts/build.py`: lint, voice, formulas, frames, captions, mux. Standard library only.
- `scripts/render.js`: Chrome frame renderer (bun).
- `scripts/frame.html`: the page that every frame is drawn on.
- `scripts/tts_phonon.py`: voice worker.
- `assets/fonts`: Inter and IBM Plex Mono, as served by teoyujie.org.
- Worked example: `~/data/made/videos/rational-triangles` ("A unique pair of triangles", arXiv:1809.09936).
