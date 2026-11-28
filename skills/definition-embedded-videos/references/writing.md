# Writing rules

## Definitions: the exact one, in simple sentences

A definition here is the definition that a textbook or the source gives. It is complete and correct. A mathematician must be able to use it in a proof. Keep the sentence form plain and clear without changing the meaning.

The test: from the definition alone, can the reader decide whether a given object is one? "A space that looks flat near each point" fails. "A topological space in which each point has a neighbourhood homeomorphic to an open subset of n-dimensional real space" passes.

| Term | Wrong: a loose description | Right: the definition |
|---|---|---|
| group | a collection where you can combine any two members and undo each one | a set with an associative binary operation that has an identity element and in which each element has an inverse |
| state | a rule that gives the average value of each thing that you can measure | a linear functional on a C*-algebra that is positive and takes the value one on the unit |
| genus | a whole number that measures how complex the curve is | the dimension of the space of regular differential forms on a smooth projective curve |
| spectrum | the list of special numbers of an operator, like the notes of a drum | the set of complex numbers `$\lambda$` for which `$T - \lambda$` has no bounded inverse |
| entropy | a number that measures how much information is missing | the number `$-\mathrm{Tr}(\rho \log \rho)$[[minus the trace of rho log rho]]` for a density matrix `$\rho$` |
| $k$ | the number that sets the size of the triangle | the positive rational number such that the right triangle has the sides `$k(1+x^2)$`, `$k(1-x^2)$` and `$2kx$`, each with its spoken form |

Rules:

- **No analogy, no picture, no purpose in place of the definition.** Not "like", "a kind of", "measures how", "special", "in the role of". The lint warns about these words. What a thing is used for is not what it is.
- **Use the technical words that the definition needs.** Do not replace "Hilbert space" with "a space where you can measure lengths and angles". Give "Hilbert space" its own entry. The video then gives that meaning too (see "Layers").
- **Start with the kind of thing**, then the condition: "a ring in which ...", "the group of ...", "a map that ...". Do not start with "for ..." or "given ...": write "the element `$ab - ba$`[[a times b minus b times a]], for two elements `$a$` and `$b$` of an algebra", because the voice says "commutator means the element ...". For an adjective, write a phrase that can follow "which means": "equal to its adjoint", "such that each open cover has a finite subcover".
- **A theorem, a conjecture or a formula with a name**: give its statement. "Baum-Connes conjecture = the statement that the assembly map from the equivariant K-homology of the classifying space for proper actions to the K-theory of the reduced group C*-algebra is an isomorphism".
- **A term from physics**: give the exact meaning in physics, with the field equations or defining property written as TeX with spoken forms.
- **A symbol**: say what it is in this source, exactly. "the Dirac operator of the spectral triple", "the field of rational numbers", "the genus of the curve `$C$`". If the source defines the symbol by a formula, write the formula as TeX between `$` with its spoken form.
- **A term that the source defines itself**: use the source's definition, in the source's words where you can.
- **A word with two meanings in the source**: one entry per meaning, with scopes, or a `<key: own words>` mark in the beat.
- **A phrase with no formal definition** ("the spectral paradigm", "quantum gravity"): say exactly what the phrase refers to. Do not invent a formal definition.
- **If you do not know the exact definition, look it up.** Do not guess and do not write a loose one. List in your report each definition that you could not confirm.

Form:

- 40 spoken words or fewer, and 25 or fewer where the definition permits. One sentence part, no full stop. If the exact definition needs more words, move one part of it into a term of its own.
- **An expression is an equation, not words.** Write each formula, each equation and each letter that stands for a mathematical object as TeX between `$`, in the source's notation: "the set of complex numbers `$\lambda$` for which `$T - \lambda$` has no bounded inverse", "the number `$S(\rho) = -\mathrm{Tr}(\rho \log \rho)$[[S of rho equals minus the trace of rho log rho]]`". The screen shows the equation. The voice says the words in `[[...]]`, or the build's own read-out when the formula is simple. "minus the trace of rho times the logarithm of rho" on the screen is hard to read: never write an expression out in words.
- Prose stays prose. "a group in which `$ab = ba$` for all elements `$a$` and `$b$`" is right. A line of symbols with no words is not a definition that a listener can follow.
- No brackets, no semicolons, no contractions, no "etc." in the words. In a formula, write `\mid` and not ` | `.
- Simple present and active voice where it does not make the definition longer.
- One word for one thing in every definition. If you write "map", do not also write "mapping", "function" and "arrow" for the same thing.
- Keep the articles. A plural form gets a plural definition.

## Finalise: the meaning for each sentence

