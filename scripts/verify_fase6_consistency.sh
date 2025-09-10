#!/bin/bash

echo "🔍 Verificación de Consistencia Fase 6"
echo "====================================="

PROJECT_ROOT="/home/javi/Programacion/axonote"
cd "$PROJECT_ROOT"

echo "1. Verificando existencia de archivos principales:"
files=(
    "scripts/test_fase6_research.sh"
    "Documentacion/B6.1-Fase-6-Research-Fuentes-Medicas.md"
    "Documentacion/B6.2-Resumen-Implementacion-Fase-6.md"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ $file"
    else
        echo "   ❌ $file - FALTANTE"
    fi
done

echo ""
echo "2. Verificando referencias inconsistentes:"
echo ""
echo "   🔍 Referencias a 'test_fase7_research' (deberían ser fase6):"
grep -r "test_fase7_research" . --exclude-dir=.git --exclude="*.backup.*" | wc -l | xargs echo "      Encontradas:"

echo ""
echo "   🔍 Referencias mezcladas 'Fase 7' + 'research':"
grep -r "Fase 7.*[Rr]esearch\|[Rr]esearch.*Fase 7" . --exclude-dir=.git --exclude="*.backup.*" | wc -l | xargs echo "      Encontradas:"

echo ""
echo "3. Estado de implementación:"
if [ -f "apps/api/app/tasks/research.py" ]; then
    echo "   ✅ Tareas de research implementadas"
else
    echo "   ❌ Tareas de research NO encontradas"
fi

if [ -f "apps/api/app/services/research_service.py" ]; then
    echo "   ✅ Servicio de research implementado"
else
    echo "   ❌ Servicio de research NO encontrado"
fi

if [ -f "apps/api/app/api/v1/endpoints/research.py" ]; then
    echo "   ✅ Endpoints de research implementados"
else
    echo "   ❌ Endpoints de research NO encontrados"
fi

echo ""
echo "✅ Verificación completada!"
