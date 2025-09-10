#!/bin/bash

# =============================================================================
# SCRIPT DE LOAD TESTING - SPRINT 1
# =============================================================================
# 
# Pruebas de carga para validar el rendimiento del sistema bajo múltiples
# usuarios concurrentes. Simula carga real de una institución médica.
#
# Escenarios:
# - 50+ usuarios concurrentes
# - 100+ archivos audio simultáneos  
# - Stress test con archivos grandes (>2GB)
# - Monitoreo de recursos en tiempo real
#
# Uso:
#   ./scripts/test_sprint1_load_testing.sh
#   ./scripts/test_sprint1_load_testing.sh --users 100
#   ./scripts/test_sprint1_load_testing.sh --stress-test
#
# =============================================================================

set -e

# Configuración
API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api/v1}"
CONCURRENT_USERS="${CONCURRENT_USERS:-50}"
TEST_DURATION="${TEST_DURATION:-60}"
STRESS_TEST="${STRESS_TEST:-false}"
LARGE_FILE_TEST="${LARGE_FILE_TEST:-false}"
OUTPUT_DIR="test_results/load_test_$(date +%Y%m%d_%H%M%S)"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Logging functions
log_header() {
    echo -e "\n${PURPLE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════════════════════════${NC}\n"
}

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

# Performance metrics
TOTAL_REQUESTS=0
SUCCESSFUL_REQUESTS=0
FAILED_REQUESTS=0
RESPONSE_TIMES=()
MIN_RESPONSE_TIME=999999
MAX_RESPONSE_TIME=0
TOTAL_RESPONSE_TIME=0

# Function to make timed request
make_timed_request() {
    local url="$1"
    local method="${2:-GET}"
    local data="$3"
    
    local start_time=$(date +%s.%N)
    local http_code
    
    if [ "$method" = "POST" ] && [ -n "$data" ]; then
        http_code=$(curl -s -w "%{http_code}" -X POST "$url" \
            -H "Content-Type: application/json" \
            -d "$data" -o /dev/null)
    else
        http_code=$(curl -s -w "%{http_code}" "$url" -o /dev/null)
    fi
    
    local end_time=$(date +%s.%N)
    local response_time=$(echo "$end_time - $start_time" | bc -l)
    local response_ms=$(echo "$response_time * 1000" | bc -l | cut -d. -f1)
    
    ((TOTAL_REQUESTS++))
    TOTAL_RESPONSE_TIME=$(echo "$TOTAL_RESPONSE_TIME + $response_time" | bc -l)
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        ((SUCCESSFUL_REQUESTS++))
    else
        ((FAILED_REQUESTS++))
    fi
    
    # Update min/max response times
    if [ "$(echo "$response_ms < $MIN_RESPONSE_TIME" | bc -l)" = "1" ]; then
        MIN_RESPONSE_TIME=$response_ms
    fi
    if [ "$(echo "$response_ms > $MAX_RESPONSE_TIME" | bc -l)" = "1" ]; then
        MAX_RESPONSE_TIME=$response_ms
    fi
    
    echo "$response_ms"
}

# Simulate user session
simulate_user_session() {
    local user_id="$1"
    local session_requests=0
    
    for i in {1..10}; do
        # Health check
        make_timed_request "$API_BASE_URL/health" > /dev/null
        ((session_requests++))
        
        # Dashboard metrics
        make_timed_request "$API_BASE_URL/dashboard/metrics" > /dev/null
        ((session_requests++))
        
        # Processing list
        make_timed_request "$API_BASE_URL/processing/list?limit=5" > /dev/null
        ((session_requests++))
        
        # Research sources
        make_timed_request "$API_BASE_URL/research/sources" > /dev/null
        ((session_requests++))
        
        # Small delay between requests
        sleep 0.1
    done
    
    echo "User $user_id completed $session_requests requests"
}

# Monitor system resources
monitor_resources() {
    local duration="$1"
    local interval=5
    local iterations=$((duration / interval))
    
    log_info "Monitoreando recursos del sistema por ${duration}s..."
    
    for i in $(seq 1 $iterations); do
        # CPU usage
        local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
        
        # Memory usage
        local mem_info=$(free | grep Mem)
        local mem_total=$(echo $mem_info | awk '{print $2}')
        local mem_used=$(echo $mem_info | awk '{print $3}')
        local mem_percent=$(echo "scale=1; $mem_used * 100 / $mem_total" | bc -l)
        
        # Docker container stats (if available)
        local docker_stats=""
        if command -v docker &> /dev/null; then
            docker_stats=$(docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | grep axonote || echo "")
        fi
        
        echo "[$i/${iterations}] CPU: ${cpu_usage}%, Memory: ${mem_percent}%"
        if [ -n "$docker_stats" ]; then
            echo "$docker_stats"
        fi
        
        sleep $interval
    done
}

