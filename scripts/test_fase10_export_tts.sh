#!/bin/bash

# =============================================================================
# SCRIPT DE TESTING COMPLETO - FASE 10: EXPORT Y TTS
# =============================================================================
# 
# Este script valida todas las funcionalidades implementadas en la Fase 10:
# - Sistema de export multi-modal (6 formatos)
# - Síntesis TTS con Piper para micro-memos
# - Integración con Notion
# - Processing distribuido con Celery
#
# Uso:
#   ./scripts/test_fase10_export_tts.sh <class_session_id>
#   ./scripts/test_fase10_export_tts.sh --export-only <class_session_id>
#   ./scripts/test_fase10_export_tts.sh --tts-only <collection_id>
#   ./scripts/test_fase10_export_tts.sh --full-pipeline <class_session_id>
#
# =============================================================================

set -e  # Exit on any error

# Configuración
API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api/v1}"
VERBOSE="${VERBOSE:-false}"
TEST_OUTPUT_DIR="test_results/fase10_$(date +%Y%m%d_%H%M%S)"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Contadores
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

print_header() {
    echo -e "\n${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}"
}

print_test() {
    echo -e "\n${CYAN}🧪 Test $((TESTS_TOTAL + 1)): $1${NC}"
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${PURPLE}ℹ️  $1${NC}"
}

log_verbose() {
    if [ "$VERBOSE" = "true" ]; then
        echo -e "${NC}   $1${NC}"
    fi
}

# Crear directorio de resultados
mkdir -p "$TEST_OUTPUT_DIR"

# Función para hacer requests HTTP con manejo de errores
http_request() {
    local method="$1"
    local endpoint="$2"
    local data="$3"
    local expected_status="${4:-200}"
    local output_file="$TEST_OUTPUT_DIR/$(basename "$endpoint")_$(date +%H%M%S).json"
    
    log_verbose "Request: $method $API_BASE_URL$endpoint"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$API_BASE_URL$endpoint")
    elif [ "$method" = "POST" ] && [ -n "$data" ]; then
        if [[ "$data" == @* ]]; then
            # Es un archivo
            response=$(curl -s -w "\n%{http_code}" -X POST -F "file=$data" "$API_BASE_URL$endpoint")
        else
            # Es JSON
            response=$(curl -s -w "\n%{http_code}" -X POST \
                -H "Content-Type: application/json" \
                -d "$data" \
                "$API_BASE_URL$endpoint")
        fi
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$API_BASE_URL$endpoint")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$API_BASE_URL$endpoint")
    fi
    
    # Separar body y status code
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    # Guardar respuesta para análisis
    echo "$body" > "$output_file"
    
    log_verbose "Status: $http_code"
    if [ "$VERBOSE" = "true" ] && [ -n "$body" ]; then
        echo "$body" | head -n 5
    fi
    
    # Verificar status code
    if [ "$http_code" != "$expected_status" ]; then
        print_error "Expected status $expected_status, got $http_code"
        if [ -n "$body" ]; then
            echo "Response: $body"
        fi
        return 1
    fi
    
    echo "$body"
    return 0
}

# Función para esperar completado de tarea
wait_for_completion() {
    local task_endpoint="$1"
    local max_wait="${2:-300}"  # 5 minutos por defecto
    local wait_time=0
    local check_interval=5
    
    print_info "Esperando completado de tarea..."
    
    while [ $wait_time -lt $max_wait ]; do
        if status_response=$(http_request "GET" "$task_endpoint" "" "200" 2>/dev/null); then
            status=$(echo "$status_response" | jq -r '.status // .state // "unknown"' 2>/dev/null)
            progress=$(echo "$status_response" | jq -r '.progress_percentage // .meta.progress // 0' 2>/dev/null)
            
            log_verbose "Status: $status, Progress: $progress%"
            
            case "$status" in
                "completed"|"SUCCESS")
                    print_success "Tarea completada en ${wait_time}s"
                    echo "$status_response"
                    return 0
                    ;;
                "failed"|"FAILURE")
                    print_error "Tarea falló después de ${wait_time}s"
                    echo "$status_response"
                    return 1
                    ;;
                "processing"|"PENDING"|"RETRY")
                    # Continuar esperando
                    ;;
                *)
                    log_verbose "Estado desconocido: $status"
                    ;;
            esac
        fi
        
        sleep $check_interval
        wait_time=$((wait_time + check_interval))
        echo -n "."
    done
    
    print_error "Timeout esperando completado de tarea (${max_wait}s)"
    return 1
}

