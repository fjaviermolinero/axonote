#!/bin/bash

# =============================================================================
# SCRIPT DE SECURITY TESTING - SPRINT 1
# =============================================================================
# 
# Pruebas de seguridad para validar la protección del sistema contra
# vulnerabilidades comunes. Incluye penetration testing automatizado.
#
# Tests incluidos:
# - OWASP Top 10 vulnerabilities
# - Input validation y sanitization
# - Authentication y autorización
# - Rate limiting y DDoS protection
# - Data encryption y privacy
# - GDPR compliance verification
#
# Uso:
#   ./scripts/test_sprint1_security.sh
#   ./scripts/test_sprint1_security.sh --full-scan
#   ./scripts/test_sprint1_security.sh --owasp-zap
#
# =============================================================================

set -e

# Configuración
API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api/v1}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
FULL_SCAN="${FULL_SCAN:-false}"
ZAP_SCAN="${ZAP_SCAN:-false}"
OUTPUT_DIR="test_results/security_$(date +%Y%m%d_%H%M%S)"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Security issues counter
CRITICAL_ISSUES=0
HIGH_ISSUES=0
MEDIUM_ISSUES=0
LOW_ISSUES=0
INFO_ISSUES=0

# Logging functions
log_header() {
    echo -e "\n${PURPLE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}═══════════════════════════════════════════════════════════════════════════════${NC}\n"
}

log_critical() {
    echo -e "${RED}🚨 CRITICAL: $1${NC}"
    ((CRITICAL_ISSUES++))
}

log_high() {
    echo -e "${RED}🔴 HIGH: $1${NC}"
    ((HIGH_ISSUES++))
}

log_medium() {
    echo -e "${YELLOW}🟡 MEDIUM: $1${NC}"
    ((MEDIUM_ISSUES++))
}

