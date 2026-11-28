#!/usr/bin/env python3
"""Build definition-embedded explainer videos. Standard library only.

  build.py WORK            build every *.beats file in WORK (one video per file)
  build.py WORK --lint     check the glossary and the beats, build nothing

WORK holds glossary.txt, one or more *.beats files and, if needed, preamble.tex.
Output goes to WORK/out. Caches (audio, formulas, frames) go to WORK/.cache and
are keyed by content, so a second run only rebuilds what changed.
See ../references/format.md for the file formats.
"""
import argparse, base64, hashlib, html, json, os, re, shutil, subprocess, sys, time, wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
# teoyujie.org series colours (blue, orange, violet, grass). The last two are the same
# Radix step-11 scale (crimson, cyan), used only when one beat has more than four terms.
PALETTE = ["0d74ce", "cc4e00", "6550b9", "2a7e3b", "cb1d63", "107d98"]
SOFT_TERMS, HARD_TERMS = 4, len(PALETTE)
SOFT_WORDS = 120            # a beat with two or more terms is cut again when the voice would say more words than this
MORE_WORDS = 90             # about this many words on one "words in the meanings" page
PACE = 2.5                  # the finished narration is about this many times as long as the source text alone
FIRST_WORDS, AGAIN_WORDS = 30, 16      # limits for a definition written for its sentence: first time, and reminder
EASE = [0.68, 0.9]          # cubic-bezier(0.23, 1, 0.32, 1) at 1/4 and 1/2 of a 200 ms fade
TWEEN = 0.05                # seconds per tween frame
HOLD = 8.0                  # longest time one encoded frame stays up; longer holds repeat it
GAP = {"prose": (0.0, 0.55), "narr": (0.0, 0.55), "more": (0.0, 0.6), "head": (0.5, 0.7), "title": (0.4, 0.8)}
PTTS = "ptts==0.7.1"


def sha(*parts):
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:20]


def die(msg):
    sys.exit("error: " + msg)


# ---------------------------------------------------------------- glossary

class Entry:
    def __init__(self, key, kind, forms, tex, say, defn, scopes, line):
        self.key, self.kind, self.forms, self.tex = key, kind, forms, tex
        self.say, self.defn, self.scopes, self.line = say, defn, scopes, line
        self.toks = textoks(tex) if tex else []
        self.base = False           # (base): defined where the source uses it, never as a word inside a definition
        self.short = None           # the reminder: the key feature, for when the listener has heard the definition


PROTECT = (r"\\(?:text|textrm|textit|textbf|textsf|texttt|emph|mathrm|operatorname|mbox|hbox|begin|end)\s*\{[^{}]*\}"
           r"|\\(?:ar|arrow)\s*(?:\[[^\]]*\])+|\\xymatrix(?:@[^{\s]*)?")       # words, and the options of diagram arrows


TEXTOK = re.compile(PROTECT + r"|\\[A-Za-z]+|\\.|\S")


def textoks(s):
    return TEXTOK.findall(s)


class Marked(list):
    """Formula tokens, with glossary symbols as (entry, tokens). `gaps[i]` says if white space came before
    token i in the source, so the formula goes back to TeX as the author spaced it."""
    gaps = ()


class Glossary:
    def __init__(self, *paths):
        self.entries, self.fixes, self._re, self.depth = [], [], {}, 1
        self.memory = 120.0         # seconds: how long the listener keeps a meaning after the first time (0: no memory)
        for path in paths:
            self.load(path)

    def load(self, path):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!depth"):
                self.depth = int(line.split()[1])
                continue
            if line.startswith("!memory"):
                self.memory = float(line.split()[1])
                continue
            if line.startswith("!readout"):        # `!readout maps`: notation of category theory (see auto_say)
                READOUT.add(line.split()[1])
                continue
            if line.startswith("!tex "):          # `!tex \sC => C`: how the automatic read-out says a TeX command
                a, _, b = line[5:].partition("=>")
                a, b = a.strip(), b.strip()
                if b == "@font":                    # a command whose argument is read out, like \mathrm
                    FONT.add(a)
                else:
                    SAY[a] = b
                continue
            if line.startswith(">>"):
                a, _, b = line[2:].partition("=>")
                self.fixes.append((a.strip(), b.strip()))
                continue
            if " = " not in line:
                die(f"{path.name}:{n}: expected 'forms = definition'")
            left, defn = (x.strip() for x in line.split(" = ", 1))
            scopes = re.findall(r"\s@([\w-]+)", " " + defn)
            defn = re.sub(r"(\s@[\w-]+)+\s*$", "", " " + defn).strip()
            defn, _, short = (x.strip() for x in defn.partition(" | "))
            m = re.match(r'\$(.+?)\$\s*(?:"(.*?)")?$', left)
            if m:
                tex = m.group(1).strip()
                e = Entry(tex, "sym", [], tex, m.group(2) or tex, defn, scopes, f"{path.name}:{n}")
                e.short = short or None
            else:
                kind, base = "noun", False
                while left.startswith(("(adj)", "(base)")):
                    if left.startswith("(adj)"):
                        kind, left = "adj", left[5:].strip()
                    else:
                        base, left = True, left[6:].strip()
                forms = [f.strip() for f in left.split(";") if f.strip()]
                e = Entry(forms[0], kind, forms, None, None, defn, scopes, f"{path.name}:{n}")
                e.base, e.short = base, short or None
            self.entries.append(e)

    def live(self, scope):
        """Entries that apply in this scope. A scoped entry beats an unscoped one with the same form."""
        out = {}
        for e in self.entries:
            if e.scopes and scope not in e.scopes:
                continue
            for name in (e.forms or [e.key]):
                k = (e.kind == "sym", name.lower() if e.kind != "sym" else name)
                if k not in out or e.scopes:
                    out[k] = e
        return out

    def words(self, scope):
        if scope not in self._re:
            table = {k[1]: e for k, e in self.live(scope).items() if not k[0]}
            forms = sorted(table, key=len, reverse=True)
            rx = re.compile(r"(?<![\w])(?:" + "|".join(map(re.escape, forms)) + r")(?![\w])", re.I) if forms else None
            syms = sorted({id(e): e for k, e in self.live(scope).items() if k[0]}.values(),
                          key=lambda e: len(e.toks), reverse=True)
            self._re[scope] = (rx, table, syms)
        return self._re[scope]

    def family(self, e):
        """One name for an entry and for the entry that is its singular or plural: the listener learns them as one."""
        if not hasattr(self, "_fam"):
            forms = {f.lower(): x for x in self.entries for f in x.forms}
            self._fam = {}
            for f, x in forms.items():
                for end, new in (("ies", "y"), ("ices", "ix"), ("es", ""), ("s", "")):
                    if f.endswith(end) and f[:len(f) - len(end)] + new in forms:
                        self._fam[x.line] = forms[f[:len(f) - len(end)] + new].line
                        break
        return self._fam.get(e.line, e.line) if e.line else e.key

    def find(self, name, scope):
        live = self.live(scope)
        return live.get((True, name)) or live.get((False, name.lower()))


# ---------------------------------------------------------------- the listener's memory

class Memory:
    """What the listener still knows of each term, on a clock of narration seconds.

    Forgetting curve (the power law of FSRS-4.5; a power law fits forgetting better than an exponential, Wixted
    and Ebbesen 1991):  R(t) = (1 + 19/81 * t / S) ** -0.5,  where S is the time until 90% is left.
    Schedule (Pimsleur 1967, graduated interval recall): each recall multiplies S by 5. His ladder is 5 s, 25 s,
    2 min, 10 min, 52 min, 4.3 h. The definition inside the sentence and the use of the term that follows stand
    for the first two steps, so S starts at `first` = 120 s (`!memory 25` gives the whole ladder). Recalls that
    grow apart keep a term alive inside one session, most of all when other material interferes (Landauer and
    Bjork 1978; Karpicke and Roediger 2007; Storm, Bjork and Storm 2010).
      new             the definition
      R >= 0.9        "known":  the term stands alone
      0.5 <= R < 0.9  "fading": a short reminder, and S grows
      R < 0.5         "lost":   a short reminder, with the same S: that step failed, so it comes again
    The clock runs on the words of the source only (times PACE), and `side` holds what the listener heard on the
    pages after the sentences. So the plan for the sentences depends on the source and the glossary's terms, not
    on the wording of any definition: a line in NAME.context.txt stays valid when other lines change.
    """
    GROW, HIGH, LOW = 5.0, 0.9, 0.5

    RANK = {"new": 0, "lost": 1, "fading": 2, "known": 3}

    def __init__(self, first, side=True):
        self.first, self.now, self.s, self.at = first, 0.0, {}, {}
        self.side = Memory(first, False) if side else None

    def either(self, k):
        """For a word on a page: what the listener has of it from the sentences or from the pages."""
        self.side.now = self.now
        return max(self.state(k), self.side.state(k), key=self.RANK.get)

    def state(self, k):
        if self.first <= 0 or k not in self.s:
            return "new"
        r = (1 + 19 / 81 * (self.now - self.at[k]) / self.s[k]) ** -0.5
        return "known" if r >= self.HIGH - 1e-9 else "fading" if r >= self.LOW else "lost"

    def told(self, k):
        st = self.state(k)
        if st == "known":
            return
        self.s[k] = self.first if st == "new" else self.s[k] * (self.GROW if st == "fading" else 1)
        self.at[k] = self.now


