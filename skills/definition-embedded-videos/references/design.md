# Design

The look is teoyujie.org, which takes its tokens from emilkowal.ski. The motion rules are Emil Kowalski's (github.com/emilkowalski/skills, `emil-design-eng`). Values come from the served CSS, not from taste. If the site changes, re-read `https://teoyujie.org/style.css` and change `scripts/frame.html`.

## Tokens

| Role | Value | Site token |
|---|---|---|
| Background | `#fdfdfc` | `--bg` |
| Source text | `#21201c`, Inter 450 | `--ink` |
| Header, footer, connective words | `#63635e` | `--muted` |
| Definition not yet spoken | `#8d8d86` | `--underline-hover` |
| Hairline, progress track | `#e9e9e7` | `--line` |
| Term 1 to 4 | `#0d74ce` `#cc4e00` `#6550b9` `#2a7e3b` | `--blue` `--orange` `--violet` `--grass` (series 1 to 4) |
| Term 5, 6 (overflow only) | `#cb1d63` `#107d98` | not on the site: Radix crimson 11 and cyan 11, the same scale and step |

Type: Inter (the site's file) with its feature settings, 46 px for the sentence on a 1920 by 1080 frame, stepping down until the beat fits. Line height 1.74 so the circles of two lines do not touch. Formulas are Computer Modern from TeX, as in the source. Light only, as the site is.

## What colour means

- A circled, tinted pill is a technical term from the source. Its colour is its identity in this beat.
- Text in the same colour is that term's meaning. The eye can pair them with no legend.
- Ink text is the source. Read only the ink and you have read the paper.
- A symbol in a formula takes its colour, and its first appearance is boxed.
- A term keeps its colour from one beat to the next when it can.
- An underlined word inside a meaning is a glossary word too. The page that follows the sentence ("Words in the meanings") gives its meaning: the word in bold, the meaning after it, both in the colour of the term that needed them.
- A term in a grey outline, with ink text, is a term that the listener heard defined a short time ago. It gets no meaning now.
- Grey text is a meaning the voice has not reached. It turns to its colour when the voice gets there, so a glance shows where the reading is.

## Motion

Each rule is from the Emil Kowalski skill, applied to a video that someone mostly listens to.

1. Motion needs a purpose. The only purposes here: show that a new sentence has come, and show where the voice is.
2. Colour and opacity only. Nothing moves, scales or reflows: the layout of a beat is the same in every state. This is also his reduced-motion rule (keep opacity and colour, drop movement), which fits a dark bedroom.
3. Ease-out, the strong curve `cubic-bezier(0.23, 1, 0.32, 1)`, never ease-in. A fade is 100 ms: two eased steps of 50 ms (68%, 90%), then the final state.
4. Under 300 ms, always.
5. Things seen hundreds of times get less animation. Over 400 beats in a file, the fades are dropped and states switch at once (`--motion steps`).
6. Nothing appears from nothing: a new beat fades from 68% opacity, not from zero.

## Layout

Left-aligned column with 128 px margins, as the site's column is left-aligned. Header: title in ink 500, section in muted. Footer: a 2 px progress line and the beat count in tabular figures. A sentence sits at the vertical centre. A display formula is centred on its own line. No cards, borders, shadows, icons or background shapes.
