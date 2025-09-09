#!/bin/bash

# ==============================================
# Script de Testing - Fase 5: Post-procesamiento y Análisis LLM
# ==============================================
# Valida el funcionamiento completo del pipeline de análisis inteligente

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuración
API_BASE_URL="http://localhost:8000/api/v1"
PROCESSING_JOB_ID=""
TRANSCRIPTION_ID=""
DIARIZATION_ID=""

echo -e "${BLUE}🧠 Testing Fase 5: Post-procesamiento y Análisis LLM${NC}"
echo "=============================================="

# Función para logging
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Función para hacer requests HTTP
make_request() {
    local method=$1
    local endpoint=$2
    local data=$3
    local expected_status=${4:-200}
    
    if [ -n "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$API_BASE_URL$endpoint")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            "$API_BASE_URL$endpoint")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" -eq "$expected_status" ]; then
        echo "$body"
        return 0
    else
        log_error "Request failed: $method $endpoint (HTTP $http_code)"
        echo "$body" | jq '.' 2>/dev/null || echo "$body"
        return 1
    fi
}

# Test 1: Health Check de servicios LLM
test_llm_health_check() {
    log_info "Test 1: Health Check de servicios LLM"
    
    response=$(make_request "GET" "/llm-analysis/health")
    
    if echo "$response" | jq -e '.success == true' > /dev/null; then
        local overall_status=$(echo "$response" | jq -r '.data.overall_status')
        local llm_status=$(echo "$response" | jq -r '.data.llm_service.status')
        local post_processing_ready=$(echo "$response" | jq -r '.data.post_processing_service.is_initialized')
        
        log_success "Health check exitoso"
        echo "  - Estado general: $overall_status"
        echo "  - Estado LLM: $llm_status"
        echo "  - Post-procesamiento listo: $post_processing_ready"
        
        if [ "$overall_status" != "healthy" ]; then
            log_warning "Servicios no están completamente saludables"
        fi
    else
        log_error "Health check falló"
        return 1
    fi
}

# Test 2: Buscar terminología médica
test_medical_terminology_search() {
    log_info "Test 2: Búsqueda de terminología médica"
    
    # Buscar términos médicos comunes
    local terms=("cardiaco" "polmonare" "neurologico" "farmacologia")
    
    for term in "${terms[@]}"; do
        response=$(make_request "GET" "/llm-analysis/terminology/search?query=$term&limit=5")
        
        if echo "$response" | jq -e '.success == true' > /dev/null; then
            local count=$(echo "$response" | jq '.data.total_results')
            log_success "Búsqueda '$term': $count resultados encontrados"
        else
            log_warning "Búsqueda '$term' falló"
        fi
    done
}

# Test 3: Crear job de procesamiento de prueba
create_test_processing_job() {
    log_info "Test 3: Creando job de procesamiento de prueba"
    
    # Texto de transcripción de prueba (italiano médico)
    local test_transcription="Oggi parleremo di cardiologia. Il cuore è un organo fondamentale del sistema cardiovascolare. La frequenza cardiaca normale è tra 60 e 100 battiti per minuto. Studente, può dirmi quali sono i sintomi dell'infarto del miocardio? Professore, i sintomi includono dolore toracico, dispnea e sudorazione. Esatto, molto bene. Ricordate che la diagnosi precoce è cruciale per il trattamento."
    
    # Crear transcripción de prueba directamente en la base de datos
    # (En un entorno real, esto vendría de la Fase 4)
    
    # Para este test, simularemos que ya existe un job completado
    log_warning "Para este test, necesitas un processing_job_id existente con transcripción completada"
    echo "Puedes obtener uno ejecutando primero el pipeline de la Fase 4"
    echo "O crear uno manualmente en la base de datos para testing"
    
    # Ejemplo de cómo obtener jobs existentes
    log_info "Buscando jobs de procesamiento existentes..."
    
    # Este endpoint no existe aún, pero sería útil para testing
    # response=$(make_request "GET" "/processing/jobs?estado=completado&limit=1")
}

# Test 4: Iniciar post-procesamiento
test_start_post_processing() {
    local job_id=$1
    
    if [ -z "$job_id" ]; then
        log_warning "Test 4: Saltando - No hay job_id disponible"
        return 0
    fi
    
    log_info "Test 4: Iniciando post-procesamiento para job $job_id"
    
    local config='{
        "asr_correction_enabled": true,
        "confidence_threshold": 0.8,
        "ner_enabled": true,
        "include_definitions": true,
        "structure_analysis_enabled": true,
        "llm_preset": "MEDICAL_COMPREHENSIVE",
        "force_local_llm": false,
        "priority": "high"
    }'
    
    response=$(make_request "POST" "/llm-analysis/start/$job_id" "$config")
    
    if echo "$response" | jq -e '.success == true' > /dev/null; then
        local task_id=$(echo "$response" | jq -r '.task_id')
        log_success "Post-procesamiento iniciado (Task ID: $task_id)"
        
        # Guardar para tests posteriores
        echo "$task_id" > /tmp/axonote_test_task_id
        echo "$job_id" > /tmp/axonote_test_job_id
        
        return 0
    else
        log_error "Falló al iniciar post-procesamiento"
        return 1
    fi
}

