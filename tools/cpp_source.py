"""The C++ reader of tools/transcribe.py: functions, arrays and scalars of a C++ source, with file:line provenance.

    src = Source(WCSIM_SRC, "src/WCSimPMTObject.cc", "WCSim e2dc7a4")
    qe, where, corr = src.array("PMT20inch::GetQE()")         # the numbers, "WCSim e2dc7a4 src/...:a-b", a factor
    sigma = src.scalar("PMT20inch::HitTimeSmearing", "timingConstant")

Comments are blanked before parsing (``/* */`` and ``//``, never inside a string or character literal), line numbers
kept, so every number the transcriber writes into a value set is parsed from the source and cited by its lines.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np


def number(x: str) -> float:
    """Return a C++ literal or a quotient of two ("0.5/100.", as PMT3inchR14374_FDOD's QE writes them)."""
    a, _, b = x.partition("/")
    return float(a) / float(b) if b else float(a)


class Source:
    """A C++ source file under ``root`` (``rel`` its path there, ``tag`` its repository and version)."""

    def __init__(self, root, rel, tag):
        """Read the file; ``clean`` holds its lines with the comments blanked (line numbers kept)."""
        self.path, self.tag, self.rel = Path(root) / rel, tag, rel
        self.lines = self.path.read_text().splitlines()
        token = r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'"  # comments, strings, chars
        blank = lambda m: re.sub(r"[^\n]", " ", m.group(0)) if m.group(0)[0] == "/" else m.group(0)  # noqa: E731
        self.clean = re.sub(token, blank, self.path.read_text(), flags=re.S).splitlines()  # comments blanked

    def has(self, signature):
        """Return whether a comment-free line holds ``signature``."""
        return any(signature in ln for ln in self.clean)

    def function(self, signature):
        """Return (first line, last line, body text without comments) of a C++ function, 1-based lines."""
        i0 = next(i for i, ln in enumerate(self.clean) if signature in ln)
        depth, i, opened = 0, i0, False
        while True:
            code = re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", "", self.clean[i])  # braces outside literals
            depth += code.count("{") - code.count("}")
            opened = opened or "{" in code
            if opened and depth == 0:
                break
            i += 1
        return i0 + 1, i + 1, "\n".join(self.clean[i0 : i + 1])

    def array(self, signature, name=None):
        """Return (the numbers of the function's first brace list, or of the one after ``name``, where, its
        correctionFactor text or None)."""  # noqa: D205, D209
        a, b, body = self.function(signature)
        inner = body.split(name, 1)[1] if name else body.split("{", 1)[1]
        vals = re.search(r"\{([^{}]*)\}", inner).group(1)
        corr = re.search(r"correctionFactor\s*=\s*([0-9./]+)\s*;", body)
        nums = [number(x.replace("*correctionFactor", "")) for x in re.split(r"[,\s]+", vals) if x.strip()]
        return np.asarray(nums), f"{self.tag} {self.rel}:{a}-{b}", corr.group(1) if corr else None

    def scalar(self, signature, name):
        """Return the number assigned to ``name`` in the function."""
        a, b, body = self.function(signature)
        return float(re.search(rf"{name}\s*=\s*([0-9.eE+\-]+)", body).group(1))

    def where(self, signature):
        """Return the function's provenance, "tag rel:first-last"."""
        a, b, _ = self.function(signature)
        return f"{self.tag} {self.rel}:{a}-{b}"

    def match(self, pattern, signature=None, same=False):
        """Return (match, "<tag> <rel>:<line>") of the one comment-free line matching ``pattern`` (in a function, if
        given); ``same``: any number of lines, all with the same groups (all cited)."""  # noqa: D205, D209
        lo, hi = (0, len(self.clean)) if signature is None else (lambda a, b, _: (a - 1, b))(*self.function(signature))
        hits = [(i + 1, m) for i in range(lo, hi) if (m := re.search(pattern, self.clean[i]))]
        if not hits or (len(hits) > 1 and not same) or len({m.groups() for _, m in hits}) > 1:
            raise ValueError(f"{self.rel}: {len(hits)} lines match {pattern!r} (want 1, or the same groups)")
        return hits[0][1], f"{self.tag} {self.rel}:" + ", ".join(str(i) for i, _ in hits)

    def at(self, pattern):
        """Return "<file name>:<l1>, <l2>, ...": the comment-free lines matching ``pattern`` (at least one)."""
        hits = [str(i + 1) for i, ln in enumerate(self.clean) if re.search(pattern, ln)]
        if not hits:
            raise ValueError(f"{self.rel}: no line matches {pattern!r}")
        return f"{Path(self.rel).name}:" + ", ".join(hits)


__all__ = ["Source", "number"]
