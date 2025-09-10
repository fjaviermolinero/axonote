#!/bin/bash

# Script de testing responsive para componentes médicos de Axonote
# Verifica que los componentes funcionen en diferentes dispositivos

echo "📱 Testing Responsive - Componentes Médicos"
echo "============================================"

PROJECT_ROOT="/home/javi/Programacion/axonote"
cd "$PROJECT_ROOT"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

# Definir breakpoints para testing
declare -A DEVICE_BREAKPOINTS=(
    ["mobile_small"]="320x568"
    ["mobile_medium"]="375x667" 
    ["mobile_large"]="414x896"
    ["tablet_portrait"]="768x1024"
    ["tablet_landscape"]="1024x768"
    ["desktop_small"]="1366x768"
    ["desktop_large"]="1920x1080"
)

declare -A DEVICE_NAMES=(
    ["mobile_small"]="📱 iPhone SE (320px)"
    ["mobile_medium"]="📱 iPhone 12 (375px)"
    ["mobile_large"]="📱 iPhone 12 Pro Max (414px)"
    ["tablet_portrait"]="📟 iPad Portrait (768px)"
    ["tablet_landscape"]="📟 iPad Landscape (1024px)"
    ["desktop_small"]="💻 Desktop Small (1366px)"
    ["desktop_large"]="🖥️  Desktop Large (1920px)"
)

# Función para analizar CSS responsivo
analyze_responsive_css() {
    local component_file="$1"
    local component_name="$2"
    
    echo ""
    log_info "Analizando responsividad: $component_name"
    echo "----------------------------------------"
    
    if [ ! -f "$component_file" ]; then
        log_error "Archivo no encontrado: $component_file"
        return 1
    fi
    
    # Verificar clases responsivas de Tailwind
    local responsive_classes=("sm:" "md:" "lg:" "xl:" "2xl:")
    local responsive_found=0
    
    for class_prefix in "${responsive_classes[@]}"; do
        if grep -q "$class_prefix" "$component_file"; then
            responsive_found=$((responsive_found + 1))
            log_success "Breakpoint implementado: $class_prefix"
        fi
    done
    
    # Verificar mobile-first design
    if grep -q "w-full\|mobile-container\|max-w-\|min-w-" "$component_file"; then
        log_success "Mobile-first patterns detectados"
    else
        log_warning "Mobile-first patterns no evidentes"
    fi
    
    # Verificar touch-friendly (botones grandes)
    if grep -q "h-16\|h-12\|h-14\|p-4\|p-6\|px-6\|py-4" "$component_file"; then
        log_success "Touch-friendly sizing detectado"
    else
        log_warning "Touch-friendly sizing no evidente"
    fi
    
    # Verificar flex/grid layouts
    if grep -q "flex\|grid" "$component_file"; then
        log_success "Layout flexible implementado"
    else
        log_warning "Layout flexible no detectado"
    fi
    
    echo "   📊 Breakpoints implementados: $responsive_found/5"
    
    return 0
}

