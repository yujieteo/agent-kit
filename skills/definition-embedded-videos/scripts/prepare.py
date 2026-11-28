#!/usr/bin/env python3
"""Make a draft .beats file from a transcription, mechanically. Standard library only.

  prepare.py paper.tex  --out WORK/01-name.beats [--source "arXiv:1234.5678v1"]
  prepare.py chapter.md --out WORK/07-name.beats          (text or Markdown with $...$ formulas)

The model does not retype the source: this script copies the sentences, one per line, keeps each
formula as TeX, resolves \\ref numbers, and drops citations, labels, figures and the reference list.
What is left for the writer: the glossary, the spoken forms of formulas that build.py cannot say by
itself (PREFIX.say.txt), @scope lines, and a few marks.
"""
import argparse, re, sys, unicodedata
from collections import Counter
from pathlib import Path

MATH_ENVS = "equation|align|eqnarray|gather|multline|displaymath|flalign|alignat"
MULTIROW = {"align", "eqnarray", "gather", "alignat", "flalign"}
THEOREMISH = {"thm": "Theorem", "theorem": "Theorem", "lem": "Lemma", "lemma": "Lemma", "prop": "Proposition",
              "proposition": "Proposition", "cor": "Corollary", "corollary": "Corollary", "defn": "Definition",
              "definition": "Definition", "rem": "Remark", "remark": "Remark", "example": "Example",
              "conjecture": "Conjecture", "claim": "Claim", "fact": "Fact", "notation": "Notation"}
DROP_ENVS = ["figure", "figure*", "table", "table*", "tabular", "tabular*", "thebibliography", "picture", "minipage"]
ABBREV = r"(?:i\.e|e\.g|cf|resp|Fig|Figs|Eq|Eqs|Thm|Prop|Cor|Lem|Def|Sect|Sec|vs|et al|etc|loc|cit|op|No|p|pp|ch|Ch|Dr|Prof|St)\.$"


def brace(s, i):
    """s[i] is '{'. Return (inside, index after the matching '}')."""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def strip_cmd_with_arg(s, name, keep=False, repl=""):
    """Remove \\name[opt]{arg} (keep=True keeps the argument text)."""
    rx = re.compile(r"\\" + name + r"\*?\s*(?:\[[^\]]*\]\s*)*(?=\{)")
    out, pos = [], 0
    for m in rx.finditer(s):
        if m.start() < pos:
            continue
        inner, end = brace(s, m.end())
        out.append(s[pos:m.start()])
        out.append(inner if keep else repl)
        pos = end
    out.append(s[pos:])
    return "".join(out)


def roman(n):
    out = ""
    for v, r in ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= v:
            out, n = out + r, n - v
    return out


def load(path, seen=()):
    s = path.read_text(encoding="utf-8", errors="replace")
    s = re.sub(r"(?<!\\)%.*", "", s)
    # text inside the verbatim/comment package's comment environment is not in the paper
    s = re.sub(r"\\begin\{comment\}.*?\\end\{comment\}", "", s, flags=re.S)
    # \texorpdfstring{tex}{plain}: keep the TeX; \num{12345} (siunitx): the digits with thin-space groups
    B = r"((?:[^{}]|\{[^{}]*\})*)"
    s = re.sub(r"\\texorpdfstring\{" + B + r"\}\{" + B + r"\}", lambda m: m.group(1), s)
    s = re.sub(r"\\num\{(\d+)\}", lambda m: m.group(1) if len(m.group(1)) < 5 else "{,}".join(re.findall(r"\d{1,3}(?=(?:\d{3})*$)", m.group(1))), s)

    def inp(m):
        name = m.group(1)
        f = path.parent / (name if name.endswith(".tex") else name + ".tex")
        return load(f, seen + (path,)) if f.exists() and f not in seen else ""
    return re.sub(r"\\(?:input|include)\{([^}]+)\}", inp, s)


