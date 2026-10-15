# suvrit.github.io

Research Preprints by Suvrit Sra: https://suvrit.github.io/

A static site generated from the release repository
[github.com/suvrit/preprints](https://github.com/suvrit/preprints). Every paper
gets its own page under `papers/<paper>/` with Google Scholar's `citation_*`
meta tags, the released PDFs and their OpenTimestamps proofs copied next to it,
and a sitemap for crawlers. Subjects and one-line labels come from the release
repository's `overview.tex`.

Rebuild after each release (the preprints clone is expected next to this one):

```sh
python3 build.py --preprints ../preprints
git add -A && git commit -m "Rebuild" && git push
```

Hand-written: `build.py`, `assets/style.css`, `notes/`. Everything else at the
root and under `papers/` is generated. The MIT licence covers the site code;
the papers are the author's own.
