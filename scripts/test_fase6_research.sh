#!/bin/bash
# ==============================================
# Script de Testing - Fase 6: Research y Fuentes Médicas
# ==============================================
# 
# Este script prueba completamente la funcionalidad de investigación
# automática de fuentes médicas implementada en la Fase 6.
#
# Uso:
#   ./scripts/test_fase6_research.sh [llm_analysis_id]
#
# Si no se proporciona llm_analysis_id, usa uno de prueba

set -e  # Salir en caso de error

# Configuración
API_BASE="${API_BASE:-http://localhost:8000/api/v1}"
LLM_ANALYSIS_ID="${1:-550e8400-e29b-41d4-a716-446655440000}"  # UUID de prueba
TEST_TERM="${TEST_TERM:-cardiomiopatia}"
TIMEOUT=30

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funciones auxiliares
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_api_response() {
    local response="$1"
    local expected_status="$2"
    
    if echo "$response" | jq -e . >/dev/null 2>&1; then
        local status=$(echo "$response" | jq -r '.status // "unknown"')
        if [[ "$status" == "$expected_status" || "$expected_status" == "any" ]]; then
            return 0
        else
            log_error "Estado inesperado: $status (esperado: $expected_status)"
            return 1
        fi
    else
        log_error "Respuesta no es JSON válido"
        echo "$response"
        return 1
    fi
}

wait_for_completion() {
    local job_id="$1"
    local max_wait="${2:-300}"  # 5 minutos por defecto
    local waited=0
    
    log_info "Esperando completion del job $job_id (máximo ${max_wait}s)..."
    
    while [ $waited -lt $max_wait ]; do
        local status_response=$(curl -s "$API_BASE/research/status/$job_id")
        local status=$(echo "$status_response" | jq -r '.status // "unknown"')
        local progress=$(echo "$status_response" | jq -r '.progress_percentage // 0')
        
        log_info "Estado: $status, Progreso: ${progress}%"
        
        if [[ "$status" == "completed" ]]; then
            log_success "Job completado exitosamente"
            return 0
        elif [[ "$status" == "failed" || "$status" == "cancelled" ]]; then
            log_error "Job falló con estado: $status"
            echo "$status_response" | jq '.'
            return 1
        fi
        
        sleep 10
        waited=$((waited + 10))
    done
    
    log_error "Timeout esperando completion del job"
    return 1
}

# Banner de inicio
echo "🔬 Testing Fase 6: Research y Fuentes Médicas"
echo "=============================================="
echo "API Base: $API_BASE"
echo "LLM Analysis ID: $LLM_ANALYSIS_ID"
echo "Test Term: $TEST_TERM"
echo ""

# Verificar dependencias
if ! command -v jq &> /dev/null; then
    log_error "jq no está instalado. Por favor instalar: apt install jq"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    log_error "curl no está instalado. Por favor instalar: apt install curl"
    exit 1
fi

# 1. Health Check del Sistema de Research
echo "1. 🏥 Health Check del Sistema de Research"
echo "========================================="

log_info "Verificando salud de servicios de research..."
HEALTH_RESPONSE=$(curl -s -w "%{http_code}" "$API_BASE/research/health")
HTTP_CODE=${HEALTH_RESPONSE: -3}
HEALTH_BODY=${HEALTH_RESPONSE%???}

if [[ "$HTTP_CODE" == "200" ]]; then
    log_success "Health check iniciado correctamente"
    echo "$HEALTH_BODY" | jq '.'
else
    log_error "Health check falló con código HTTP: $HTTP_CODE"
    echo "$HEALTH_BODY"
fi

echo ""

# 2. Verificar Presets de Research Disponibles
echo "2. 📋 Verificar Presets de Research Disponibles"
echo "=============================================="

log_info "Obteniendo presets de research..."
PRESETS_RESPONSE=$(curl -s "$API_BASE/research/presets")

if check_api_response "$PRESETS_RESPONSE" "any"; then
    log_success "Presets obtenidos exitosamente"
    echo "$PRESETS_RESPONSE" | jq '.presets | keys'
    
    # Mostrar detalles del preset COMPREHENSIVE
    log_info "Detalles del preset COMPREHENSIVE:"
    echo "$PRESETS_RESPONSE" | jq '.presets.COMPREHENSIVE'
else
    log_error "Error obteniendo presets"
fi

echo ""

# 3. Verificar Fuentes Médicas Disponibles
echo "3. 🔍 Verificar Fuentes Médicas Disponibles"
echo "=========================================="

log_info "Obteniendo fuentes médicas disponibles..."
SOURCES_RESPONSE=$(curl -s "$API_BASE/research/sources")

if check_api_response "$SOURCES_RESPONSE" "any"; then
    log_success "Fuentes obtenidas exitosamente"
    echo "$SOURCES_RESPONSE" | jq '.sources | keys'
    
    # Mostrar detalles de PubMed
    log_info "Detalles de PubMed:"
    echo "$SOURCES_RESPONSE" | jq '.sources.pubmed'
else
    log_error "Error obteniendo fuentes"
fi

echo ""