# Concurrent users test
run_concurrent_users_test() {
    log_header "🔄 CONCURRENT USERS TEST: $CONCURRENT_USERS usuarios"
    
    mkdir -p "$OUTPUT_DIR"
    
    log_info "Iniciando $CONCURRENT_USERS usuarios concurrentes..."
    log_info "Duración: ${TEST_DURATION}s"
    
    # Start resource monitoring in background
    monitor_resources $TEST_DURATION > "$OUTPUT_DIR/resource_monitor.log" &
    local monitor_pid=$!
    
    # Start user sessions
    local start_time=$(date +%s)
    
    for i in $(seq 1 $CONCURRENT_USERS); do
        simulate_user_session $i > "$OUTPUT_DIR/user_$i.log" &
    done
    
    # Wait for all users to complete or timeout
    local timeout_time=$((start_time + TEST_DURATION))
    
    while [ $(date +%s) -lt $timeout_time ]; do
        local active_jobs=$(jobs -r | wc -l)
        if [ $active_jobs -le 1 ]; then  # Only monitor job should be running
            break
        fi
        sleep 1
    done
    
    # Kill remaining jobs
    jobs -p | xargs -r kill 2>/dev/null || true
    kill $monitor_pid 2>/dev/null || true
    
    local end_time=$(date +%s)
    local actual_duration=$((end_time - start_time))
    
    log_success "Test completado en ${actual_duration}s"
    
    # Calculate metrics
    calculate_performance_metrics $actual_duration
}

# Large file upload test
run_large_file_test() {
    log_header "📁 LARGE FILE UPLOAD TEST"
    
    log_info "Generando archivo de prueba de 2GB..."
    local large_file="$OUTPUT_DIR/large_test_file.bin"
    
    # Generate 2GB test file
    dd if=/dev/zero of="$large_file" bs=1M count=2048 2>/dev/null || {
        log_error "No se pudo generar archivo de 2GB"
        return 1
    }
    
    log_info "Iniciando upload de archivo grande..."
    
    # Test upload initialization
    local file_size=$(stat -c%s "$large_file")
    local chunks_needed=$((file_size / 10485760 + 1))  # 10MB chunks
    
    local init_data="{
        \"nombreArchivo\": \"large_test_file.bin\",
        \"tamanoTotal\": $file_size,
        \"tipoMime\": \"application/octet-stream\",
        \"numeroChunks\": $chunks_needed
    }"
    
    local start_time=$(date +%s.%N)
    local response=$(curl -s -X POST "$API_BASE_URL/upload/init" \
        -H "Content-Type: application/json" \
        -d "$init_data")
    local end_time=$(date +%s.%N)
    
    local upload_time=$(echo "$end_time - $start_time" | bc -l)
    
    log_success "Upload init completado en ${upload_time}s"
    
    # Cleanup
    rm -f "$large_file"
}

# Stress test with resource exhaustion
run_stress_test() {
    log_header "💥 STRESS TEST - Resource Exhaustion"
    
    log_warning "ADVERTENCIA: Este test puede sobrecargar el sistema"
    
    # Gradually increase load
    local stress_users=(10 25 50 100 200)
    
    for users in "${stress_users[@]}"; do
        log_info "Testing con $users usuarios..."
        
        # Start users
        for i in $(seq 1 $users); do
            (
                for j in {1..5}; do
                    make_timed_request "$API_BASE_URL/health" > /dev/null
                done
            ) &
        done
        
        # Wait for completion
        wait
        
        # Check system responsiveness
        local health_response_time=$(make_timed_request "$API_BASE_URL/health")
        log_info "$users usuarios: tiempo respuesta ${health_response_time}ms"
        
        # If response time > 5 seconds, system is overloaded
        if [ "$(echo "$health_response_time > 5000" | bc -l)" = "1" ]; then
            log_warning "Sistema sobrecargado con $users usuarios (${health_response_time}ms)"
            break
        fi
        
        sleep 10  # Cool down between stress levels
    done
}

