"""End HTML comments where the browser's tokenizer does (#544).

The tokenizer closes a comment at `<!-->`, `<!--->` and `--!>` as well as `-->`.
Python's HTMLParser before 3.13 runs `<!-->` on to the next `-->` and swallows the
markup in between, so a verifier never sees an element the browser draws. Put
TokenizerComments ahead of HTMLParser in a scanner's bases. HTMLParser only asks
for a comment outside `<script>` and `<style>` text, so raw text stays as it is.
"""

from __future__ import annotations

import re

COMMENT_RE = re.compile(r"<!--(?:-?>|.*?--!?>)", re.DOTALL)


class TokenizerComments:
    def parse_comment(self, i: int, report: bool = True) -> int:
        match = COMMENT_RE.match(self.rawdata, i)
        if match is None:
            return -1
        if report:
            body = match.group(0)[4:]
            for ending in ("--!>", "-->", "->", ">"):
                if body.endswith(ending):
                    self.handle_comment(body[: -len(ending)])
                    break
        return match.end()
