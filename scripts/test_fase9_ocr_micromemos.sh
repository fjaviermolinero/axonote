#!/bin/bash

# =============================================================================
# SCRIPT DE TESTING COMPLETO - FASE 9: OCR Y MICRO-MEMOS
# =============================================================================
# Este script valida la implementación completa de OCR y generación de micro-memos
# con pruebas exhaustivas de todos los componentes implementados.
# 
# Uso: ./test_fase9_ocr_micromemos.sh [class_session_id] [--ocr-only] [--micromemos-only] [--file path]
# =============================================================================

set -e  # Exit on any error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuración
API_BASE_URL="http://localhost:8000/api/v1"
TEST_CLASS_SESSION_ID=""
OCR_ONLY=false
MICROMEMOS_ONLY=false
TEST_FILE=""

# Archivos de test por defecto
TEST_FILES_DIR="./test_files"
DEFAULT_PDF="medical_document_sample.pdf"
DEFAULT_IMAGE="medical_slide_sample.png"

# Contadores de tests
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Variables para tracking de IDs
OCR_TASK_ID=""
OCR_RESULT_ID=""
MEMO_TASK_ID=""
COLLECTION_ID=""

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

print_header() {
    echo -e "\n${PURPLE}===============================================${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}===============================================${NC}\n"
}