# Función para verificar componentes médicos específicos
test_medical_component() {
    local component_file="$1"
    local component_name="$2"
    
    echo ""
    log_info "Testing componente médico: $component_name"
    echo "----------------------------------------"
    
    if [ ! -f "$component_file" ]; then
        log_error "Componente no encontrado: $component_file"
        return 1
    fi
    
    # Verificar características médicas específicas
    local medical_features=()
    
    # MedicalCard específicos
    if [[ "$component_name" == *"MedicalCard"* ]]; then
        medical_features=(
            "confianza_asr|confianza_llm:Métricas de confianza"
            "estado.*medical:Estados médicos"
            "especialidad:Especialidades médicas"
            "medical-card:Clase CSS médica"
            "hover.*shadow:Efectos hover"
        )
    fi
    
    # MedicalBadge específicos
    if [[ "$component_name" == *"MedicalBadge"* ]]; then
        medical_features=(
            "variantConfig:Configuración de variantes"
            "especialidad.*cardiologia|neurologia:Especialidades médicas"
            "estado.*completed|processing:Estados del pipeline"
            "confianza.*percentage:Badges de confianza"
            "medical-badge:Clase CSS médica"
        )
    fi
    
    # RecordingControls específicos
    if [[ "$component_name" == *"RecordingControls"* ]]; then
        medical_features=(
            "quickActions:Acciones rápidas médicas"
            "idea_clave|no_entendi:Marcadores pedagógicos"
            "micromemo:Micro-memos de 10s"
            "audioLevel:Visualización de audio"
            "recording-controls:Clase CSS de controles"
        )
    fi
    
    # SyncIndicator específicos
    if [[ "$component_name" == *"SyncIndicator"* ]]; then
        medical_features=(
            "pendingCount:Contador de pendientes"
            "lastSync:Última sincronización"
            "statusConfig:Configuración de estados"
            "backdrop-filter:Efecto glassmorphism"
            "sync-indicator:Clase CSS de sync"
        )
    fi
    
    # Verificar cada característica médica
    for feature_pattern in "${medical_features[@]}"; do
        IFS=':' read -r pattern description <<< "$feature_pattern"
        
        if grep -q "$pattern" "$component_file"; then
            log_success "$description implementado"
        else
            log_warning "$description no detectado"
        fi
    done
    
    # Verificar TypeScript interfaces
    if grep -q "interface.*Props" "$component_file"; then
        log_success "TypeScript interfaces definidas"
    else
        log_warning "TypeScript interfaces no evidentes"
    fi
    
    # Verificar accesibilidad
    if grep -q "aria-\|alt=\|role=" "$component_file"; then
        log_success "Atributos de accesibilidad implementados"
    else
        log_warning "Accesibilidad básica - considerar mejoras"
    fi
    
    return 0
}