log_low() {
    echo -e "${BLUE}🔵 LOW: $1${NC}"
    ((LOW_ISSUES++))
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
    ((INFO_ISSUES++))
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Security test functions

test_sql_injection() {
    log_header "💉 SQL INJECTION TESTING"
    
    local payloads=(
        "' OR '1'='1"
        "1'; DROP TABLE users; --"
        "1' UNION SELECT * FROM users --"
        "admin'--"
        "' OR 1=1 --"
        "'; EXEC sp_configure 'show advanced options', 1--"
    )
    
    log_info "Testing SQL injection en endpoints principales..."
    
    for payload in "${payloads[@]}"; do
        # Test in query parameters
        local response=$(curl -s "$API_BASE_URL/health?id=${payload}" | grep -i error | wc -l)
        if [ "$response" -gt 0 ]; then
            log_high "Posible SQL injection vulnerability en query params: $payload"
        fi
        
        # Test in POST body
        local post_response=$(curl -s -X POST "$API_BASE_URL/auth/login" \
            -H "Content-Type: application/json" \
            -d "{\"username\": \"$payload\", \"password\": \"test\"}" | grep -i error | wc -l)
        if [ "$post_response" -gt 0 ]; then
            log_high "Posible SQL injection vulnerability en POST body: $payload"
        fi
    done
    
    log_success "SQL injection testing completado"
}

test_xss_vulnerabilities() {
    log_header "🕷️ XSS (Cross-Site Scripting) TESTING"
    
    local xss_payloads=(
        "<script>alert('XSS')</script>"
        "<img src=x onerror=alert('XSS')>"
        "javascript:alert('XSS')"
        "<svg onload=alert('XSS')>"
        "<iframe src='javascript:alert(\"XSS\")'></iframe>"
        "';alert(String.fromCharCode(88,83,83))//'"
    )
    
    log_info "Testing XSS vulnerabilities..."
    
    for payload in "${xss_payloads[@]}"; do
        # Test reflected XSS
        local response=$(curl -s "$API_BASE_URL/health?search=${payload}" | grep -o "$payload" | wc -l)
        if [ "$response" -gt 0 ]; then
            log_high "Posible reflected XSS vulnerability: $payload"
        fi
        
        # Test stored XSS (simulate)
        local post_response=$(curl -s -X POST "$API_BASE_URL/test" \
            -H "Content-Type: application/json" \
            -d "{\"content\": \"$payload\"}" 2>/dev/null | grep -o "$payload" | wc -l)
        if [ "$post_response" -gt 0 ]; then
            log_high "Posible stored XSS vulnerability: $payload"
        fi
    done
    
    log_success "XSS testing completado"
}

test_authentication_security() {
    log_header "🔐 AUTHENTICATION SECURITY TESTING"
    
    log_info "Testing authentication endpoints..."
    
    # Test weak password acceptance
    local weak_passwords=("123456" "password" "admin" "test" "12345678")
    
    for weak_pass in "${weak_passwords[@]}"; do
        local response=$(curl -s -X POST "$API_BASE_URL/auth/register" \
            -H "Content-Type: application/json" \
            -d "{\"username\": \"testuser\", \"password\": \"$weak_pass\", \"email\": \"test@test.com\"}")
        
        local status=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('status', 'unknown'))
except:
    print('unknown')
" 2>/dev/null)
        
        if [ "$status" = "success" ]; then
            log_medium "Sistema acepta contraseña débil: $weak_pass"
        fi
    done
    
    # Test brute force protection
    log_info "Testing brute force protection..."
    local failed_attempts=0
    
    for i in {1..10}; do
        local response=$(curl -s -w "%{http_code}" -X POST "$API_BASE_URL/auth/login" \
            -H "Content-Type: application/json" \
            -d '{"username": "nonexistent", "password": "wrongpass"}' | tail -n1)
        
        if [ "$response" = "429" ]; then
            log_success "Brute force protection activa (429 después de $i intentos)"
            break
        elif [ "$response" = "401" ]; then
            ((failed_attempts++))
        fi
    done
    
    if [ $failed_attempts -eq 10 ]; then
        log_medium "No se detectó protección contra brute force"
    fi
    
    # Test JWT token validation
    log_info "Testing JWT token validation..."
    local invalid_tokens=(
        "invalid.jwt.token"
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        ""
        "Bearer malformed"
    )
    
    for token in "${invalid_tokens[@]}"; do
        local response=$(curl -s -w "%{http_code}" "$API_BASE_URL/protected-endpoint" \
            -H "Authorization: Bearer $token" | tail -n1)
        
        if [ "$response" != "401" ] && [ "$response" != "403" ]; then
            log_high "Token JWT inválido aceptado: $token"
        fi
    done
    
    log_success "Authentication security testing completado"
}

test_authorization_controls() {
    log_header "🛡️ AUTHORIZATION CONTROLS TESTING"
    
    log_info "Testing RBAC (Role-Based Access Control)..."
    
    # Test privilege escalation
    local escalation_payloads=(
        '{"role": "admin"}'
        '{"permissions": ["admin", "write", "delete"]}'
        '{"user_id": 1, "role": "superuser"}'
    )
    
    for payload in "${escalation_payloads[@]}"; do
        local response=$(curl -s -X POST "$API_BASE_URL/user/update" \
            -H "Content-Type: application/json" \
            -d "$payload")
        
        local status=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('status', 'unknown'))
except:
    print('unknown')
" 2>/dev/null)
        
        if [ "$status" = "success" ]; then
            log_critical "Posible privilege escalation: $payload"
        fi
    done
    
    # Test direct object references
    log_info "Testing Insecure Direct Object References (IDOR)..."
    
    local sensitive_endpoints=(
        "/users/1"
        "/sessions/1"
        "/admin/users"
        "/processing/jobs/1"
    )
    
    for endpoint in "${sensitive_endpoints[@]}"; do
        local response=$(curl -s -w "%{http_code}" "$API_BASE_URL$endpoint" | tail -n1)
        
        if [ "$response" = "200" ]; then
            log_medium "Endpoint sensible accesible sin autenticación: $endpoint"
        fi
    done
    
    log_success "Authorization controls testing completado"
}

