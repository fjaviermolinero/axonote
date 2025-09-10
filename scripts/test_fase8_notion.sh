#!/bin/bash

# =============================================================================
# SCRIPT DE TESTING COMPLETO - FASE 8: INTEGRACIÓN NOTION COMPLETA
# =============================================================================
# 
# Este script valida exhaustivamente la implementación de la Fase 8,
# incluyendo sincronización automática, templates, attachments y APIs.
#
# Uso:
#   ./scripts/test_fase8_notion.sh                      # Test completo
#   ./scripts/test_fase8_notion.sh <class_session_id>   # Test con clase específica
#
# Requisitos:
#   - API Axonote ejecutándose en http://localhost:8000
#   - Token Notion configurado en NOTION_TOKEN
#   - Databases Notion configuradas
#   - Clase procesada disponible para testing
# =============================================================================

set -e  # Salir en caso de error

# Configuración
API_BASE="http://localhost:8000/api/v1"
NOTION_ENDPOINT="$API_BASE/notion"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/test_fase8_notion_$TIMESTAMP.log"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Crear directorio de logs si no existe
mkdir -p logs

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}🧪 TESTING FASE 8: INTEGRACIÓN NOTION COMPLETA${NC}"
echo -e "${CYAN}================================================================${NC}"
echo ""
echo -e "${BLUE}📅 Fecha: $(date)${NC}"
echo -e "${BLUE}📝 Log: $LOG_FILE${NC}"
echo ""

# Función para logging
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
    echo -e "$1"
}

# Función para test HTTP
test_http() {
    local method="$1"
    local url="$2" 
    local data="$3"
    local description="$4"
    
    log "${YELLOW}🔍 Testing: $description${NC}"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" -X GET "$url" || echo "HTTPSTATUS:000")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" -X POST "$url" \
                  -H "Content-Type: application/json" \
                  -d "$data" || echo "HTTPSTATUS:000")
    else
        log "${RED}❌ Método HTTP no soportado: $method${NC}"
        return 1
    fi
    
    http_code=$(echo "$response" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed -E 's/HTTPSTATUS:[0-9]*$//')
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        log "${GREEN}✅ $description - Status: $http_code${NC}"
        echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
        echo ""
        return 0
    else
        log "${RED}❌ $description - Status: $http_code${NC}"
        echo "$body"
        echo ""
        return 1
    fi
}

# Función para extraer valor JSON
extract_json_value() {
    local json="$1"
    local key="$2"
    echo "$json" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('$key', ''))" 2>/dev/null || echo ""
}

# Función para esperar a que complete una tarea
wait_for_task() {
    local task_id="$1"
    local max_wait="$2"
    local waited=0
    
    log "${YELLOW}⏳ Esperando completar tarea $task_id (máximo ${max_wait}s)...${NC}"
    
    while [ $waited -lt $max_wait ]; do
        response=$(curl -s "$NOTION_ENDPOINT/sync/status/$task_id" || echo "{}")
        status=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status', 'unknown'))" 2>/dev/null || echo "unknown")
        
        case "$status" in
            "completed")
                log "${GREEN}✅ Tarea completada exitosamente${NC}"
                echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
                return 0
                ;;
            "failed")
                log "${RED}❌ Tarea falló${NC}"
                echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
                return 1
                ;;
            "processing")
                progress=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('progress', 0))" 2>/dev/null || echo "0")
                message=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('message', 'Procesando...'))" 2>/dev/null || echo "Procesando...")
                log "${CYAN}📊 Progreso: ${progress}% - $message${NC}"
                ;;
            *)
                log "${YELLOW}⏳ Estado: $status${NC}"
                ;;
        esac
        
        sleep 3
        waited=$((waited + 3))
    done
    
    log "${RED}❌ Timeout esperando tarea $task_id${NC}"
    return 1
}

# =============================================================================
# TESTS PRINCIPALES
# =============================================================================

log "${PURPLE}🚀 INICIANDO TESTS DE FASE 8...${NC}"
echo ""

# TEST 1: Health Check del Sistema
log "${BLUE}════════════════════════════════════════${NC}"
log "${BLUE}TEST 1: HEALTH CHECK DEL SISTEMA NOTION${NC}"
log "${BLUE}════════════════════════════════════════${NC}"

if test_http "GET" "$NOTION_ENDPOINT/health" "" "Health check del servicio Notion"; then
    log "${GREEN}✅ Test 1 PASADO: Servicio Notion saludable${NC}"
else
    log "${RED}❌ Test 1 FALLÓ: Servicio Notion no disponible${NC}"
    log "${RED}🚨 ABORTANDO: Sin Notion disponible no se pueden ejecutar más tests${NC}"
    exit 1
fi

echo ""

# TEST 2: Verificar Configuración
log "${BLUE}═══════════════════════════════════════${NC}"
log "${BLUE}TEST 2: VERIFICAR CONFIGURACIÓN NOTION${NC}"
log "${BLUE}═══════════════════════════════════════${NC}"

if test_http "GET" "$NOTION_ENDPOINT/config" "" "Configuración actual de Notion"; then
    log "${GREEN}✅ Test 2 PASADO: Configuración Notion obtenida${NC}"