def number(body, pre, first_section=1):
    """Pass 1: give sections, theorems, equations and list items their numbers; return the body with
    the numbers written in, and the label table."""
    thm = {}                                   # env -> (printed name, counter name or None, within section?)
    for m in re.finditer(r"\\newtheorem(\*?)\{([^}]+)\}(?:\[([^\]]+)\])?\{([^}]+)\}(?:\[([^\]]+)\])?", pre):
        star, env, shared, name, within = m.groups()
        thm[env] = (name, None if star else (shared or env), bool(within))
    for env, (name, ctr, within) in list(thm.items()):
        if ctr in thm and ctr != env:
            thm[env] = (name, ctr, thm[ctr][2])
    eq_in_sec = bool(re.search(r"\\numberwithin\{equation\}\{section\}", pre))
    eq_in_ssec = bool(re.search(r"\\numberwithin\{equation\}\{subsection\}|\\@addtoreset\{equation\}\{subsection\}", pre))
    rx = re.compile(r"\\(section|subsection|subsubsection)(\*?)\s*(?:\[[^\]]*\])?(?=\{)|\\begin\{([A-Za-z]+\*?)\}(\[[^\]]*\])?"
                    r"|\\end\{([A-Za-z]+\*?)\}|\\label\{([^}]+)\}|\\item\b(\[[^\]]*\])?|\\appendix\b|\\\\|\\(?:nonumber|notag)\b")
    sec = [first_section - 1, 0, 0]
    counters, eq, labels, stack, out, pos, appendix = Counter(), 0, {}, [], [], 0, False

    def secnum(level):
        head = chr(64 + sec[0]) if appendix else str(sec[0])
        return ".".join([head] + [str(x) for x in sec[1:level + 1]])

    def eqnum():
        if eq_in_ssec:
            return f"{secnum(1)}.{eq}"
        return f"{secnum(0)}.{eq}" if eq_in_sec else str(eq)

    for m in rx.finditer(body):
        out.append(body[pos:m.start()])
        pos = m.end()
        tok = m.group(0)
        if m.group(1):
            level = ["section", "subsection", "subsubsection"].index(m.group(1))
            if m.group(2):
                out.append(f"\\{m.group(1)}\u27e6\u27e7")
            else:
                sec[level] += 1
                for k in range(level + 1, 3):
                    sec[k] = 0
                if eq_in_ssec and level <= 1:
                    eq = 0
                if level == 0:
                    for env, (_, ctr, within) in thm.items():
                        if within:
                            counters[ctr] = 0
                    if eq_in_sec:
                        eq = 0
                out.append(f"\\{m.group(1)}\u27e6{secnum(level)}\u27e7")
            stack[:] = [x for x in stack if x["kind"] != "sec"] + [{"kind": "sec", "num": secnum(level)}]
        elif m.group(3):
            env, base = m.group(3), m.group(3).rstrip("*")
            if base in MATH_ENVS.split("|"):
                numbered = not env.endswith("*") and base != "displaymath"
                if numbered:
                    eq += 1
                stack.append({"kind": "math", "env": base, "num": eqnum() if numbered else None, "numbered": numbered, "at": m.end()})
                out.append(tok + (f"\u27e6{eqnum()}\u27e7" if numbered and base in ("equation", "multline") else ""))
            elif env in thm or base in THEOREMISH:
                name, ctr, within = thm.get(env, (THEOREMISH.get(base, base.capitalize()), None if env.endswith("*") else base, True))
                if ctr == "equation" and eq_in_ssec:
                    eq += 1
                    num = eqnum()
                elif ctr:
                    counters[ctr] += 1
                    num = f"{secnum(0)}.{counters[ctr]}" if within and sec[0] else str(counters[ctr])
                else:
                    num = ""
                stack.append({"kind": "thm", "num": num})
                out.append(f"\\begin{{THM}}\u27e6{(name + ' ' + num).strip()}\u27e7" + (m.group(4) or ""))
            elif base in ("enumerate", "itemize", "description"):
                style = m.group(4) or ""
                kind = "none" if base != "enumerate" else ("roman" if re.search(r"roman|\bi\b|\(i\)", style) else
                                                           "alpha" if re.search(r"alph|\(a\)|\ba\b", style) else "arabic")
                stack.append({"kind": "list", "style": kind, "n": 0, "num": None})
                out.append(f"\\begin{{LIST}}")
            elif base in ("figure", "table"):       # a \label inside gets the float's own number
                counters[base] += 1
                stack.append({"kind": "float", "num": str(counters[base])})
                out.append(tok)
            else:
                stack.append({"kind": "other", "env": env})
                out.append(tok)
        elif m.group(5):
            env, base = m.group(5), m.group(5).rstrip("*")
            if stack and stack[-1]["kind"] != "sec":
                stack.pop()
            out.append("\\end{THM}" if (env in thm or base in THEOREMISH) else
                       "\\end{LIST}" if base in ("enumerate", "itemize", "description") else tok)
        elif m.group(6):
            ctx = next((x for x in reversed(stack) if x.get("num")), None)
            labels[m.group(6)] = ctx["num"] if ctx else "?"
        elif tok.startswith("\\item"):
            lst = next((x for x in reversed(stack) if x["kind"] == "list"), None)
            if m.group(7):
                lab = m.group(7)[1:-1]
            elif lst and lst["style"] != "none":
                lst["n"] += 1
                lab = "(%s)" % {"roman": roman(lst["n"]), "alpha": chr(96 + lst["n"]), "arabic": str(lst["n"])}[lst["style"]]
            else:
                lab = ""
            if lst:
                lst["num"] = lab.strip("()") or None
            out.append(f"\\item\u27e6{lab}\u27e7")
        elif tok == "\\appendix":
            appendix, sec[0] = True, 0
        elif tok == "\\\\":
            top = stack[-1] if stack else None
            # a row break only at brace depth 0 (not inside \substack{..}) and not a trailing \\ before \end
            seg = re.sub(r"\\[{}]", "", body[top["at"]:m.start()]) if top and top.get("at") is not None else ""
            row = top and top["kind"] == "math" and top["numbered"] and top["env"] in MULTIROW and \
                seg.count("{") == seg.count("}") and not re.match(r"\s*\\end\{", body[m.end():])
            if row:
                eq += 1
                top["num"] = eqnum()
            out.append(tok)
        else:                                   # \nonumber
            top = stack[-1] if stack else None
            if top and top["kind"] == "math" and top["numbered"]:
                eq -= 1
    out.append(body[pos:])
    return "".join(out), labels