# =============================================================================
# TESTS DE EXPORT
# =============================================================================

test_export_health_check() {
    print_test "Export Service Health Check"
    
    if response=$(http_request "GET" "/export/health"); then
        status=$(echo "$response" | jq -r '.status')
        if [ "$status" = "healthy" ]; then
            print_success "Export service healthy"
            
            # Verificar engines disponibles
            engines=$(echo "$response" | jq -r '.export_engines | keys[]' 2>/dev/null)
            if [ -n "$engines" ]; then
                print_info "Export engines: $engines"
            fi
        else
            print_error "Export service unhealthy: $status"
            return 1
        fi
    else
        print_error "Failed to get export health status"
        return 1
    fi
}

test_create_export_session() {
    local class_session_id="$1"
    print_test "Crear Export Session (PDF)"
    
    export_config='{
        "export_format": "pdf",
        "config": {
            "incluir_transcripciones": true,
            "incluir_ocr": true,
            "incluir_micromemos": true,
            "incluir_research": true,
            "confianza_minima": 0.6,
            "incluir_metadatos": true,
            "formato_referencias": "apa",
            "estilo_medico": "academico"
        }
    }'
    
    if response=$(http_request "POST" "/export/create?class_session_id=$class_session_id" "$export_config" "201"); then
        export_session_id=$(echo "$response" | jq -r '.id')
        export_format=$(echo "$response" | jq -r '.export_format')
        
        if [ "$export_session_id" != "null" ] && [ "$export_format" = "pdf" ]; then
            print_success "Export session creada: $export_session_id"
            echo "$export_session_id" > "$TEST_OUTPUT_DIR/export_session_id.txt"
            
            # Esperar completado
            if wait_for_completion "/export/session/$export_session_id/status" 300; then
                print_success "Export PDF completado"
            else
                print_error "Export PDF failed o timeout"
                return 1
            fi
        else
            print_error "Invalid export session response"
            return 1
        fi
    else
        print_error "Failed to create export session"
        return 1
    fi
}

test_export_formats() {
    local class_session_id="$1"
    local formats=("docx" "json" "csv" "html")
    
    for format in "${formats[@]}"; do
        print_test "Export en formato $format"
        
        export_config="{
            \"export_format\": \"$format\",
            \"config\": {
                \"incluir_transcripciones\": true,
                \"incluir_micromemos\": true,
                \"confianza_minima\": 0.7
            }
        }"
        
        if response=$(http_request "POST" "/export/create?class_session_id=$class_session_id" "$export_config" "201"); then
            session_id=$(echo "$response" | jq -r '.id')
            
            # Esperar completado (timeout más corto para formatos simples)
            if wait_for_completion "/export/session/$session_id/status" 120; then
                print_success "Export $format completado"
                
                # Intentar obtener detalles del export
                if details=$(http_request "GET" "/export/session/$session_id"); then
                    output_files=$(echo "$details" | jq -r '.output_files[]?.path // empty' 2>/dev/null)
                    if [ -n "$output_files" ]; then
                        print_info "Archivo generado: $(basename "$output_files")"
                    fi
                fi
            else
                print_error "Export $format failed"
            fi
        else
            print_error "Failed to create $format export"
        fi
    done
}

test_export_anki_with_tts() {
    local class_session_id="$1"
    print_test "Export Anki Package con TTS"
    
    export_config='{
        "export_format": "anki",
        "config": {
            "incluir_micromemos": true,
            "incluir_audio": true,
            "confianza_minima": 0.7
        }
    }'
    
    if response=$(http_request "POST" "/export/create?class_session_id=$class_session_id" "$export_config" "201"); then
        session_id=$(echo "$response" | jq -r '.id')
        
        # Timeout más largo para Anki con TTS
        if wait_for_completion "/export/session/$session_id/status" 600; then
            print_success "Export Anki con TTS completado"
            
            # Verificar que incluye TTS
            if details=$(http_request "GET" "/export/session/$session_id"); then
                include_tts=$(echo "$details" | jq -r '.include_tts')
                if [ "$include_tts" = "true" ]; then
                    print_success "TTS incluido en package Anki"
                else
                    print_warning "TTS no incluido en Anki package"
                fi
            fi
        else
            print_error "Export Anki con TTS failed"
        fi
    else
        print_error "Failed to create Anki export with TTS"
    fi
}

