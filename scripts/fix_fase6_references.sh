#!/bin/bash

# Script para resolver inconsistencia de numeración Fase 6/7
# Renombra referencias "Fase 7" a "Fase 6" en código y scripts

echo "🔧 Resolviendo inconsistencia Fase 6/7"
echo "========================================"

PROJECT_ROOT="/home/javi/Programacion/axonote"
cd "$PROJECT_ROOT"

# Función para hacer backup
make_backup() {
    local file="$1"
    cp "$file" "$file.backup.$(date +%Y%m%d_%H%M%S)"
    echo "   📄 Backup: $file.backup.$(date +%Y%m%d_%H%M%S)"
}

# 1. Renombrar script de testing
echo "1. 🔄 Renombrando script de testing..."
if [ -f "scripts/test_fase7_research.sh" ]; then
    make_backup "scripts/test_fase7_research.sh"
    mv "scripts/test_fase7_research.sh" "scripts/test_fase6_research.sh"
    echo "   ✅ scripts/test_fase7_research.sh → scripts/test_fase6_research.sh"
else
    echo "   ⚠️  Script test_fase7_research.sh no encontrado"
fi

# 2. Actualizar referencias en el script renombrado
echo "2. 📝 Actualizando referencias en script de testing..."
if [ -f "scripts/test_fase6_research.sh" ]; then
    sed -i 's/Testing Fase 7/Testing Fase 6/g' "scripts/test_fase6_research.sh"
    sed -i 's/Fase 7/Fase 6/g' "scripts/test_fase6_research.sh"
    sed -i 's/fase7/fase6/g' "scripts/test_fase6_research.sh"
    echo "   ✅ Referencias actualizadas en test_fase6_research.sh"
fi

# 3. Actualizar comentarios en código Python
echo "3. 🐍 Actualizando comentarios en código Python..."

# Buscar archivos Python con referencias a "Fase 7" o "fase 7" en contexto de research
find apps/api/app -name "*.py" -type f | while read file; do
    if grep -q "FASE 7\|Fase 7\|fase 7" "$file" && grep -q "research\|Research" "$file"; then
        echo "   📄 Actualizando: $file"
        make_backup "$file"
        
        # Actualizar comentarios y strings
        sed -i 's/FASE 7/FASE 6/g' "$file"
        sed -i 's/Fase 7/Fase 6/g' "$file"
        sed -i 's/fase 7/fase 6/g' "$file"
        
        echo "   ✅ $file actualizado"
    fi
done

# 4. Actualizar variables de entorno
echo "4. ⚙️  Actualizando variables de entorno..."
if [ -f "env.example" ]; then
    if grep -q "FASE 7" "env.example"; then
        make_backup "env.example"
        sed -i 's/FASE 7/FASE 6/g' "env.example"
        echo "   ✅ env.example actualizado"
    fi
fi

# 5. Actualizar referencias en documentación existente
echo "5. 📚 Actualizando referencias en documentación..."

# Actualizar documentación que mencione "Fase 7" como research
find Documentacion -name "*.md" -type f | while read file; do
    if grep -q "Fase 7.*[Rr]esearch\|[Rr]esearch.*Fase 7" "$file"; then
        echo "   📄 Actualizando: $file"
        make_backup "$file"
        
        # Solo actualizar referencias a Fase 7 cuando se refiera específicamente a research médico
        sed -i 's/Fase 7.*[Rr]esearch/Fase 6 Research/g' "$file"
        sed -i 's/scripts\/test_fase7_research\.sh/scripts\/test_fase6_research.sh/g' "$file"
        
        echo "   ✅ $file actualizado"
    fi
done

# 6. Verificar qué archivos todavía tienen referencias problemáticas
echo "6. 🔍 Verificando referencias restantes..."
echo ""
echo "   Referencias a 'test_fase7_research' encontradas en:"
grep -r "test_fase7_research" . --exclude-dir=.git --exclude="*.backup.*" | head -5

echo ""
echo "   Referencias a 'Fase 7' en contexto de research:"
grep -r "Fase 7.*[Rr]esearch\|[Rr]esearch.*Fase 7" . --exclude-dir=.git --exclude="*.backup.*" | head -5

# 7. Crear script de verificación
echo "7. 📋 Creando script de verificación..."
cat > "scripts/verify_fase6_consistency.sh" << 'EOF'
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
EOF

chmod +x "scripts/verify_fase6_consistency.sh"
echo "   ✅ scripts/verify_fase6_consistency.sh creado"

# 8. Ejecutar verificación
echo ""
echo "8. 🎯 Ejecutando verificación final..."
./scripts/verify_fase6_consistency.sh

echo ""
echo "🎉 Resolución de inconsistencia Fase 6/7 completada!"
echo ""
echo "📋 Resumen de cambios:"
echo "   - Script renombrado: test_fase7_research.sh → test_fase6_research.sh"
echo "   - Referencias actualizadas en código Python"
echo "   - Variables de entorno corregidas"
echo "   - Documentación actualizada"
echo "   - Script de verificación creado"
echo ""
echo "💡 Próximos pasos:"
echo "   1. Revisar que todos los tests funcionen con el nuevo script"
echo "   2. Actualizar cualquier documentación externa que referencie Fase 7"
echo "   3. Verificar que la numeración de fases posteriores sea consistente"
echo ""
echo "🔗 Para verificar estado: ./scripts/verify_fase6_consistency.sh"
