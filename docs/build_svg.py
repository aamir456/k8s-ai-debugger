"""Builds docs/architecture.svg (standalone, light theme) from docs/architecture.html.

The diagram is authored once in architecture.html (published as a Claude artifact);
this script copies the <svg> and adds fixed colors so it renders on GitHub.
Run:  python docs/build_svg.py
"""
import pathlib
import re

here = pathlib.Path(__file__).parent
html = (here / "architecture.html").read_text(encoding="utf-8")
svg = re.search(r"<svg .*?</svg>", html, re.S).group(0)

style = """
<style>
  .bg { fill: #f5f7f8; }
  .panel { fill: #eaeef2; }
  .group { fill: none; stroke: #7d8898; stroke-dasharray: 5 4; }
  .box { fill: #ffffff; stroke: #7d8898; stroke-width: 1.2; }
  .box-accent { fill: #dcf1ed; stroke: #0b7a6a; stroke-width: 2; }
  .t { fill: #17202b; font: 600 14px "Segoe UI", Inter, Helvetica, Arial, sans-serif; }
  .s { fill: #586474; font: 11.5px "Segoe UI", Inter, Helvetica, Arial, sans-serif; }
  .k { fill: #586474; font: 11px Consolas, "JetBrains Mono", monospace; letter-spacing: .08em; }
  .e { fill: #17202b; font: 11px Consolas, "JetBrains Mono", monospace; }
  .ea { fill: #0b7a6a; font: 500 11px Consolas, "JetBrains Mono", monospace; }
  .edge { fill: none; stroke: #7d8898; stroke-width: 1.5; }
  .edge-dash { fill: none; stroke: #7d8898; stroke-width: 1.5; stroke-dasharray: 4 4; }
  .edge-accent { fill: none; stroke: #0b7a6a; stroke-width: 2.2; }
  .ah { fill: #7d8898; }
  .ah-accent { fill: #0b7a6a; }
</style>
<rect class="bg" x="0" y="0" width="1210" height="760"/>
"""
svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" width="1210" height="760" ', 1)
svg = svg.replace("<defs>", style + "<defs>", 1)
(here / "architecture.svg").write_text(svg + "\n", encoding="utf-8")
print("wrote", here / "architecture.svg")
