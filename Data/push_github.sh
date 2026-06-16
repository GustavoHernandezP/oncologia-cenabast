#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# push_github.sh
# Commit y push de los cambios al repositorio GitHub.
# Ejecutar cada vez que quieras guardar cambios.
#
# USO:
#   ./push_github.sh "descripción del cambio"
#   ./push_github.sh          ← usa mensaje automático con fecha
# ─────────────────────────────────────────────────────────────────────────────

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Verificar que hay un repo inicializado
if [ ! -d ".git" ]; then
    echo "❌  No hay repositorio git. Ejecuta setup_github.sh primero."
    exit 1
fi

# Mensaje del commit
if [ -n "$1" ]; then
    MSG="$1"
else
    MSG="Actualización $(date '+%Y-%m-%d %H:%M')"
fi

# Mostrar qué hay pendiente
echo "📋  Cambios a commitear:"
git status --short

# Agregar todos los cambios (respeta .gitignore)
git add .

# Verificar si hay algo que commitear
if git diff --cached --quiet; then
    echo "ℹ️   Sin cambios nuevos. Nada que hacer."
    exit 0
fi

git commit -m "$MSG"
git push origin main

echo ""
echo "✅  Push completado: \"$MSG\""