print_step() {
    echo -e "${CYAN}➤ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
    ((PASSED_TESTS++))
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
    ((FAILED_TESTS++))
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Incrementar contador total
count_test() {
    ((TOTAL_TESTS++))
}

# Función para hacer requests HTTP con manejo de errores
make_request() {
    local method=$1
    local endpoint=$2
    local data=${3:-""}
    local content_type=${4:-"application/json"}
    
    if [ -n "$data" ]; then
        curl -s -X "$method" "$API_BASE_URL$endpoint" \
            -H "Content-Type: $content_type" \
            -d "$data"
    else
        curl -s -X "$method" "$API_BASE_URL$endpoint"
    fi
}

# Función para upload de archivos
upload_file() {
    local file_path=$1
    local class_session_id=$2
    local auto_generate_memos=${3:-true}
    
    curl -s -X POST "$API_BASE_URL/ocr/process" \
        -F "file=@$file_path" \
        -F "class_session_id=$class_session_id" \
        -F "auto_generate_memos=$auto_generate_memos"
}

# Función para esperar completación de tarea
wait_for_task() {
    local task_id=$1
    local endpoint=$2
    local max_wait=${3:-300}  # 5 minutos por defecto
    local wait_time=0
    local interval=5
    
    print_step "Esperando completación de tarea $task_id..."
    
    while [ $wait_time -lt $max_wait ]; do
        local response=$(make_request "GET" "$endpoint/$task_id")
        local status=$(echo "$response" | jq -r '.data.status // "UNKNOWN"')
        local progress=$(echo "$response" | jq -r '.data.progress // 0')
        
        echo -ne "\r${CYAN}Estado: $status - Progreso: $progress%${NC}"
        
        if [ "$status" = "SUCCESS" ]; then
            echo -e "\n${GREEN}✓ Tarea completada exitosamente${NC}"
            echo "$response"
            return 0
        elif [ "$status" = "FAILURE" ]; then
            echo -e "\n${RED}✗ Tarea falló${NC}"
            echo "$response" | jq '.data.error // "Error desconocido"'
            return 1
        fi
        
        sleep $interval
        wait_time=$((wait_time + interval))
    done
    
    echo -e "\n${RED}✗ Timeout esperando tarea${NC}"
    return 1
}

# Validar JSON response
validate_json_response() {
    local response=$1
    local expected_success=${2:-true}
    
    if ! echo "$response" | jq . >/dev/null 2>&1; then
        print_error "Response no es JSON válido"
        echo "Response: $response"
        return 1
    fi
    
    local success=$(echo "$response" | jq -r '.success')
    if [ "$success" != "$expected_success" ]; then
        print_error "Expected success=$expected_success, got success=$success"
        echo "$response" | jq '.message // "No message"'
        return 1
    fi
    
    return 0
}

# Crear archivos de test si no existen
create_test_files() {
    if [ ! -d "$TEST_FILES_DIR" ]; then
        mkdir -p "$TEST_FILES_DIR"
    fi
    
    # Crear PDF de test simple
    if [ ! -f "$TEST_FILES_DIR/$DEFAULT_PDF" ]; then
        print_step "Creando archivo PDF de test..."
        cat > "$TEST_FILES_DIR/test_content.txt" << 'EOF'
DOCUMENTO MÉDICO DE PRUEBA

Paciente: Mario Rossi
Edad: 45 años
Diagnóstico: Hipertensión arterial

Síntomas presentados:
- Cefalea frecuente
- Mareos ocasionales  
- Presión arterial elevada (160/95 mmHg)

Tratamiento prescrito:
- Enalapril 10mg, una vez al día
- Dieta hiposódica
- Ejercicio cardiovascular moderado

Términos médicos relevantes:
- Hipertensión
- Cefalea
- Cardiovascular
- Farmacología
- Patología

Próxima consulta: 15 días
EOF
        
        # Crear PDF simple con pandoc si está disponible
        if command -v pandoc >/dev/null 2>&1; then
            pandoc "$TEST_FILES_DIR/test_content.txt" -o "$TEST_FILES_DIR/$DEFAULT_PDF"
        else
            # Fallback: copiar como texto plano
            cp "$TEST_FILES_DIR/test_content.txt" "$TEST_FILES_DIR/$DEFAULT_PDF"
            print_warning "Pandoc no disponible, usando archivo de texto como PDF"
        fi
    fi
    
    # Crear imagen de test simple (solo si ImageMagick está disponible)
    if [ ! -f "$TEST_FILES_DIR/$DEFAULT_IMAGE" ] && command -v convert >/dev/null 2>&1; then
        print_step "Creando imagen de test..."
        convert -size 800x600 xc:white \
            -pointsize 24 -fill black \
            -annotate +50+100 "SLIDE MÉDICO DE PRUEBA" \
            -annotate +50+200 "Anatomía del sistema cardiovascular" \
            -annotate +50+300 "• Corazón: órgano muscular" \
            -annotate +50+350 "• Arterias: vasos eferentes" \
            -annotate +50+400 "• Venas: vasos aferentes" \
            -annotate +50+500 "Especialidad: Cardiología" \
            "$TEST_FILES_DIR/$DEFAULT_IMAGE"
    fi
}

# =============================================================================
# TESTS ESPECÍFICOS
# =============================================================================

# Test 1: Health Check OCR Service
test_ocr_health_check() {
    print_step "Test 1: Health Check del servicio OCR"
    count_test
    
    local response=$(make_request "GET" "/ocr/health")
    
    if validate_json_response "$response"; then
        local status=$(echo "$response" | jq -r '.data.status')
        if [ "$status" = "healthy" ] || [ "$status" = "initializing" ]; then
            print_success "Servicio OCR operativo (status: $status)"
            
            # Mostrar información adicional
            echo "$response" | jq '.data.tesseract_version // "N/A"' | sed 's/^/"Tesseract version: /'
            echo "$response" | jq '.data.supported_formats[]? // empty' | tr '\n' ',' | sed 's/,$//' | sed 's/^/Formatos soportados: /'
            echo ""
        else
            print_error "Servicio OCR no está saludable: $status"
        fi
    else
        print_error "Health check OCR falló"
    fi
}

# Test 2: Procesamiento OCR de documento
test_ocr_document_processing() {
    print_step "Test 2: Procesamiento OCR de documento"
    count_test
    
    local test_file="$TEST_FILES_DIR/$DEFAULT_PDF"
    if [ -n "$TEST_FILE" ]; then
        test_file="$TEST_FILE"
    fi
    
    if [ ! -f "$test_file" ]; then
        print_error "Archivo de test no encontrado: $test_file"
        return 1
    fi
    
    print_info "Procesando archivo: $(basename "$test_file")"
    
    local response=$(upload_file "$test_file" "$TEST_CLASS_SESSION_ID" true)
    
    if validate_json_response "$response"; then
        OCR_TASK_ID=$(echo "$response" | jq -r '.data.task_id')
        local filename=$(echo "$response" | jq -r '.data.filename')
        local file_size=$(echo "$response" | jq -r '.data.file_size')
        
        print_success "Documento enviado a procesamiento OCR"
        print_info "Task ID: $OCR_TASK_ID"
        print_info "Archivo: $filename ($file_size bytes)"
        
        # Esperar completación
        if wait_for_task "$OCR_TASK_ID" "/ocr/status" 300; then
            local task_response=$(make_request "GET" "/ocr/status/$OCR_TASK_ID")
            OCR_RESULT_ID=$(echo "$task_response" | jq -r '.data.result.ocr_result_id // empty')
            
            if [ -n "$OCR_RESULT_ID" ]; then
                print_success "OCR completado - Result ID: $OCR_RESULT_ID"
                
                # Mostrar métricas
                local confidence=$(echo "$task_response" | jq -r '.data.result.confidence_score // 0')
                local text_length=$(echo "$task_response" | jq -r '.data.result.text_extracted_length // 0')
                local processing_time=$(echo "$task_response" | jq -r '.data.result.processing_time // 0')
                local memos_generated=$(echo "$task_response" | jq -r '.data.result.memos_generated // 0')
                
                print_info "Confianza: ${confidence}"
                print_info "Texto extraído: ${text_length} caracteres"
                print_info "Tiempo procesamiento: ${processing_time}s"
                print_info "Micro-memos generados: ${memos_generated}"
            else
                print_error "No se obtuvo OCR result ID"
            fi
        else
            print_error "Timeout o error en procesamiento OCR"
        fi
    else
        print_error "Error enviando documento a OCR"
    fi
}

# Test 3: Obtener detalles de resultado OCR
test_ocr_result_details() {
    print_step "Test 3: Obtener detalles de resultado OCR"
    count_test
    
    if [ -z "$OCR_RESULT_ID" ]; then
        print_error "No hay OCR Result ID disponible"
        return 1
    fi
    
    local response=$(make_request "GET" "/ocr/result/$OCR_RESULT_ID?include_raw_data=false")
    
    if validate_json_response "$response"; then
        local filename=$(echo "$response" | jq -r '.data.source_filename')
        local content_type=$(echo "$response" | jq -r '.data.content_type')
        local is_medical=$(echo "$response" | jq -r '.data.is_medical_content')
        local terms_count=$(echo "$response" | jq -r '.data.medical_terms_detected | length')
        local related_memos=$(echo "$response" | jq -r '.data.related_memos | length')
        
        print_success "Detalles OCR obtenidos correctamente"
        print_info "Archivo: $filename"
        print_info "Tipo contenido: $content_type"
        print_info "Contenido médico: $is_medical"
        print_info "Términos médicos detectados: $terms_count"
        print_info "Micro-memos relacionados: $related_memos"
        
        # Mostrar algunos términos médicos si existen
        if [ "$terms_count" -gt 0 ]; then
            echo -e "${BLUE}Términos médicos detectados:${NC}"
            echo "$response" | jq -r '.data.medical_terms_detected[]?.term // empty' | head -5 | sed 's/^/  - /'
        fi
    else
        print_error "Error obteniendo detalles OCR"
    fi
}

# Test 4: Health Check Micro-Memos Service
test_micromemos_health_check() {
    print_step "Test 4: Health Check del servicio Micro-Memos"
    count_test
    
    local response=$(make_request "GET" "/micromemos/health")
    
    if validate_json_response "$response"; then
        local status=$(echo "$response" | jq -r '.data.status')
        if [ "$status" = "healthy" ] || [ "$status" = "initializing" ]; then
            print_success "Servicio Micro-Memos operativo (status: $status)"
            
            # Mostrar información adicional
            local templates=$(echo "$response" | jq -r '.data.available_templates | length')
            local languages=$(echo "$response" | jq -r '.data.supported_languages[]?' | tr '\n' ',' | sed 's/,$//')
            
            print_info "Templates disponibles: $templates"
            print_info "Idiomas soportados: $languages"
        else
            print_error "Servicio Micro-Memos no está saludable: $status"
        fi
    else
        print_error "Health check Micro-Memos falló"
    fi
}

# Test 5: Generar micro-memos desde OCR
test_generate_micromemos_from_ocr() {
    print_step "Test 5: Generar micro-memos desde resultado OCR"
    count_test
    
    if [ -z "$OCR_RESULT_ID" ]; then
        print_error "No hay OCR Result ID disponible para generar micro-memos"
        return 1
    fi
    
    local config='{"max_memos_per_concept": 2, "min_confidence_threshold": 0.5, "balance_difficulty": true}'
    local response=$(make_request "POST" "/micromemos/generate/from-source?source_id=$OCR_RESULT_ID&source_type=ocr" "$config")
    
    if validate_json_response "$response"; then
        MEMO_TASK_ID=$(echo "$response" | jq -r '.data.task_id')
        
        print_success "Generación de micro-memos iniciada"
        print_info "Task ID: $MEMO_TASK_ID"
        
        # Esperar completación
        if wait_for_task "$MEMO_TASK_ID" "/micromemos/generate/status" 180; then
            local task_response=$(make_request "GET" "/micromemos/generate/status/$MEMO_TASK_ID")
            local memos_generated=$(echo "$task_response" | jq -r '.data.result.memos_generated // 0')
            local avg_confidence=$(echo "$task_response" | jq -r '.data.result.avg_confidence // 0')
            
            print_success "Micro-memos generados: $memos_generated"
            print_info "Confianza promedio: $avg_confidence"
            
            # Mostrar distribución por dificultad
            echo -e "${BLUE}Distribución por dificultad:${NC}"
            echo "$task_response" | jq -r '.data.result.difficulty_distribution // {}' | jq -r 'to_entries[] | "  \(.key): \(.value)"'
        else
            print_error "Timeout o error en generación de micro-memos"
        fi
    else
        print_error "Error iniciando generación de micro-memos"
    fi
}

# Test 6: Obtener micro-memos de clase
test_get_class_micromemos() {
    print_step "Test 6: Obtener micro-memos de la clase"
    count_test
    
    local response=$(make_request "GET" "/micromemos/class/$TEST_CLASS_SESSION_ID?limit=20")
    
    if validate_json_response "$response"; then
        local total_memos=$(echo "$response" | jq -r '.data.pagination.total')
        local returned_memos=$(echo "$response" | jq -r '.data.pagination.returned')
        
        print_success "Micro-memos de clase obtenidos"
        print_info "Total memos: $total_memos"
        print_info "Memos retornados: $returned_memos"
        
        if [ "$returned_memos" -gt 0 ]; then
            echo -e "${BLUE}Primeros micro-memos:${NC}"
            echo "$response" | jq -r '.data.memos[]? | "  - \(.title // .question[:50])... (\(.memo_type), \(.difficulty_level))"' | head -5
        fi
    else
        print_error "Error obteniendo micro-memos de clase"
    fi
}

# Test 7: Crear colección de micro-memos
test_create_micromemo_collection() {
    print_step "Test 7: Crear colección de micro-memos"
    count_test
    
    local collection_config='{
        "name": "Test Collection - Fase 9",
        "description": "Colección de prueba generada durante test de Fase 9",
        "collection_type": "auto",
        "study_mode": "spaced_repetition",
        "max_memos_per_session": 15,
        "max_session_time": 25,
        "auto_include_new_memos": true
    }'
    
    local response=$(make_request "POST" "/micromemos/collections/create?class_session_id=$TEST_CLASS_SESSION_ID" "$collection_config")
    
    if validate_json_response "$response"; then
        local collection_task_id=$(echo "$response" | jq -r '.data.task_id')
        local collection_name=$(echo "$response" | jq -r '.data.collection_name')
        
        print_success "Creación de colección iniciada"
        print_info "Task ID: $collection_task_id"
        print_info "Nombre: $collection_name"
        
        # Esperar completación
        if wait_for_task "$collection_task_id" "/micromemos/collections/status" 600; then
            local task_response=$(make_request "GET" "/micromemos/collections/status/$collection_task_id")
            COLLECTION_ID=$(echo "$task_response" | jq -r '.data.result.collection_id // empty')
            local total_memos=$(echo "$task_response" | jq -r '.data.result.total_memos // 0')
            local completion_rate=$(echo "$task_response" | jq -r '.data.result.completion_rate // 0')
            
            print_success "Colección creada exitosamente"
            print_info "Collection ID: $COLLECTION_ID"
            print_info "Total memos: $total_memos"
            print_info "Completitud: ${completion_rate}%"
        else
            print_error "Timeout o error en creación de colección"
        fi
    else
        print_error "Error iniciando creación de colección"
    fi
}

