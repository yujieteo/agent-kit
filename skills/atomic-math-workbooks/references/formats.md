# Slides

## Set the slides

Use teoyujie.org's restrained style: plain headings, dark text on white, quiet grey rules, no decoration. Typeset with XeLaTeX, `fontspec`, and `unicode-math` on a 16:9 page, one slide per page. Set text in Inter, mathematics in STIX Two Math, and upright names in math (`\mathrm`) in STIX Two Text. Treat any "Missing character" line in the log as a failure.

Build on [wbslides.sty](wbslides.sty), which implements this layout: `\round{title}{goal}{notation}`, `\given` for a line to copy, `\step` for a blank, `\choosestep` for a blank whose rule is hidden, `\textslide`, and `\fullchain[n]`. [example-dorigoni.tex](example-dorigoni.tex) is a finished deck. The template loads Inter from its `.ttf` files by name. Build with `OSFONTDIR` set to the folder that holds them, for example `OSFONTDIR=~/Library/Fonts/HomeManager/truetype xelatex deck.tex`.

Lay out every slide the same way, so the eye always finds things in the same place:

- **Header.** Workbook name, round title, and the line numbers on this slide, in small grey type.
- **Main column, left, about two thirds.** The last two or three chain lines in grey, then the current line in black. Each chain line is its number, the expression, and its rule tag. Set the expression large enough to read at a glance and short enough to fit one line.
- **Margin column, right.** The round's notation, then **Why it works** and **Why do it** for the current line, in smaller type.

A prompt slide shows the current line as its number, a one-line instruction, a blank, and the rule tag. The next slide fills the blank. Nothing else changes between the two, so the eye goes straight to the answer.

## Check for friction

These checks look for what slows the reader down. They do not check the mathematics.

- **Cold pass.** Take each blank with the next slide unseen. Read the visible lines and margin, say the next line, and say why it helps. A reread to recover a symbol, a guess, or a second move in one line means split the step or move the information onto the slide.
- **Chain alone.** Read the final chain slides on their own. They must read as a complete derivation, and no line should be too long to write as one line by hand.
- **Render.** Run `pdffonts` and confirm every font is embedded. Render the slides to images and look at them: legibility, crowding, overflow, and that each answer slide differs from its prompt slide only in the blank.

In the handoff, say which checks ran and list any steps you flagged in the source.