LETTERS = {"oe": "\u0153", "OE": "\u0152", "ae": "\u00e6", "AE": "\u00c6", "ss": "\u00df", "o": "\u00f8",
           "O": "\u00d8", "aa": "\u00e5", "AA": "\u00c5", "l": "\u0142", "L": "\u0141", "i": "\u0131"}
ACCENTS = {"'": "\u0301", "`": "\u0300", '"': "\u0308", "^": "\u0302", "~": "\u0303", "c": "\u0327", "v": "\u030c"}


def text_clean(t, labels, macros, unknown):
    for name in ("label", "vspace", "hspace", "phantom", "url", "bibliographystyle", "bibliography", "thanks",
                 "address", "email", "date", "keywords", "subjclass", "pagestyle", "thispagestyle", "setcounter",
                 "includegraphics", "caption", "renewcommand", "hypersetup", "index", "color"):
        t = strip_cmd_with_arg(t, name)
    t = re.sub(r"~?\\cite[a-z]*\*?\s*(?:\[[^\]]*\]\s*)*\{[^}]*\}", " [\u00b7]", t)   # shown as [·], said as "the cited work"
    t = re.sub(r"\\eqref\{([^}]+)\}", lambda m: "(" + labels.get(m.group(1), "?") + ")", t)
    t = re.sub(r"\\(?:ref|autoref|cref|Cref)\{([^}]+)\}", lambda m: labels.get(m.group(1), "?"), t)
    t = re.sub(r"\\href\{[^}]*\}", "", t)
    for name, body in macros.items():
        t = re.sub(r"\\" + name + r"(?![A-Za-z])\s*(?:\{\})?", lambda m: body + " ", t)
    t = re.sub(r"\\(['`\"^~])\s*\{?([A-Za-z])\}?|\\([cv])(?:\s*\{([A-Za-z])\}|\s+([A-Za-z]))",
               lambda m: unicodedata.normalize("NFC", (m.group(2) or m.group(4) or m.group(5)) + ACCENTS[m.group(1) or m.group(3)]), t)
    for name, ch in LETTERS.items():
        t = re.sub(r"\\" + name + r"(?![A-Za-z])\s*(?:\{\})?", ch, t)
    t = re.sub(r"\\S(?![A-Za-z])\s*", "Section ", t)
    t = re.sub(r"\\(?:newline|linebreak|\\)(?:\[[^\]]*\])?|\\[,;:! ]|~", " ", t)
    t = re.sub(r"\\(?:noindent|medskip|bigskip|smallskip|hfill|vfill|newpage|clearpage|maketitle|tableofcontents|"
               r"centering|qed|qedhere|par|indent|break|small|large|Large|normalsize|footnotesize|it|em|bf|rm|sl|sc|tt|"
               r"itshape|bfseries|scshape|upshape|quad|qquad)\b\s*", " ", t)
    t = re.sub(r"\\vskip\s*[\d.]+\s*\w+", " ", t)
    t = t.replace("\\%", "%").replace("\\&", "&").replace("\\_", "_").replace("\\#", "#")
    t = t.replace("---", "\u2014").replace("--", "\u2013").replace("``", "\u201c").replace("''", "\u201d")
    for m in re.finditer(r"\\([A-Za-z]+)", t):
        if m.group(1) not in ("item", "begin", "end"):
            unknown[m.group(1)] += 1
    t = re.sub(r"\\(?!item|begin|end)[A-Za-z]+\*?\s*(?:\[[^\]]*\])?", "", t)   # \emph{x} -> {x}; unknown commands go
    return t.replace("{", "").replace("}", "")