# Test 8: Obtener sesión de estudio
test_get_study_session() {
    print_step "Test 8: Obtener sesión de estudio de colección"
    count_test
    
    if [ -z "$COLLECTION_ID" ]; then
        print_error "No hay Collection ID disponible"
        return 1
    fi
    
    local session_request='{"max_memos": 10, "focus_weaknesses": false}'
    local response=$(make_request "POST" "/micromemos/collection/$COLLECTION_ID/study-session" "$session_request")
    
    if validate_json_response "$response"; then
        local collection_name=$(echo "$response" | jq -r '.data.collection_name')
        local total_memos=$(echo "$response" | jq -r '.data.total_memos')
        local estimated_time=$(echo "$response" | jq -r '.data.estimated_time')
        local study_mode=$(echo "$response" | jq -r '.data.study_mode')
        
        print_success "Sesión de estudio preparada"
        print_info "Colección: $collection_name"
        print_info "Memos en sesión: $total_memos"
        print_info "Tiempo estimado: ${estimated_time} minutos"
        print_info "Modo estudio: $study_mode"
        
        if [ "$total_memos" -gt 0 ]; then
            echo -e "${BLUE}Memos en la sesión:${NC}"
            echo "$response" | jq -r '.data.session_memos[]? | "  - \(.question[:60])... (\(.difficulty))"' | head -3
        fi
    else
        print_error "Error obteniendo sesión de estudio"
    fi
}

