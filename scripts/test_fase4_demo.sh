#!/bin/bash

# ==============================================================================
# Script de demo y testing para Fase 4 - ASR y Diarización
# ==============================================================================

set -e

echo "🎯 Demo de Fase 4: ASR y Diarización"
echo "======================================"

API_URL="http://localhost:8000"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función para logging con colores
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

# Verificar que el servidor está ejecutándose
echo ""
log_info "Verificando servidor API..."
if ! curl -s "$API_URL/api/v1/health" > /dev/null; then
    log_error "API no disponible en $API_URL"
    log_info "Asegúrate de que el servidor esté ejecutándose:"
    log_info "docker-compose -f docker-compose.dev.yml up -d"
    exit 1
fi
log_success "API disponible"

# Health check de servicios de procesamiento
echo ""
log_info "Verificando servicios de IA..."
HEALTH_RESPONSE=$(curl -s "$API_URL/api/v1/processing/health")
OVERALL_STATUS=$(echo "$HEALTH_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['data']['overall_status'])
except:
    print('error')
")

if [ "$OVERALL_STATUS" = "healthy" ]; then
    log_success "Servicios de IA operativos"
    
    # Mostrar detalles de servicios
    echo "$HEALTH_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    whisper = data['data']['whisper_service']
    diarization = data['data']['diarization_service']
    
    print(f'🎤 Whisper: {whisper[\"status\"]} - {whisper.get(\"modelo_size\", \"unknown\")} - {whisper.get(\"device\", \"unknown\")}')
    print(f'🗣️  Diarización: {diarization[\"status\"]} - {diarization.get(\"device\", \"unknown\")}')
    
    if 'estadisticas' in whisper:
        stats = whisper['estadisticas']
        print(f'📊 Transcripciones completadas: {stats.get(\"transcripciones_completadas\", 0)}')
        print(f'⏱️  Tiempo promedio/min: {stats.get(\"tiempo_promedio_por_minuto\", 0):.1f}s')
except Exception as e:
    print(f'Error parsing health data: {e}')
    "
else
    log_error "Servicios de IA no disponibles"
    log_warning "Verifica configuración de GPU y dependencias ML"
    echo ""
    log_info "Comandos para debug:"
    echo "  ./scripts/install_ml_dependencies.sh"
    echo "  docker logs axonote_worker_dev"
    exit 1
fi

# Listar jobs de procesamiento existentes
echo ""
log_info "Listando jobs de procesamiento recientes..."
JOBS_RESPONSE=$(curl -s "$API_URL/api/v1/processing/list?limit=5")
JOBS_COUNT=$(echo "$JOBS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(len(data['data']['jobs']))
except:
    print('0')
")

if [ "$JOBS_COUNT" -gt 0 ]; then
    log_success "Encontrados $JOBS_COUNT jobs de procesamiento"
    echo "$JOBS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for job in data['data']['jobs']:
        estado = job['estado']
        progreso = job['progreso_porcentaje']
        job_id = job['id'][:8]
        tipo = job['tipo_procesamiento']
        
        status_icon = '✅' if estado == 'completado' else '🔄' if estado == 'procesando' else '⏳' if estado == 'pendiente' else '❌'
        print(f'{status_icon} Job {job_id}: {tipo} - {estado} ({progreso:.1f}%)')
except Exception as e:
    print(f'Error parsing jobs: {e}')
    "
else
    log_info "No hay jobs de procesamiento previos"
fi

# Verificar si hay ClassSessions disponibles para testing
echo ""
log_info "Verificando ClassSessions disponibles..."
# Nota: Este endpoint puede no existir aún, es para futuro reference
# SESSIONS_RESPONSE=$(curl -s "$API_URL/api/v1/recordings?limit=5")

# Demo de inicio de procesamiento (simulado)
echo ""
log_info "Demo de comandos de procesamiento:"
echo ""

log_info "1. Iniciar procesamiento completo:"
echo "curl -X POST \"$API_URL/api/v1/processing/start/uuid-class-session\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{"
echo "    \"tipo_procesamiento\": \"full_pipeline\","
echo "    \"prioridad\": \"high\","
echo "    \"preset_whisper\": \"MEDICAL_HIGH_PRECISION\","
echo "    \"preset_diarizacion\": \"MEDICAL_CLASS_STANDARD\""
echo "  }'"

echo ""
log_info "2. Verificar estado de un job:"
echo "curl \"$API_URL/api/v1/processing/status/uuid-job\""

echo ""
log_info "3. Obtener resultado de transcripción:"
echo "curl \"$API_URL/api/v1/processing/results/transcription/uuid-transcription\""

echo ""
log_info "4. Obtener resultado de diarización:"
echo "curl \"$API_URL/api/v1/processing/results/diarization/uuid-diarization\""

# Verificar configuraciones críticas
echo ""
log_info "Verificando configuración crítica..."

# Verificar HF_TOKEN
if [ -z "$HF_TOKEN" ]; then
    log_warning "HF_TOKEN no configurado - Requerido para diarización"
    log_info "Configurar en .env: HF_TOKEN=hf_tu_token_aqui"
    log_info "Obtener en: https://huggingface.co/settings/tokens"
else
    log_success "HF_TOKEN configurado"
fi

# Verificar GPU
log_info "Verificando GPU CUDA..."
if docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu20.04 nvidia-smi > /dev/null 2>&1; then
    log_success "GPU CUDA disponible"
else
    log_warning "GPU CUDA no disponible - El procesamiento será más lento en CPU"
fi

echo ""
echo "🎯 Demo completado!"
echo ""
log_success "La Fase 4 está operativa y lista para procesar clases médicas"
echo ""
log_info "Próximos pasos:"
echo "1. Subir audio de clase mediante Fase 3 (upload chunks)"
echo "2. Iniciar procesamiento con los comandos mostrados arriba"
echo "3. Monitorear progreso en tiempo real"
echo "4. Obtener resultados de transcripción y diarización"
echo ""
log_info "Para más detalles, ver:"
echo "  📖 Documentacion/B4.1-Fase-4-ASR-y-Diarizacion.md"
echo "  📋 Documentacion/B4.2-Resumen-Implementacion-Fase-4.md"