# ---------------------------------------------------------------- beats

TOK = re.compile(
    r"\$\$(.+?)\$\$(?:\s*\[\[(.+?)\]\])?"      # 1,2  display formula and how to say it
    r"|\$(.+?)\$(?:\[\[(.+?)\]\])?"            # 3,4  inline formula and how to say it
    r"|\[-((?:[^\[\]]|\[[^\[\]]*\])+)\]"       # 5    do not define this key in this beat (the key may hold [..])
    r"|<([^<>:=$]+?)(?::\s*([^<>]+))?>"        # 6,7  put the definition of a key here (own words optional)
    r"|\{([^{}=]+)=([^{}]+)\}")                # 8,9  one-off term with its definition
ADJ_STOP = re.compile(
    r"[,.;:()?!]|\s(?:of|with|and|or|is|are|was|has|have|which|that|in|on|over|at|to|for|by|as|we|there|be|from|"
    r"such|than|if|then|when|where|whose|it|this|these|those|can|may|will|does|do)\b|$", re.I)
NUM_AFTER = re.compile(r"\s+\d+(?:\.\d+)*\)?|\)")
LEADS = [", that is, ", ", meaning "]
DMATH = re.compile(r"\$(.+?)\$(?:\[\[(.*?)\]\])?")      # a formula inside a meaning, and how to say it


def def_say(text, unknown=""):
    """A meaning as the voice says it: each formula gives its spoken form."""
    if "$" not in text:
        return text
    def one(m):                                      # a formula with no spoken form yet: one word if it is one symbol
        if m.group(2) is not None:
            return " " + m.group(2) + " "
        return " " + (unknown if len(textoks(m.group(1))) > 2 else unknown[:1]) + " "
    return re.sub(r"\s+([,.;:?]|!(?!-)|-\w)", r"\1", re.sub(r"\s+", " ", DMATH.sub(one, text))).strip()


def def_plain(text):
    """A meaning with its formulas blanked, to look for words in."""
    return DMATH.sub(lambda m: " " * len(m.group(0)), text) if "$" in text else text


def math_jobs(beats, pre):
    """Every formula that the frames show: {id: (tex, display)}."""
    jobs = {}
    for b in beats:
        for s in b.segs:
            if s[0] in ("imath", "dmath"):
                jobs[sha(pre, s[1], s[0])] = (s[1], s[0] == "dmath")
            elif s[0] == "wsym":
                jobs[sha(pre, s[2], "imath")] = (s[2], False)
            elif s[0] == "def":
                for m in DMATH.finditer(s[3]):
                    jobs[sha(pre, m.group(1).strip(), "imath")] = (m.group(1).strip(), False)
    return jobs


class Beat:
    def __init__(self, kind, raw, scope, section, src):
        self.kind, self.raw, self.scope, self.section, self.src = kind, raw, scope, section, src
        self.segs, self.colour, self.problems, self.unsaid = [], {}, [], []
        self.head_say, self.cont, self.more = None, False, []
        self.told, self.told_side, self.todo, self.known, self.used = [], [], [], 0, []
        self.quote = False                           # a '> ' line: the source's own words inside a narrative script
        self.fig = None                              # '@fig NAME part:term, ...': the figure beside this beat, and what it points to