# Test 9: Métricas OCR
test_ocr_metrics() {
    print_step "Test 9: Métricas del servicio OCR"
    count_test
    
    local response=$(make_request "GET" "/ocr/metrics?days_back=1")
    
    if validate_json_response "$response"; then
        local total_docs=$(echo "$response" | jq -r '.data.total_documents')
        local success_rate=$(echo "$response" | jq -r '.data.success_rate')
        local avg_confidence=$(echo "$response" | jq -r '.data.quality_metrics.avg_confidence // "N/A"')
        local avg_processing_time=$(echo "$response" | jq -r '.data.quality_metrics.avg_processing_time // "N/A"')
        
        print_success "Métricas OCR obtenidas"
        print_info "Documentos procesados: $total_docs"
        print_info "Tasa de éxito: ${success_rate}%"
        print_info "Confianza promedio: $avg_confidence"
        print_info "Tiempo procesamiento promedio: ${avg_processing_time}s"
        
        # Mostrar distribución de contenido
        echo -e "${BLUE}Distribución contenido médico:${NC}"
        local medical=$(echo "$response" | jq -r '.data.medical_content_distribution.medical // 0')
        local non_medical=$(echo "$response" | jq -r '.data.medical_content_distribution.non_medical // 0')
        echo "  Médico: $medical"
        echo "  No médico: $non_medical"
    else
        print_error "Error obteniendo métricas OCR"
    fi
}

