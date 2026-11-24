# File formats

## glossary.txt

One entry per line. `#` starts a comment.

```
forms = definition
rational point; rational points = points on the curve whose two coordinates are fractions
(adj) coprime = with greatest common divisor equal to one
(base) integer = a whole number that is positive, negative or zero
$C_1$ "C one" = the smooth projective curve whose affine part has the equation of case one @proof
>> i.e., => that is,
!depth 3
```

- **Word entry.** Forms are separated by `;`. Matching ignores case, takes the longest form first, and needs whole words. List each form you want matched: plurals are not guessed. If the singular and the plural need different wording, make two entries.
- **`(adj)`** marks an adjective. Its definition goes after the noun it describes ("rational lengths, which means ..."), not between the adjective and the noun. A noun entry's definition goes straight after the term ("..., that is, ...").
- **Symbol entry.** TeX between `$`, then how to say it in quotes. The symbol is matched inside formulas token by token, so `$k$` matches the k in `2kx` but not in `\kappa`. A longer entry wins: `$C_1(\mathbb{Q})$` before `$C_1$`.
- **`@scope`** at the end limits an entry to beats in that scope. Several scopes: `@a @b`. A scoped entry beats an unscoped entry with the same form.
- **`>> written => spoken`** changes what the voice says, not what the screen shows. Use it for abbreviations, citation keys and hard names. The build already respells the Greek letter names that the voice gets wrong (see SKILL.md): a `>>` line for one of them wins.
- **`(base)`** marks a word below the floor (see [writing](writing.md)): it gets its definition where the source uses it, but not when another definition uses it. `(base) (adj) continuous = ...` is valid.
- **`!depth N`** sets how many layers of definitions the video gives. With `!depth 3`, a definition may use other glossary terms; the page after each sentence gives the definitions of those words, and then of the words inside those. With no `!depth` line, a definition must not contain a glossary term.
- **Formulas in a meaning.** A definition, a reminder, a line of `NAME.context.txt` and the own words of a mark can hold formulas: `$tex$` or `$tex$[[spoken form]]`. The screen shows the equation in the colour of its term. The voice says the spoken form; without one it uses `PREFIX.say.txt`, then the build's own read-out, and lint lists what is left in `NAME.say.todo.txt`. The word limits count the spoken words. `PREFIX.preamble.tex` applies. Inside a formula write `\mid`, not ` | `. In a mark in the beats file, a formula cannot hold `<`, `>`, `{` or `}`.
- **` | reminder`** after a definition is its short form: the key feature, 16 words or fewer. `Hilbert space = a complex vector space with ... defines | a complete complex inner product space`. The page after a sentence uses it. A sentence uses it when `NAME.context.txt` has no line for that place.
- **`!tex \cmd => words`** tells the automatic formula read-out how to say an author's TeX command (`!tex \sC => C`, `!tex \fibprod => times over`). `!tex \on => @font` marks a command whose argument is read out, like `\mathrm`. Words that end in ` over` (`times over`, `the limit over`) take the subscript after them ("X times over Y, Z") and drop "over" when there is none. One `!tex` line saves a say line in every formula that uses the command: write them before the first lint of a book with its own macros (first used in `~/data/made/videos/khan-stacks`).
- **`!readout maps`** reads formulas in the way of category theory: a superscript is an index ("V zero", "C op", "i upper star"), `i_*` is "i lower star", every letter before a bracket is a function ("i of Y"), `f: X \to Y` is "f from X to Y" and `:=` is "is defined as".
- **`!memory S`** (optional) sets the first interval of the listener's memory in seconds. The default is 120. `!memory 25` gives more reminders (the whole Pimsleur ladder). `!memory 0` turns the memory off: each term gets its meaning in each beat.

### A glossary for one file

`PREFIX.glossary.txt` is added to `glossary.txt` for each beats file whose name starts with `PREFIX`: `04.glossary.txt` goes with `04a-part-one.beats` and `04b-part-two.beats`. Use it for the terms and symbols of one paper or chapter when several share a work folder. `PREFIX.preamble.tex` works the same way for TeX macros. A form may have only one definition per scope across the shared file and the own file.

### Spoken forms: PREFIX.say.txt

```
C_0(\mathbb{A}_K) \rtimes K^\times => the crossed product of C zero of the adeles of K by K cross
```

One formula per line: the TeX exactly as it stands in the beats file, then ` => `, then the words. Lint writes these lines for you, with the right side empty, in `NAME.say.todo.txt`. The file goes with each beats file whose name starts with `PREFIX`. A `[[spoken form]]` in the beats file wins over this file, and this file wins over the automatic read-out.

### Meanings for each sentence: NAME.context.txt

```
9 spectral triple => an algebra of bounded operators on a Hilbert space, with a self-adjoint operator D whose resolvent is compact
212 spectral triple => the algebra, the Hilbert space and the operator D
```