# 4. Búsqueda Manual de Término Individual
echo "4. 🔍 Búsqueda Manual de Término Individual"
echo "========================================="

log_info "Buscando término '$TEST_TERM' manualmente..."
MANUAL_SEARCH_RESPONSE=$(curl -s -X POST "$API_BASE/research/term" \
  -H "Content-Type: application/json" \
  -d "{
    \"term\": \"$TEST_TERM\",
    \"config\": {
      \"preset\": \"QUICK\",
      \"language\": \"it\",
      \"max_sources_per_term\": 3,
      \"enabled_sources\": [\"pubmed\", \"who\"]
    },
    \"context\": \"Enfermedad cardíaca en clase de cardiología\"
  }")

if check_api_response "$MANUAL_SEARCH_RESPONSE" "any"; then
    log_success "Búsqueda manual iniciada"
    echo "$MANUAL_SEARCH_RESPONSE" | jq '.'
    
    # Verificar si hay task_id para monitorear
    TASK_ID=$(echo "$MANUAL_SEARCH_RESPONSE" | jq -r '.task_id // empty')
    if [[ -n "$TASK_ID" ]]; then
        log_info "Monitoreando tarea $TASK_ID..."
        sleep 5
        
        TASK_STATUS=$(curl -s "$API_BASE/research/task-status/$TASK_ID")
        echo "$TASK_STATUS" | jq '.'
    fi
else
    log_error "Error en búsqueda manual"
fi

echo ""

# 5. Iniciar Research Completo
echo "5. 🚀 Iniciar Research Completo"
echo "=============================="

log_info "Iniciando research completo para LLM analysis $LLM_ANALYSIS_ID..."
RESEARCH_RESPONSE=$(curl -s -X POST "$API_BASE/research/start/$LLM_ANALYSIS_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "preset": "COMPREHENSIVE",
    "priority": "high",
    "language": "it",
    "max_sources_per_term": 3,
    "enabled_sources": ["pubmed", "who", "nih", "italian_official"],
    "include_related_terms": true,
    "enable_translation": true
  }')

if check_api_response "$RESEARCH_RESPONSE" "any"; then
    log_success "Research iniciado exitosamente"
    echo "$RESEARCH_RESPONSE" | jq '.'
    
    RESEARCH_JOB_ID=$(echo "$RESEARCH_RESPONSE" | jq -r '.research_job_id')
    TASK_ID=$(echo "$RESEARCH_RESPONSE" | jq -r '.task_id')
    
    if [[ "$RESEARCH_JOB_ID" != "null" && -n "$RESEARCH_JOB_ID" ]]; then
        log_info "Research Job ID: $RESEARCH_JOB_ID"
        log_info "Celery Task ID: $TASK_ID"
    else
        log_error "No se pudo obtener el ID del research job"
        exit 1
    fi
else
    log_error "Error iniciando research"
    exit 1
fi

echo ""

# 6. Monitorear Progreso del Research
echo "6. 📊 Monitorear Progreso del Research"
echo "====================================="

if [[ -n "$RESEARCH_JOB_ID" ]]; then
    log_info "Monitoreando progreso del research job $RESEARCH_JOB_ID..."
    
    # Intentar esperar completion (con timeout reducido para testing)
    if wait_for_completion "$RESEARCH_JOB_ID" 120; then
        log_success "Research completado exitosamente"
    else
        log_warning "Research no completado en tiempo esperado, continuando con verificaciones..."
    fi
    
    # Mostrar estado final
    log_info "Estado final del research:"
    FINAL_STATUS=$(curl -s "$API_BASE/research/status/$RESEARCH_JOB_ID")
    echo "$FINAL_STATUS" | jq '.'
else
    log_error "No hay research job ID para monitorear"
fi

echo ""

# 7. Verificar Resultados de Research
echo "7. 📋 Verificar Resultados de Research"
echo "====================================="

if [[ -n "$RESEARCH_JOB_ID" ]]; then
    log_info "Obteniendo resultados del research..."
    RESULTS_RESPONSE=$(curl -s "$API_BASE/research/results/$RESEARCH_JOB_ID?include_sources=true&limit=5")
    
    if check_api_response "$RESULTS_RESPONSE" "any"; then
        log_success "Resultados obtenidos exitosamente"
        
        # Mostrar resumen
        TOTAL_RESULTS=$(echo "$RESULTS_RESPONSE" | jq '.total_results // 0')
        log_info "Total de resultados: $TOTAL_RESULTS"
        
        if [[ "$TOTAL_RESULTS" -gt 0 ]]; then
            # Mostrar primer resultado como ejemplo
            log_info "Ejemplo de resultado:"
            echo "$RESULTS_RESPONSE" | jq '.results[0] | {medical_term, sources_count, quality_grade, confidence_score}'
            
            # Mostrar fuentes del primer resultado
            log_info "Fuentes del primer resultado:"
            echo "$RESULTS_RESPONSE" | jq '.results[0].sources[] | {title, domain, source_type, relevance_score}' 2>/dev/null || log_info "Sin fuentes detalladas"
        else
            log_warning "No hay resultados disponibles"
        fi
    else
        log_error "Error obteniendo resultados"
    fi