def read_beats(path, G):
    meta, beats, scope, section = {"title": path.stem}, [], None, ""
    fig = [None]
    say_memo, prev = {}, {}
    mem, ctx = Memory(G.memory), {}
    cf = path.with_suffix(".context.txt")           # LINE key => the reminder that fits that sentence
    for l in (cf.read_text().splitlines() if cf.exists() else []):
        left, sep, text = l.rpartition(" => ")
        num, _, key = left.strip().partition(" ")
        if sep and text.strip() and num.isdigit():
            ctx[(int(num), key.strip())] = text.strip()

    def keep(b):
        """Add a beat and its pages. The listener has now heard them: move the clock."""
        pages = more_beats(b)
        for x in [b] + pages:
            x.fig = fig[0]
        mem.side.now = mem.now
        for k in dict.fromkeys(b.told):
            mem.told(k)
        for k in dict.fromkeys(b.told_side):
            mem.side.told(k)
        own = sum(len(t.split()) for kind, t, _ in pieces(b) if kind not in ("def", "wsym"))
        mem.now += own * PACE / 165 * 60
        beats.extend([b] + pages)

    for f in own_files(path.parent, path, ".say.txt"):       # TeX => spoken form, one per line
        for l in f.read_text().splitlines():
            tex, sep, say = l.rpartition(" => ")
            if sep and say.strip() and not l.startswith("#"):
                say_memo[" ".join(textoks(tex.strip().strip("$")))] = say.strip()
    for n, line in enumerate(path.read_text().replace("\u2019", "'").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("%"):
            continue
        src = f"{path.name}:{n}"
        if line.startswith("## "):
            b = Beat("head", line[3:].strip(), scope, "", src)
            compose(b, G, say_memo, prev)
            section = b.section = re.sub(r"\s+", " ", re.sub(r"\$[^$]*\$", "\u2026", b.raw))   # short label for the header
            keep(b)
            continue
        elif line.startswith("# "):
            meta["title"] = line[2:].strip()
            continue
        elif line.startswith("@"):
            k, _, v = line[1:].partition(" ")
            if k == "scope":
                scope = v.strip() or None
            elif k == "fig":
                fig[0] = v.strip() or None
            else:
                meta[k] = v.strip()
            continue
        elif line.startswith("~ "):
            b = Beat("narr", line[2:].strip(), scope, section, src)
        else:
            quote = line.startswith("> ")
            line = line[2:].strip() if quote else line
            helped = set()                           # a word inside a definition gets its meaning once per sentence
            for n_part, part in enumerate(auto_split(line, G, scope, section, say_memo, mem)):
                b = Beat("prose", part, scope, section, src)
                b.cont, b.quote = n_part > 0, quote
                compose(b, G, say_memo, prev, helped, mem, ctx)
                prev = b.colour
                keep(b)
            continue
        compose(b, G, say_memo, prev, None, mem, ctx)
        prev = b.colour
        keep(b)
    title = Beat("title", meta["title"], None, "", path.name)
    opening = meta["title"].rstrip(".") + "."
    if meta.get("authors"):
        opening += f" By {meta['authors']}."
    opening += " " + meta.get("intro", "This reading follows the text. A technical word comes with its meaning when it is new, "
                                    "and again when it is time to recall it.")
    title.segs = [("text", opening)]
    title.meta = meta
    title.fig = meta.get("cover")
    return meta, [title] + beats


def more_beats(b):
    """The pages that follow a beat: the meaning of each glossary word that its definitions use."""
    out, cur, n = [], [], 0
    for root, word, found, layer, defn in b.more:
        if cur and n + len(def_say(defn).split()) + 2 > MORE_WORDS:
            out.append(cur)
            cur, n = [], 0
        head = word[0].upper() + word[1:] if (cur or out) and word[1:2] != "-" else word      # lower case after "Here,"
        text = f"{head} means {defn.rstrip('.')}."
        cur.append(("def", root, " " if cur or out else "Here, ", text, found, head, layer > 1))
        n += len(def_say(text).split())
    if cur:
        out.append(cur)
    pages = []
    for segs in out:
        m = Beat("more", "", b.scope, b.section, b.src)
        m.segs, m.colour = segs, b.colour
        pages.append(m)
    return pages


CUTS = [r"[,;:]\s+",
        r"\s+(?=(?:which|where|whose|such that|so that|but|while|whereas|because|since|when|if|then)\s)",
        r"\s+(?=(?:and|or)\s)",
        r"\s+(?=(?:due to|with|under|over|by|for|from|in|on|of|to|as|into|between|through)\s)"]


def auto_split(raw, G, scope, section, say_memo, mem=None):
    """A sentence with more than 4 terms is cut at a comma or a conjunction, as often as needed.
    Both parts keep the source's words. Marks such as [-k] go with every part."""
    found = [m for m in TOK.finditer(raw) if m.group(5) is not None]      # real marks only: "[-1, x]" in a formula is not one
    marks, core = "".join(m.group(0) for m in found), raw
    for m in reversed(found):
        core = core[:m.start()] + core[m.end():]
    core = core.strip()

    def terms(text):
        t = Beat("prose", text + marks, scope, section, "")
        compose(t, G, dict(say_memo), {}, None, mem)
        return len(t.colour), len(spoken(t)[0].split())

    def over(nw):
        n, w = nw
        return max(0, n - SOFT_TERMS) * 60 + (max(0, w - SOFT_WORDS) if n > 1 else 0)

    def split(text, nw):
        n = nw[0]
        if not over(nw):
            return [text]
        spans = [(m.start(), m.end()) for m in TOK.finditer(text)]
        rx = G.words(scope)[0]
        spans += [(m.start(), m.end()) for m in (rx.finditer(text) if rx else [])]    # never cut inside a term
        best = None
        for tier, pat in enumerate(CUTS):                    # commas first, small words last
            for m in re.finditer(pat, text):
                c = m.end()
                left, right = text[:c].rstrip(), text[c:].lstrip()
                if re.search(r"\b(?:together|along|equipped|endowed|associated|compared|respect)$", left) and tier == 3:
                    continue                        # "together / with" is one phrase
                if any(lo < c < hi for lo, hi in spans) or len(left.split()) < 3 or len(right.split()) < 3:
                    continue
                a_, b_ = terms(left), terms(right)
                worst = max(a_[0], b_[0])
                score = (max(over(a_), over(b_)) // 20, tier, worst, abs(len(left) - len(right)))
                if worst < n and (best is None or score < best[0]):
                    best = (score, left, right)
        if best is None:
            return [text]
        return split(best[1], terms(best[1])) + split(best[2], terms(best[2]))

    return [part + marks for part in split(core, terms(core))]


def colourise(tex, syms, excl, order):
    """Mark glossary symbols inside a formula. Returns the token list with (entry, tokens) groups."""
    found = [(m.group(0), m.start() > 0 and tex[m.start() - 1].isspace()) for m in TEXTOK.finditer(tex)]
    toks, gap = [t for t, _ in found], [g for _, g in found]
    out, gaps, i = Marked(), [], 0
    while i < len(toks):
        # a letter inside \mathbb{R} or \mathcal{R}_{k-1} is not the symbol R: only an entry that has the font
        # command itself (it starts at the command) can match there
        infont = i >= 2 and toks[i - 1] == "{" and toks[i - 2] in FONT
        if not infont:
            for e in syms:
                n = len(e.toks)
                if toks[i:i + n] == e.toks:
                    if e.key in excl:                   # `[-key]`: the symbol stays plain, and a shorter symbol
                        out.extend(toks[i:i + n])       # inside it (R in \mathcal{R}_k) is not matched either
                        gaps.extend((g, None) for g in gap[i:i + n])
                        i += n
                        break
                    order.setdefault(e.key, e)
                    out.append((e, toks[i:i + n]))
                    gaps.append((gap[i], gap[i:i + n]))
                    i += n
                    break
            else:
                out.append(toks[i])
                gaps.append((gap[i], None))
                i += 1
        else:
            out.append(toks[i])
            gaps.append((gap[i], None))
            i += 1
    out.gaps = gaps
    return out


def tex_join(toks, gaps):
    out = ""
    for t, g in zip(toks, gaps):
        if out and (g or (re.search(r"\\[A-Za-z]+$", out) and t[:1].isalpha())):
            out += " "
        out += t
    return out


GREEK = ("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi rho sigma "
         "tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega ell").split()
SAY = {"+": "plus", "-": "minus", "=": "equals", "<": "is less than", ">": "is greater than", ",": ",", ";": ",", ":": ",",
       "/": "over", "'": "prime", "!": "factorial", "\\leq": "is at most", "\\le": "is at most", "\\geq": "is at least",
       "\\ge": "is at least", "\\neq": "is not equal to", "\\ne": "is not equal to", "\\in": "in", "\\notin": "not in",
       "\\to": "to", "\\rightarrow": "to", "\\longrightarrow": "to", "\\mapsto": "maps to", "\\times": "times",
       "\\cdot": "times", "\\subset": "inside", "\\subseteq": "inside", "\\cup": "union", "\\cap": "intersected with",
       "\\otimes": "tensor", "\\oplus": "direct sum", "\\simeq": "is isomorphic to", "\\cong": "is isomorphic to",
       "\\sim": "is similar to", "\\approx": "is about", "\\infty": "infinity", "\\pm": "plus or minus",
       "\\circ": "after", "\\ldots": "and so on", "\\cdots": "and so on", "\\dots": "and so on",
       "\\forall": "for all", "\\exists": "there exists", "\\emptyset": "the empty set", "\\log": "log", "\\exp": "exp",
       "\\sin": "sine", "\\cos": "cosine", "\\det": "determinant of", "\\dim": "dimension of", "\\ker": "kernel of",
       "\\prime": "prime", "\\ast": "star", "*": "star", "\\hbar": "h bar", "\\partial": "d", "\\nabla": "nabla"}
SAY.update({"\\" + g: ("epsilon" if g == "varepsilon" else "phi" if g == "varphi" else "theta" if g == "vartheta" else g)
            for g in GREEK})
SKIP = {"\\left", "\\right", "\\,", "\\;", "\\!", "\\:", "\\ ", "\\quad", "\\qquad", "~", "&", "\\displaystyle",
        "\\big", "\\Big", "\\bigl", "\\bigr", "\\Bigl", "\\Bigr", "\\limits", "\\nolimits", "\\textstyle", "."}
FONT = {"\\mathbb", "\\mathcal", "\\mathbf", "\\mathrm", "\\mathfrak", "\\mathscr", "\\mathit", "\\boldsymbol", "\\bm",
        "\\underline", "\\mathsf", "\\rm", "\\bf"}
AFTER = {"\\widehat": "hat", "\\hat": "hat", "\\tilde": "tilde", "\\widetilde": "tilde", "\\bar": "bar",
         "\\overline": "bar", "\\dot": "dot", "\\vec": "vector"}
READOUT = set()     # `!readout maps`: x^n is an index ("V zero", "C op", "i upper star"), f(x) is "f of x" for each letter,
                    # and "f: X \to Y" is "f from X to Y"
NOT_FN = {"to", "from", "into", "onto", "times", "inside", "in", "equals", "plus", "minus", "after", "of", "over", "union",
          "with", "tensor", "sum", "is", "than", "most", "least", "arrow", "dot", "and", "on", ","}
POWER = {"2": "squared", "3": "cubed", "- 1": "inverse", "star": "star", "prime": "prime", "times": "cross"}


def auto_say(marked):
    """Say a simple formula in words. None when it holds something this table does not know: the writer
    then gives the spoken form. Deliberately small: a wrong read-out is worse than a missing one."""
    def atom(i):
        """One token, or one {group}. Returns (words, next index)."""
        t = marked[i]
        if t == "{":
            depth, j = 1, i + 1
            while j < len(marked) and depth:
                depth += (marked[j] == "{") - (marked[j] == "}")
                j += 1
            return run(i + 1, j - 1), j
        if isinstance(t, str) and (t in FONT or t in AFTER):     # \mathbb{Q}, \hat x: the command and its argument
            w, j = atom(i + 1)
            return w + ([AFTER[t]] if t in AFTER else []), j
        return run(i, i + 1), i + 1

    def run(i, end):
        out = []
        while i < end:
            t = marked[i]
            if isinstance(t, tuple):
                out.append(t[0].say)
                i += 1
            elif t in SKIP or t == "}":
                i += 1
            elif t == "{":
                w, i = atom(i)
                out += w
            elif t in FONT or t in AFTER:
                w, i = atom(i)
                out += w
            elif t == "\\frac":
                a, j = atom(i + 1)
                b, i = atom(j)
                out += a + ["over"] + b
            elif t == "\\sqrt":
                w, i = atom(i + 1)
                out += ["the square root of"] + w
            elif t == "^":
                w, i = atom(i + 1)
                key = " ".join(w)
                if "maps" in READOUT:
                    out.append({"star": "upper star", "- 1": "inverse", "minus 1": "inverse", "prime": "prime"}.get(key, key))
                else:
                    out.append(POWER.get(key, "to the " + key))
            elif t == "_":
                w, i = atom(i + 1)
                if "maps" in READOUT and w == ["star"]:
                    out.append("lower star")
                else:
                    out += ["sub"] + w
            elif t == ":" and "maps" in READOUT:
                nxt = marked[i + 1] if i + 1 < end else None
                if nxt == "=":
                    out.append("is defined as")
                    i += 2
                    continue
                arrows = {"\\to", "\\hook", "\\hookrightarrow", "\\rightarrow", "\\twoheadrightarrow", "\\xrightarrow"}
                out.append("from" if any(isinstance(x, str) and x in arrows for x in marked[i + 1:end]) else ",")
                i += 1
            elif t == "(":
                prev = marked[i - 1] if i else None
                fn = isinstance(prev, tuple) or ("maps" in READOUT and isinstance(prev, str) and (
                    re.fullmatch(r"[A-Za-z]", prev) or prev in SAY and SAY[prev].split()[-1] not in NOT_FN)) or (isinstance(prev, str) and (
                    prev == "}" or re.fullmatch(r"[A-Zfgh]", prev) or prev in SAY and prev[1:] in GREEK
                    or re.match(r"\\(mathrm|text|operatorname|mathbf|mathcal|mathbb)\s*\{", prev)))
                out.append("of" if fn else ("times," if isinstance(prev, str) and re.fullmatch(r"[a-z0-9]", prev) else ","))
                i += 1
            elif t in (")", "[", "]"):
                out.append(",")
                i += 1
            elif t == "\\\\":
                out.append(".")
                i += 1
            elif re.fullmatch(PROTECT, t):
                m = re.match(r"\\(\w+)\s*\{([^{}]*)\}", t)
                if not m:
                    raise KeyError(t)                # a diagram: the writer says it
                if m.group(1) not in ("begin", "end"):
                    num = re.fullmatch(r"\(([\dA-Z.]+)\)", m.group(2).strip())     # the number of a display
                    out.append(f", equation {num.group(1)}" if num else m.group(2).strip())
                i += 1
            elif re.fullmatch(r"[A-Za-z]", t):
                out.append(t)
                i += 1
            elif t.isdigit():
                j = i
                while j < end and isinstance(marked[j], str) and marked[j].isdigit():
                    j += 1
                out.append("".join(marked[i:j]))
                i = j
            elif t in SAY:
                w = SAY[t]
                if w.endswith(" over"):              # `times over`, `the limit over`: only before a subscript
                    nxt = marked[i + 1] if i + 1 < end else None
                    if nxt == "_":
                        sub, i = atom(i + 2)
                        out += [w] + sub + [","]
                        continue
                    w = w[:-5]
                out.append(w)
                i += 1
            else:
                raise KeyError(t)
        return out
    try:
        words = run(0, len(marked))
    except (KeyError, IndexError):
        return None
    text = re.sub(r"\s+,", ",", " ".join(w for w in words if w))
    text = re.sub(r"^[,\s]+|(,\s*)+(?=,)", "", text).strip()
    return text or None


def tex_of(marked, colour, circled):
    parts = []
    for t, (g, inner) in zip(marked, marked.gaps):
        if isinstance(t, tuple):
            e, toks = t
            macro = "DVsym" if e.key in circled else "DVbox"
            if e.key in colour:
                circled.add(e.key)
            # the outer braces make the coloured symbol one argument: \frac 1n, x_\R and \sqrt x still work
            if e.key not in colour:                  # the listener knows this one: it stays in ink
                parts.append("{%s}" % tex_join(toks, [False] + inner[1:]))
                continue
            parts.append("{\\%s{c%d}{%s}}" % (macro, colour[e.key], tex_join(toks, [False] + inner[1:])))
        else:
            parts.append(t)
    return tex_join(parts, [g for g, _ in marked.gaps])


def compose(b, G, say_memo, prev, helped=None, mem=None, ctx=None):
    """Turn one source line into segments: text, terms, formulas and the definitions put next to them."""
    rx, table, syms = G.words(b.scope)
    if b.kind == "head":
        m = re.search(r"(?<!\$)\s*\[\[([^\]]+)\]\]\s*$", b.raw)
        if m:                                        # one spoken form for the whole heading
            b.head_say, b.raw = m.group(1), b.raw[:m.start()].strip()
        rx, syms = None, []                          # a heading shows its formulas but defines nothing
    excl = {m.group(5).strip() for m in TOK.finditer(b.raw) if m.group(5)}
    excl |= {e.key for k in list(excl) for e in [G.find(k, b.scope)] if e}
    items, pos, order = [], 0, {}

    def add_text(s):
        p = 0
        for m in (rx.finditer(s) if rx else []):
            e = table[m.group(0).lower()]
            if e.key in excl:
                continue
            if m.start() > p:
                items.append(["text", s[p:m.start()]])
            items.append(["term", m.group(0), e])
            order.setdefault(e.key, e)
            p = m.end()
        if p < len(s):
            items.append(["text", s[p:]])

    for m in TOK.finditer(b.raw):
        if m.start() > pos:
            add_text(b.raw[pos:m.start()])
        pos = m.end()
        if m.group(1) is not None or m.group(3) is not None:
            disp = m.group(1) is not None
            tex = (m.group(1) if disp else m.group(3)).strip()
            say = m.group(2) if disp else m.group(4)
            marked = colourise(tex, syms, excl, order)
            memo_key = " ".join(textoks(tex))
            if say is None:
                say = say_memo.get(memo_key)
            if say is None:
                whole = G.find(tex, b.scope)
                say = whole.say if whole and whole.kind == "sym" else auto_say(marked)
                if say is None:
                    b.problems.append(f"formula ${tex}$ has no [[spoken form]]")
                    b.unsaid.append(tex)
                    say = ""
            else:
                say_memo[memo_key] = say
            items.append(["dmath" if disp else "imath", marked, say])
        elif m.group(6) is not None:
            e = G.find(m.group(6).strip(), b.scope)
            if not e:
                b.problems.append(f"<{m.group(6)}> is not in the glossary for this scope")
                continue
            order.setdefault(e.key, e)
            items.append(["place", e, m.group(7)])
        elif m.group(8) is not None:
            e = Entry(m.group(8).strip(), "noun", [], None, None, m.group(9).strip(), [], 0)
            order.setdefault(e.key, e)
            items.append(["term", e.key, e])
    if pos < len(b.raw):
        add_text(b.raw[pos:])

    # what the listener needs now: the definition (new), a reminder (fading or lost), or nothing (known)
    def state(e):
        return mem.state(G.family(e)) if mem else "new"
    own_words = {it[1].key for it in items if it[0] == "place" and it[2]}
    level = {}
    for k, e in order.items():
        st = state(e)
        level[k] = "full" if k in own_words or st == "new" else "short" if st in ("fading", "lost") else None
    shown = [k for k in order if level[k]]
    b.known = len(order) - len(shown)
    b.told = [G.family(order[k]) for k in shown]
    b.told += [G.family(e) for k in excl for e in [G.find(k, b.scope)] if e]      # the sentence itself defines these
    b.todo, b.told_side, b.used = [], [], []
    line_no = int(b.src.rsplit(":", 1)[1]) if b.src.rsplit(":", 1)[-1].isdigit() else 0

    # colours: keep the colour a term had in the beat before, then fill from the start of the palette
    free = [i for i in range(1, HARD_TERMS + 1)]
    for k in shown:
        if prev.get(k) in free:
            b.colour[k] = prev[k]
            free.remove(prev[k])
    for k in shown:
        if k not in b.colour:                       # past six terms the colours repeat
            b.colour[k] = free.pop(0) if free else 1 + len(b.colour) % HARD_TERMS

    placed = {it[1].key for it in items if it[0] == "place"}
    done, circled, where, segs, after, ninline = set(), set(), [], [], {}, [0]

    helped = set() if helped is None else helped
    b.more = []
    inline = {G.family(order[k]) for k in shown}

    def words_for(e):
        """The words written for this sentence (NAME.context.txt), else the glossary's: the definition the first
        time, its reminder later."""
        text = (ctx or {}).get((line_no, e.key))
        if text is None:
            if e.line:                              # not a one-off term
                b.todo.append((e, level.get(e.key)))
            return e.defn if level.get(e.key) == "full" else (e.short or e.defn)
        b.used.append((e, level.get(e.key), text))
        return text

    def settle(text):
        """Give each formula inside a meaning its spoken form: $tex$ becomes $tex$[[words]]."""
        def one(m):
            tex, say = m.group(1).strip(), m.group(2)
            key = " ".join(textoks(tex))
            if say is None:
                say = say_memo.get(key)
            if say is None:
                whole = G.find(tex, b.scope)
                say = whole.say if whole and whole.kind == "sym" else auto_say(colourise(tex, [], set(), {}))
            if say is None:
                b.problems.append(f"formula ${tex}$ inside a meaning has no [[spoken form]]")
                b.unsaid.append(tex)
                say = ""
            return f"${tex}$[[{say}]]"
        return DMATH.sub(one, text) if "$" in text else text

    def gloss(e, text, root, layer=1):
        """`!depth N`: the glossary words inside a definition get their own meaning on the page after the beat,
        N - 1 layers deep, once per sentence. Returns the words of `text` to underline."""
        if not rx or layer >= G.depth:
            return []
        own, found = {f.lower() for f in e.forms}, []
        for m in rx.finditer(def_plain(text)):       # the words on the screen: a word inside a spoken form gets no page
            h = table[m.group(0).lower()]
            fam = G.family(h)
            if m.group(0).lower() in own or fam in inline or h.key in excl or h.base or fam == G.family(e):
                continue                            # the sentence itself gives this one, or it is a base word
            st = mem.either(fam) if mem else "new"
            if st == "known" or fam in helped:
                continue                            # the listener has it
            helped.add(fam)
            found.append(m.group(0))
            b.told_side.append(fam)
            head = m.group(0)                       # a plural form that shares the singular wording: name the singular
            if h.forms and head.lower() != h.forms[0].lower() and head.lower().endswith("s") \
                    and not h.forms[0].lower().endswith("s"):
                head = h.forms[0]
            item = [root, head, [], layer, settle(h.short or h.defn)]
            b.more.append(item)                     # before its own helpers: each word is followed by the words it uses
            if st == "new":
                item[2] = gloss(h, item[4], root, layer + 1)
        return found

    def put_def(e, text=None):
        kind = "adj" if e.kind == "adj" else "noun"
        text = settle(text or words_for(e))
        if text.startswith("&"):           # own words that carry their own connective
            lead, text = ", ", text[1:].strip()
        else:
            lead = ", which means " if kind == "adj" else LEADS[ninline[0] % len(LEADS)]
            ninline[0] += 1
        segs.append(("def", e.key, lead, text, gloss(e, text, e.key)))
        done.add(e.key)

    i = 0
    while i < len(items):
        it = items[i]
        if it[0] == "text":
            segs.append(("text", it[1]))
        elif it[0] == "place":
            if it[2] or level.get(it[1].key):
                put_def(it[1], it[2])
        elif it[0] in ("imath", "dmath"):
            segs.append((it[0], tex_of(it[1], b.colour, circled), it[2]))
            for t in it[1]:
                if (isinstance(t, tuple) and t[0].key not in done and t[0].key not in placed and t[0] not in where
                        and level.get(t[0].key)):
                    where.append(t[0])
        else:
            e = it[2]
            segs.append(("term", it[1], e.key))
            if e.key not in done and e.key not in placed and level.get(e.key):
                nxt = items[i + 1] if i + 1 < len(items) else None
                nx2 = items[i + 2] if i + 2 < len(items) else None
                blank = nxt and nxt[0] == "text" and not nxt[1].strip()
                if e.kind == "adj" and blank and nx2 and nx2[0] == "term":
                    after.setdefault(i + 2, []).append(e)       # adjective before another term: define after that term
                elif e.kind != "adj" and blank and nx2 and nx2[0] == "imath":
                    after.setdefault(i + 2, []).append(e)       # "genus $g$": define after the symbol
                elif nxt and nxt[0] == "text":
                    m = (ADJ_STOP.search(nxt[1]) if e.kind == "adj" else NUM_AFTER.match(nxt[1]))
                    cut = (m.start() if e.kind == "adj" else m.end()) if m else 0
                    if cut:
                        segs.append(("text", nxt[1][:cut]))
                        nxt[1] = nxt[1][cut:]
                    put_def(e)
                else:
                    put_def(e)
        for e in after.pop(i, []):
            put_def(e)
        i += 1

    if where:
        tail = ""
        if segs and segs[-1][0] == "text":
            m = re.search(r"[.?!,;:]\s*$", segs[-1][1])
            if m:
                tail = segs[-1][1][m.start():].strip()
                segs[-1] = ("text", segs[-1][1][:m.start()])
        lead_in = "where " if segs and segs[-1][0] == "dmath" else ", where "
        segs.append(("text", lead_in))
        for n, e in enumerate(where):
            if n:
                segs.append(("text", ", and " if n == len(where) - 1 else ", "))
            segs.append(("wsym", e.key, "\\DVsym{c%d}{%s}" % (b.colour[e.key], e.tex), e.say))
            segs.append(("text", " is "))
            text = settle(words_for(e))
            segs.append(("def", e.key, "", text, gloss(e, text, e.key)))
        segs.append(("text", tail or ("." if b.raw.rstrip().endswith(("$$", "]]")) else "")))
    b.segs = [s for s in segs if not (s[0] == "text" and s[1] == "")]


def next_char(segs, i):
    for s in segs[i + 1:]:
        if s[0] == "text":
            t = s[1].lstrip()
            if t:
                return t[0]
        elif s[0] == "def":
            return "," if s[2] else "A"
        else:
            return "A"
    return None


def pieces(b):
    """(kind, shown-or-spoken text, extra) for each segment, with the commas around definitions settled."""
    out = []
    for i, s in enumerate(b.segs):
        if s[0] == "def":
            nc = next_char(b.segs, i)
            trail = "," if s[2] and nc is not None and nc not in ".,;:?!)" else ""
            out.append(("def", s[3], (s[1], s[2], trail, s[4]) + (tuple(s[5:7]) if len(s) > 5 else (None, False))))
        elif s[0] == "term":
            out.append(("term", s[1], s[2]))
        elif s[0] in ("imath", "dmath"):
            out.append((s[0], s[2], s[1]))
        elif s[0] == "wsym":
            out.append(("wsym", s[3], s[2]))
        else:
            out.append(("text", s[1], None))
    return out


def spoken(b):
    """The sentence as the voice says it, and where each definition starts (as a share of the text)."""
    text, starts = "", []
    if b.head_say:
        return b.head_say, []
    for kind, t, x in pieces(b):
        if kind == "def":
            text += x[1]
            starts.append(len(text))
            text += def_say(t) + x[2]
        elif kind == "dmath":
            text += " " + t + ("" if t.rstrip()[-1:] in ",.;:?!" else ",") + " "
        else:
            text += t
    text = re.sub(r"\s+([,.;:?]|!(?!-))", r"\1", re.sub(r"\s+", " ", text)).strip()     # "!-descent" is a word, not punctuation
    return text, [min(1.0, s / max(1, len(text))) for s in starts]


# How Phonon (voice Everly) must be spelled to say a Greek letter in the usual way of English mathematics. Tested by
# ear of a speech recogniser: as written it says xi as "she", psi as "see", phi as "fee", chi as "chee", tau as "tah".
GREEK_SAY = {"xi": "zye", "psi": "sigh", "phi": "fie", "chi": "kye", "pi": "pie", "tau": "tao"}


def for_voice(text, G):
    for a, c in G.fixes:
        text = text.replace(a, c)
    own = {a.strip().lower() for a, _ in G.fixes}            # a glossary line `>> xi => ...` wins
    text = re.sub(r"(?<![\w'-])(" + "|".join(GREEK_SAY) + r")(?![\w'-])",
                  lambda m: m.group(0) if m.group(1).lower() in own else GREEK_SAY[m.group(1).lower()], text, flags=re.I)
    text = re.sub(r",(?=[A-Za-z])", ", ", text)          # a placed meaning before a formula: "scheme,X"
    # Phonon says the hyphen in "infinity-category" as "dash", and blurs "1-category": a space reads well
    text = re.sub(r"(?<![\w'-])(infinity|[A-Za-z0-9])-(?=[A-Za-z])", r"\1 ", text)
    text = re.sub(r"(?<![\w'-])nth(?![\w'-])", "N-th", text)
    # a variable of one small letter: the voice swallows "s", "t", "q", "d" ("zeta of s"), but says the capital well
    text = re.sub(r"(?<![\w'-])([b-z])(?![\w'-])", lambda m: m.group(1).upper(), text)
    # the letter "a" as a variable, where the word after it shows that it is not the article
    text = re.sub(r"(?<![\w'-])a(?=\s*(?:[,.;:?!]|$)|\s+(?:is|are|has|and|or|equals?|times|plus|minus|star|squared|cubed|inverse|"
                  r"prime|sub|over|in|of|to|with|from|by|on|for|if|as|at|such|where|when|that|which|then|maps|goes|commutes)(?![\w-]))", "A", text)
    text = re.sub(r"(?<![\w'-])a(?= [B-Z] (?:equals?|is|times|plus|minus|and|squared)\b| [B-Z]\s*(?:[,.;:?!]|$))", "A", text)
    text = re.sub(r"(\[\u00b7\](,? (and )?)?)+", "the cited work ", text)       # prepare.py writes [·] for a citation
    text = re.sub(r"\s*[()\[\]]\s*", ", ", text)
    text = re.sub(r"\s*,(\s*,)+", ",", text)
    text = re.sub(r",\s*([.;:?!])", r"\1", re.sub(r"\s+", " ", text))
    return re.sub(r"\s+([,.;:?!])", r"\1", text).strip(" ,")


# ---------------------------------------------------------------- lint

VAGUE = re.compile(r"\b(?:like|such as|kind of|sort of|roughly|loosely|more or less|in a way|special(?! relativity| linear| orthogonal| unitary| fib| case)|things?|"
                   r"something|somehow|measures how|behaves like|tells you|in the role of)\b", re.I)


def lint_glossary(G):
    errs, warns = [], []
    forms, uses, seen = [], {}, {}
    for e in G.entries:
        forms += [(f.lower(), e) for f in e.forms]
        for name in (e.forms or [e.key]):
            k = (name if e.kind == "sym" else name.lower(), tuple(sorted(e.scopes)))
            if k in seen:
                errs.append(f"{e.line} ({name}): already defined at {seen[k]}. One definition per term and scope.")
            seen[k] = e.line
    by_len = sorted({f for f, _ in forms}, key=len, reverse=True)
    rx = re.compile(r"(?<![\w])(?:" + "|".join(map(re.escape, by_len)) + r")(?![\w])") if by_len else None
    table = {}
    for f, o in forms:
        table.setdefault(f, []).append(o)

    for e in G.entries:
        tag = f"{e.line} ({e.key})"
        d = e.defn
        own = {f.lower() for f in e.forms}
        used = [(m.group(0), o) for m in (rx.finditer(def_plain(d).lower()) if rx else []) if m.group(0) not in own
                for o in table[m.group(0)] if o is not e and not o.base]
        uses[id(e)] = used
        if used and G.depth == 1:
            errs.append(f"{tag}: the definition uses the glossary term '{used[0][0]}'. "
                        f"Without '!depth', a definition has no glossary term in it.")
        n = len(def_say(d, "x x x").split())
        if n > 40:
            errs.append(f"{tag}: {n} words. The limit for a definition is 40: move a part into a term of its own.")
        plain = def_plain(d)
        if re.search(r"[;()]", plain) or re.search(r"\b\w+(?:n't|'(?:re|ll|ve|m|d))\b", plain, re.I):
            errs.append(f"{tag}: no semicolons, brackets or contractions in a definition (outside formulas).")
        if e.short:
            ns = len(def_say(e.short, "x x x").split())
            if ns > 16:
                errs.append(f"{tag}: the reminder after '|' has {ns} words. The limit is 16.")
            if re.search(r"[;()]", def_plain(e.short)):
                errs.append(f"{tag}: no semicolons or brackets in a reminder (outside formulas).")
        m = VAGUE.search(def_plain(d + " " + (e.short or "")))
        if m:
            warns.append(f"{tag}: '{m.group(0)}' is a sign of a loose description. Give the exact definition.")

    state = {}                                       # a definition must not come back to its own term

    def walk(e, path):
        if state.get(id(e)) == 2:
            return
        if state.get(id(e)) == 1:
            loop = path[[x for x, _ in path].index(e):]
            errs.append(f"{e.line} ({e.key}): definition loop: " + " -> ".join(k for _, k in loop) + f" -> {e.key}")
            return
        state[id(e)] = 1
        for _, o in uses[id(e)]:
            walk(o, path + [(e, e.key)])
        state[id(e)] = 2
    for e in G.entries:
        walk(e, [])
    return errs, warns


# ---------------------------------------------------------------- formulas

TEX_HEAD = r"""\documentclass[10pt]{article}
\usepackage{amsmath,amssymb,xcolor,tikz}
%s
%s
\makeatletter
\newcommand\DVsym[2]{{\color{#1}#2}}
\newcommand\DVbox[2]{\mathpalette{\DVbox@{#1}}{#2}}
\newcommand\DVbox@[3]{\tikz[baseline=(n.base)]\node[draw=#1,fill=#1!7,rounded corners=3.2pt,inner xsep=1.7pt,inner ysep=1.5pt,line width=.5pt](n){$\m@th#2\color{#1}#3$};}
\makeatother
\newwrite\dimfile \immediate\openout\dimfile=\jobname.dims
\pdfhorigin=0pt \pdfvorigin=0pt \pagestyle{empty}
\newcommand\DVpage[2]{\setbox0\hbox{#2}\immediate\write\dimfile{#1,\the\wd0 ,\the\ht0 ,\the\dp0 }%%
 \pdfpagewidth=\dimexpr\wd0+2pt\relax \pdfpageheight=\dimexpr\ht0+\dp0+2pt\relax
 \shipout\vbox{\kern1pt\hbox{\kern1pt\box0}}}
\begin{document}
"""


def amp_safe(tex):
    """A tikzcd inside a macro argument cannot read `&`: give it `ampersand replacement` (the SVG is the same)."""
    def fix(m):
        opts, inner = m.group(1), m.group(2).replace("&", "\\&")
        opts = "[ampersand replacement=\\&" + ("," + opts[1:-1] if opts else "") + "]"
        return "\\begin{tikzcd}" + opts + inner + "\\end{tikzcd}"
    return re.sub(r"\\begin\{tikzcd\}(\[[^\]]*\])?(.*?)\\end\{tikzcd\}", fix, tex, flags=re.S)


def build_math(jobs, cache, preamble, njobs):
    """jobs: {id: (tex, display)}. One pdflatex run for all new formulas, then one SVG per page."""
    cache.mkdir(parents=True, exist_ok=True)
    dims = {}
    for k in jobs:
        f = cache / f"{k}.dim"
        if f.exists() and (cache / f"{k}.svg").exists():
            dims[k] = json.loads(f.read_text())
    todo = {k: v for k, v in jobs.items() if k not in dims}
    if todo:
        tmp = cache / f"tmp-{os.getpid()}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        cols = "\n".join("\\definecolor{c%d}{HTML}{%s}" % (i + 1, c.upper()) for i, c in enumerate(PALETTE))
        body = "".join("\\DVpage{%s}{$%s%s$}\n" % (k, "\\displaystyle " if d else "", amp_safe(t)) for k, (t, d) in todo.items())
        (tmp / "m.tex").write_text(TEX_HEAD % (preamble, cols) + body + "\\end{document}\n")
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "m.tex"],
                           cwd=tmp, capture_output=True, text=True)
        if r.returncode:
            err = "\n".join(l for l in r.stdout.splitlines() if l.startswith("!") or l.startswith("l."))
            die("pdflatex failed on a formula:\n" + err[:1500])
        order = []
        for line in (tmp / "m.dims").read_text().split("\n"):
            if line.strip():
                k, w, h, d = line.strip().split(",")
                order.append(k)
                dims[k] = [float(x[:-2]) for x in (w, h, d)]

        def svg(n_k):
            n, k = n_k
            subprocess.run(["pdftocairo", "-svg", "-f", str(n), "-l", str(n), "m.pdf", str(cache / f"{k}.svg")],
                           cwd=tmp, check=True)
        with ThreadPoolExecutor(njobs) as ex:
            list(ex.map(svg, enumerate(order, 1)))
        for k in order:
            (cache / f"{k}.dim").write_text(json.dumps(dims[k]))
        shutil.rmtree(tmp, ignore_errors=True)
    return dims, len(todo)