def math_clean(tex, env=None):
    tex = re.sub(r"\\label\{[^}]*\}|\\(?:nonumber|notag)\b|\\tag\{[^}]*\}", "", tex)
    num = re.search("\u27e6([^\u27e7]*)\u27e7", tex)               # the display's number, shown at its right
    tex = re.sub("\u27e6[^\u27e7]*\u27e7", "", tex)
    if env in ("align", "alignat", "flalign", "eqnarray"):
        tex = "\\begin{aligned}" + tex.replace("&=&", "&=").replace("& = &", "&=") + "\\end{aligned}"
    elif env in ("gather", "multline"):
        tex = "\\begin{gathered}" + tex + "\\end{gathered}"
    tex = re.sub(r"\s+", " ", tex).strip()
    return tex + (r" \qquad \mathrm{(%s)}" % num.group(1) if num else "")


def dollars(s, keep):
    """Pair up $...$ and $$...$$ with a scanner. A regex goes wrong on "$a$$b$" and on one stray dollar."""
    out, i, n, text_from = [], 0, len(s), 0
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c != "$":
            i += 1
            continue
        disp = s[i:i + 2] == "$$"
        j = i + (2 if disp else 1)
        start, close = j, None
        while j < n:
            if s[j] == "\\":
                j += 2
                continue
            if disp and s[j:j + 2] == "$$":
                close = j
                break
            if not disp and s[j] == "$":
                close = j
                break
            if not disp and s[j] == "\n" and re.match(r"\n[ \t]*\n", s[j:]):
                break                             # blank line inside $...$: the dollar was stray
            j += 1
        if close is None:
            i += 2 if disp else 1                 # leave a stray dollar in the text
            continue
        out.append(s[text_from:i])
        out.append(keep(s[start:close], disp))
        i = text_from = close + (2 if disp else 1)
    out.append(s[text_from:])
    return "".join(out)


def sentences(par):
    """Split a paragraph into sentences. Formula placeholders (\\x00I12\\x00, \\x00D12\\x00) count as words."""
    out, start = [], 0
    for m in re.finditer(r"[.?!][\u201d\")\]]?\s+(?=[A-Z\u201c(\x00])|\x00D\d+\x00\s+(?=[A-Z\u201c])", par):
        head = par[start:m.end()].rstrip()
        if re.search(ABBREV, head) or re.search(r"(?:^|\s)[A-Z]\.$", head):
            continue
        if head.endswith("\x00") and not m.group(0).startswith("\x00"):
            continue
        out.append(head)
        start = m.end()
    tail = par[start:].strip()
    if tail:
        out.append(tail)
    return out