# Test 10: Métricas Micro-Memos
test_micromemos_metrics() {
    print_step "Test 10: Métricas del servicio Micro-Memos"
    count_test
    
    local response=$(make_request "GET" "/micromemos/metrics?days_back=1")
    
    if validate_json_response "$response"; then
        local total_memos=$(echo "$response" | jq -r '.data.total_memos')
        local total_collections=$(echo "$response" | jq -r '.data.total_collections')
        local study_rate=$(echo "$response" | jq -r '.data.study_rate')
        local avg_success_rate=$(echo "$response" | jq -r '.data.avg_success_rate // "N/A"')
        
        print_success "Métricas Micro-Memos obtenidas"
        print_info "Total micro-memos: $total_memos"
        print_info "Total colecciones: $total_collections"
        print_info "Tasa de estudio: ${study_rate}%"
        print_info "Tasa éxito promedio: $avg_success_rate"
        
        # Mostrar distribución por tipo
        echo -e "${BLUE}Distribución por tipo:${NC}"
        echo "$response" | jq -r '.data.type_distribution // {} | to_entries[] | "  \(.key): \(.value)"'
    else
        print_error "Error obteniendo métricas Micro-Memos"
    fi
}

# Test 11: Revisiones próximas
test_upcoming_reviews() {
    print_step "Test 11: Revisiones próximas (spaced repetition)"
    count_test
    
    local response=$(make_request "GET" "/micromemos/review/upcoming?days_ahead=7&limit=20")
    
    if validate_json_response "$response"; then
        local total_memos=$(echo "$response" | jq -r '.data.total_memos')
        local date_range_start=$(echo "$response" | jq -r '.data.date_range.start')
        local date_range_end=$(echo "$response" | jq -r '.data.date_range.end')
        
        print_success "Revisiones próximas obtenidas"
        print_info "Memos para revisar: $total_memos"
        print_info "Rango fechas: $date_range_start a $date_range_end"
        
        if [ "$total_memos" -gt 0 ]; then
            echo -e "${BLUE}Revisiones por fecha:${NC}"
            echo "$response" | jq -r '.data.reviews_by_date // {} | to_entries[] | "  \(.key): \(.value | length) memos"'
        fi
    else
        print_error "Error obteniendo revisiones próximas"
    fi
}