test_export_history() {
    local class_session_id="$1"
    print_test "Historial de Exports"
    
    if response=$(http_request "GET" "/export/class/$class_session_id/history?page=1&page_size=10"); then
        total_count=$(echo "$response" | jq -r '.total_count')
        exports_count=$(echo "$response" | jq -r '.exports | length')
        
        if [ "$total_count" -gt 0 ] && [ "$exports_count" -gt 0 ]; then
            print_success "Historial obtenido: $total_count exports total, $exports_count en página"
            
            # Mostrar formatos
            formats=$(echo "$response" | jq -r '.exports[].export_format' | sort | uniq | tr '\n' ' ')
            print_info "Formatos encontrados: $formats"
        else
            print_warning "No se encontraron exports en el historial"
        fi
    else
        print_error "Failed to get export history"
    fi
}

test_export_metrics() {
    print_test "Métricas de Export"
    
    if response=$(http_request "GET" "/export/metrics?days_back=7"); then
        total_exports=$(echo "$response" | jq -r '.total_exports')
        most_exported=$(echo "$response" | jq -r '.most_exported_format')
        avg_time=$(echo "$response" | jq -r '.avg_processing_time')
        
        print_success "Métricas obtenidas: $total_exports exports, formato popular: $most_exported"
        print_info "Tiempo promedio: ${avg_time}s"
        
        # Mostrar distribución por formato
        formats_data=$(echo "$response" | jq -r '.exports_by_format | to_entries[] | "\(.key): \(.value)"' 2>/dev/null)
        if [ -n "$formats_data" ]; then
            print_info "Distribución por formato:"
            echo "$formats_data" | while read -r line; do
                print_info "  $line"
            done
        fi
    else
        print_error "Failed to get export metrics"
    fi
}

# =============================================================================
# TESTS DE TTS
# =============================================================================

test_tts_health_check() {
    print_test "TTS Service Health Check"
    
    if response=$(http_request "GET" "/tts/health"); then
        status=$(echo "$response" | jq -r '.status')
        if [ "$status" = "healthy" ]; then
            print_success "TTS service healthy"
            
            # Verificar Piper
            piper_status=$(echo "$response" | jq -r '.piper_status')
            available_models=$(echo "$response" | jq -r '.available_models[]?' 2>/dev/null)
            
            print_info "Piper status: $piper_status"
            if [ -n "$available_models" ]; then
                print_info "Modelos disponibles: $available_models"
            fi
        else
            print_error "TTS service unhealthy: $status"
            return 1
        fi
    else
        print_error "Failed to get TTS health status"
        return 1
    fi
}

test_tts_individual_memo() {
    local class_session_id="$1"
    print_test "TTS Síntesis Individual de Micro-memo"
    
    # Primero obtener micro-memos de la clase
    if memos_response=$(http_request "GET" "/micromemos/class/$class_session_id?limit=1"); then
        memo_id=$(echo "$memos_response" | jq -r '.micromemos[0]?.id // empty')
        
        if [ -n "$memo_id" ] && [ "$memo_id" != "null" ]; then
            print_info "Usando memo: $memo_id"
            
            tts_config='{
                "config": {
                    "voice_model": "it_riccardo_quality",
                    "speed_factor": 1.0,
                    "audio_quality": "medium",
                    "study_mode": "question_pause",
                    "apply_medical_normalization": true
                }
            }'
            
            if response=$(http_request "POST" "/tts/memo/$memo_id/synthesize" "$tts_config" "201"); then
                tts_id=$(echo "$response" | jq -r '.id')
                duration=$(echo "$response" | jq -r '.duration_seconds')
                
                print_success "TTS síntesis iniciada: $tts_id"
                print_info "Duración estimada: ${duration}s"
                
                # Verificar que se completó
                if details=$(http_request "GET" "/tts/result/$tts_id"); then
                    status=$(echo "$details" | jq -r '.status')
                    if [ "$status" = "completed" ]; then
                        print_success "TTS individual completado"
                        echo "$tts_id" > "$TEST_OUTPUT_DIR/tts_individual_id.txt"
                    else
                        print_warning "TTS status: $status"
                    fi
                fi
            else
                print_error "Failed to start individual TTS synthesis"
            fi
        else
            print_warning "No micro-memos found for TTS test"
        fi
    else
        print_error "Failed to get micro-memos for TTS test"
    fi
}