# ---------------------------------------------------------------- frames

def esc(s):
    return html.escape(s, quote=False)


def beat_html(b, meta, idx, total, lit, part, enter, mathref):
    """HTML for one state: `lit` definitions are in colour, the next one is `part` of the way there."""
    if b.kind == "title":
        m = b.meta
        body = (f'<div class="card"><div class="eyebrow">{esc(m.get("source", ""))}</div><h1>{esc(m["title"])}</h1>'
                f'<div class="by">{esc(m.get("authors", ""))}</div>'
                f'<div class="how">Each <span class="t" style="--c:var(--c1)">technical word</span> '
                f'<span class="d" style="--c:var(--c1);--p:1"><span class="k">comes with</span> its meaning in the same colour</span></div></div>')
    else:
        out, n = [], 0
        for kind, t, x in pieces(b):
            if kind == "text":
                out.append(esc(t))
            elif kind == "term":
                nw = " nw" if len(t) <= 30 else ""
                if x in b.colour:
                    out.append(f'<span class="t{nw}" style="--c:var(--c{b.colour[x]})">{esc(t)}</span>')
                else:                               # a term that the listener knows: a quiet outline, no colour
                    out.append(f'<span class="t t0{nw}">{esc(t)}</span>')
            elif kind == "def":
                key, lead, trail, helpers, head, sub = x
                p = 1 if n < lit else (part if n == lit else 0)
                n += 1
                k1 = f'<span class="k">{esc(lead)}</span>' if lead else ""
                k2 = f'<span class="k">{trail}</span>' if trail else ""
                rest = sorted(set(helpers), key=len, reverse=True)

                def words(chunk):
                    """Plain words of a meaning: the first use of each helper word is underlined."""
                    h_ = esc(chunk)
                    for h in list(rest):
                        new = re.sub(r"(?<![\w>])(" + re.escape(esc(h)) + r")(?![\w<])", r'<span class="h">\1</span>', h_, count=1)
                        if new != h_:
                            h_ = new
                            rest.remove(h)
                    return h_
                raw, body_, at = (t[len(head):] if head else t), "", 0
                for m in DMATH.finditer(raw):                # a formula takes the colour of its meaning
                    uri, (w, h, d) = mathref(m.group(1).strip(), False, True)
                    body_ += words(raw[at:m.start()]) + (
                        f'<span class="fm" style="width:{(w + 2) / 10 * 1.2:.3f}em;height:{(h + d + 2) / 10 * 1.2:.3f}em;'
                        f'vertical-align:{-(d + 1) / 10 * 1.2:.3f}em;margin-right:-0.1em;-webkit-mask-image:url({uri});mask-image:url({uri})"></span>')
                    at = m.end()
                body_ += words(raw[at:])
                if head:
                    body_ = f'<b>{esc(head)}</b>' + body_
                out.append(f'<span class="d{" sub" if sub else ""}" style="--c:var(--c{b.colour[key]});--p:{p}">{k1}{body_}{k2}</span>')
            else:
                tex = x
                disp = kind == "dmath"
                mid, (w, h, d) = mathref(tex, disp)
                s = 1.34 if disp else 1.0 if b.kind == "head" else 1.2
                img = (f'<img src="{mid}" style="height:{(h + d + 2) / 10 * s:.3f}em;'
                       f'vertical-align:{-(d + 1) / 10 * s:.3f}em">')
                out.append(f'<span class="dm">{img}</span>' if disp else img)
        tag = "From the text" if b.quote else {"narr": "Not in the text", "more": "Words in the meanings"}.get(b.kind, "")
        tag = f'<div class="eyebrow">{tag}</div>' if tag else ""
        body = f'{tag}<p class="s {b.kind}">{"".join(out)}</p>'
        if b.kind == "head":
            body = f'<div class="card"><div class="eyebrow">{esc(meta["title"])}</div><h1>{"".join(out)}</h1></div>'
    pct = 100 * idx / max(1, total - 1)
    fig = fig_html(b, meta) if b.fig else ""
    return (f'<header><span class="name">{esc(meta["title"])}</span><span class="sec">{esc(b.section)}</span></header>'
            f'<main{" class=withfig" if fig else ""}>{fig}<div id="beat" style="opacity:{enter}">{body}</div></main>'
            f'<footer><div class="bar"><i style="width:{pct:.2f}%"></i></div>'
            f'<div class="foot"><span>{esc(meta.get("source", ""))}</span><span>{idx + 1} / {total}</span></div></footer>')