The glossary holds the exact definition. The video does not read it out in full each time: that makes the video too long. When the script is final, you write, for each place where the video gives a meaning, the words for that sentence. `build.py --lint` lists the places in `NAME.context.todo.txt`, each with its sentence and the exact definition. You fill in the lines and move them to `NAME.context.txt`.

- **first** (the listener meets the term for the first time): give the definition itself, cut to the conditions that this sentence and this source use. 30 words or fewer. Leave out side conditions that play no part here (a domain, a countability condition, a second equivalent form). If each part matters, keep each part.
- **reminder** (the listener heard the definition some time ago): give the one key feature that this sentence depends on. 16 spoken words or fewer, and 8 is better. For "the spectrum of D is discrete": "the set of `$\lambda$` where `$D - \lambda$` has no bounded inverse". For "D has compact resolvent" in a sentence on eigenvalues: "the inverse `$(D - \lambda)^{-1}$[[D minus lambda, inverse]]`, a compact operator".
- Expressions are equations here too (see the form rules above): TeX between `$`, with a spoken form.
- Each one must be true, and must come from the exact definition. Cut words: do not change the meaning, and do not put an analogy or a purpose in its place. This is a part of the definition, not a simpler idea.
- It must fit the sentence. It follows the term after ", that is," or ", meaning". For a symbol it follows "where x is". Read the sentence with your words in it.
- Use a technical word only if this definition cannot be said without it. Each glossary word in your text gets a line on the page after the sentence if the listener does not know it yet.
- Do not write a line for a place where the sentence itself gives the meaning. Mark the beat `[-key]`.

Give each entry that other definitions use a reminder in the glossary too, after ` | `: the page after a sentence uses it. "Hilbert space = a complex vector space with an inner product, in which each Cauchy sequence converges for the norm that the inner product defines | a complete complex inner product space".

## Layers

With `!depth 3` in the glossary, the video gives three layers:

1. the meaning of each term in the sentence, in the sentence;
2. on the page after the sentence, the meaning of each glossary word that those meanings use;
3. on the same page, the meaning of each glossary word that the meanings of layer 2 use.

Each layer follows the listener's memory (see SKILL.md): a word that the listener knows gets nothing.

The video does not go deeper. A glossary word in a layer 3 definition stays as it is. So:

- Define a term from the nearest notions that are well known, not from first principles. "factor = a von Neumann algebra whose centre contains only the scalar multiples of the identity" is right. Do not open "von Neumann algebra" inside it.
- Each glossary word in a definition costs the listener time. Use one only where the exact definition needs it. Do not add them for decoration.
- No loops: if "category" uses "morphism", then "morphism" must not use "category". The lint finds loops.
- A common word can be a glossary term by accident ("state", "degree", "field", "complete"). If your definition uses such a word in its common sense, change the word. Read the narration to find these.
- **The floor.** Words that the reader of this source knows for certain need no entry when a definition uses them. For a research paper in mathematics or physics the floor is first-year university mathematics: set, element, subset, map, function, sequence, limit, sum, product, real number, complex number, matrix, derivative, integral. For a text for a general reader the floor is school mathematics. If the source uses a floor word as a term in a sentence, give it an entry with `(base)`: the video defines it there, and does not repeat it under other definitions.

Use `!depth 2` for one layer under the definitions. With no `!depth` line a definition must not contain a glossary term at all: use that only for a source whose terms all have exact definitions in common words.

## Beats

- `prepare.py` copies the sentences. Do not retype or reword them. Fix only what the transcription broke: hyphenation, ligatures, footnote marks, line numbers.
- One sentence per line. The build cuts a line that has more than 4 terms, or more than about 120 spoken words. If lint says a line still has more than 4 terms, break it at a comma or a conjunction and put the conjunction at the start of the next line, so each line still reads as a clause.
- Footnotes that carry part of the argument go in the text where their mark is. Footnotes that are only links or cross-references are left out.
- Leave out citation keys. Where the sentence needs one to stand ("the only previous work is [ZP17]"), keep it and add a `>>` line that says the authors' names.
- Headings are the source's headings. Do not invent sections.

## Narration for the bed

- The listener hears each beat once and cannot look back. After the build prints, read the spoken text aloud in your head. If you lose the thread of a sentence, the listener will too: split it.
- Formulas: say the structure, not the keystrokes. "the square of the bracket, u cubed minus u plus six, and then minus thirty-two". Put a full stop inside a spoken form between two equations of a system.
- Lists of number pairs: say "and" inside a pair and a comma between pairs.
- Do not add jokes, summaries, "as we saw", or signposts. The source is the script.
