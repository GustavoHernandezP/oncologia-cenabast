#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_github.sh
# Inicializa el repositorio git y lo vincula a GitHub (solo se corre UNA vez).
#
# USO:
#   1. Crea el repositorio vacío en https://github.com/new
#   2. Copia la URL del repo (ej: https://github.com/tu-usuario/mercado-oncologico.git)
#   3. Edita REPO_URL abajo
#   4. chmod +x setup_github.sh && ./setup_github.sh
# ─────────────────────────────────────────────────────────────────────────────

REPO_URL="https://github.com/TU_USUARIO/TU_REPOSITORIO.git"   # ← EDITAR

# Directorio del script
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Verificar que se editó la URL
if [[ "$REPO_URL" == *"TU_USUARIO"* ]]; then
    echo "❌  Edita REPO_URL en este script antes de ejecutarlo."
    exit 1
fi

echo "📁  Directorio: $DIR"

# Inicializar git si no existe
if [ ! -d ".git" ]; then
    git init
    git branch -M main
    echo "✅  Repositorio git inicializado"
fi

# .gitignore — excluye BD (puede ser grande), xlsx generados y archivos temporales
cat > .gitignore << 'EOF'
# Base de datos SQLite (puede ser grande; regenerar con el extractor)
oncologia.db

# Archivos Excel generados automáticamente
oncologia_*.xlsx

# Estado del extractor (local)
estado_extractor.json

# Python
__pycache__/
*.pyc
*.pyo
.env

# macOS
.DS_Store
EOF

echo "✅  .gitignore creado"

# Agregar remote
if git remote get-url origin &>/dev/null; then
    git remote set-url origin "$REPO_URL"
    echo "✅  Remote 'origin' actualizado"
else
    git remote add origin "$REPO_URL"
    echo "✅  Remote 'origin' agregado"
fi

# Primer commit
git add .
git commit -m "Inicio: dashboard + extractor oncológico Mercado Público Chile"

# Push inicial
git push -u origin main

echo ""
echo "🎉  Repositorio publicado en: $REPO_URL"
