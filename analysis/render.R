# Renderiza el informe de modelos multivariados a docs/.
# Ejecutar desde la raíz del repositorio, después de `python main.py`:
#   Rscript analysis/render.R
rmarkdown::render(
  "analysis/modelos_multivariados.Rmd",
  output_dir = "docs",
  knit_root_dir = getwd(),
  encoding = "UTF-8"
)