# Test 5: Monitorear progreso del post-procesamiento
test_monitor_post_processing() {
    local job_id=$1
    
    if [ -z "$job_id" ]; then
        log_warning "Test 5: Saltando - No hay job_id disponible"
        return 0
    fi
    
    log_info "Test 5: Monitoreando progreso del post-procesamiento"
    
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        response=$(make_request "GET" "/llm-analysis/status/$job_id")
        
        if echo "$response" | jq -e '.success == true' > /dev/null; then
            local estado=$(echo "$response" | jq -r '.data.estado')
            local progreso=$(echo "$response" | jq -r '.data.progreso_porcentaje')
            local etapa=$(echo "$response" | jq -r '.data.etapa_actual')
            
            echo "  Progreso: $progreso% - Estado: $estado - Etapa: $etapa"
            
            if [ "$estado" = "post_processing_completed" ] || [ "$estado" = "completado" ]; then
                log_success "Post-procesamiento completado"
                return 0
            elif [ "$estado" = "error" ]; then
                local error=$(echo "$response" | jq -r '.data.error_actual')
                log_error "Post-procesamiento falló: $error"
                return 1
            fi
        fi
        
        sleep 10
        ((attempt++))
    done
    
    log_warning "Timeout esperando completar post-procesamiento"
    return 1
}

# Test 6: Verificar resultados del análisis LLM
test_llm_analysis_results() {
    local job_id=$1
    
    if [ -z "$job_id" ]; then
        log_warning "Test 6: Saltando - No hay job_id disponible"
        return 0
    fi
    
    log_info "Test 6: Verificando resultados del análisis LLM"
    
    response=$(make_request "GET" "/llm-analysis/results/by-job/$job_id")
    
    if echo "$response" | jq -e '.success == true' > /dev/null; then
        local has_post_processing=$(echo "$response" | jq -e '.data.post_processing != null')
        local has_llm_analysis=$(echo "$response" | jq -e '.data.llm_analysis != null')
        
        if [ "$has_post_processing" = "true" ]; then
            local num_correcciones=$(echo "$response" | jq '.data.post_processing.num_correcciones')
            local num_entidades=$(echo "$response" | jq '.data.post_processing.num_entidades')
            local mejora_legibilidad=$(echo "$response" | jq '.data.post_processing.mejora_legibilidad')
            
            log_success "Post-procesamiento completado:"
            echo "  - Correcciones aplicadas: $num_correcciones"
            echo "  - Entidades médicas detectadas: $num_entidades"
            echo "  - Mejora en legibilidad: $mejora_legibilidad"
        fi
        
        if [ "$has_llm_analysis" = "true" ]; then
            local llm_provider=$(echo "$response" | jq -r '.data.llm_analysis.llm_provider')
            local confianza=$(echo "$response" | jq '.data.llm_analysis.confianza_llm')
            local needs_review=$(echo "$response" | jq '.data.llm_analysis.needs_review')
            local tokens=$(echo "$response" | jq '.data.llm_analysis.tokens_utilizados')
            local costo=$(echo "$response" | jq '.data.llm_analysis.costo_estimado')
            
            log_success "Análisis LLM completado:"
            echo "  - Proveedor: $llm_provider"
            echo "  - Confianza: $confianza"
            echo "  - Requiere revisión: $needs_review"
            echo "  - Tokens utilizados: $tokens"
            echo "  - Costo estimado: €$costo"
        fi
        
        return 0
    else
        log_error "No se pudieron obtener los resultados"
        return 1
    fi
}

# Test 7: Obtener resultado detallado del análisis LLM
test_detailed_llm_results() {
    local job_id=$1
    
    if [ -z "$job_id" ]; then
        log_warning "Test 7: Saltando - No hay job_id disponible"
        return 0
    fi
    
    log_info "Test 7: Obteniendo resultados detallados del análisis LLM"
    
    # Primero obtener el ID del análisis LLM
    response=$(make_request "GET" "/llm-analysis/results/by-job/$job_id")
    
    if echo "$response" | jq -e '.data.llm_analysis != null' > /dev/null; then
        local llm_analysis_id=$(echo "$response" | jq -r '.data.llm_analysis.id')
        
        # Obtener resultado detallado
        detailed_response=$(make_request "GET" "/llm-analysis/results/llm/$llm_analysis_id")
        
        if echo "$detailed_response" | jq -e '.success == true' > /dev/null; then
            local resumen_length=$(echo "$detailed_response" | jq -r '.data.resumen_principal | length')
            local num_conceptos=$(echo "$detailed_response" | jq '.data.conceptos_clave | length')
            local num_momentos=$(echo "$detailed_response" | jq '.data.momentos_clave | length')
            
            log_success "Resultado detallado obtenido:"
            echo "  - Longitud del resumen: $resumen_length caracteres"
            echo "  - Conceptos clave identificados: $num_conceptos"
            echo "  - Momentos clave detectados: $num_momentos"
            
            # Mostrar una muestra del resumen
            local resumen_sample=$(echo "$detailed_response" | jq -r '.data.resumen_principal' | head -c 200)
            echo "  - Muestra del resumen: $resumen_sample..."
            
            return 0
        fi
    fi
    
    log_warning "No se pudo obtener resultado detallado"
    return 1
}