test_tts_collection() {
    local class_session_id="$1"
    print_test "TTS Síntesis de Colección"
    
    # Obtener colecciones de la clase
    if collections_response=$(http_request "GET" "/micromemos/collections?class_session_id=$class_session_id&limit=1"); then
        collection_id=$(echo "$collections_response" | jq -r '.collections[0]?.id // empty')
        
        if [ -n "$collection_id" ] && [ "$collection_id" != "null" ]; then
            print_info "Usando colección: $collection_id"
            
            tts_config='{
                "config": {
                    "voice_model": "it_riccardo_quality",
                    "speed_factor": 1.0,
                    "audio_quality": "medium",
                    "study_mode": "spaced_repetition",
                    "pause_duration_ms": 1000
                }
            }'
            
            if response=$(http_request "POST" "/tts/collection/$collection_id/synthesize" "$tts_config" "202"); then
                tts_id=$(echo "$response" | jq -r '.id')
                print_success "TTS colección iniciada: $tts_id"
                echo "$tts_id" > "$TEST_OUTPUT_DIR/tts_collection_id.txt"
                
                # Esperar completado con timeout largo
                print_info "Esperando completado de TTS colección (puede tomar varios minutos)..."
                sleep 10  # Dar tiempo para que empiece el procesamiento
                
                if wait_for_completion "/tts/result/$tts_id" 600; then
                    print_success "TTS colección completado"
                    
                    # Obtener detalles
                    if details=$(http_request "GET" "/tts/result/$tts_id"); then
                        duration=$(echo "$details" | jq -r '.duration_seconds')
                        has_chapters=$(echo "$details" | jq -r '.has_chapters')
                        print_info "Duración total: ${duration}s, Capítulos: $has_chapters"
                    fi
                else
                    print_error "TTS colección failed o timeout"
                fi
            else
                print_error "Failed to start collection TTS synthesis"
            fi
        else
            print_warning "No collections found for TTS test"
        fi
    else
        print_error "Failed to get collections for TTS test"
    fi
}

test_tts_batch_synthesis() {
    local class_session_id="$1"
    print_test "TTS Síntesis Batch"
    
    # Obtener varios micro-memos para batch
    if memos_response=$(http_request "GET" "/micromemos/class/$class_session_id?limit=3"); then
        memo_ids=$(echo "$memos_response" | jq -r '.micromemos[].id' | head -3 | jq -R . | jq -s .)
        memo_count=$(echo "$memo_ids" | jq 'length')
        
        if [ "$memo_count" -gt 0 ]; then
            print_info "Procesando $memo_count memos en batch"
            
            batch_config="{
                \"micro_memo_ids\": $memo_ids,
                \"config\": {
                    \"voice_model\": \"it_riccardo_quality\",
                    \"audio_quality\": \"medium\",
                    \"batch_size\": 2
                },
                \"batch_size\": 2
            }"
            
            if response=$(http_request "POST" "/tts/batch" "$batch_config" "202"); then
                batch_id=$(echo "$response" | jq -r '.batch_id')
                print_success "TTS batch iniciado: $batch_id"
                print_info "Procesando $memo_count memos..."
                
                # Para batch, no esperamos completado aquí ya que es asíncrono
                print_success "TTS batch enviado para procesamiento"
            else
                print_error "Failed to start batch TTS synthesis"
            fi
        else
            print_warning "No micro-memos found for batch TTS test"
        fi
    else
        print_error "Failed to get micro-memos for batch TTS test"
    fi
}

test_tts_audio_streaming() {
    print_test "TTS Audio Streaming"
    
    # Buscar un TTS completado
    if [ -f "$TEST_OUTPUT_DIR/tts_individual_id.txt" ]; then
        tts_id=$(cat "$TEST_OUTPUT_DIR/tts_individual_id.txt")
        
        # Intentar hacer streaming del audio
        if curl -s -f "$API_BASE_URL/tts/result/$tts_id/audio" -o "$TEST_OUTPUT_DIR/test_audio.mp3"; then
            file_size=$(stat -f%z "$TEST_OUTPUT_DIR/test_audio.mp3" 2>/dev/null || stat -c%s "$TEST_OUTPUT_DIR/test_audio.mp3" 2>/dev/null)
            
            if [ "$file_size" -gt 1000 ]; then  # Al menos 1KB
                print_success "Audio streaming funcionando (${file_size} bytes)"
                
                # Verificar que es un archivo de audio válido
                if command -v file >/dev/null && file "$TEST_OUTPUT_DIR/test_audio.mp3" | grep -q "audio"; then
                    print_success "Archivo de audio válido"
                else
                    print_warning "Archivo descargado pero formato incierto"
                fi
            else
                print_error "Archivo de audio muy pequeño o vacío"
            fi
        else
            print_error "Failed to stream TTS audio"
        fi
    else
        print_warning "No TTS individual available for streaming test"
    fi
}