test_input_validation() {
    log_header "🔍 INPUT VALIDATION TESTING"
    
    log_info "Testing input validation y sanitization..."
    
    # Test oversized inputs
    local large_string=$(python3 -c "print('A' * 10000)")
    local response=$(curl -s -X POST "$API_BASE_URL/test" \
        -H "Content-Type: application/json" \
        -d "{\"data\": \"$large_string\"}")
    
    local status=$(echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('status', 'unknown'))
except:
    print('unknown')
" 2>/dev/null)
    
    if [ "$status" = "success" ]; then
        log_medium "Sistema acepta inputs excesivamente grandes"
    fi
    
    # Test malformed JSON
    local malformed_json='{"invalid": json, "missing": quote}'
    local json_response=$(curl -s -w "%{http_code}" -X POST "$API_BASE_URL/test" \
        -H "Content-Type: application/json" \
        -d "$malformed_json" | tail -n1)
    
    if [ "$json_response" != "400" ]; then
        log_medium "JSON malformado no rechazado apropiadamente"
    fi
    
    # Test special characters
    local special_chars='{"test": "<?xml version=\"1.0\"?><!DOCTYPE test [ <!ENTITY xxe SYSTEM \"file:///etc/passwd\"> ]><test>&xxe;</test>"}'
    local xxe_response=$(curl -s "$API_BASE_URL/test" \
        -H "Content-Type: application/json" \
        -d "$special_chars" | grep -i "root:" | wc -l)
    
    if [ "$xxe_response" -gt 0 ]; then
        log_critical "Posible XXE (XML External Entity) vulnerability"
    fi
    
    log_success "Input validation testing completado"
}

test_data_encryption() {
    log_header "🔒 DATA ENCRYPTION TESTING"
    
    log_info "Testing encryption y data protection..."
    
    # Test HTTPS enforcement
    if [ "${API_BASE_URL:0:5}" = "http:" ]; then
        log_high "API usando HTTP en lugar de HTTPS"
    else
        log_success "API usando HTTPS"
    fi
    
    # Test sensitive data exposure
    local endpoints=(
        "/health"
        "/metrics"
        "/dashboard/overview"
        "/auth/health"
    )
    
    for endpoint in "${endpoints[@]}"; do
        local response=$(curl -s "$API_BASE_URL$endpoint")
        
        # Check for exposed secrets
        if echo "$response" | grep -i "password\|secret\|key\|token" | grep -v "status\|health\|endpoint" > /dev/null; then
            log_high "Posible exposición de datos sensibles en: $endpoint"
        fi
    done
    
    # Test password hashing
    log_info "Verificando seguridad de contraseñas..."
    # This would require access to database or specific endpoint
    # For now, we check if passwords are returned in responses
    
    local auth_response=$(curl -s -X POST "$API_BASE_URL/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username": "test", "password": "test"}')
    
    if echo "$auth_response" | grep -i "password" > /dev/null; then
        log_critical "Contraseñas expuestas en respuestas de autenticación"
    fi
    
    log_success "Data encryption testing completado"
}

test_rate_limiting() {
    log_header "🚦 RATE LIMITING TESTING"
    
    log_info "Testing rate limiting y DDoS protection..."
    
    # Test API rate limiting
    local rate_limit_hit=false
    
    for i in {1..50}; do
        local response=$(curl -s -w "%{http_code}" "$API_BASE_URL/health" | tail -n1)
        
        if [ "$response" = "429" ]; then
            log_success "Rate limiting activo (429 después de $i requests)"
            rate_limit_hit=true
            break
        fi
        
        sleep 0.1
    done
    
    if [ "$rate_limit_hit" = false ]; then
        log_medium "Rate limiting no detectado en endpoint /health"
    fi
    
    # Test different endpoints
    local endpoints_to_test=(
        "/auth/login"
        "/processing/list"
        "/dashboard/metrics"
    )
    
    for endpoint in "${endpoints_to_test[@]}"; do
        local requests_made=0
        
        for j in {1..20}; do
            local ep_response=$(curl -s -w "%{http_code}" "$API_BASE_URL$endpoint" | tail -n1)
            ((requests_made++))
            
            if [ "$ep_response" = "429" ]; then
                log_success "Rate limiting en $endpoint después de $requests_made requests"
                break
            fi
        done
    done
    
    log_success "Rate limiting testing completado"
}