def from_tex(path, source, first_section=1):
    s = load(path)
    s = re.sub(r"\\iffalse.*?\\fi\b", "", s, flags=re.S)
    pre, _, body = s.partition("\\begin{document}")
    body = body.split("\\end{document}")[0]
    body = re.split(r"\\begin\{thebibliography\}|\\bibliography\{|\\printbibliography", body)[0]
    title = brace(pre + body, m.end() - 1)[0] if (m := re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{", pre + body)) else path.stem
    authors = []
    for m in re.finditer(r"\\author\s*(?:\[[^\]]*\])?\s*\{", pre + body):
        a = strip_cmd_with_arg(brace(pre + body, m.end() - 1)[0], "thanks")
        a = re.sub(r"\s+", " ", re.sub(r"\\footnote\{.*?\}|\$[^$]*\$|\\\\.*", " ", a, flags=re.S))   # names only: addresses follow \\
        authors += [x.strip() for x in re.split(r"\\and\b|,| and ", a) if x.strip()]
    macros = {}
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?\s*(?=\{)|\\def\s*\\([A-Za-z]+)\s*(?=\{)", pre):
        val = brace(pre, m.end())[0]
        val = re.sub(r"\\(?:it|em|rm|bf|sl|xspace|textit|emph|textrm)\b|\\/|\\ |[{}]", " ", val).strip()
        if val and "\\" not in val and "$" not in val and "#" not in val:
            macros[m.group(1) or m.group(2)] = re.sub(r"\s+", " ", val)   # text shorthands such as \ie -> i.e.

    body, labels = number(body, pre, first_section)
    math, unknown = [], Counter()

    def keep(tex, disp, env=None):
        math.append((math_clean(tex, env), disp))
        return f"\x00{'D' if disp else 'I'}{len(math) - 1}\x00"

    body = re.sub(r"\\begin\{(" + MATH_ENVS + r")(\*?)\}(?:\{\d+\})?(.*?)\\end\{\1\2\}",
                  lambda m: keep(m.group(3), True, m.group(1)), body, flags=re.S)
    body = re.sub(r"(?<!\\)\\\[(.*?)(?<!\\)\\\]", lambda m: keep(m.group(1), True), body, flags=re.S)
    body = re.sub(r"\\\((.*?)\\\)", lambda m: keep(m.group(1), False), body, flags=re.S)
    body = dollars(body, keep)
    for env in DROP_ENVS:
        e = re.escape(env)
        body = re.sub(r"\\begin\{" + e + r"\}.*?\\end\{" + e + r"\}", "\n\n\x02% [" + env.rstrip("*") + " omitted here]\x02\n\n", body, flags=re.S)
    for name in ("title", "author", "address", "email", "date", "thanks", "subjclass", "keywords", "dedicatory"):
        body = strip_cmd_with_arg(body, name)
    notes = []

    while (m := re.search(r"\\footnote\s*(?=\{)", body)):
        inner, end = brace(body, m.end())
        notes.append(inner)
        body = body[:m.start()] + f"\x03{len(notes) - 1}\x03" + body[end:]
    body = re.sub(r"\\begin\{abstract\}", "\n\n\x02## Abstract\x02\n\n", body)
    body = re.sub(r"\\end\{abstract\}|\\begin\{(?:center|quote|quotation|flushleft|document)\}|\\end\{(?:center|quote|quotation|flushleft)\}", "\n\n", body)

    def head(m):
        inner, end = brace(body, m.end())
        return m.start(), end, "\n\n\x02## " + ((m.group(2) + " ") if m.group(2) else "") + "\x04" + inner + "\x04\x02\n\n"
    while (m := re.search(r"\\(section|subsection|subsubsection)\u27e6([^\u27e7]*)\u27e7\s*(?=\{)", body)):
        a, b, rep = head(m)
        body = body[:a] + rep + body[b:]
    body = re.sub(r"\\paragraph\*?\s*\{([^}]*)\}", lambda m: "\n\n" + m.group(1).rstrip(". ") + ". ", body)
    body = re.sub(r"\\addcontentsline\{[^}]*\}\{[^}]*\}\{[^}]*\}", "", body)
    body = re.sub(r"\\begin\{THM\}\u27e6([^\u27e7]*)\u27e7(?:\[([^\]]*)\])?", lambda m: "\n\n" + m.group(1) + (f" ({m.group(2)})" if m.group(2) else "") + ". ", body)
    body = re.sub(r"\\begin\{proof\}(?:\[([^\]]*)\])?|\\proof\b", lambda m: "\n\n" + ((m.group(1) or "Proof").rstrip(".") + ". "), body)
    body = re.sub(r"\\end\{THM\}|\\end\{proof\}|\\endproof\b|\\begin\{LIST\}|\\end\{LIST\}", "\n\n", body)
    body = re.sub(r"\\item\u27e6([^\u27e7]*)\u27e7", lambda m: "\n\n" + (m.group(1) + " " if m.group(1) else ""), body)
    body = re.sub(r"\\begin\{[A-Za-z*]+\}(?:\[[^\]]*\])?|\\end\{[A-Za-z*]+\}", "\n\n", body)

    lines = [f"# {text_clean(title, labels, macros, Counter()).strip()}"]
    if authors:
        lines.append("@authors " + text_clean(", ".join(authors[:-1]) + (" and " if len(authors) > 1 else "") + authors[-1], labels, macros, Counter()).strip())
    if source:
        lines.append("@source " + source)

    def restore(t):
        def inline(m):
            tex, rest = math[int(m.group(1))][0], t[m.end():m.end() + 2]
            name = re.fullmatch(r"([A-Za-z0-9]{1,3}|\*)(\^\*)?", tex)
            if name and re.match(r"-[A-Za-z]", rest):      # "$K$-theory" is a name, not a formula: K-theory
                return name.group(1) + ("*" if name.group(2) else "")
            return "$" + tex + "$"
        t = re.sub(r"\x00I(\d+)\x00", inline, t)
        t = re.sub(r"\s*\x00D(\d+)\x00\s*", lambda m: " $$" + math[int(m.group(1))][0] + "$$ ", t)
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"\(\s*\)|\[\s*\]", "", t)
        return re.sub(r"\s+([,.;:?!)])", r"\1", re.sub(r"([(\[])\s+", r"\1", t))

    def emit(par):
        par = re.sub(r"\s+", " ", text_clean(par, labels, macros, unknown)).strip()
        for sent in sentences(par):
            fn = [int(k) for k in re.findall(r"\x03(\d+)\x03", sent)]
            sent = restore(re.sub(r"\x03\d+\x03", "", sent))
            if sent and re.search(r"[A-Za-z$]", sent):
                lines.append(sent)
            for k in fn:                             # a footnote is read right after its sentence
                emit(notes[k])

    skipping = False
    for chunk in re.split(r"\n\s*\n", body):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines.append("")
        for piece in re.split(r"(\x02.*?\x02)", chunk, flags=re.S):
            piece = piece.strip()
            if piece.startswith("\x02"):
                h = piece.strip("\x02")
                if "\x04" in h:
                    a, t, _ = h.split("\x04")
                    h = a + restore(text_clean(t, labels, macros, unknown))
                skipping = bool(re.search(r"acknowledg", h, re.I))     # not part of the argument
                if not skipping:
                    lines.append(h)
            elif piece and not skipping:
                emit(piece)
    return lines, unknown, len(math)


def from_text(path, source):
    """A .md or .txt transcription: its headings are kept as written, with no section numbers."""
    lines, math = [], 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for chunk in re.split(r"\n\s*\n", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines.append("")
        if chunk.startswith("#"):
            first, _, body = chunk.partition("\n")
            level, _, t = first.partition(" ")
            lines.append(("# " if level == "#" and not any(l.startswith("# ") for l in lines) else "## ") + t.strip())
            chunk = body.strip()
            if not chunk:
                continue
            lines.append("")
        held = []

        def keep(m):
            held.append(m.group(0))
            return f"\x00{'D' if m.group(0).startswith('$$') else 'I'}{len(held) - 1}\x00"
        par = re.sub(r"\$\$.*?\$\$|(?<!\\)\$.+?(?<!\\)\$", keep, chunk, flags=re.S)
        for sent in sentences(re.sub(r"\s+", " ", par)):
            lines.append(re.sub(r"\x00[DI](\d+)\x00", lambda m: re.sub(r"\s+", " ", held[int(m.group(1))]), sent))
        math += len(held)
    if source:
        idx = next((i + 1 for i, l in enumerate(lines) if l.startswith("# ")), 0)
        lines.insert(idx, "@source " + source)
    return lines, Counter(), math


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--source", default="", help="the @source line, e.g. arXiv:1809.09936v1")
    ap.add_argument("--force", action="store_true", help="overwrite an existing .beats file")
    ap.add_argument("--first-section", type=int,
                    help="LaTeX only: number of the first \\section (default 1; 0 when the printed version leaves "
                         "the introduction unnumbered)")
    a = ap.parse_args()
    tex = a.src.suffix == ".tex"
    if a.first_section is not None and not tex:
        ap.error("--first-section works only for a .tex source: a .md or .txt source keeps its headings "
                 "as written and numbers no sections")
    if a.out.exists() and not a.force:
        sys.exit(f"{a.out} exists. It may hold hand edits. Use --force to overwrite.")
    if tex:
        lines, unknown, nmath = from_tex(a.src, a.source, 1 if a.first_section is None else a.first_section)
    else:
        lines, unknown, nmath = from_text(a.src, a.source)
    out, blank = [], False
    for l in lines:                              # one blank line between paragraphs, none doubled
        if l == "":
            blank = True
            continue
        if blank and out:
            out.append("")
        blank = False
        out.append(l)
    a.out.write_text("\n".join(out) + "\n")
    n = sum(1 for l in out if l and l[0] not in "#@%")
    print(f"{a.out.name}: {n} sentences, {sum(l.startswith('## ') for l in out)} headings, {nmath} formulas")
    if unknown:
        print("  commands dropped from the text (check the ones that carry words):",
              ", ".join(f"\\{k} x{v}" for k, v in unknown.most_common(25)))


if __name__ == "__main__":
    main()
