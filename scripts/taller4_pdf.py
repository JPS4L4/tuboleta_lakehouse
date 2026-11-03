"""Taller 4 - Build docs/taller4/informe_taller4.pdf from informe_taller4.md (stdlib Markdown subset + Edge/Chrome headless).

Uso: python -m scripts.taller4_pdf   (edita el .md y vuelve a correrlo)
"""
import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def inline(t: str) -> str:
    partes = re.split(r"(`[^`]+`)", t)
    out = []
    for p in partes:
        if p.startswith("`") and p.endswith("`") and len(p) > 1:
            out.append(f"<code>{html.escape(p[1:-1])}</code>")
        else:
            p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
            p = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", p)
            out.append(p)
    return "".join(out)


def convertir(md: str) -> str:
    lineas, out, i = md.splitlines(), [], 0
    while i < len(lineas):
        l = lineas[i]
        if l.startswith("```"):
            j = i + 1
            while not lineas[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lineas[i + 1:j])) + "</code></pre>")
            i = j + 1
        elif l.startswith("|"):
            filas = []
            while i < len(lineas) and lineas[i].startswith("|"):
                filas.append([c.strip() for c in lineas[i].strip().strip("|").split("|")])
                i += 1
            alin = ["right" if c.endswith(":") and not c.startswith(":") else "left" for c in filas[1]]
            t = ["<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in filas[0]) + "</tr></thead><tbody>"]
            for f in filas[2:]:
                t.append("<tr>" + "".join(f'<td style="text-align:{a}">{inline(c)}</td>' for c, a in zip(f, alin)) + "</tr>")
            out.append("".join(t) + "</tbody></table>")
        elif m := re.match(r"^(#{1,3}) (.+)", l):
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
        elif re.match(r"^(\d+\.|-) ", l):
            tag = "ol" if l[0].isdigit() else "ul"
            items = []
            while i < len(lineas) and re.match(r"^(\d+\.|-) ", lineas[i]):
                items.append("<li>" + inline(re.sub(r"^(\d+\.|-) ", "", lineas[i])) + "</li>")
                i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
        elif l.startswith("<"):
            out.append(l)
            i += 1
        elif not l.strip():
            i += 1
        else:
            par = []
            while i < len(lineas) and lineas[i].strip() and not re.match(r"^(#|\||```|<|\d+\. |- )", lineas[i]):
                par.append(lineas[i])
                i += 1
            out.append("<p>" + inline(" ".join(par)) + "</p>")
    return "\n".join(out)


DOCS = Path(__file__).resolve().parents[1] / "docs" / "taller4"
NAVEGADORES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
               r"C:\Program Files\Google\Chrome\Application\chrome.exe", "msedge", "google-chrome", "chromium"]


def main() -> None:
    navegador = next((n for n in NAVEGADORES if Path(n).exists() or shutil.which(n)), None)
    if navegador is None:
        raise SystemExit("Se necesita Microsoft Edge o Google Chrome para imprimir el PDF.")
    cuerpo = convertir((DOCS / "informe_taller4.md").read_text(encoding="utf-8"))
    estilo = (DOCS / "informe.css").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        pagina = Path(tmp) / "informe.html"
        pagina.write_text(f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
                          f"<title>Taller 4 — Laboratorio de Optimización de Consultas</title><style>{estilo}</style>"
                          f"</head><body>{cuerpo}</body></html>", encoding="utf-8")
        subprocess.run([navegador, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={DOCS / 'informe_taller4.pdf'}", pagina.as_uri()], check=True, capture_output=True)
    print(f"PDF generado: {DOCS / 'informe_taller4.pdf'}")


if __name__ == "__main__":
    main()