else
    log_warning "No hay research job ID para obtener resultados"
fi

echo ""

# 8. Obtener Resumen Ejecutivo
echo "8. 📈 Obtener Resumen Ejecutivo"
echo "=============================="

if [[ -n "$RESEARCH_JOB_ID" ]]; then
    log_info "Obteniendo resumen ejecutivo..."
    SUMMARY_RESPONSE=$(curl -s "$API_BASE/research/results/summary/$RESEARCH_JOB_ID")
    
    if check_api_response "$SUMMARY_RESPONSE" "any"; then
        log_success "Resumen obtenido exitosamente"
        
        # Mostrar métricas clave
        echo "$SUMMARY_RESPONSE" | jq '{
          overview: .overview,
          quality_metrics: .quality_metrics,
          performance: .performance
        }'
    else
        log_error "Error obteniendo resumen"
    fi
fi

echo ""

# 9. Verificar Estadísticas de Cache
echo "9. 📈 Verificar Estadísticas de Cache"
echo "===================================="

log_info "Obteniendo estadísticas de cache..."
CACHE_STATS_RESPONSE=$(curl -s "$API_BASE/research/cache/stats")

if check_api_response "$CACHE_STATS_RESPONSE" "any"; then
    log_success "Estadísticas de cache obtenidas"
    echo "$CACHE_STATS_RESPONSE" | jq '.cache_statistics.overview'
else
    log_error "Error obteniendo estadísticas de cache"
fi

echo ""

# 10. Test de Limpieza de Cache (opcional)
echo "10. 🧹 Test de Limpieza de Cache"
echo "==============================="

log_info "Iniciando limpieza de cache (solo para testing)..."
CLEANUP_RESPONSE=$(curl -s -X POST "$API_BASE/research/cache/cleanup")

if check_api_response "$CLEANUP_RESPONSE" "any"; then
    log_success "Limpieza de cache iniciada"
    echo "$CLEANUP_RESPONSE" | jq '.'
    
    # Monitorear tarea de limpieza
    CLEANUP_TASK_ID=$(echo "$CLEANUP_RESPONSE" | jq -r '.task_id')
    if [[ -n "$CLEANUP_TASK_ID" ]]; then
        log_info "Monitoreando limpieza..."
        sleep 5
        
        CLEANUP_STATUS=$(curl -s "$API_BASE/research/task-status/$CLEANUP_TASK_ID")
        echo "$CLEANUP_STATUS" | jq '.'
    fi
else
    log_error "Error iniciando limpieza de cache"
fi

echo ""

# 11. Verificaciones Finales
echo "11. ✅ Verificaciones Finales"
echo "==========================="

log_info "Realizando verificaciones finales..."

# Verificar que los endpoints responden
ENDPOINTS=(
    "/research/presets"
    "/research/sources"
    "/research/health"
    "/research/cache/stats"
)

ALL_OK=true
for endpoint in "${ENDPOINTS[@]}"; do
    HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null "$API_BASE$endpoint")
    if [[ "$HTTP_CODE" == "200" ]]; then
        log_success "✓ $endpoint - OK"
    else
        log_error "✗ $endpoint - HTTP $HTTP_CODE"
        ALL_OK=false
    fi
done

echo ""

# Resumen final
echo "📋 RESUMEN DE TESTING"
echo "===================="

if [[ "$ALL_OK" == true ]]; then
    log_success "🎉 Todos los endpoints principales funcionan correctamente"
else
    log_error "❌ Algunos endpoints tienen problemas"
fi

if [[ -n "$RESEARCH_JOB_ID" ]]; then
    log_info "🔬 Research Job creado: $RESEARCH_JOB_ID"
    log_info "📊 Para ver progreso: curl '$API_BASE/research/status/$RESEARCH_JOB_ID'"
    log_info "📋 Para ver resultados: curl '$API_BASE/research/results/$RESEARCH_JOB_ID'"
fi

echo ""
echo "💡 COMANDOS ÚTILES PARA TESTING MANUAL:"
echo "======================================="
echo ""
echo "# Verificar estado de un research job:"
echo "curl '$API_BASE/research/status/\$RESEARCH_JOB_ID' | jq '.'"
echo ""
echo "# Buscar término individual:"
echo "curl -X POST '$API_BASE/research/term' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"term\": \"$TEST_TERM\", \"config\": {\"preset\": \"QUICK\"}}' | jq '.'"
echo ""
echo "# Ver estadísticas de cache:"
echo "curl '$API_BASE/research/cache/stats' | jq '.cache_statistics.overview'"
echo ""
echo "# Iniciar research para un LLM analysis:"
echo "curl -X POST '$API_BASE/research/start/\$LLM_ANALYSIS_ID' \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"preset\": \"COMPREHENSIVE\", \"priority\": \"high\"}' | jq '.'"

echo ""
log_success "✅ Testing de Fase 6 completado!"

# Si hay algún error, salir con código de error
if [[ "$ALL_OK" != true ]]; then
    exit 1
fi