# Calculate performance metrics
calculate_performance_metrics() {
    local duration="$1"
    
    log_header "📊 PERFORMANCE METRICS"
    
    # Calculate averages
    local avg_response_time=0
    if [ $TOTAL_REQUESTS -gt 0 ]; then
        avg_response_time=$(echo "scale=2; $TOTAL_RESPONSE_TIME * 1000 / $TOTAL_REQUESTS" | bc -l)
    fi
    
    local success_rate=0
    if [ $TOTAL_REQUESTS -gt 0 ]; then
        success_rate=$(echo "scale=2; $SUCCESSFUL_REQUESTS * 100 / $TOTAL_REQUESTS" | bc -l)
    fi
    
    local rps=$(echo "scale=2; $TOTAL_REQUESTS / $duration" | bc -l)
    
    # Display metrics
    echo "Total Requests: $TOTAL_REQUESTS"
    echo "Successful: $SUCCESSFUL_REQUESTS"
    echo "Failed: $FAILED_REQUESTS"
    echo "Success Rate: ${success_rate}%"
    echo "Requests/Second: $rps"
    echo "Avg Response Time: ${avg_response_time}ms"
    echo "Min Response Time: ${MIN_RESPONSE_TIME}ms"
    echo "Max Response Time: ${MAX_RESPONSE_TIME}ms"
    
    # Performance evaluation
    echo ""
    if [ "$(echo "$success_rate >= 95" | bc -l)" = "1" ] && [ "$(echo "$avg_response_time <= 1000" | bc -l)" = "1" ]; then
        log_success "PERFORMANCE EXCELENTE"
    elif [ "$(echo "$success_rate >= 90" | bc -l)" = "1" ] && [ "$(echo "$avg_response_time <= 2000" | bc -l)" = "1" ]; then
        log_success "PERFORMANCE BUENA"
    elif [ "$(echo "$success_rate >= 80" | bc -l)" = "1" ] && [ "$(echo "$avg_response_time <= 5000" | bc -l)" = "1" ]; then
        log_warning "PERFORMANCE ACEPTABLE"
    else
        log_error "PERFORMANCE INSUFICIENTE"
    fi
    
    # Save detailed report
    cat > "$OUTPUT_DIR/load_test_report.json" << EOF
{
    "timestamp": "$(date -Iseconds)",
    "configuration": {
        "concurrent_users": $CONCURRENT_USERS,
        "test_duration": $duration,
        "api_base_url": "$API_BASE_URL"
    },
    "metrics": {
        "total_requests": $TOTAL_REQUESTS,
        "successful_requests": $SUCCESSFUL_REQUESTS,
        "failed_requests": $FAILED_REQUESTS,
        "success_rate": $success_rate,
        "requests_per_second": $rps,
        "avg_response_time_ms": $avg_response_time,
        "min_response_time_ms": $MIN_RESPONSE_TIME,
        "max_response_time_ms": $MAX_RESPONSE_TIME
    }
}
EOF
}

# Main function
main() {
    log_header "⚡ AXONOTE - LOAD TESTING SUITE"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --users)
                CONCURRENT_USERS="$2"
                shift 2
                ;;
            --duration)
                TEST_DURATION="$2"
                shift 2
                ;;
            --stress-test)
                STRESS_TEST=true
                shift
                ;;
            --large-file-test)
                LARGE_FILE_TEST=true
                shift
                ;;
            --help)
                echo "Uso: $0 [opciones]"
                echo "  --users N          Número de usuarios concurrentes (default: 50)"
                echo "  --duration N       Duración del test en segundos (default: 60)"
                echo "  --stress-test      Ejecutar test de estrés"
                echo "  --large-file-test  Test de archivos grandes"
                exit 0
                ;;
            *)
                log_error "Argumento desconocido: $1"
                exit 1
                ;;
        esac
    done
    
    # Verify API is available
    if ! curl -s "$API_BASE_URL/health" > /dev/null; then
        log_error "API no disponible en $API_BASE_URL"
        exit 1
    fi
    
    log_info "Configuración del test:"
    log_info "  Usuarios concurrentes: $CONCURRENT_USERS"
    log_info "  Duración: ${TEST_DURATION}s"
    log_info "  Output: $OUTPUT_DIR"
    echo ""
    
    # Run tests
    run_concurrent_users_test
    
    if [ "$LARGE_FILE_TEST" = true ]; then
        run_large_file_test
    fi
    
    if [ "$STRESS_TEST" = true ]; then
        run_stress_test
    fi
    
    log_success "Load testing completado. Resultados en: $OUTPUT_DIR"
}

# Execute
main "$@"
