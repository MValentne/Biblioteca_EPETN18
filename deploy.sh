#!/usr/bin/env bash

# Terminar inmediatamente si un comando falla
set -e

printf "\033[0;32mDesplegando actualizaciones a GitHub Pages...\033[0m\n"

# Limpiar directorio public previo si existe
rm -rf public

# Construir el sitio con Hugo
hugo --minify

# Ir al directorio generado
cd public

# Inicializar un nuevo repo git para la rama gh-pages o sobreescribir
git init -b gh-pages
git add -A

# Commit de los cambios
msg="Despliegue del sitio $(date '+%Y-%m-%d %H:%M:%S')"
if [ -n "$*" ]; then
    msg="$*"
fi
git commit -m "$msg"

# Empujar a la rama gh-pages del repositorio remoto
git remote add origin git@github.com:MValentne/Biblioteca_EPETN18.git
git push -f origin gh-pages

cd ..
printf "\033[0;32m¡Despliegue completado con éxito!\033[0m\n"