FIGS = {}


def fig_html(b, meta):
    """The figure beside a beat: WORK/figs/NAME.svg, inlined. A part is an element with data-p="part"; its label
    (text and leader line) has data-l="part". '@fig NAME a:term, b' dims the other parts and shows the labels of a and b,
    each in the colour of its term in this beat (ink if the term has no colour here)."""
    name, _, spec = b.fig.partition(" ")
    if name not in FIGS:
        f = meta["_work"] / "figs" / f"{name}.svg"
        if not f.exists():
            die(f"{b.src}: no figure {f}")
        FIGS[name] = re.sub(r"<\?xml[^>]*>", "", f.read_text())
    css = []
    parts = [x.strip() for x in spec.split(",") if x.strip()]
    if parts:
        css.append("#fig .p{opacity:.22} #fig .lab{display:none}")
    for x in parts:
        part, _, term = (s.strip() for s in x.partition(":"))
        c = f"var(--c{b.colour[term]})" if term in b.colour else "var(--ink)"
        sel = f'[data-p~="{part}"]'
        css.append(f'#fig .p{sel}{{opacity:1}} #fig .p{sel} .hl{{stroke:{c};stroke-width:5}} '
                   f'#fig .lab[data-l~="{part}"]{{display:inline;color:{c}}}')
    return f'<div id="fig"><style>{" ".join(css)}</style>{FIGS[name]}</div>'