test_cors_security() {
    log_header "🌐 CORS SECURITY TESTING"
    
    log_info "Testing CORS configuration..."
    
    # Test CORS headers
    local cors_response=$(curl -s -H "Origin: http://malicious-site.com" \
        -H "Access-Control-Request-Method: POST" \
        -H "Access-Control-Request-Headers: X-Requested-With" \
        -X OPTIONS "$API_BASE_URL/health")
    
    if echo "$cors_response" | grep -i "access-control-allow-origin: *" > /dev/null; then
        log_high "CORS configurado para permitir cualquier origen (*)"
    fi
    
    # Test preflight requests
    local preflight_response=$(curl -s -I -H "Origin: http://localhost:3000" \
        -H "Access-Control-Request-Method: POST" \
        -X OPTIONS "$API_BASE_URL/auth/login")
    
    if echo "$preflight_response" | grep -i "access-control" > /dev/null; then
        log_success "CORS preflight requests configurados"
    else
        log_medium "CORS preflight no configurado apropiadamente"
    fi
    
    log_success "CORS security testing completado"
}

test_gdpr_compliance() {
    log_header "📋 GDPR COMPLIANCE TESTING"
    
    log_info "Testing GDPR compliance features..."
    
    # Test privacy policy endpoint
    if curl -s "$API_BASE_URL/privacy" > /dev/null; then
        log_success "Endpoint de privacy policy disponible"
    else
        log_medium "Endpoint de privacy policy no encontrado"
    fi
    
    # Test data subject rights endpoints
    local gdpr_endpoints=(
        "/gdpr/export"
        "/gdpr/delete"
        "/gdpr/rectification"
        "/gdpr/consent"
    )
    
    for endpoint in "${gdpr_endpoints[@]}"; do
        local gdpr_response=$(curl -s -w "%{http_code}" "$API_BASE_URL$endpoint" | tail -n1)
        
        if [ "$gdpr_response" != "404" ]; then
            log_success "Endpoint GDPR disponible: $endpoint"
        fi
    done
    
    # Test consent tracking
    log_info "Verificando tracking de consentimientos..."
    # This would require specific implementation details
    
    log_success "GDPR compliance testing completado"
}

run_owasp_zap_scan() {
    log_header "🕷️ OWASP ZAP AUTOMATED SCAN"
    
    if ! command -v zap-cli &> /dev/null; then
        log_warning "OWASP ZAP CLI not installed. Skipping automated scan."
        log_info "Install with: pip install zap-cli"
        return
    fi
    
    log_info "Iniciando OWASP ZAP scan automatizado..."
    
    # Start ZAP daemon
    zap-cli start &
    local zap_pid=$!
    sleep 10
    
    # Open URL
    zap-cli open-url "$API_BASE_URL"
    
    # Spider the application
    log_info "Spidering application..."
    zap-cli spider "$API_BASE_URL"
    
    # Active scan
    log_info "Running active scan..."
    zap-cli active-scan "$API_BASE_URL"
    
    # Wait for scan to complete
    while [ "$(zap-cli status)" != "100" ]; do
        echo "Scan progress: $(zap-cli status)%"
        sleep 10
    done
    
    # Generate report
    log_info "Generando reporte ZAP..."
    zap-cli report -o "$OUTPUT_DIR/zap_report.html" -f html
    
    # Stop ZAP
    zap-cli shutdown
    wait $zap_pid
    
    log_success "OWASP ZAP scan completado. Reporte: $OUTPUT_DIR/zap_report.html"
}

