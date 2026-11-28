# Narrative, budget and cuts

## Find the story

Before you write a line, answer these from the paper. Each answer becomes one or more acts.

1. **The question.** What problem or old question does the paper start from? Who asked it? One or two lines.
2. **The setting.** What dictionary or framework does the paper work in? Only what the main statements need.
3. **The central object.** What does the paper build or study? Its exact definition, and the standard example.
4. **The main statements.** Each theorem, definition or equation that the paper's title and abstract are about. Copy each exact statement into your notes with its number. Usually two to four.
5. **The proofs.** For each main statement, the one or two ideas that make it work, and the deep results it cites (author and content). A proof sketch is three to six true steps, not a summary of the proof's length.
6. **The cases.** Where the statements split into cases, or where the paper compares settings (dimension one against four, a weak hypothesis against a strong one, a one-sided against a two-sided equation), pick the two or three that show the main idea best.
7. **The consequence.** What follows, and what the paper says is still open.

## Write the script

The acts, in this order. Number the headings; the names are yours.

| Act | Lines | What it holds |
|---|---|---|
| The question | 3–5 | The problem, and the paper's answer in one line. |
| The setting | 6–9 | The framework, only as far as the main statements need it. |
| The central object | 6–9 | Its definition (the build defines its words), the example, one comparison with the old view. |
| Context that the theorems need | 0–10 | Short. Cut first when over budget. |
| Each main statement | 4–8 | The statement in full, then what each symbol is. |
| Each proof | 4–8 | The key steps in order. |
| Case by case | 4–8 per case | Each case: the statement, then its proof idea. |
| The cases side by side | 3–5 | One line per case, same shape; one line for what changes. |
| What emerges | 3–6 | The consequence, and what is open. |

Sentence rules:

- One sentence per line, about 8 to 25 words. Plain, clear sentences in simple present and active voice. A sentence that already holds 3 technical words carries no more.
- Put each technical word where its definition can follow it: "the index pairing of $D$ with ..." works; "the Dixmier trace of $X$" breaks if the definition lands between "trace" and "of". If a reminder would split a phrase, mark the line `[-key]`.
- When the sentence itself states what a thing is ("Heisenberg's relation is $[p,q]=i\hbar$", "The volume is ..."), mark it `[-key]`. When the next line defines a symbol, mark the symbol on this line.
- Name theorems and lemmas by the paper's numbers, and state them in full: every hypothesis, the conclusion, "if and only if" where the paper has it.
- A display formula on its own line is a beat of its own; introduce it with a line that ends "is" or ":".
- No "as we saw", no jokes, no summary of the summary. The comparison act is the only recap.

## Fit 15 minutes

The measured pace of the voice with the definitions in place is about 155 spoken words a minute, so 15 minutes is about **2350 spoken words** in the lint count (lint reports minutes at 165 a minute, so its "about 15 min" is about 15.5 real minutes). A good split:

| Part | Words |
|---|---|
| Your narrative, with the spoken forms of formulas | 1100–1300 |
| Meanings in the sentences (first meanings and reminders) | 800–1000 |
| "Words in the meanings" pages | 150–300 |

To see the split, run this from the work folder:

```
python3 - <<'E'
import sys; sys.path.insert(0, "SKILL_DIR/../definition-embedded-videos/scripts")
import build; from pathlib import Path
G = build.Glossary(Path("glossary.txt"), Path("01.glossary.txt"))
own = dw = pw = 0
for b in build.read_beats(Path("01-SLUG.beats"), G)[1]:
    if b.kind == "more": pw += len(build.spoken(b)[0].split()); continue
    for kind, t, _ in build.pieces(b):
        own, dw = (own, dw + len(t.split())) if kind == "def" else (own + len(t.split()), dw)
print("narrative", own, "meanings", dw, "pages", pw)
E
```

When it is over, cut in this order:

1. **Context acts** (history, physics around the result, side remarks). The main statements stay whole.
2. **Entries below the floor.** In the work folder's copy of a shared glossary, delete the entries of words that a first-year graduate student knows (group, vector space, linear map, inner product, norm, topological space, operator, bounded operator, adjoint, eigenvalue, manifold, Riemannian metric, integer, matrix, smooth, continuous ...). Delete, do not mark `(base)`: a base word is still defined where a sentence uses it. Delete entries for side physics and for letters that a sentence introduces.
3. **Pages.** A long "Words in the meanings" page means a definition uses a word that has its own long entry. Drop the inner word's entry if it is below the floor, or reword the outer definition.
4. **Meanings.** First meanings of 10 to 18 words, reminders of 4 to 8. Still exact: cut conditions, never change them.
5. **Symbol reminders** that only repeat the sentence ("where $D$ is the operator of the triple"): mark them `[-key]`.

The first draft of the worked example was 40 minutes: 2300 words of narrative and every operator word defined three layers down. Halving the script and raising the floor brought it to 20; the per-sentence meanings brought it to 15.4.

## Read it once

Print the narration (the "Check" block of the reading skill) and read it as a listener. The faults that came up in the worked example, and their fixes:

| Fault | Fix |
|---|---|
| A definition lands inside a phrase ("the Dixmier trace, that is, ..., of gamma") | `[-key]` on that line, or reorder the sentence so the term ends a clause |
| A symbol's spoken form reads badly at the end of a sentence ("which the paper writes as the Dixmier trace of") | give the formula a `[[spoken form]]` in the beat |
| A compound symbol suppressed with `[-key]`, and its parts now get defined | also mark the parts (`[-M_2(\H)][-M_4(\C)]`) |
| A definition uses a glossary word in another sense ("component of degree 2k" pulled in the topological degree) | reword the definition |
| A symbol definition repeats the name ("where M two of H plus M four of C is ...") | say the meaning in the sentence and mark the symbol |
| A number word after a term gets the definition after it ("KO-dimension, meaning ..., six") | write the number as a digit: the build puts the definition after "6" |
| Two reminders in one sentence for things just said | mark the ones the listener heard in the last minute |

## Output

`WORK/out/01-SLUG.mp4`, `.m4a` and `.srt`, as in the reading skill. The title card's eyebrow, the footer (`@source ... · a narrative guide, not a reading`) and the `@intro` line make it clear that this is a guide.
