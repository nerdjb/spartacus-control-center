"""QDT (LCD Wiki / QScreen) theme import support.

lcdwiki.com ships cooler-screen themes as ``.qdt`` packages (e.g.
``480X480-1.qdt`` … ``480X480-7.qdt`` for round panels). No formal public
specification exists and vendor variants differ, so the reader is layered:

  container.py   format sniffing + asset extraction (ZIP/gzip/bare/binary-carve)
  parser.py      normalized QdtTheme/QdtWidget model from whatever descriptors exist
  mapper.py      QDT variable names -> canonical SPARTACUS telemetry keys
  conversion.py  QdtTheme -> native LcdLayout for LCD Studio editing

Every layer logs its evidence; unknown structures surface as ``unresolved``
entries instead of raising, so a theme always loads with best-effort fidelity.
"""