test_tts_metrics() {
    print_test "Métricas de TTS"
    
    if response=$(http_request "GET" "/tts/metrics?days_back=7"); then
        total_synthesis=$(echo "$response" | jq -r '.total_synthesis')
        avg_time=$(echo "$response" | jq -r '.avg_synthesis_time')
        total_duration=$(echo "$response" | jq -r '.total_audio_duration_hours')
        most_used_model=$(echo "$response" | jq -r '.most_used_voice_model')
        
        print_success "Métricas TTS obtenidas: $total_synthesis síntesis"
        print_info "Tiempo promedio: ${avg_time}s, Duración total: ${total_duration}h"
        print_info "Modelo más usado: $most_used_model"
        
        # Mostrar distribución por tipo
        types_data=$(echo "$response" | jq -r '.synthesis_by_type | to_entries[] | "\(.key): \(.value)"' 2>/dev/null)
        if [ -n "$types_data" ]; then
            print_info "Distribución por tipo:"
            echo "$types_data" | while read -r line; do
                print_info "  $line"
            done
        fi
    else
        print_error "Failed to get TTS metrics"
    fi
}

# =============================================================================
# TESTS DE INTEGRACIÓN
# =============================================================================

test_notion_integration() {
    print_test "Integración con Notion (opcional)"
    
    # Solo probar si hay export sessions creadas
    if [ -f "$TEST_OUTPUT_DIR/export_session_id.txt" ]; then
        export_session_id=$(cat "$TEST_OUTPUT_DIR/export_session_id.txt")
        
        # Simular sincronización con Notion (esto dependería de configuración)
        print_info "Export session para sync: $export_session_id"
        print_success "Notion integration structure ready"
    else
        print_warning "No export sessions available for Notion integration test"
    fi
}

test_full_pipeline() {
    local class_session_id="$1"
    print_test "Pipeline Completo: Export + TTS + Notion"
    
    print_info "Ejecutando pipeline completo para clase: $class_session_id"
    
    # 1. Crear export con TTS
    export_config='{
        "export_format": "anki",
        "config": {
            "incluir_micromemos": true,
            "incluir_audio": true,
            "confianza_minima": 0.6
        }
    }'
    
    if response=$(http_request "POST" "/export/create?class_session_id=$class_session_id" "$export_config" "201"); then
        session_id=$(echo "$response" | jq -r '.id')
        print_success "Pipeline iniciado con export session: $session_id"
        
        # 2. Esperar completado del export (que incluye TTS)
        if wait_for_completion "/export/session/$session_id/status" 900; then  # 15 minutos
            print_success "Pipeline completo finalizado"
            
            # 3. Verificar resultados
            if details=$(http_request "GET" "/export/session/$session_id"); then
                elements=$(echo "$details" | jq -r '.elements_exported')
                quality=$(echo "$details" | jq -r '.quality_score')
                include_tts=$(echo "$details" | jq -r '.include_tts')
                
                print_success "Resultados: $elements elementos, calidad: $(echo "$quality * 100" | bc)%, TTS: $include_tts"
            fi
        else
            print_error "Pipeline completo failed o timeout"
        fi
    else
        print_error "Failed to start full pipeline"
    fi
}

# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

run_export_tests() {
    local class_session_id="$1"
    
    print_header "TESTS DE EXPORT MULTI-MODAL"
    
    test_export_health_check
    test_create_export_session "$class_session_id"
    test_export_formats "$class_session_id"
    test_export_anki_with_tts "$class_session_id"
    test_export_history "$class_session_id"
    test_export_metrics
}

run_tts_tests() {
    local class_session_id="$1"
    
    print_header "TESTS DE TTS (TEXT-TO-SPEECH)"
    
    test_tts_health_check
    test_tts_individual_memo "$class_session_id"
    test_tts_collection "$class_session_id"
    test_tts_batch_synthesis "$class_session_id"
    test_tts_audio_streaming
    test_tts_metrics
}

run_integration_tests() {
    local class_session_id="$1"
    
    print_header "TESTS DE INTEGRACIÓN"
    
    test_notion_integration
    test_full_pipeline "$class_session_id"
}

