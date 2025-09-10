#!/bin/bash

# =============================================================================
# PRODUCTION DEPLOYMENT SCRIPT - AXONOTE
# =============================================================================
# 
# Script seguro para deployment en producción con validaciones y rollback
# automático en caso de falla.
#
# Requisitos:
# - kubectl configurado para cluster de producción
# - Kustomize instalado
# - Variables de entorno configuradas
# - Acceso a registry de imágenes
#
# Uso:
#   ./scripts/deploy_production.sh
#   ./scripts/deploy_production.sh --version v1.2.0
#   ./scripts/deploy_production.sh --rollback
#
# =============================================================================

set -e

# Configuración
NAMESPACE="axonote"
KUSTOMIZE_DIR="k8s/production"
HEALTH_CHECK_TIMEOUT=300
ROLLBACK_ON_FAILURE=true
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"

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

log_step() {
    echo -e "${BLUE}🔄 $1${NC}"
}

# Notification function
send_notification() {
    local status="$1"
    local message="$2"
    
    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        local emoji="🚀"
        if [ "$status" = "error" ]; then
            emoji="🚨"
        elif [ "$status" = "warning" ]; then
            emoji="⚠️"
        fi
        
        curl -s -X POST "$SLACK_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"text\": \"$emoji AxoNote Production: $message\"}" || true
    fi
}

# Validation functions
validate_prerequisites() {
    log_step "Validando prerequisitos..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl no está instalado"
        exit 1
    fi
    
    # Check kustomize
    if ! command -v kustomize &> /dev/null; then
        log_error "kustomize no está instalado"
        exit 1
    fi
    
    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        log_error "No se puede conectar al cluster Kubernetes"
        exit 1
    fi
    
    # Verify we're connected to production cluster
    local current_context=$(kubectl config current-context)
    if [[ ! "$current_context" == *"production"* ]] && [[ ! "$current_context" == *"prod"* ]]; then
        log_warning "ADVERTENCIA: No parece ser un cluster de producción: $current_context"
        read -p "¿Continuar? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    log_success "Prerequisites validados"
}

validate_images() {
    log_step "Validando disponibilidad de imágenes..."
    
    local images=(
        "ghcr.io/axonote/axonote-api:${VERSION}"
        "ghcr.io/axonote/axonote-web:${VERSION}"
        "ghcr.io/axonote/axonote-worker:${VERSION}"
    )
    
    for image in "${images[@]}"; do
        if docker manifest inspect "$image" &> /dev/null; then
            log_success "Imagen disponible: $image"
        else
            log_error "Imagen no encontrada: $image"
            exit 1
        fi
    done
}

# Pre-deployment checks
pre_deployment_checks() {
    log_step "Ejecutando verificaciones pre-deployment..."
    
    # Check namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace $NAMESPACE no existe"
        exit 1
    fi
    
    # Check current deployment health
    local unhealthy_pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running -o name | wc -l)
    if [ "$unhealthy_pods" -gt 0 ]; then
        log_warning "$unhealthy_pods pods no están en estado Running"
        kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running
    fi
    
    # Check resource quotas
    local resource_usage=$(kubectl top nodes | awk 'NR>1 {cpu+=$3; mem+=$5} END {print cpu, mem}')
    log_info "Uso actual de recursos: $resource_usage"
    
    log_success "Verificaciones pre-deployment completadas"
}

# Deployment function
deploy() {
    log_step "Iniciando deployment en producción..."
    
    # Update image tags in kustomization
    cd "$KUSTOMIZE_DIR"
    kustomize edit set image "ghcr.io/axonote/axonote-api:${VERSION}"
    kustomize edit set image "ghcr.io/axonote/axonote-web:${VERSION}"
    kustomize edit set image "ghcr.io/axonote/axonote-worker:${VERSION}"
    cd - > /dev/null
    
    # Apply manifests
    log_step "Aplicando manifests de Kubernetes..."
    if kustomize build "$KUSTOMIZE_DIR" | kubectl apply -f -; then
        log_success "Manifests aplicados exitosamente"
    else
        log_error "Error aplicando manifests"
        return 1
    fi
    
    # Wait for rollout
    log_step "Esperando rollout de deployments..."
    
    local deployments=("axonote-api" "axonote-web" "axonote-worker")
    for deployment in "${deployments[@]}"; do
        log_step "Rollout de $deployment..."
        
        if kubectl rollout status deployment/"$deployment" -n "$NAMESPACE" --timeout="${HEALTH_CHECK_TIMEOUT}s"; then
            log_success "$deployment rollout completado"
        else
            log_error "$deployment rollout falló"
            return 1
        fi
    done
    
    return 0
}

