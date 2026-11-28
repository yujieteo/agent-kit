---
name: atomic-math-workbooks
description: Turn original mathematical proofs into PDF slide explainers that get the reader up to speed with a calculation fast. The reader copies the calculation onto their own paper to internalise it. Use when the reader wants to derive the starting formulas, keep each move in their head, learn to choose each move as well as apply it, and see why each move is valid and useful. It does not audit the proof for correctness.
---

# Atomic math workbooks

Produce a PDF explainer in slide form, one move per slide. The reader keeps a separate sheet of paper and copies the calculation onto it, one line at a time, predicting each line before copying it. The goal is speed: after one pass, the sheet holds the whole chain from definitions to target, and the reader can read the source's calculation at reading speed and redo its key lines from memory. Design the calculation first, then the practice sequence, then the page. Cut anything that does not serve that goal.

## Separate what to copy from what to read

- **The copy chain** is the numbered display lines. Copied alone, they must read as a complete derivation from the starting definitions to the target. Each line ends with a short rule tag, such as (zero pair) or (even degree), that the reader copies too.
- **The commentary** is everything else: the round's goal, **Why it works**, **Why do it**, and notation reminders. Set it apart, in the margin or in smaller type, so the reader never wonders whether to copy it.
- Keep each display line short enough to write as one line on the reader's paper. Split a longer expression into several moves, or name a common part once in the chain.
- Number lines continuously across the explainer so the sheet and the PDF stay in step. A later line may refer back to an earlier number.

## Start from the source's own lines

- Work from the paper's LaTeX source on arXiv where it exists, so each equation matches the author's exactly. Use a reading-list summary only to find passages.
- Take the conventions from the source: grading, sign rules, normalization, hypotheses. State them once at the start. Do not convert to other conventions.
- Follow the calculation as the source gives it. Do not audit it. If a line plainly does not follow, flag it in one sentence and move on.

## Find the calculation that carries the proof

1. Work backward from the target: what identity or estimate just before it would suffice? Work forward from the definitions. Build each round where the chains meet, around one load-bearing calculation, such as the sign that enables a cancellation or the coefficient that turns a sum into an exponential.
2. Note where each hypothesis is first used and whether each inference is an equality or one-way. Cite imported theorems with an exact anchor (theorem, equation, page) and a link. Do not re-derive them.
3. For each load-bearing move, write down the cue an expert reads off the expression to pick the rule. That cue is what makes the reader fast, so the page must show it.

## Make each move possible in the reader's head

- **Keep the input, the rule, and the next expression local.** Cover the answer and try the move with only the visible line and the adjacent rule. If you need a second identity, two changing expressions, or a definition from pages back, split the move or bring the information next to it.
- **Leave the unchanged terms visible.** Show exactly what replaced the changing term. Name a long common expression once, locally, and restore it when it matters. Preserve signs, degree, and operator order.
- **Use one mathematical decision per line.** Expand one product, insert one sign, match one coefficient, or cancel one pair.
- **Separate choosing from applying.** Where the choice is the difficulty, the first blank asks for the rule and the second for the result. Where the choice is obvious, use one blank.
- **Reintroduce notation where it is needed.** Define every symbol before first use. Put a short reminder beside later uses, such as `$r_i$` = power of ħ at vertex `$i$`, at page turns, and wherever a letter changes meaning.

For example, to pass an even operator `$A$` through a square, expand `$[D,A^2]$` into `$DA^2-A^2D$`. The first blank asks what to insert; the answer is the zero pair `$-ADA+ADA$`, because it exposes the two places where `$D$` crosses `$A$`. Factor the two pairs on separate lines before naming the commutators. Even degree fixes the sign in the graded commutator.

## Sequence for speed

- **Fade the support.** Early rounds are worked out with one blank. Later rounds blank more of the same move types and drop reminders the reader has already used. Help that a novice needs slows a reader who has the move.
- **Reuse moves instead of re-explaining them.** When a move recurs, give it as a blank with only its name ("zero pair"). Do not repeat its explanation.

## Build the round as slides

- State in one line what the round establishes and why it matters. Derive each starting formula line by line. Label definitions, hypotheses, and cited theorems where they enter.
- Give each exercise one move. Beside it, put **Why it works** (the local rule applied to this expression) and **Why do it** (what it makes possible next), one short line each.
- Each slide shows the last few lines of the chain in grey above the current line, and the round's notation in the margin. The reader never pages back.
- A worked line gets one slide: the reader copies it. A blank gets two slides: the first shows the line number, the instruction, and the rule tag; the next slide shows the same with the line filled in. The reader says the line, advances, checks, and copies. Where the choice is the difficulty, hide the tag too, and reveal it on its own slide before the line.
- Do not leave writing space; the reader writes on their own sheet. End the round on the line that reaches the goal.
- Open with one slide: source with exact anchor, target, conventions, and how to use the deck. Close with the whole chain on as few slides as possible, so the reader can check their sheet.
- Follow [Slides](references/formats.md) for type, layout, and the friction checks.