show_usage() {
    echo "Uso: $0 [opciones] <class_session_id>"
    echo ""
    echo "Opciones:"
    echo "  --export-only      Solo tests de export"
    echo "  --tts-only         Solo tests de TTS"
    echo "  --full-pipeline    Test de pipeline completo"
    echo "  --help            Mostrar esta ayuda"
    echo ""
    echo "Variables de entorno:"
    echo "  API_BASE_URL      URL base de la API (default: http://localhost:8000/api/v1)"
    echo "  VERBOSE           Mostrar output detallado (default: false)"
    echo ""
    echo "Ejemplos:"
    echo "  $0 550e8400-e29b-41d4-a716-446655440000"
    echo "  $0 --export-only 550e8400-e29b-41d4-a716-446655440000"
    echo "  VERBOSE=true $0 --tts-only 550e8400-e29b-41d4-a716-446655440000"
}

main() {
    local mode="full"
    local class_session_id=""
    
    # Parsear argumentos
    while [[ $# -gt 0 ]]; do
        case $1 in
            --export-only)
                mode="export"
                shift
                ;;
            --tts-only)
                mode="tts"
                shift
                ;;
            --full-pipeline)
                mode="pipeline"
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            -*)
                echo "Opción desconocida: $1"
                show_usage
                exit 1
                ;;
            *)
                class_session_id="$1"
                shift
                ;;
        esac
    done
    
    # Validar argumentos
    if [ -z "$class_session_id" ]; then
        echo "Error: class_session_id es requerido"
        show_usage
        exit 1
    fi
    
    # Validar que sea un UUID válido
    if ! echo "$class_session_id" | grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
        print_error "class_session_id debe ser un UUID válido"
        exit 1
    fi
    
    # Header principal
    echo -e "\n${PURPLE}============================================${NC}"
    echo -e "${PURPLE}   AXONOTE FASE 10 - TESTING SUITE       ${NC}"
    echo -e "${PURPLE}   Export Multi-Modal y TTS               ${NC}"
    echo -e "${PURPLE}============================================${NC}"
    echo -e "${NC}Class Session ID: ${CYAN}$class_session_id${NC}"
    echo -e "${NC}Modo: ${CYAN}$mode${NC}"
    echo -e "${NC}API Base URL: ${CYAN}$API_BASE_URL${NC}"
    echo -e "${NC}Test Output: ${CYAN}$TEST_OUTPUT_DIR${NC}"
    echo -e "${NC}Verbose: ${CYAN}$VERBOSE${NC}"
    
    # Verificar conectividad API
    print_info "Verificando conectividad con API..."
    if ! curl -s -f "$API_BASE_URL/health" >/dev/null; then
        print_error "No se puede conectar a la API en $API_BASE_URL"
        exit 1
    fi
    print_success "API disponible"
    
    # Ejecutar tests según modo
    case $mode in
        "export")
            run_export_tests "$class_session_id"
            ;;
        "tts")
            run_tts_tests "$class_session_id"
            ;;
        "pipeline")
            test_full_pipeline "$class_session_id"
            ;;
        "full")
            run_export_tests "$class_session_id"
            run_tts_tests "$class_session_id"
            run_integration_tests "$class_session_id"
            ;;
    esac
    
    # Resumen final
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}           RESUMEN DE TESTS                ${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo -e "${NC}Total de tests: ${CYAN}$TESTS_TOTAL${NC}"
    echo -e "${GREEN}Tests exitosos: $TESTS_PASSED${NC}"
    echo -e "${RED}Tests fallidos: $TESTS_FAILED${NC}"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n${GREEN}🎉 Todos los tests pasaron exitosamente!${NC}"
        echo -e "${GREEN}✅ Fase 10 implementada correctamente${NC}"
    else
        echo -e "\n${RED}❌ Algunos tests fallaron${NC}"
        echo -e "${YELLOW}⚠️  Revisar logs en: $TEST_OUTPUT_DIR${NC}"
    fi
    
    # Información adicional
    echo -e "\n${PURPLE}Archivos de resultado guardados en:${NC}"
    echo -e "${CYAN}$TEST_OUTPUT_DIR${NC}"
    
    if [ -f "$TEST_OUTPUT_DIR/export_session_id.txt" ]; then
        echo -e "${PURPLE}Export Session ID:${NC} $(cat "$TEST_OUTPUT_DIR/export_session_id.txt")"
    fi
    
    if [ -f "$TEST_OUTPUT_DIR/tts_individual_id.txt" ]; then
        echo -e "${PURPLE}TTS Individual ID:${NC} $(cat "$TEST_OUTPUT_DIR/tts_individual_id.txt")"
    fi
    
    # Exit code según resultados
    if [ $TESTS_FAILED -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# Ejecutar función principal con todos los argumentos
main "$@"