generate_security_report() {
    log_header "📊 SECURITY REPORT"
    
    mkdir -p "$OUTPUT_DIR"
    
    local total_issues=$((CRITICAL_ISSUES + HIGH_ISSUES + MEDIUM_ISSUES + LOW_ISSUES))
    
    cat > "$OUTPUT_DIR/security_report.md" << EOF
# Security Testing Report
## $(date)

### Executive Summary
- **Critical Issues**: $CRITICAL_ISSUES
- **High Risk Issues**: $HIGH_ISSUES
- **Medium Risk Issues**: $MEDIUM_ISSUES
- **Low Risk Issues**: $LOW_ISSUES
- **Total Issues**: $total_issues

### Risk Assessment
$(if [ $CRITICAL_ISSUES -gt 0 ]; then
    echo "🚨 **CRITICAL**: Sistema no apto para producción"
elif [ $HIGH_ISSUES -gt 0 ]; then
    echo "🔴 **HIGH RISK**: Requiere atención inmediata"
elif [ $MEDIUM_ISSUES -gt 0 ]; then
    echo "🟡 **MEDIUM RISK**: Revisar antes de producción"
else
    echo "✅ **LOW RISK**: Sistema seguro para producción"
fi)

### Tests Ejecutados
- ✅ SQL Injection Testing
- ✅ XSS Vulnerability Testing
- ✅ Authentication Security
- ✅ Authorization Controls
- ✅ Input Validation
- ✅ Data Encryption
- ✅ Rate Limiting
- ✅ CORS Security
- ✅ GDPR Compliance
$(if [ "$ZAP_SCAN" = true ]; then echo "- ✅ OWASP ZAP Automated Scan"; fi)

### Recommendations
1. Corregir todos los issues críticos antes de deployment
2. Implementar monitoring de seguridad continuo
3. Realizar auditorías de seguridad regulares
4. Mantener dependencias actualizadas
5. Implementar logging de eventos de seguridad

### Technical Details
- API Base URL: $API_BASE_URL
- Test Date: $(date)
- Test Duration: Generated by AxoNote Security Testing Suite
EOF

    log_success "Reporte de seguridad generado: $OUTPUT_DIR/security_report.md"
    
    # Display summary
    echo ""
    echo "══════════════════════════════════════════════════════════════════════════════"
    echo "🔐 SECURITY TESTING SUMMARY"
    echo "══════════════════════════════════════════════════════════════════════════════"
    echo "🚨 Critical: $CRITICAL_ISSUES"
    echo "🔴 High: $HIGH_ISSUES"
    echo "🟡 Medium: $MEDIUM_ISSUES"
    echo "🔵 Low: $LOW_ISSUES"
    echo "══════════════════════════════════════════════════════════════════════════════"
    
    if [ $CRITICAL_ISSUES -eq 0 ] && [ $HIGH_ISSUES -eq 0 ]; then
        echo -e "${GREEN}✅ SISTEMA SEGURO PARA PRODUCCIÓN${NC}"
        return 0
    else
        echo -e "${RED}⚠️  ISSUES DE SEGURIDAD DETECTADOS${NC}"
        return 1
    fi
}

# Main function
main() {
    log_header "🛡️ AXONOTE - SECURITY TESTING SUITE"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --full-scan)
                FULL_SCAN=true
                shift
                ;;
            --owasp-zap)
                ZAP_SCAN=true
                shift
                ;;
            --help)
                echo "Uso: $0 [opciones]"
                echo "  --full-scan    Ejecutar suite completo de tests"
                echo "  --owasp-zap    Incluir OWASP ZAP automated scan"
                exit 0
                ;;
            *)
                log_warning "Argumento desconocido: $1"
                shift
                ;;
        esac
    done
    
    # Verify API is available
    if ! curl -s "$API_BASE_URL/health" > /dev/null; then
        log_critical "API no disponible en $API_BASE_URL"
        exit 1
    fi
    
    log_info "Iniciando security testing suite..."
    log_info "Target: $API_BASE_URL"
    log_info "Output: $OUTPUT_DIR"
    echo ""
    
    # Run security tests
    test_sql_injection
    test_xss_vulnerabilities
    test_authentication_security
    test_authorization_controls
    test_input_validation
    test_data_encryption
    test_rate_limiting
    test_cors_security
    test_gdpr_compliance
    
    if [ "$ZAP_SCAN" = true ]; then
        run_owasp_zap_scan
    fi
    
    # Generate report and exit with appropriate code
    generate_security_report
}

# Execute
main "$@"
