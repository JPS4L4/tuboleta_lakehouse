"""Entrega final - renderiza docs/informe_final.md y docs/guia_proyecto.md a PDF A4 (Markdown propio + Edge/Chrome headless).

Uso: python -m scripts.entrega_pdf   (edita los .md y vuelve a correrlo)
Reutiliza el conversor y la búsqueda de navegador de scripts/taller4_pdf.py, sin modificarlo.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.taller4_pdf import DOCS as T4, NAVEGADORES, convertir

DOCS = T4.parent
DOCUMENTOS = [("informe_final", "Informe final"), ("guia_proyecto", "Guía del proyecto")]
CSS_A4 = "\n@page { size: A4; margin: 1.35cm 1.35cm; }\nimg { max-width: 100%; display: block; margin: 6px auto; }\n"


def preparar(md: str) -> str:
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)                                   # YAML front matter
    md = re.sub(r"^~~~(\w*)\s*$", "```", md, flags=re.M)                                    # fences ~~~ -> ```
    md = re.sub(r"^::: (\w+)\s*$", r'<div class="\1">', md, flags=re.M)                     # ::: portada
    md = re.sub(r"^:::\s*$", "</div>", md, flags=re.M)
    md = re.sub(r"^(#{1,3}) (.+?) \{\.([\w-]+)\}\s*$",
                lambda m: f'<h{len(m[1])} class="{m[3]}">{m[2]}</h{len(m[1])}>', md, flags=re.M)  # {.salto}
    md = re.sub(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$",
                lambda m: f'<p><img src="{(DOCS / m[2]).as_uri()}" alt="{m[1]}"></p>', md, flags=re.M)
    md = re.sub(r"\\n", "<br>\n", md)                                                      # salto de línea duro
    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", r"\1", md)                              # enlaces relativos: solo la etiqueta


def main() -> None:
    navegador = next((n for n in NAVEGADORES if Path(n).exists() or shutil.which(n)), None)
    if navegador is None:
        raise SystemExit("Se necesita Microsoft Edge o Google Chrome para imprimir el PDF.")
    estilo = (T4 / "informe.css").read_text(encoding="utf-8") + CSS_A4
    for nombre, titulo in DOCUMENTOS:
        cuerpo = convertir(preparar((DOCS / f"{nombre}.md").read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            pagina = Path(tmp) / f"{nombre}.html"
            pagina.write_text(f'<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>{titulo}</title>'
                              f"<style>{estilo}</style></head><body>{cuerpo}</body></html>", encoding="utf-8")
            salida = DOCS / f"{nombre}.pdf"
            subprocess.run([navegador, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={salida}", pagina.as_uri()], check=True, capture_output=True)
        print(f"PDF generado: {salida}")


if __name__ == "__main__":
    main()
