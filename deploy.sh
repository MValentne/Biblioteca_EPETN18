#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

printf "\033[0;32mDesplegando actualizaciones a GitHub Pages...\033[0m\n"

# Construir el sitio con Hugo
hugo --gc --minify --cleanDestinationDir

# GitHub Pages no debe procesar el contenido con Jekyll.
touch public/.nojekyll

# Inicializar un repositorio independiente para la rama gh-pages.
git -C public init
git -C public checkout -B gh-pages
git -C public add --all

# Commit de los cambios
msg="Despliegue del sitio $(date '+%Y-%m-%d %H:%M:%S')"
if [ -n "$*" ]; then
    msg="$*"
fi
git -C public commit --allow-empty -m "$msg"

# Empujar a la rama gh-pages del repositorio remoto
git -C public remote remove origin 2>/dev/null || true
git -C public remote add origin git@github.com:MValentne/Biblioteca_EPETN18.git
git -C public push --force origin gh-pages

printf "\033[0;32m¡Despliegue completado con éxito!\033[0m\n"