# Test 12: Integración Notion (si está configurado)
test_notion_integration() {
    print_step "Test 12: Integración con Notion (opcional)"
    count_test
    
    # Verificar si Notion está configurado
    local notion_health=$(make_request "GET" "/notion/health")
    local notion_status=$(echo "$notion_health" | jq -r '.data.status // "not_configured"')
    
    if [ "$notion_status" = "not_configured" ] || [ "$notion_status" = "error" ]; then
        print_warning "Notion no configurado o no disponible - Test saltado"
        return 0
    fi
    
    # Test sincronización OCR
    if [ -n "$OCR_RESULT_ID" ]; then
        print_info "Intentando sincronizar contenido OCR con Notion..."
        # Este endpoint podría no existir aún, es conceptual
        local sync_response=$(make_request "POST" "/notion/sync/ocr/$OCR_RESULT_ID" "{}")
        if validate_json_response "$sync_response" true; then
            print_success "Contenido OCR sincronizado con Notion"
        else
            print_warning "Sincronización OCR con Notion no disponible"
        fi
    fi
    
    # Test sincronización colección
    if [ -n "$COLLECTION_ID" ]; then
        print_info "Intentando sincronizar colección con Notion..."
        # Este endpoint podría no existir aún, es conceptual
        local collection_sync=$(make_request "POST" "/notion/sync/collection/$COLLECTION_ID" "{}")
        if validate_json_response "$collection_sync" true; then
            print_success "Colección sincronizada con Notion"
        else
            print_warning "Sincronización colección con Notion no disponible"
        fi
    fi
}

# =============================================================================
# FUNCIÓN PRINCIPAL DE TESTING
# =============================================================================

run_all_tests() {
    print_header "TESTING FASE 9: OCR Y MICRO-MEMOS"
    
    # Mostrar configuración del test
    print_info "API Base URL: $API_BASE_URL"
    print_info "Class Session ID: $TEST_CLASS_SESSION_ID"
    if [ -n "$TEST_FILE" ]; then
        print_info "Archivo de test: $TEST_FILE"
    fi
    if [ "$OCR_ONLY" = true ]; then
        print_info "Modo: Solo tests OCR"
    elif [ "$MICROMEMOS_ONLY" = true ]; then
        print_info "Modo: Solo tests Micro-Memos"
    fi
    echo ""
    
    # Crear archivos de test si es necesario
    create_test_files
    
    # Ejecutar tests según configuración
    if [ "$MICROMEMOS_ONLY" != true ]; then
        test_ocr_health_check
        test_ocr_document_processing
        test_ocr_result_details
        test_ocr_metrics
    fi
    
    if [ "$OCR_ONLY" != true ]; then
        test_micromemos_health_check
        test_generate_micromemos_from_ocr
        test_get_class_micromemos
        test_create_micromemo_collection
        test_get_study_session
        test_micromemos_metrics
        test_upcoming_reviews
    fi
    
    # Test de integración (siempre ejecutar)
    test_notion_integration
}

# =============================================================================
# FUNCIÓN DE CLEANUP
# =============================================================================

cleanup_test_data() {
    print_header "CLEANUP DE DATOS DE TEST"
    
    # Eliminar resultado OCR si fue creado
    if [ -n "$OCR_RESULT_ID" ]; then
        print_step "Eliminando resultado OCR: $OCR_RESULT_ID"
        local delete_response=$(make_request "DELETE" "/ocr/result/$OCR_RESULT_ID?delete_memos=true")
        if validate_json_response "$delete_response"; then
            print_success "Resultado OCR eliminado"
        else
            print_warning "No se pudo eliminar resultado OCR"
        fi
    fi
    
    # Eliminar colección si fue creada
    if [ -n "$COLLECTION_ID" ]; then
        print_step "Eliminando colección: $COLLECTION_ID"
        local delete_collection=$(make_request "DELETE" "/micromemos/collection/$COLLECTION_ID?delete_memos=false")
        if validate_json_response "$delete_collection"; then
            print_success "Colección eliminada"
        else
            print_warning "No se pudo eliminar colección"
        fi
    fi
    
    print_info "Cleanup completado"
}