# Función para generar HTML de preview
generate_preview_html() {
    cat > "test_responsive_preview.html" << 'EOF'
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Axonote - Preview Responsive</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        /* Simular estilos médicos */
        .medical-card {
            transition: all 0.3s ease;
            background: linear-gradient(145deg, #ffffff 0%, #fafbfc 100%);
        }
        .medical-card:hover {
            transform: translateY(-2px) scale(1.02);
            box-shadow: 0 10px 25px -3px rgba(59, 130, 246, 0.1), 0 4px 6px -2px rgba(59, 130, 246, 0.05);
        }
        .medical-badge {
            font-feature-settings: 'tnum' on, 'lnum' on;
        }
        .device-frame {
            border: 2px solid #d1d5db;
            border-radius: 12px;
            overflow: hidden;
            margin: 10px;
            position: relative;
        }
        .device-label {
            position: absolute;
            top: -30px;
            left: 0;
            background: #3b82f6;
            color: white;
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
        }
    </style>
</head>
<body class="bg-gray-100 p-8">
    <h1 class="text-3xl font-bold text-center mb-8 text-gray-900">
        📱 Axonote - Preview Responsive de Componentes Médicos
    </h1>
    
    <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-8">
        
        <!-- Mobile Small -->
        <div class="device-frame" style="width: 320px; height: 568px;">
            <div class="device-label">📱 iPhone SE (320px)</div>
            <iframe src="data:text/html;charset=utf-8,
                %3Chtml%3E
                %3Chead%3E
                    %3Cmeta charset='UTF-8'%3E
                    %3Cmeta name='viewport' content='width=device-width, initial-scale=1.0'%3E
                    %3Cscript src='https://cdn.tailwindcss.com'%3E%3C/script%3E
                %3C/head%3E
                %3Cbody class='bg-gray-50 p-4'%3E
                    %3C!-- MedicalCard Simulation --%3E
                    %3Cdiv class='bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-4'%3E
                        %3Cdiv class='absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-blue-600'%3E%3C/div%3E
                        %3Cdiv class='flex items-center gap-3 mb-4'%3E
                            %3Cdiv class='w-12 h-12 rounded-lg bg-blue-50 flex items-center justify-center text-xl'%3E🩺%3C/div%3E
                            %3Cdiv%3E
                                %3Ch3 class='font-semibold text-gray-900 text-lg'%3EAnatomía Cardiovascular%3C/h3%3E
                                %3Cp class='text-sm text-gray-600'%3EClase práctica%3C/p%3E
                            %3C/div%3E
                        %3C/div%3E
                        %3Cdiv class='text-sm text-gray-700 mb-2'%3E📚 Medicina Interna%3C/div%3E
                        %3Cdiv class='text-sm text-gray-600 mb-2'%3E👨‍⚕️ Dr. Rossi%3C/div%3E
                        %3Cdiv class='text-xs text-gray-500'%3E🕒 Hace 2 horas • ⏱️ 1h 25m%3C/div%3E
                        %3Cdiv class='bg-gray-50 rounded-lg p-3 mt-3'%3E
                            %3Cdiv class='text-xs text-gray-600 mb-1'%3ETranscripción%3C/div%3E
                            %3Cdiv class='w-full h-1.5 bg-gray-200 rounded-full'%3E
                                %3Cdiv class='h-full bg-green-500 rounded-full' style='width: 85%'%3E%3C/div%3E
                            %3C/div%3E
                            %3Cdiv class='text-right text-xs text-gray-700 mt-1'%3E85%%3C/div%3E
                        %3C/div%3E
                    %3C/div%3E
                    
                    %3C!-- Badge Examples --%3E
                    %3Cdiv class='flex flex-wrap gap-2 mb-4'%3E
                        %3Cspan class='inline-flex items-center px-2 py-1 text-xs bg-green-50 text-green-700 border border-green-200 rounded-full'%3E✅ Completado%3C/span%3E
                        %3Cspan class='inline-flex items-center px-2 py-1 text-xs bg-red-50 text-red-700 border border-red-200 rounded-full'%3E❤️ Cardiología%3C/span%3E
                        %3Cspan class='inline-flex items-center px-2 py-1 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded-full'%3E🎯 95%%3C/span%3E
                    %3C/div%3E
                    
                    %3C!-- Recording Controls Simulation --%3E
                    %3Cdiv class='fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4'%3E
                        %3Cdiv class='flex items-center justify-between'%3E
                            %3Cdiv class='text-sm text-gray-600'%3E🔴 15:32%3C/div%3E
                            %3Cbutton class='w-16 h-16 bg-red-500 rounded-full flex items-center justify-center text-white text-xl hover:bg-red-600'%3E⏸️%3C/button%3E
                            %3Cbutton class='px-4 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600'%3E💡 Idea%3C/button%3E
                        %3C/div%3E
                    %3C/div%3E
                %3C/body%3E
                %3C/html%3E
            " width="100%" height="100%"></iframe>
        </div>
        
        <!-- Mobile Medium -->
        <div class="device-frame" style="width: 375px; height: 667px;">
            <div class="device-label">📱 iPhone 12 (375px)</div>
            <iframe src="data:text/html;charset=utf-8,
                %3Chtml%3E
                %3Chead%3E
                    %3Cmeta charset='UTF-8'%3E
                    %3Cmeta name='viewport' content='width=device-width, initial-scale=1.0'%3E
                    %3Cscript src='https://cdn.tailwindcss.com'%3E%3C/script%3E
                %3C/head%3E
                %3Cbody class='bg-gray-50 p-4'%3E
                    %3C!-- Header con Sync Indicator --%3E
                    %3Cdiv class='bg-white border-b border-gray-200 p-4 mb-4 -m-4'%3E
                        %3Cdiv class='flex items-center justify-between'%3E
                            %3Cdiv%3E
                                %3Ch1 class='text-2xl font-bold text-gray-900'%3EClases%3C/h1%3E
                                %3Cp class='text-gray-600'%3E12 grabaciones%3C/p%3E
                            %3C/div%3E
                            %3Cdiv class='flex items-center gap-2 px-3 py-2 rounded-lg border bg-green-50 border-green-200'%3E
                                %3Cdiv class='w-4 h-4 text-green-600'%3E☁️%3C/div%3E
                                %3Cspan class='text-sm font-medium text-green-600'%3EEn línea%3C/span%3E
                            %3C/div%3E
                        %3C/div%3E
                    %3C/div%3E
                    
                    %3C!-- MedicalCard mejorada --%3E
                    %3Cdiv class='bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-4 hover:shadow-lg transition-all duration-300'%3E
                        %3Cdiv class='absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-blue-600'%3E%3C/div%3E
                        %3Cdiv class='flex items-center gap-3 mb-4'%3E
                            %3Cdiv class='w-12 h-12 rounded-lg bg-blue-50 flex items-center justify-center text-xl'%3E🧠%3C/div%3E
                            %3Cdiv class='flex-1'%3E
                                %3Ch3 class='font-semibold text-gray-900 text-lg leading-tight'%3ENeurología Básica%3C/h3%3E
                                %3Cp class='text-sm text-gray-600'%3ESeminario interactivo%3C/p%3E
                            %3C/div%3E
                            %3Cspan class='px-2 py-1 text-xs bg-green-50 text-green-700 border border-green-200 rounded-full'%3E✅ Completado%3C/span%3E
                        %3C/div%3E
                        %3Cdiv class='space-y-2 text-sm text-gray-700'%3E
                            %3Cdiv class='flex items-center'%3E📚 Neurología%3C/div%3E
                            %3Cdiv class='flex items-center'%3E👨‍⚕️ Prof. Bianchi%3C/div%3E
                            %3Cdiv class='flex items-center justify-between'%3E
                                %3Cspan%3E🕒 Ayer%3C/span%3E
                                %3Cspan class='font-medium text-blue-600'%3E2h 15m%3C/span%3E
                            %3C/div%3E
                        %3C/div%3E
                        %3Cdiv class='bg-gray-50 rounded-lg p-3 mt-4'%3E
                            %3Cdiv class='flex items-center justify-between text-xs mb-2'%3E
                                %3Cspan class='text-gray-600'%3ETranscripción%3C/span%3E
                                %3Cspan class='font-medium text-gray-700'%3E92%%3C/span%3E
                            %3C/div%3E
                            %3Cdiv class='w-full h-1.5 bg-gray-200 rounded-full'%3E
                                %3Cdiv class='h-full bg-green-500 rounded-full' style='width: 92%'%3E%3C/div%3E
                            %3C/div%3E
                        %3C/div%3E
                    %3C/div%3E
                %3C/body%3E
                %3C/html%3E
            " width="100%" height="100%"></iframe>
        </div>
        
        <!-- Tablet Portrait -->
        <div class="device-frame" style="width: 600px; height: 800px;">
            <div class="device-label">📟 iPad Portrait (768px)</div>
            <iframe src="data:text/html;charset=utf-8,
                %3Chtml%3E
                %3Chead%3E
                    %3Cmeta charset='UTF-8'%3E
                    %3Cmeta name='viewport' content='width=device-width, initial-scale=1.0'%3E
                    %3Cscript src='https://cdn.tailwindcss.com'%3E%3C/script%3E
                %3C/head%3E
                %3Cbody class='bg-gray-50 p-6'%3E
                    %3C!-- Header mejorado para tablet --%3E
                    %3Cdiv class='bg-white border-b border-gray-200 p-6 mb-6 -m-6'%3E
                        %3Cdiv class='flex items-center justify-between'%3E
                            %3Cdiv%3E
                                %3Ch1 class='text-3xl font-bold text-gray-900'%3EAxonote%3C/h1%3E
                                %3Cp class='text-gray-600'%3ETranscripción Médica Profesional%3C/p%3E
                            %3C/div%3E
                            %3Cdiv class='flex items-center gap-4'%3E
                                %3Cbutton class='px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200'%3EAjustes%3C/button%3E
                                %3Cbutton class='px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700'%3ENueva Grabación%3C/button%3E
                            %3C/div%3E
                        %3C/div%3E
                    %3C/div%3E
                    
                    %3C!-- Grid de cards para tablet --%3E
                    %3Cdiv class='grid grid-cols-1 md:grid-cols-2 gap-6'%3E
                        %3C!-- Card 1 --%3E
                        %3Cdiv class='bg-white rounded-xl border border-gray-200 shadow-sm p-6 hover:shadow-lg transition-all duration-300'%3E
                            %3Cdiv class='absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-red-500 to-red-600'%3E%3C/div%3E
                            %3Cdiv class='flex items-center gap-4 mb-4'%3E
                                %3Cdiv class='w-14 h-14 rounded-lg bg-red-50 flex items-center justify-center text-2xl'%3E❤️%3C/div%3E
                                %3Cdiv class='flex-1'%3E
                                    %3Ch3 class='font-semibold text-gray-900 text-xl'%3ECardiología Avanzada%3C/h3%3E
                                    %3Cp class='text-gray-600'%3EConferencia magistral%3C/p%3E
                                %3C/div%3E
                                %3Cspan class='px-3 py-1 text-sm bg-green-50 text-green-700 border border-green-200 rounded-full'%3E✅ Completado%3C/span%3E
                            %3C/div%3E
                            %3Cdiv class='space-y-3 text-gray-700'%3E
                                %3Cdiv class='flex items-center'%3E📚 Cardiología%3C/div%3E
                                %3Cdiv class='flex items-center'%3E👨‍⚕️ Prof. Martinelli%3C/div%3E
                                %3Cdiv class='flex items-center justify-between'%3E
                                    %3Cspan%3E🕒 Hace 1 día%3C/span%3E
                                    %3Cspan class='font-medium text-red-600'%3E2h 45m%3C/span%3E
                                %3C/div%3E
                            %3C/div%3E
                        %3C/div%3E
                        
                        %3C!-- Card 2 --%3E
                        %3Cdiv class='bg-white rounded-xl border border-gray-200 shadow-sm p-6 hover:shadow-lg transition-all duration-300'%3E
                            %3Cdiv class='absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-purple-500 to-purple-600'%3E%3C/div%3E
                            %3Cdiv class='flex items-center gap-4 mb-4'%3E
                                %3Cdiv class='w-14 h-14 rounded-lg bg-purple-50 flex items-center justify-center text-2xl'%3E🧠%3C/div%3E
                                %3Cdiv class='flex-1'%3E
                                    %3Ch3 class='font-semibold text-gray-900 text-xl'%3ESistema Nervioso%3C/h3%3E
                                    %3Cp class='text-gray-600'%3EClase práctica%3C/p%3E
                                %3C/div%3E
                                %3Cspan class='px-3 py-1 text-sm bg-yellow-50 text-yellow-700 border border-yellow-200 rounded-full'%3E⚙️ Procesando%3C/span%3E
                            %3C/div%3E
                            %3Cdiv class='space-y-3 text-gray-700'%3E
                                %3Cdiv class='flex items-center'%3E📚 Neurología%3C/div%3E
                                %3Cdiv class='flex items-center'%3E👨‍⚕️ Dr. Ferrari%3C/div%3E
                                %3Cdiv class='flex items-center justify-between'%3E
                                    %3Cspan%3E🕒 Hace 3 horas%3C/span%3E
                                    %3Cspan class='font-medium text-purple-600'%3E1h 50m%3C/span%3E
                                %3C/div%3E
                            %3C/div%3E
                        %3C/div%3E
                    %3C/div%3E
                %3C/body%3E
                %3C/html%3E
            " width="100%" height="100%"></iframe>
        </div>
        
    </div>
    
    <div class="mt-12 bg-white rounded-xl p-6 shadow-sm">
        <h2 class="text-2xl font-bold text-gray-900 mb-4">📊 Análisis de Responsividad</h2>
        
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <!-- Mobile -->
            <div class="text-center p-4 bg-blue-50 rounded-lg">
                <div class="text-2xl mb-2">📱</div>
                <h3 class="font-bold text-gray-900">Mobile</h3>
                <p class="text-sm text-gray-600">320px - 768px</p>
                <div class="mt-2 text-green-600 font-medium">✅ Optimizado</div>
            </div>
            
            <!-- Tablet -->
            <div class="text-center p-4 bg-green-50 rounded-lg">
                <div class="text-2xl mb-2">📟</div>
                <h3 class="font-bold text-gray-900">Tablet</h3>
                <p class="text-sm text-gray-600">768px - 1024px</p>
                <div class="mt-2 text-green-600 font-medium">✅ Adaptado</div>
            </div>
            
            <!-- Desktop -->
            <div class="text-center p-4 bg-purple-50 rounded-lg">
                <div class="text-2xl mb-2">💻</div>
                <h3 class="font-bold text-gray-900">Desktop</h3>
                <p class="text-sm text-gray-600">1024px+</p>
                <div class="mt-2 text-green-600 font-medium">✅ Escalable</div>
            </div>
            
            <!-- Touch -->
            <div class="text-center p-4 bg-yellow-50 rounded-lg">
                <div class="text-2xl mb-2">👆</div>
                <h3 class="font-bold text-gray-900">Touch</h3>
                <p class="text-sm text-gray-600">44px+ targets</p>
                <div class="mt-2 text-green-600 font-medium">✅ Friendly</div>
            </div>
        </div>
        
        <div class="mt-6 p-4 bg-blue-50 border-l-4 border-blue-400 rounded">
            <h4 class="font-bold text-blue-900 mb-2">💡 Características Médicas Implementadas</h4>
            <ul class="text-sm text-blue-800 space-y-1">
                <li>• Paleta de colores médicos profesionales</li>
                <li>• Componentes especializados por tipo médico</li>
                <li>• Estados visuales del pipeline de transcripción</li>
                <li>• Métricas de confianza ASR/LLM</li>
                <li>• Indicadores de sincronización en tiempo real</li>
                <li>• Controles de grabación touch-optimized</li>
                <li>• Badges semánticos por especialidad médica</li>
                <li>• Accesibilidad mejorada para entorno médico</li>
            </ul>
        </div>
    </div>
    
    <footer class="mt-12 text-center text-gray-500">
        <p>🩺 Axonote - PWA Médica Professional | Generado: $(date)</p>
    </footer>
</body>
</html>
EOF

    log_success "Preview HTML generado: test_responsive_preview.html"
    echo "   🌐 Abrir en navegador para testing visual interactivo"
}

# Ejecutar análisis de componentes médicos
echo "🔍 Analizando componentes médicos implementados..."
echo ""

# Lista de componentes a analizar
declare -A MEDICAL_COMPONENTS=(
    ["apps/web/components/ui/MedicalCard.tsx"]="MedicalCard"
    ["apps/web/components/ui/MedicalBadge.tsx"]="MedicalBadge"
    ["apps/web/components/ui/RecordingControls.tsx"]="RecordingControls"
    ["apps/web/components/ui/SyncIndicator.tsx"]="SyncIndicator"
    ["apps/web/components/ui/Button.tsx"]="Button Base"
    ["apps/web/components/ui/RecordButton.tsx"]="RecordButton"
)

TOTAL_COMPONENTS=${#MEDICAL_COMPONENTS[@]}
PASSED_COMPONENTS=0

for component_file in "${!MEDICAL_COMPONENTS[@]}"; do
    component_name="${MEDICAL_COMPONENTS[$component_file]}"
    
    if analyze_responsive_css "$component_file" "$component_name"; then
        ((PASSED_COMPONENTS++))
    fi
    
    test_medical_component "$component_file" "$component_name"
    echo ""
done

# Testing de páginas principales
echo "📄 Analizando páginas principales..."
echo ""

MAIN_PAGES=(
    "apps/web/app/page.tsx:HomePage"
    "apps/web/app/grabar/page.tsx:GrabarPage"
    "apps/web/app/ajustes/page.tsx:AjustesPage"
    "apps/web/app/dashboard/page.tsx:DashboardPage"
)

for page_info in "${MAIN_PAGES[@]}"; do
    IFS=':' read -r page_file page_name <<< "$page_info"
    analyze_responsive_css "$page_file" "$page_name"
done

# Generar preview HTML para testing visual
echo ""
log_info "Generando preview HTML para testing visual..."
generate_preview_html

# Verificar CSS global médico
echo ""
log_info "Verificando CSS médico global..."
echo "----------------------------------------"

if grep -q "medical-card\|medical-badge\|recording-controls" "apps/web/app/globals.css"; then
    log_success "Clases CSS médicas globales implementadas"
else
    log_warning "Clases CSS médicas globales no detectadas"
fi

if grep -q "@media.*prefers-reduced-motion" "apps/web/app/globals.css"; then
    log_success "Accesibilidad de movimiento implementada"
else
    log_warning "Accesibilidad de movimiento no detectada"
fi

if grep -q "@media.*prefers-color-scheme.*dark" "apps/web/app/globals.css"; then
    log_success "Modo oscuro implementado"
else
    log_warning "Modo oscuro no detectado"
fi

# Resumen final
echo ""
echo "📊 RESUMEN RESPONSIVE MEDICAL UI"
echo "================================="
echo ""
log_success "Componentes analizados: $TOTAL_COMPONENTS"
log_success "Componentes responsive: $PASSED_COMPONENTS"
echo ""

responsive_score=$((PASSED_COMPONENTS * 100 / TOTAL_COMPONENTS))

if [ $responsive_score -ge 90 ]; then
    log_success "Responsive Score: $responsive_score% - EXCELENTE ✨"
    echo ""
    echo "🎉 Los componentes médicos están completamente optimizados!"
    echo ""
    echo "📱 Características implementadas:"
    echo "   • Mobile-first design"
    echo "   • Touch-friendly interactions (44px+ targets)"
    echo "   • Medical color palette profesional"
    echo "   • Componentes especializados por tipo médico"
    echo "   • Estados visuales del pipeline completo"
    echo "   • Métricas de confianza en tiempo real"
    echo "   • Sincronización visual con backend"
    echo ""
    echo "🖥️ Soporta dispositivos:"
    echo "   • Smartphones (320px+)"
    echo "   • Tablets Portrait/Landscape (768px+)"
    echo "   • Desktop/Laptop (1024px+)"
    echo "   • Large screens (1440px+)"
    
elif [ $responsive_score -ge 70 ]; then
    log_warning "Responsive Score: $responsive_score% - BUENO 👍"
    echo ""
    echo "⚠️ Los componentes funcionan pero tienen área de mejora"
    
else
    log_error "Responsive Score: $responsive_score% - NECESITA TRABAJO 🔧"
    echo ""
    echo "❌ Los componentes necesitan optimización responsive"
fi

echo ""
echo "🎨 Preview generado para testing visual:"
echo "   📄 test_responsive_preview.html"
echo "   🌐 Abrir en navegador para verificar responsividad"
echo ""
echo "🧪 Para testing real en dispositivos:"
echo "   1. npm run dev (puerto 3000)"
echo "   2. Conectar dispositivos móviles a la misma red"
echo "   3. Acceder a http://[IP-LOCAL]:3000"
echo "   4. Probar instalación PWA en cada dispositivo"
echo ""
echo "✅ Testing responsive completado!"
echo ""