One line per place: the line number in `NAME.beats`, the key of the term (its first form, or the TeX of a symbol), ` => `, and the words for that sentence. `NAME` is the whole name of the beats file. Lint writes the lines for you in `NAME.context.todo.txt`, with the sentence, the exact definition, and whether the place is a first meaning or a reminder. The plan of places depends only on the source text and on which terms the glossary has, so a line stays valid when you change the wording of a definition. If you change the forms of a term or the lines of the beats file, run lint again.

## NN-name.beats

Made by `prepare.py`, then annotated by you. One beat per line. A beat is one sentence, or one clause of a long sentence. The build cuts a line with more than 4 terms by itself; a line break that you add is a cut too.

```
# A unique pair of triangles                 title (once)
@authors Yoshinosuke Hirakawa and Hideki Matsumura
@source arXiv:1809.09936v1
@intro  Optional sentence the voice says after the title and authors.

## 1. Main theorem and its proof             section: a title card, a chapter mark, and spoken
## 3. $K$-theory [[Section three. K theory]] a heading can have a spoken form
@scope proof                                 symbols with @proof apply from here
@scope                                       back to no scope

A plain sentence, copied from the source.
Inline formula $k(1 + x^2)$[[k times one plus x squared]] in a sentence.
We obtain $$r^2 = w^6 - 8$$[[r squared equals w to the sixth minus eight,]] which defines a curve.
~ A line of your own. It shows as "Not in the text".
> A quotation of the source inside a narrative script. It shows as "From the text" (narrative-definition-videos).
% a comment
```

Figures (optional; first used in `~/data/made/videos/packaging-atlas-narrative`):

- `@fig NAME part:term, part` puts `WORK/figs/NAME.svg` on the left of each beat from here on, with the words on the right. Write one before each beat whose pointer changes. Pages after a beat keep its figure. `@cover NAME` gives the title card a figure.
- The SVG is inlined (viewBox about 880 by 790). A part is an element with `class="p" data-p="NAME"` (several names may share it, separated by spaces), with an outline `<rect class="hl" fill="none" stroke="none">`. Its label is `<g class="lab" data-l="NAME">` drawn in `currentColor` (text, leader line, dot). `class="p x"` marks a part drawn only when a beat points to it.
- The listed parts stay at full strength, get their outline and show their label. Every other part fades to 22 percent. The colour is that of `term` in this beat (the glossary key), so the circle in the words and the pointer in the figure match. A part with no term, or whose term has no colour in this beat, is drawn in ink.
- With no `@fig` line the frames are exactly as before.

Formulas:

- `$...$[[spoken]]` inline, `$$...$$[[spoken]]` on its own line. The same TeX later in the file reuses the spoken form. A formula needs none if it is one glossary symbol, if it is in `PREFIX.say.txt`, or if the build can say it itself (letters, numbers, Greek, sub and superscripts, simple operators, fractions, `f(x)`). Read the automatic forms once in the narration print-out: `k(1+x)` is said as "k times, 1 plus x" and `C(Q)` as "C of Q". Where that guess is wrong, give the spoken form.
- Write the spoken form as you would read it to someone who cannot see it. Use commas for the pauses that brackets make: "two k, times w minus one". End it with a comma if the sentence goes on.
- `preamble.tex` in the work folder is added to the TeX preamble (the author's macros, extra packages).

Marks for one beat:

| Mark | Effect |
|---|---|
| `[-key]` | Do not define this term or symbol in this beat. Use it where the sentence itself introduces the thing. The key is the first form, or the TeX of a symbol. |
| `<key>` | Put the definition of `key` here, not at the default place. |
| `<key: own words>` | The same, with a definition written for this sentence. The video gives it here each time, whatever the listener knows. |
| `<key:& own words>` | The same, and your words carry their own connective (no "that is"). |
| `{surface=definition}` | A one-off term that is not worth a glossary entry. |

Where the script puts a definition by default:

- noun term: straight after the term. If a number or an inline formula follows ("genus 2", "genus $g$"), after that.
- adjective term: before the next comma, bracket, or small word such as "of", "is", "which". If another term follows directly, after that term.
- symbol: in one "where k is ..., and x is ..." clause at the end of the beat.
- a glossary word inside a meaning, if the listener does not know it: underlined there. Its own meaning (the reminder form if the entry has one) is on the page that follows the beat, under "Words in the meanings", as "Here, Hilbert space means ...". Each word is followed by the words that its own meaning uses. A page holds about 90 words; more words make more pages.
- a term that the listener knows: a quiet grey outline, no colour and no meaning.

## Output

`WORK/out/NAME.mp4` (H.264 with variable frame timing, AAC, captions, chapter marks), `NAME.m4a`, `NAME.srt`. `WORK/.cache` holds audio, formulas and frames by content hash. It is safe to delete; the next build remakes it.

## Options

```
build.py WORK [--only GLOB] [--lint [--formulas] [--narration]] [--engine phonon|say] [--voice NAME] [--motion full|steps|none] [--jobs N]
```

`--lint --narration` writes `NAME.narration.txt`: what the voice says, one beat per paragraph, each with its line number in the beats file. It is the text that "Check" in SKILL.md asks you to read.