# =============================================================================
# FUNCIÓN DE REPORTE FINAL
# =============================================================================

print_final_report() {
    print_header "REPORTE FINAL DE TESTING"
    
    echo -e "${CYAN}Tests ejecutados: $TOTAL_TESTS${NC}"
    echo -e "${GREEN}Tests exitosos: $PASSED_TESTS${NC}"
    echo -e "${RED}Tests fallidos: $FAILED_TESTS${NC}"
    
    local success_rate=0
    if [ $TOTAL_TESTS -gt 0 ]; then
        success_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    fi
    echo -e "${BLUE}Tasa de éxito: ${success_rate}%${NC}"
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "\n${GREEN}🎉 TODOS LOS TESTS PASARON EXITOSAMENTE${NC}"
        echo -e "${GREEN}✅ La Fase 9 está completamente operativa${NC}"
    else
        echo -e "\n${RED}❌ ALGUNOS TESTS FALLARON${NC}"
        echo -e "${YELLOW}⚠ Revisar la implementación antes de pasar a producción${NC}"
    fi
    
    # Información adicional para debugging
    if [ $FAILED_TESTS -gt 0 ]; then
        echo -e "\n${BLUE}Para debugging:${NC}"
        echo "- Verificar logs del servidor: docker logs axonote-api"
        echo "- Verificar configuración en .env"
        echo "- Verificar que Tesseract esté instalado y configurado"
        echo "- Verificar conexión con base de datos y Redis"
    fi
}

# =============================================================================
# PARSING DE ARGUMENTOS Y EJECUCIÓN PRINCIPAL
# =============================================================================

# Parsing de argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --ocr-only)
            OCR_ONLY=true
            shift
            ;;
        --micromemos-only)
            MICROMEMOS_ONLY=true
            shift
            ;;
        --file)
            TEST_FILE="$2"
            shift 2
            ;;
        --help|-h)
            echo "Uso: $0 [class_session_id] [opciones]"
            echo ""
            echo "Opciones:"
            echo "  --ocr-only              Solo ejecutar tests de OCR"
            echo "  --micromemos-only       Solo ejecutar tests de Micro-Memos"
            echo "  --file <path>           Usar archivo específico para test OCR"
            echo "  --help, -h              Mostrar esta ayuda"
            echo ""
            echo "Ejemplos:"
            echo "  $0 123e4567-e89b-12d3-a456-426614174000"
            echo "  $0 123e4567-e89b-12d3-a456-426614174000 --file ./my_document.pdf"
            echo "  $0 --ocr-only --file ./test.pdf"
            exit 0
            ;;
        *)
            if [ -z "$TEST_CLASS_SESSION_ID" ]; then
                TEST_CLASS_SESSION_ID=$1
            else
                echo "Argumento desconocido: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Validar class_session_id si es requerido
if [ -z "$TEST_CLASS_SESSION_ID" ] && [ "$MICROMEMOS_ONLY" != true ]; then
    echo -e "${RED}Error: class_session_id es requerido${NC}"
    echo "Uso: $0 <class_session_id> [opciones]"
    echo "Usar --help para más información"
    exit 1
fi

# Verificar que el servidor esté disponible
print_step "Verificando disponibilidad del servidor..."
if ! curl -s "$API_BASE_URL/health/simple" > /dev/null; then
    echo -e "${RED}Error: Servidor no disponible en $API_BASE_URL${NC}"
    echo "Asegúrate de que el servidor esté ejecutándose"
    exit 1
fi
print_success "Servidor disponible"

# Ejecutar tests
echo -e "${CYAN}Iniciando tests de Fase 9...${NC}\n"
run_all_tests

# Cleanup (comentado por defecto para permitir inspección manual)
# cleanup_test_data

# Reporte final
print_final_report

# Exit con código apropiado
if [ $FAILED_TESTS -eq 0 ]; then
    exit 0
else
    exit 1
fi