# ---------------------------------------------------------------- voice

def build_audio(jobs, cache, a, njobs):
    """jobs: {hash: text}. Synthesise the missing ones in parallel worker processes."""
    cache.mkdir(parents=True, exist_ok=True)
    todo = [(h, t) for h, t in jobs.items() if not (cache / f"{h}.wav").exists()]
    if not todo:
        return 0
    if a.engine == "say":
        def one(ht):
            h, t = ht
            subprocess.run(["say", "-v", a.voice, "-r", "172", "--file-format=WAVE", "--data-format=LEI16@24000",
                            "-o", str(cache / f"{h}.wav"), t], check=True)
        with ThreadPoolExecutor(njobs) as ex:
            list(ex.map(one, todo))
    else:
        n = max(1, min(njobs, 3, len(todo) // 4 or 1))
        procs = []
        for i in range(n):
            part = [{"out": str(cache / f"{h}.wav"), "text": t} for h, t in todo[i::n]]
            f = cache / f"jobs-{os.getpid()}-{i}.json"          # two builds may run at once
            f.write_text(json.dumps(part))
            procs.append(subprocess.Popen(["uv", "run", "--quiet", "--with", PTTS, "python",
                                           str(HERE / "tts_phonon.py"), str(f), a.voice]))
        if any(p.wait() for p in procs):
            die("the voice worker failed")
        for i in range(n):
            (cache / f"jobs-{os.getpid()}-{i}.json").unlink()
    return len(todo)


# ---------------------------------------------------------------- one chapter

def srt_time(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def cues(text, t0, t1, maxw=14):
    words, chunks, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(cur) >= maxw or (len(cur) >= 6 and w[-1] in ",.;:?!"):
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    total, at, out = sum(map(len, chunks)) or 1, t0, []
    for c in chunks:
        dur = (t1 - t0) * len(c) / total
        out.append((at, at + dur, c))
        at += dur
    return out


def own_files(work, path, suffix):
    """Files that belong to one beats file: '04.glossary.txt' goes with '04a-part-one.beats' and '04b-...'."""
    return sorted(g for g in work.glob("*" + suffix) if path.name.startswith(g.name[:-len(suffix)]))


def preamble(work, path):
    files = ([work / "preamble.tex"] if (work / "preamble.tex").exists() else []) + own_files(work, path, ".preamble.tex")
    return "\n".join(f.read_text() for f in files)


def build_chapter(path, G, a, work):
    t_start = time.time()
    cache, out = work / ".cache", work / "out"
    out.mkdir(exist_ok=True)
    meta, beats = read_beats(path, G)
    meta["_work"] = path.parent
    problems = [(b.src, p) for b in beats for p in b.problems]
    unsaid = list(dict.fromkeys(t for b in beats for t in b.unsaid))
    todo = work / (path.stem + ".say.todo.txt")
    if unsaid:
        todo.write_text("# Formulas that need a spoken form. Fill in after ' => ' and move the lines to PREFIX.say.txt\n"
                        + "".join(f"{t} => \n" for t in unsaid))
        print(f"  {path.name}: {len(unsaid)} formulas need a spoken form. They are listed in {todo.name}")
    elif todo.exists():
        todo.unlink()
    for src, p in problems:
        if "has no [[spoken form]]" not in p:
            print(f"  {src}: {p}")
    due = [(b, e, lvl) for b in beats for e, lvl in b.todo]
    ctodo = work / (path.stem + ".context.todo.txt")
    if due:
        out_l = ["# Places where the video gives a meaning and " + path.stem + ".context.txt has no line for it.",
                 "# After ' => ' write the meaning for that sentence (see 'Finalise' in references/writing.md):",
                 f"#   first:    the definition, cut to the conditions that matter here ({FIRST_WORDS} words or fewer)",
                 f"#   reminder: the key feature that matters in this sentence ({AGAIN_WORDS} words or fewer)",
                 "# Then move the lines to " + path.stem + ".context.txt.", ""]
        for b, e, lvl in due:
            n = b.src.rsplit(":", 1)[1]
            out_l += [f"# {n} ({'first' if lvl == 'full' else 'reminder'}): {b.raw}", f"#   definition: {e.defn}",
                      f"{n} {e.key} => ", ""]
        ctodo.write_text("\n".join(out_l))
        print(f"  {path.name}: {len(due)} meanings use the glossary's words, not words for their sentence "
              f"({sum(l == 'full' for _, _, l in due)} first, {sum(l != 'full' for _, _, l in due)} reminders). "
              f"They are listed in {ctodo.name}")
    elif ctodo.exists():
        ctodo.unlink()
    for b in beats:
        for e, lvl, text in b.used:
            cap, n = (FIRST_WORDS if lvl == "full" else AGAIN_WORDS), len(def_say(text, "x x x").split())
            where_ = f"{path.stem}.context.txt, line {b.src.rsplit(':', 1)[1]} ({e.key})"
            if n > cap:
                print(f"  warning: {where_}: {n} words. The limit for a {'first meaning' if lvl == 'full' else 'reminder'} is {cap}.")
            if VAGUE.search(def_plain(text)):
                print(f"  warning: {where_}: '{VAGUE.search(def_plain(text)).group(0)}' is a sign of a loose description.")
    crowded = [(len(b.colour), b.src) for b in beats if len(b.colour) > SOFT_TERMS and b.kind != "more"]
    if crowded:
        worst = ", ".join(f"{src.split(':')[-1]} ({n})" for n, src in sorted(crowded, reverse=True)[:12])
        print(f"  {path.name}: {len(crowded)} beats still have more than {SOFT_TERMS} terms after the automatic split; "
              f"{sum(n > HARD_TERMS for n, _ in crowded)} have more than {HARD_TERMS} and repeat colours. "
              f"Break those lines by hand. Worst lines: {worst}")
    failed = bool(problems)
    if failed and not a.lint:
        die("fix the beats above")
    if a.lint:
        nt = sum(len(b.colour) for b in beats if b.kind != "more")
        nk = sum(b.known for b in beats)
        nh = sum(len(b.more) for b in beats)
        words = sum(len(spoken(b)[0].split()) for b in beats)
        print(f"  {path.name}: {len(beats)} beats, {nt} definitions and reminders in the sentences, {nk} terms left alone "
              f"because the listener knows them, {nh} meanings of words inside definitions, "
              f"{words} spoken words (about {words / 165:.0f} min)")
        if a.narration:                              # what the voice will say, one beat per paragraph
            (work / f"{path.stem}.narration.txt").write_text(
                "\n\n".join(f"[{(b.src or ':').rsplit(':', 1)[-1]}] {for_voice(spoken(b)[0], G)}" for b in beats) + "\n")
        if a.formulas:
            pre = preamble(work, path)
            mj = math_jobs(beats, pre)
            build_math(mj, cache / "math", pre, a.jobs)
            print(f"  {path.name}: {len(mj)} formulas compile")
        if failed:
            die(f"{path.name} is not ready to build: see the lines above")
        return

    # voice
    said = [spoken(b) for b in beats]
    ah = [sha(a.engine, a.voice, for_voice(s, G)) for s, _ in said]
    t0 = time.time()
    n_tts = build_audio({h: for_voice(s, G) for h, (s, _) in zip(ah, said)}, cache / "audio", a, a.jobs)
    t_tts = time.time() - t0

    # formulas
    pre = preamble(work, path)
    mjobs = math_jobs(beats, pre)
    t0 = time.time()
    dims, n_math = build_math(mjobs, cache / "math", pre, a.jobs)
    t_math = time.time() - t0

    inline_svg = {}

    def mathref(tex, disp, data=False):
        k = sha(pre, tex, "dmath" if disp else "imath")
        f = cache / "math" / f"{k}.svg"
        if not data:
            return f.as_uri(), dims[k]
        if k not in inline_svg:                      # a CSS mask must not load from another file: give the SVG itself
            inline_svg[k] = "data:image/svg+xml;base64," + base64.b64encode(f.read_bytes()).decode()
        return inline_svg[k], dims[k]

    # timeline: (start time, frame html)
    rate = 24000
    tl, t, pcm, srt, chapters = [], 0.0, [], [], []
    for i, (b, (text, starts), h) in enumerate(zip(beats, said, ah)):
        lead, tail = GAP[b.kind]
        if i + 1 < len(beats) and beats[i + 1].kind == "more":
            tail = 0.3                                # its words come next
        elif i + 1 < len(beats) and beats[i + 1].cont and b.kind != "more":
            tail = 0.15                               # the next beat is the rest of the same sentence
        with wave.open(str(cache / "audio" / f"{h}.wav")) as w:
            if w.getframerate() != rate or w.getnchannels() != 1 or w.getsampwidth() != 2:
                die(f"unexpected audio format in {h}.wav")
            data = w.readframes(w.getnframes())
        dur = len(data) / 2 / rate
        pcm += [b"\0\0" * int(lead * rate), data, b"\0\0" * int(tail * rate)]
        t_voice, t_end = t + lead, t + lead + dur + tail
        if b.kind in ("head", "title"):
            chapters.append((t, b.section if b.kind == "head" else "Start"))

        def fr(lit, part=0, enter=1):
            return beat_html(b, meta, i, len(beats), lit, part, enter, mathref)
        if a.motion == "full":
            tl += [(t, fr(0, 0, EASE[0])), (t + TWEEN, fr(0, 0, EASE[1])), (t + 2 * TWEEN, fr(0))]
        else:
            tl.append((t, fr(0)))
        last = t + 2 * TWEEN
        for n, share in enumerate(starts if a.motion != "none" else []):
            at = max(last + 0.02, t_voice + share * dur - 0.12)
            if a.motion == "full" and at + 2 * TWEEN < t_end:
                tl += [(at, fr(n, EASE[0])), (at + TWEEN, fr(n, EASE[1]))]
                at += 2 * TWEEN
            tl.append((at, fr(n + 1)))
            last = at
        if a.motion == "none" and starts:
            tl[-1] = (tl[-1][0], fr(len(starts)))
        srt += cues(text, t_voice, t_voice + dur)
        t = t_end
    total = t

    # frames
    frames = {}
    for _, h_ in tl:
        frames.setdefault(sha(h_), h_)
    fdir = cache / "frames"
    fdir.mkdir(exist_ok=True)
    todo = [{"id": k, "html": v} for k, v in frames.items() if not (fdir / f"{k}.png").exists()]
    t0 = time.time()
    if todo:
        jf = cache / f"frames-{os.getpid()}.json"
        jf.write_text(json.dumps(todo))
        r = subprocess.run(["bun", str(HERE / "render.js"), str(jf), str(fdir), str(HERE / "frame.html"),
                            str(min(a.jobs, 6))])
        if r.returncode:
            die("the frame renderer failed")
        jf.unlink()
    t_frames = time.time() - t0

    # mux
    stem = path.stem
    wav = cache / f"{stem}.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(pcm))
    lines, n_enc = ["ffconcat version 1.0"], 0
    for j, (at, h_) in enumerate(tl):
        end = tl[j + 1][0] if j + 1 < len(tl) else total
        f = fdir / f"{sha(h_)}.png"
        while end - at > 1e-3:
            d = min(HOLD, end - at)
            lines += [f"file '{f}'", f"duration {d:.4f}"]
            at += d
            n_enc += 1
    lines.append(f"file '{f}'")
    (cache / f"{stem}.ffconcat").write_text("\n".join(lines) + "\n")
    (out / f"{stem}.srt").write_text("".join(f"{n}\n{srt_time(s)} --> {srt_time(e)}\n{c}\n\n"
                                               for n, (s, e, c) in enumerate(srt, 1)))
    ffm = [";FFMETADATA1", f"title={meta['title']}", f"artist={meta.get('authors', '')}"]
    for j, (at, name) in enumerate(chapters):
        end = chapters[j + 1][0] if j + 1 < len(chapters) else total
        ffm += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(at * 1000)}", f"END={int(end * 1000)}",
                "title=" + re.sub(r"([=;#\\])", r"\\\1", name)]
    (cache / f"{stem}.ffmeta").write_text("\n".join(ffm) + "\n")
    mp4 = out / f"{stem}.mp4"
    t0 = time.time()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(cache / f"{stem}.ffconcat"),
                    "-i", str(wav), "-i", str(out / f"{stem}.srt"), "-i", str(cache / f"{stem}.ffmeta"),
                    "-map", "0:v", "-map", "1:a", "-map", "2:s", "-map_metadata", "3", "-map_chapters", "3",
                    "-fps_mode", "vfr", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-g", "15", "-video_track_timescale", "90000",
                    "-c:a", "aac", "-b:a", "80k", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
                    "-movflags", "+faststart", "-t", f"{total:.3f}", str(mp4)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-map", "0:a", "-map_chapters", "0", "-c", "copy",
                    str(out / f"{stem}.m4a")], check=True)
    t_mux = time.time() - t0
    wav.unlink()
    wall = time.time() - t_start
    print(f"  {mp4.name}: {total / 60:.1f} min, {len(beats)} beats, {len(frames)} frames ({n_enc} encoded)\n"
          f"    voice {t_tts:.1f}s ({n_tts} new) · formulas {t_math:.1f}s ({n_math} new) · "
          f"frames {t_frames:.1f}s ({len(todo)} new) · mux {t_mux:.1f}s · total {wall:.1f}s = {total / wall:.0f}x real time")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work", type=Path)
    ap.add_argument("--only", default="*", help="glob for the .beats files to build, e.g. '03-*'")
    ap.add_argument("--lint", action="store_true", help="check only")
    ap.add_argument("--formulas", action="store_true", help="with --lint: also typeset every formula")
    ap.add_argument("--narration", action="store_true", help="with --lint: write NAME.narration.txt, the text the voice says")
    ap.add_argument("--engine", choices=["phonon", "say"], default="phonon")
    ap.add_argument("--voice", default=None, help="Phonon catalogue voice (default Everly) or a macOS voice for --engine say")
    ap.add_argument("--motion", choices=["full", "steps", "none"], default=None,
                    help="full: eased fades. steps: definitions light up with no fade. none: one frame per beat. "
                         "Default: full up to 400 beats in a file, then steps.")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    a.voice = a.voice or ("Everly" if a.engine == "phonon" else "Samantha")
    work = a.work.resolve()
    if not (work / "glossary.txt").exists():
        die(f"{work}/glossary.txt not found")
    files = sorted(work.glob(a.only + ".beats"))
    if not files:
        die("no .beats files")
    auto = a.motion is None
    base_readout, base_font, base_say = set(READOUT), set(FONT), dict(SAY)
    for f in files:
        READOUT.clear(); READOUT.update(base_readout)
        FONT.clear(); FONT.update(base_font)
        SAY.clear(); SAY.update(base_say)
        G = Glossary(work / "glossary.txt", *own_files(work, f, ".glossary.txt"))   # shared, then this file's own
        errs, warns = lint_glossary(G)
        for w in warns:
            print("  warning:", w)
        for e in errs:
            print("  error:", e)
        if errs:
            die("fix the glossary first")
        if auto:
            n = sum(1 for l in f.read_text().splitlines() if l.strip() and l.strip()[0] not in "#@%")
            a.motion = "full" if n <= 400 else "steps"
        build_chapter(f, G, a, work)


if __name__ == "__main__":
    main()