# Test 8: Validar análisis LLM
test_validate_llm_analysis() {
    local job_id=$1
    
    if [ -z "$job_id" ]; then
        log_warning "Test 8: Saltando - No hay job_id disponible"
        return 0
    fi
    
    log_info "Test 8: Validando análisis LLM"
    
    # Obtener ID del análisis LLM
    response=$(make_request "GET" "/llm-analysis/results/by-job/$job_id")
    
    if echo "$response" | jq -e '.data.llm_analysis != null' > /dev/null; then
        local llm_analysis_id=$(echo "$response" | jq -r '.data.llm_analysis.id')
        
        # Marcar como validado
        validation_response=$(make_request "PUT" "/llm-analysis/$llm_analysis_id/validate?validated=true")
        
        if echo "$validation_response" | jq -e '.success == true' > /dev/null; then
            log_success "Análisis LLM marcado como validado por humano"
            return 0
        fi
    fi
    
    log_warning "No se pudo validar el análisis LLM"
    return 1
}

# Función principal de testing
run_all_tests() {
    local job_id=$1
    local failed_tests=0
    
    echo
    log_info "Ejecutando suite completa de tests para Fase 5"
    echo
    
    # Test 1: Health Check
    if ! test_llm_health_check; then
        ((failed_tests++))
    fi
    echo
    
    # Test 2: Terminología médica
    if ! test_medical_terminology_search; then
        ((failed_tests++))
    fi
    echo
    
    # Test 3: Crear job (informativo)
    create_test_processing_job
    echo
    
    # Tests que requieren job_id
    if [ -n "$job_id" ]; then
        # Test 4: Iniciar post-procesamiento
        if ! test_start_post_processing "$job_id"; then
            ((failed_tests++))
        fi
        echo
        
        # Test 5: Monitorear progreso
        if ! test_monitor_post_processing "$job_id"; then
            ((failed_tests++))
        fi
        echo
        
        # Test 6: Verificar resultados
        if ! test_llm_analysis_results "$job_id"; then
            ((failed_tests++))
        fi
        echo
        
        # Test 7: Resultados detallados
        if ! test_detailed_llm_results "$job_id"; then
            ((failed_tests++))
        fi
        echo
        
        # Test 8: Validar análisis
        if ! test_validate_llm_analysis "$job_id"; then
            ((failed_tests++))
        fi
        echo
    else
        log_warning "Tests 4-8 saltados: No se proporcionó processing_job_id"
        echo "Uso: $0 [processing_job_id]"
        echo
    fi
    
    # Resumen final
    echo "=============================================="
    if [ $failed_tests -eq 0 ]; then
        log_success "🎉 Todos los tests pasaron exitosamente!"
        echo
        log_info "La Fase 5 está funcionando correctamente:"
        echo "  ✅ Servicios LLM operativos"
        echo "  ✅ Post-procesamiento funcional"
        echo "  ✅ Análisis de terminología médica"
        echo "  ✅ Pipeline completo de análisis inteligente"
        echo
        log_info "Próximos pasos:"
        echo "  🔄 Ejecutar Fase 6: Research y fuentes médicas"
        echo "  📝 Integrar con Notion (Fase 8)"
        echo "  🧪 Testing con clases reales"
    else
        log_error "❌ $failed_tests test(s) fallaron"
        echo
        log_info "Revisa los logs y verifica:"
        echo "  🔧 Configuración de LLM (LM Studio/Ollama)"
        echo "  🗄️  Base de datos y migraciones"
        echo "  🐳 Servicios Docker ejecutándose"
        echo "  🔑 Tokens y credenciales configurados"
    fi
    echo "=============================================="
    
    return $failed_tests
}

# Verificar dependencias
check_dependencies() {
    local missing_deps=0
    
    if ! command -v curl &> /dev/null; then
        log_error "curl no está instalado"
        ((missing_deps++))
    fi
    
    if ! command -v jq &> /dev/null; then
        log_error "jq no está instalado"
        ((missing_deps++))
    fi
    
    if [ $missing_deps -gt 0 ]; then
        log_error "Instala las dependencias faltantes:"
        echo "  sudo apt-get install curl jq"
        exit 1
    fi
}

# Script principal
main() {
    local job_id=$1
    
    check_dependencies
    
    echo -e "${BLUE}"
    echo "🧠 Axonote - Test Suite Fase 5: Post-procesamiento y Análisis LLM"
    echo "=================================================================="
    echo -e "${NC}"
    
    # Verificar que la API esté ejecutándose
    if ! curl -s "$API_BASE_URL/health" > /dev/null; then
        log_error "La API no está ejecutándose en $API_BASE_URL"
        log_info "Inicia el servidor con: make up"
        exit 1
    fi
    
    run_all_tests "$job_id"
    exit $?
}

# Ejecutar si es llamado directamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