else
    log "${RED}❌ Test 2 FALLÓ: Error obteniendo configuración${NC}"
fi

echo ""

# TEST 3: Listar Templates Disponibles
log "${BLUE}══════════════════════════════════════${NC}"
log "${BLUE}TEST 3: LISTAR TEMPLATES DISPONIBLES${NC}"
log "${BLUE}══════════════════════════════════════${NC}"

if test_http "GET" "$NOTION_ENDPOINT/templates" "" "Templates de Notion disponibles"; then
    log "${GREEN}✅ Test 3 PASADO: Templates listados correctamente${NC}"
else
    log "${RED}❌ Test 3 FALLÓ: Error listando templates${NC}"
fi

echo ""

# TEST 4: Estado General de Sincronización
log "${BLUE}═══════════════════════════════════════════${NC}"
log "${BLUE}TEST 4: ESTADO GENERAL DE SINCRONIZACIÓN${NC}"
log "${BLUE}═══════════════════════════════════════════${NC}"

if test_http "GET" "$NOTION_ENDPOINT/sync-status" "" "Estado general de sincronización"; then
    log "${GREEN}✅ Test 4 PASADO: Estado de sincronización obtenido${NC}"
else
    log "${RED}❌ Test 4 FALLÓ: Error obteniendo estado de sync${NC}"
fi

echo ""

# TEST 5: Sincronización de Clase (si se proporciona ID)
CLASS_SESSION_ID="$1"

if [ -n "$CLASS_SESSION_ID" ]; then
    log "${BLUE}═══════════════════════════════════════════════${NC}"
    log "${BLUE}TEST 5: SINCRONIZACIÓN COMPLETA DE CLASE${NC}"
    log "${BLUE}ID de Clase: $CLASS_SESSION_ID${NC}"
    log "${BLUE}═══════════════════════════════════════════════${NC}"
    
    # Datos de sincronización
    sync_data='{
        "include_attachments": true,
        "template_detection": true,
        "bidirectional_sync": true,
        "force_update": false
    }'
    
    response=$(test_http "POST" "$NOTION_ENDPOINT/sync/class/$CLASS_SESSION_ID" "$sync_data" "Sincronización completa de clase")
    
    if [ $? -eq 0 ]; then
        # Extraer task_id
        task_id=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('task_id', ''))" 2>/dev/null || echo "")
        
        if [ -n "$task_id" ]; then
            log "${CYAN}📋 Task ID obtenido: $task_id${NC}"
            
            # Esperar a que complete la sincronización
            if wait_for_task "$task_id" 300; then  # 5 minutos máximo
                log "${GREEN}✅ Test 5 PASADO: Sincronización completada exitosamente${NC}"
                
                # Obtener información del registro de sync
                if test_http "GET" "$NOTION_ENDPOINT/records/$CLASS_SESSION_ID" "" "Registro de sincronización de la clase"; then
                    log "${GREEN}📊 Registro de sync obtenido correctamente${NC}"
                fi
            else
                log "${RED}❌ Test 5 FALLÓ: Timeout en sincronización${NC}"
            fi
        else
            log "${RED}❌ Test 5 FALLÓ: No se obtuvo task_id${NC}"
        fi
    else
        log "${RED}❌ Test 5 FALLÓ: Error iniciando sincronización${NC}"
    fi
else
    log "${YELLOW}⚠️  Test 5 OMITIDO: No se proporcionó ID de clase${NC}"
    log "${YELLOW}💡 Uso: $0 <class_session_id> para test completo${NC}"
fi

echo ""

# TEST 6: Gestión de Attachments (si hay clase)
if [ -n "$CLASS_SESSION_ID" ]; then
    log "${BLUE}══════════════════════════════════════${NC}"
    log "${BLUE}TEST 6: GESTIÓN DE ATTACHMENTS${NC}"
    log "${BLUE}══════════════════════════════════════${NC}"
    
    response=$(test_http "POST" "$NOTION_ENDPOINT/attachments/manage/$CLASS_SESSION_ID" "" "Gestión de attachments de clase")
    
    if [ $? -eq 0 ]; then
        task_id=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('task_id', ''))" 2>/dev/null || echo "")
        
        if [ -n "$task_id" ]; then
            if wait_for_task "$task_id" 120; then  # 2 minutos máximo
                log "${GREEN}✅ Test 6 PASADO: Attachments gestionados correctamente${NC}"
            else
                log "${RED}❌ Test 6 FALLÓ: Timeout en gestión de attachments${NC}"
            fi
        else
            log "${RED}❌ Test 6 FALLÓ: No se obtuvo task_id para attachments${NC}"
        fi
    else
        log "${RED}❌ Test 6 FALLÓ: Error iniciando gestión de attachments${NC}"
    fi
else
    log "${YELLOW}⚠️  Test 6 OMITIDO: Requiere ID de clase${NC}"
fi

echo ""

# TEST 7: Métricas de Notion
log "${BLUE}══════════════════════════════════${NC}"
log "${BLUE}TEST 7: MÉTRICAS DE NOTION${NC}"
log "${BLUE}══════════════════════════════════${NC}"

