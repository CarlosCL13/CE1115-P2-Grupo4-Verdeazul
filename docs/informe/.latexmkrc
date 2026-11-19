# Compilar el informe con latexmk, como en los documentos de la Parte 1.
#
#   latexmk Informe-Grupo4.tex
#
# latexmk corre pdflatex las veces que hagan falta: el indice, las
# referencias cruzadas y el "Pagina N de M" se escriben en una pasada y se
# leen en la siguiente. Con una sola pasada salen sin indice y con "de ??".
#
# En VS Code, LaTeX Workshop usa latexmk por omision y toma este archivo.

$pdf_mode = 1;
$pdflatex = 'pdflatex -synctex=1 -interaction=nonstopmode -file-line-error %O %S';

# Lo que se borra con  latexmk -c  (el PDF se conserva: va en el repositorio).
$clean_ext = 'synctex.gz';