# Health checks
run_health_checks() {
    log_step "Ejecutando health checks post-deployment..."
    
    # Wait for pods to be ready
    sleep 30
    
    # Check pod status
    local ready_pods=$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' | wc -w)
    local total_pods=$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}' | wc -w)
    
    log_info "Pods ready: $ready_pods/$total_pods"
    
    if [ "$ready_pods" -lt "$total_pods" ]; then
        log_error "No todos los pods están ready"
        kubectl get pods -n "$NAMESPACE"
        return 1
    fi
    
    # Health check API endpoints
    local api_service_ip=$(kubectl get service axonote-api-service -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
    
    # Port forward for testing (background process)
    kubectl port-forward service/axonote-api-service 8080:80 -n "$NAMESPACE" &
    local port_forward_pid=$!
    sleep 5
    
    # Test health endpoint
    if curl -f http://localhost:8080/api/v1/health &> /dev/null; then
        log_success "API health check passed"
    else
        log_error "API health check failed"
        kill $port_forward_pid 2>/dev/null || true
        return 1
    fi
    
    # Test database connection
    if curl -f http://localhost:8080/api/v1/health/db &> /dev/null; then
        log_success "Database health check passed"
    else
        log_error "Database health check failed"
        kill $port_forward_pid 2>/dev/null || true
        return 1
    fi
    
    # Cleanup port forward
    kill $port_forward_pid 2>/dev/null || true
    
    log_success "Health checks completados exitosamente"
    return 0
}

# Rollback function
rollback() {
    log_step "Iniciando rollback automático..."
    
    local deployments=("axonote-api" "axonote-web" "axonote-worker")
    for deployment in "${deployments[@]}"; do
        log_step "Rollback de $deployment..."
        
        if kubectl rollout undo deployment/"$deployment" -n "$NAMESPACE"; then
            log_success "$deployment rollback iniciado"
        else
            log_error "$deployment rollback falló"
        fi
    done
    
    # Wait for rollback to complete
    for deployment in "${deployments[@]}"; do
        if kubectl rollout status deployment/"$deployment" -n "$NAMESPACE" --timeout="${HEALTH_CHECK_TIMEOUT}s"; then
            log_success "$deployment rollback completado"
        else
            log_error "$deployment rollback falló"
        fi
    done
    
    send_notification "error" "Deployment falló y se ejecutó rollback automático"
}

# Cleanup function
cleanup() {
    # Kill any background processes
    jobs -p | xargs -r kill 2>/dev/null || true
}

# Main deployment flow
main() {
    log_header "🚀 AXONOTE PRODUCTION DEPLOYMENT"
    
    # Parse arguments
    VERSION="latest"
    ROLLBACK_MODE=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --version)
                VERSION="$2"
                shift 2
                ;;
            --rollback)
                ROLLBACK_MODE=true
                shift
                ;;
            --help)
                echo "Uso: $0 [--version VERSION] [--rollback]"
                echo "  --version VERSION    Versión específica a deployar (default: latest)"
                echo "  --rollback           Ejecutar rollback del último deployment"
                exit 0
                ;;
            *)
                log_error "Argumento desconocido: $1"
                exit 1
                ;;
        esac
    done
    
    # Setup cleanup trap
    trap cleanup EXIT
    
    if [ "$ROLLBACK_MODE" = true ]; then
        rollback
        exit 0
    fi
    
    log_info "Deploying version: $VERSION"
    log_info "Namespace: $NAMESPACE"
    log_info "Cluster: $(kubectl config current-context)"
    echo ""
    
    # Pre-deployment validation
    validate_prerequisites
    validate_images
    pre_deployment_checks
    
    # Record deployment start
    local deployment_start=$(date -Iseconds)
    send_notification "info" "Iniciando deployment versión $VERSION"
    
    # Execute deployment
    if deploy; then
        log_success "Deployment aplicado exitosamente"
        
        # Post-deployment health checks
        if run_health_checks; then
            local deployment_end=$(date -Iseconds)
            log_success "🎉 DEPLOYMENT COMPLETADO EXITOSAMENTE"
            send_notification "success" "Deployment $VERSION completado exitosamente"
            
            # Log deployment info
            echo ""
            echo "╭─────────────────────────────────────────────────────────────────╮"
            echo "│                        DEPLOYMENT SUCCESS                      │"
            echo "├─────────────────────────────────────────────────────────────────┤"
            echo "│ Version: $VERSION"
            echo "│ Start:   $deployment_start"
            echo "│ End:     $deployment_end"
            echo "│ Status:  ✅ SUCCESS"
            echo "╰─────────────────────────────────────────────────────────────────╯"
            
        else
            log_error "Health checks fallaron"
            if [ "$ROLLBACK_ON_FAILURE" = true ]; then
                rollback
            fi
            exit 1
        fi
        
    else
        log_error "Deployment falló"
        if [ "$ROLLBACK_ON_FAILURE" = true ]; then
            rollback
        fi
        exit 1
    fi
}

# Execute main function
main "$@"