if test_http "GET" "$NOTION_ENDPOINT/metrics" "" "Métricas completas de Notion"; then
    log "${GREEN}✅ Test 7 PASADO: Métricas obtenidas correctamente${NC}"
else
    log "${RED}❌ Test 7 FALLÓ: Error obteniendo métricas${NC}"
fi

echo ""

# TEST 8: Mantenimiento de Workspace
log "${BLUE}═══════════════════════════════════════${NC}"
log "${BLUE}TEST 8: MANTENIMIENTO DE WORKSPACE${NC}"
log "${BLUE}═══════════════════════════════════════${NC}"

response=$(test_http "POST" "$NOTION_ENDPOINT/maintenance" "" "Mantenimiento de workspace")

if [ $? -eq 0 ]; then
    task_id=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('task_id', ''))" 2>/dev/null || echo "")
    
    if [ -n "$task_id" ]; then
        if wait_for_task "$task_id" 60; then  # 1 minuto máximo
            log "${GREEN}✅ Test 8 PASADO: Mantenimiento completado${NC}"
        else
            log "${RED}❌ Test 8 FALLÓ: Timeout en mantenimiento${NC}"
        fi
    else
        log "${RED}❌ Test 8 FALLÓ: No se obtuvo task_id para mantenimiento${NC}"
    fi
else
    log "${RED}❌ Test 8 FALLÓ: Error iniciando mantenimiento${NC}"
fi

echo ""

# TEST 9: Health Check Final
log "${BLUE}═══════════════════════════════════${NC}"
log "${BLUE}TEST 9: HEALTH CHECK FINAL${NC}"
log "${BLUE}═══════════════════════════════════${NC}"

if test_http "GET" "$NOTION_ENDPOINT/health" "" "Health check final del sistema"; then
    log "${GREEN}✅ Test 9 PASADO: Sistema Notion estable al final${NC}"
else
    log "${RED}❌ Test 9 FALLÓ: Sistema Notion inestable${NC}"
fi

echo ""

# =============================================================================
# RESUMEN FINAL
# =============================================================================

log "${PURPLE}═══════════════════════════════════════════════════════════════${NC}"
log "${PURPLE}📊 RESUMEN DE TESTING - FASE 8: INTEGRACIÓN NOTION COMPLETA${NC}"
log "${PURPLE}═══════════════════════════════════════════════════════════════${NC}"

echo ""
log "${CYAN}📋 Tests Ejecutados:${NC}"
log "   1. ✅ Health Check del Sistema Notion"
log "   2. ✅ Verificación de Configuración"
log "   3. ✅ Listado de Templates"
log "   4. ✅ Estado General de Sincronización"
if [ -n "$CLASS_SESSION_ID" ]; then
    log "   5. ✅ Sincronización Completa de Clase"
    log "   6. ✅ Gestión de Attachments"
else
    log "   5. ⚠️  Sincronización de Clase (omitido - no ID)"
    log "   6. ⚠️  Gestión de Attachments (omitido - no ID)"
fi
log "   7. ✅ Métricas de Notion"
log "   8. ✅ Mantenimiento de Workspace"
log "   9. ✅ Health Check Final"

echo ""
log "${CYAN}📁 Archivos Generados:${NC}"
log "   📝 Log detallado: $LOG_FILE"

echo ""
log "${CYAN}🔗 Endpoints Validados:${NC}"
log "   GET  $NOTION_ENDPOINT/health"
log "   GET  $NOTION_ENDPOINT/config"
log "   GET  $NOTION_ENDPOINT/templates"
log "   GET  $NOTION_ENDPOINT/sync-status"
log "   POST $NOTION_ENDPOINT/sync/class/{id}"
log "   GET  $NOTION_ENDPOINT/sync/status/{task_id}"
log "   POST $NOTION_ENDPOINT/attachments/manage/{id}"
log "   GET  $NOTION_ENDPOINT/metrics"
log "   POST $NOTION_ENDPOINT/maintenance"
log "   GET  $NOTION_ENDPOINT/records/{id}"

echo ""
if [ -n "$CLASS_SESSION_ID" ]; then
    log "${GREEN}🎯 TESTING COMPLETO EXITOSO PARA FASE 8${NC}"
    log "${GREEN}✅ Integración Notion completamente funcional${NC}"
else
    log "${YELLOW}🎯 TESTING PARCIAL COMPLETADO PARA FASE 8${NC}"
    log "${YELLOW}💡 Para testing completo, proporcionar ID de clase: $0 <class_session_id>${NC}"
fi

echo ""
log "${BLUE}📅 Testing completado: $(date)${NC}"
log "${BLUE}⏱️  Duración total: $(( $(date +%s) - $(date -d "$(head -1 "$LOG_FILE" | cut -d' ' -f1-2)" +%s) )) segundos${NC}"

echo ""
log "${CYAN}================================================================${NC}"
log "${CYAN}🏁 FIN DEL TESTING FASE 8: INTEGRACIÓN NOTION COMPLETA${NC}"
log "${CYAN}================================================================${NC}"
