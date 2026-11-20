# FYP poster (22.5 x 34.5 in, portrait)

`python make_poster.py F26-XXX "Mr."` writes `FYPPoster-<ID>-TURN.pdf` next to the script (needs Playwright's
Chromium). Before running:

- fonts: `cd .. && npm pack @fontsource/anton @fontsource/bebas-neue @fontsource/oswald @fontsource/special-elite
  @fontsource/archivo-narrow` and unpack each into `docs/fonts/<package>-<version>/` (the script reads
  `../fonts/fontsource-*/files/*.woff2`; adjust the version numbers in `FONTFACE` if they differ);
- `nu_logo.png`: the university logo (not kept in git), placed next to the script.

Every figure on the poster comes from a recorded run (see `docs/RESULTS_*`). Update the stamps and the
iteration frames when the numbers change.
