#!/bin/bash

# =============================================================================
# SCRIPT DE INSTALACIÓN AUTOMÁTICA DE AXONOTE
# =============================================================================
# Script para instalación completa de AxoNote en servidor LAMP
# Compatible con Ubuntu 20.04+, Ubuntu 22.04+, Debian 11+, Debian 12+
# 
# Uso: sudo bash install-axonote.sh
# 
# Autor: AxoNote Team
# Fecha: Septiembre 2025
# Versión: 1.0.0
# =============================================================================

set -euo pipefail  # Salir en cualquier error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Variables globales
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/axonote-install.log"
INSTALL_DIR="/var/www/html/axonote"
BACKUP_DIR="/var/backups/axonote"
AXONOTE_USER="axonote"
DB_NAME="axonote"
DB_USER="axonote_user"

# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log_info() {
    log "${BLUE}[INFO]${NC} $*"
}

log_success() {
    log "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    log "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    log "${RED}[ERROR]${NC} $*"
}

log_step() {
    log "${PURPLE}[STEP]${NC} $*"
}

# Función para mostrar spinner durante operaciones largas
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# Función para confirmar acciones críticas
confirm() {
    local message="$1"
    local default="${2:-n}"
    
    while true; do
        if [[ "$default" == "y" ]]; then
            read -p "$message [Y/n]: " choice
            choice=${choice:-y}
        else
            read -p "$message [y/N]: " choice
            choice=${choice:-n}
        fi
        
        case $choice in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Por favor responde 'y' o 'n'.";;
        esac
    done
}

# Función para validar entrada no vacía
validate_not_empty() {
    local var_name="$1"
    local var_value="$2"
    local prompt="$3"
    
    while [[ -z "$var_value" ]]; do
        log_error "$var_name no puede estar vacío."
        read -p "$prompt: " var_value
    done
    echo "$var_value"
}

# Función para validar URL de Git
validate_git_url() {
    local url="$1"
    
    if [[ ! "$url" =~ ^https?://github\.com/.+/.+\.git$ ]] && [[ ! "$url" =~ ^git@github\.com:.+/.+\.git$ ]]; then
        return 1
    fi
    return 0
}

# Función para validar email
validate_email() {
    local email="$1"
    local regex="^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    
    if [[ $email =~ $regex ]]; then
        return 0
    else
        return 1
    fi
}

# Función para generar password seguro
generate_secure_password() {
    local length="${1:-32}"
    openssl rand -base64 $length | tr -d "=+/" | cut -c1-$length
}

# Función para validar password
validate_password() {
    local password="$1"
    local min_length=12
    
    if [[ ${#password} -lt $min_length ]]; then
        log_error "La contraseña debe tener al menos $min_length caracteres."
        return 1
    fi
    
    if [[ ! "$password" =~ [A-Z] ]]; then
        log_error "La contraseña debe contener al menos una letra mayúscula."
        return 1
    fi
    
    if [[ ! "$password" =~ [a-z] ]]; then
        log_error "La contraseña debe contener al menos una letra minúscula."
        return 1
    fi
    
    if [[ ! "$password" =~ [0-9] ]]; then
        log_error "La contraseña debe contener al menos un número."
        return 1
    fi
    
    if [[ ! "$password" =~ [^a-zA-Z0-9] ]]; then
        log_error "La contraseña debe contener al menos un carácter especial."
        return 1
    fi
    
    return 0
}

# =============================================================================
# VERIFICACIONES INICIALES
# =============================================================================

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Este script debe ejecutarse como root (sudo)."
        log_info "Uso: sudo bash $0"
        exit 1
    fi
    log_success "Ejecutándose como root ✓"
}

check_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
        CODENAME=$VERSION_CODENAME
    else
        log_error "No se puede detectar el sistema operativo."
        exit 1
    fi
    
    case $OS in
        "Ubuntu")
            if [[ $(echo "$VER >= 20.04" | bc -l) -eq 1 ]]; then
                log_success "Sistema operativo soportado: $OS $VER ✓"
                PACKAGE_MANAGER="apt"
            else
                log_error "Ubuntu $VER no soportado. Se requiere Ubuntu 20.04 o superior."
                exit 1
            fi
            ;;
        "Debian GNU/Linux")
            if [[ $(echo "$VER >= 11" | bc -l) -eq 1 ]]; then
                log_success "Sistema operativo soportado: $OS $VER ✓"
                PACKAGE_MANAGER="apt"
            else
                log_error "Debian $VER no soportado. Se requiere Debian 11 o superior."
                exit 1
            fi
            ;;
        *)
            log_error "Sistema operativo no soportado: $OS"
            log_info "Este script soporta Ubuntu 20.04+ y Debian 11+"
            exit 1
            ;;
    esac
}

check_internet() {
    log_info "Verificando conexión a internet..."
    if ping -c 1 google.com &> /dev/null; then
        log_success "Conexión a internet activa ✓"
    else
        log_error "No hay conexión a internet. Verifique su configuración de red."
        exit 1
    fi
}

check_system_resources() {
    log_info "Verificando recursos del sistema..."
    
    # Verificar RAM (mínimo 4GB)
    total_ram=$(free -m | awk 'NR==2{print $2}')
    if [[ $total_ram -lt 4000 ]]; then
        log_warning "RAM insuficiente: ${total_ram}MB. Se recomienda al menos 4GB."
        if ! confirm "¿Continuar con la instalación?"; then
            exit 1
        fi
    else
        log_success "RAM suficiente: ${total_ram}MB ✓"
    fi
    
    # Verificar espacio en disco (mínimo 10GB)
    available_space=$(df / | awk 'NR==2{print $4}')
    available_space_gb=$((available_space / 1024 / 1024))
    if [[ $available_space_gb -lt 10 ]]; then
        log_warning "Espacio en disco insuficiente: ${available_space_gb}GB. Se recomienda al menos 10GB."
        if ! confirm "¿Continuar con la instalación?"; then
            exit 1
        fi
    else
        log_success "Espacio en disco suficiente: ${available_space_gb}GB ✓"
    fi
}

# =============================================================================
# RECOLECCIÓN DE INFORMACIÓN
# =============================================================================

collect_user_input() {
    log_step "Recolectando información de configuración..."
    
    # Repositorio Git
    while true; do
        read -p "URL del repositorio de GitHub: " GIT_REPO_URL
        GIT_REPO_URL=$(validate_not_empty "URL del repositorio" "$GIT_REPO_URL" "URL del repositorio de GitHub")
        
        if validate_git_url "$GIT_REPO_URL"; then
            break
        else
            log_error "URL de repositorio inválida. Debe ser una URL válida de GitHub."
            log_info "Ejemplo: https://github.com/usuario/axonote.git"
        fi
    done
    log_success "Repositorio: $GIT_REPO_URL ✓"
    
    # Dominio
    read -p "Dominio del sitio web (ej: axonote.ejemplo.com): " DOMAIN_NAME
    DOMAIN_NAME=$(validate_not_empty "Dominio" "$DOMAIN_NAME" "Dominio del sitio web")
    log_success "Dominio: $DOMAIN_NAME ✓"
    
    # Email del administrador
    while true; do
        read -p "Email del administrador: " ADMIN_EMAIL
        ADMIN_EMAIL=$(validate_not_empty "Email del administrador" "$ADMIN_EMAIL" "Email del administrador")
        
        if validate_email "$ADMIN_EMAIL"; then
            break
        else
            log_error "Email inválido. Por favor ingrese un email válido."
        fi
    done
    log_success "Email del administrador: $ADMIN_EMAIL ✓"
    
    # Contraseña de base de datos
    while true; do
        read -s -p "Contraseña para la base de datos (mín. 12 caracteres): " DB_PASSWORD
        echo
        
        if [[ -z "$DB_PASSWORD" ]]; then
            log_error "La contraseña no puede estar vacía."
            continue
        fi
        
        if validate_password "$DB_PASSWORD"; then
            read -s -p "Confirme la contraseña: " DB_PASSWORD_CONFIRM
            echo
            
            if [[ "$DB_PASSWORD" == "$DB_PASSWORD_CONFIRM" ]]; then
                break
            else
                log_error "Las contraseñas no coinciden. Intente nuevamente."
            fi
        fi
    done
    log_success "Contraseña de base de datos configurada ✓"
    
    # Generar clave secreta
    SECRET_KEY=$(generate_secure_password 64)
    log_success "Clave secreta generada ✓"
    
    # Configuración de IA
    log_info ""
    log_info "Configuración de IA (opcional):"
    if confirm "¿Tiene una GPU NVIDIA para procesamiento de IA local?"; then
        USE_GPU=true
        log_success "GPU habilitada para IA local ✓"
    else
        USE_GPU=false
        log_info "Se configurará IA con CPU (más lento)"
    fi
    
    # OpenAI API Key (opcional)
    log_info ""
    log_info "OpenAI API Key (opcional, para funcionalidades avanzadas):"
    read -p "OpenAI API Key (opcional, presione Enter para omitir): " OPENAI_API_KEY
    if [[ -n "$OPENAI_API_KEY" ]]; then
        log_success "OpenAI API Key configurada ✓"
    else
        log_info "OpenAI API Key omitida (se puede configurar después)"
    fi
    
    # SSL automático
    if confirm "¿Configurar SSL automáticamente con Let's Encrypt?" "y"; then
        SETUP_SSL=true
        log_success "SSL automático habilitado ✓"
    else
        SETUP_SSL=false
        log_warning "SSL manual - deberá configurar certificados manualmente"
    fi
}

# =============================================================================
# INSTALACIÓN DE DEPENDENCIAS
# =============================================================================

update_system() {
    log_step "Actualizando sistema..."
    
    export DEBIAN_FRONTEND=noninteractive
    
    $PACKAGE_MANAGER update -y &
    spinner $!
    wait
    
    $PACKAGE_MANAGER upgrade -y &
    spinner $!
    wait
    
    log_success "Sistema actualizado ✓"
}

install_base_packages() {
    log_step "Instalando paquetes base..."
    
    local packages=(
        curl wget unzip git
        build-essential
        software-properties-common
        apt-transport-https
        ca-certificates
        gnupg
        lsb-release
        bc
        mailutils
        ufw
        fail2ban
        htop
        nano
        tree
        jq
    )
    
    export DEBIAN_FRONTEND=noninteractive
    $PACKAGE_MANAGER install -y "${packages[@]}" &
    spinner $!
    wait
    
    log_success "Paquetes base instalados ✓"
}

install_apache() {
    log_step "Instalando Apache..."
    
    $PACKAGE_MANAGER install -y apache2 &
    spinner $!
    wait
    
    # Habilitar módulos necesarios
    a2enmod rewrite ssl headers proxy proxy_http expires
    
    systemctl enable apache2
    systemctl start apache2
    
    log_success "Apache instalado y configurado ✓"
}

install_postgresql() {
    log_step "Instalando PostgreSQL..."
    
    $PACKAGE_MANAGER install -y postgresql postgresql-contrib &
    spinner $!
    wait
    
    systemctl enable postgresql
    systemctl start postgresql
    
    # Crear base de datos y usuario
    log_info "Configurando base de datos..."
    sudo -u postgres psql << EOF
CREATE DATABASE $DB_NAME;
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
ALTER USER $DB_USER CREATEDB;
\q
EOF
    
    log_success "PostgreSQL instalado y configurado ✓"
}

install_redis() {
    log_step "Instalando Redis..."
    
    $PACKAGE_MANAGER install -y redis-server &
    spinner $!
    wait
    
    systemctl enable redis-server
    systemctl start redis-server
    
    # Verificar instalación
    if redis-cli ping | grep -q "PONG"; then
        log_success "Redis instalado y funcionando ✓"
    else
        log_error "Error en la instalación de Redis"
        exit 1
    fi
}

install_python() {
    log_step "Instalando Python 3.11..."
    
    # Agregar repositorio para Python 3.11
    add-apt-repository ppa:deadsnakes/ppa -y
    $PACKAGE_MANAGER update -y
    
    $PACKAGE_MANAGER install -y python3.11 python3.11-venv python3.11-dev python3-pip &
    spinner $!
    wait
    
    # Instalar Poetry
    log_info "Instalando Poetry..."
    curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - &
    spinner $!
    wait
    
    ln -sf /opt/poetry/bin/poetry /usr/local/bin/poetry
    
    log_success "Python 3.11 y Poetry instalados ✓"
}

install_nodejs() {
    log_step "Instalando Node.js 18..."
    
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - &
    spinner $!
    wait
    
    $PACKAGE_MANAGER install -y nodejs &
    spinner $!
    wait
    
    # Verificar instalación
    NODE_VERSION=$(node --version)
    NPM_VERSION=$(npm --version)
    
    log_success "Node.js $NODE_VERSION y npm $NPM_VERSION instalados ✓"
}

install_ai_dependencies() {
    log_step "Instalando dependencias de IA..."
    
    # FFmpeg para procesamiento de audio
    $PACKAGE_MANAGER install -y ffmpeg &
    spinner $!
    wait
    
    # Tesseract OCR
    $PACKAGE_MANAGER install -y tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng &
    spinner $!
    wait
    
    # Dependencias de compilación para Python ML
    $PACKAGE_MANAGER install -y libffi-dev libssl-dev pkg-config &
    spinner $!
    wait
    
    if [[ "$USE_GPU" == true ]]; then
        log_info "Instalando drivers NVIDIA..."
        
        # Detectar y instalar drivers NVIDIA
        ubuntu-drivers autoinstall &
        spinner $!
        wait
        
        log_warning "Se requiere reiniciar el sistema después de la instalación para cargar los drivers de GPU."
    fi
    
    log_success "Dependencias de IA instaladas ✓"
}

# =============================================================================
# CONFIGURACIÓN DEL USUARIO DEL SISTEMA
# =============================================================================

create_system_user() {
    log_step "Creando usuario del sistema..."
    
    if id "$AXONOTE_USER" &>/dev/null; then
        log_warning "Usuario $AXONOTE_USER ya existe, omitiendo creación."
    else
        useradd -r -m -s /bin/bash "$AXONOTE_USER"
        usermod -aG www-data "$AXONOTE_USER"
        log_success "Usuario $AXONOTE_USER creado ✓"
    fi
    
    # Crear directorios necesarios
    mkdir -p "$INSTALL_DIR" "$BACKUP_DIR" "/var/log/axonote" "/var/lib/axonote"
    chown -R "$AXONOTE_USER:www-data" "$INSTALL_DIR" "$BACKUP_DIR" "/var/log/axonote" "/var/lib/axonote"
    chmod -R 755 "$INSTALL_DIR" "$BACKUP_DIR"
    
    log_success "Directorios del sistema creados ✓"
}

# =============================================================================
# DESCARGA E INSTALACIÓN DEL PROYECTO
# =============================================================================

clone_repository() {
    log_step "Clonando repositorio de AxoNote..."
    
    # Limpiar directorio si existe
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log_warning "Directorio $INSTALL_DIR ya contiene un repositorio git."
        if confirm "¿Eliminar y clonar nuevamente?"; then
            rm -rf "$INSTALL_DIR"
            mkdir -p "$INSTALL_DIR"
        else
            log_info "Actualizando repositorio existente..."
            cd "$INSTALL_DIR"
            sudo -u "$AXONOTE_USER" git pull origin main
            return
        fi
    fi
    
    # Clonar repositorio
    cd "$(dirname "$INSTALL_DIR")"
    sudo -u "$AXONOTE_USER" git clone "$GIT_REPO_URL" "$(basename "$INSTALL_DIR")" &
    spinner $!
    wait
    
    cd "$INSTALL_DIR"
    
    # Verificar estructura del proyecto
    if [[ ! -f "apps/api/pyproject.toml" ]] || [[ ! -f "apps/web/package.json" ]]; then
        log_error "Estructura del proyecto incorrecta. Verifique que el repositorio sea correcto."
        exit 1
    fi
    
    chown -R "$AXONOTE_USER:www-data" "$INSTALL_DIR"
    
    log_success "Repositorio clonado correctamente ✓"
}

install_backend_dependencies() {
    log_step "Instalando dependencias del backend..."
    
    cd "$INSTALL_DIR/apps/api"
    
    # Crear entorno virtual
    sudo -u "$AXONOTE_USER" python3.11 -m venv venv
    
    # Instalar dependencias
    sudo -u "$AXONOTE_USER" bash -c "
        source venv/bin/activate
        pip install --upgrade pip setuptools wheel
        poetry install --no-dev --no-interaction
    " &
    spinner $!
    wait
    
    log_success "Dependencias del backend instaladas ✓"
}

install_frontend_dependencies() {
    log_step "Instalando dependencias del frontend..."
    
    cd "$INSTALL_DIR/apps/web"
    
    sudo -u "$AXONOTE_USER" npm ci --production &
    spinner $!
    wait
    
    log_success "Dependencias del frontend instaladas ✓"
}

# =============================================================================
# CONFIGURACIÓN DE LA APLICACIÓN
# =============================================================================

create_env_file() {
    log_step "Creando archivo de configuración..."
    
    cat > "$INSTALL_DIR/.env" << EOF
# ==============================================
# AXONOTE - Configuración de Producción
# ==============================================
# Generado automáticamente por el script de instalación
# Fecha: $(date)

# Aplicación
APP_ENV=production
SECRET_KEY=$SECRET_KEY
API_PORT=8000
API_HOST=127.0.0.1
CORS_ORIGINS=https://$DOMAIN_NAME,https://www.$DOMAIN_NAME

# Base de Datos
DATABASE_URL=postgresql+psycopg://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
DATABASE_ECHO=false

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Almacenamiento
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/var/lib/axonote/uploads
MINIO_BUCKET=recordings

# Administrador
ADMIN_EMAIL=$ADMIN_EMAIL

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/var/log/axonote/app.log

# Seguridad
RATE_LIMIT_PER_MINUTE=60
MAX_UPLOAD_SIZE_MB=500
ALLOWED_AUDIO_FORMATS=wav,mp3,m4a,flac,ogg
ALLOWED_IMAGE_FORMATS=jpg,jpeg,png,webp

# IA/ML
EOF

    if [[ "$USE_GPU" == true ]]; then
        cat >> "$INSTALL_DIR/.env" << EOF
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
USE_WHISPERX=true
DIARIZATION_DEVICE=cuda
EOF
    else
        cat >> "$INSTALL_DIR/.env" << EOF
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
USE_WHISPERX=false
DIARIZATION_DEVICE=cpu
EOF
    fi

    if [[ -n "$OPENAI_API_KEY" ]]; then
        cat >> "$INSTALL_DIR/.env" << EOF

# OpenAI
OPENAI_API_KEY=$OPENAI_API_KEY
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_MONTHLY_COST=25.0
LLM_PROVIDER=openai
EOF
    else
        cat >> "$INSTALL_DIR/.env" << EOF

# LLM (sin OpenAI)
LLM_PROVIDER=local
EOF
    fi

    cat >> "$INSTALL_DIR/.env" << EOF

# Features
FEATURE_OCR=true
FEATURE_TTS=true
FEATURE_BATCH_REPROCESS=true
ENABLE_MEDICAL_RESEARCH=true

# Fuentes médicas
ALLOWED_MEDICAL_SOURCES=who.int,ecdc.europa.eu,cdc.gov,nih.gov,pubmed.ncbi.nlm.nih.gov

# Idiomas
DEFAULT_SOURCE_LANGUAGE=it
OUTPUT_LANGUAGE=es
SUPPORTED_LANGUAGES=it,en,es

# Monitoring
ENABLE_METRICS=true
METRICS_RETENTION_DAYS=90
ERROR_REPORTING=true
EOF

    chown "$AXONOTE_USER:www-data" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    
    log_success "Archivo de configuración creado ✓"
}

setup_database() {
    log_step "Configurando base de datos..."
    
    cd "$INSTALL_DIR/apps/api"
    
    # Ejecutar migraciones
    sudo -u "$AXONOTE_USER" bash -c "
        source venv/bin/activate
        export \$(cat ../../.env | xargs)
        alembic upgrade head
    "
    
    log_success "Base de datos configurada ✓"
}

build_frontend() {
    log_step "Construyendo frontend..."
    
    cd "$INSTALL_DIR/apps/web"
    
    # Crear archivo de configuración del frontend
    cat > .env.local << EOF
NODE_ENV=production
NEXT_PUBLIC_API_URL=https://$DOMAIN_NAME/api
NEXT_PUBLIC_APP_NAME=AxoNote
NEXT_PUBLIC_APP_VERSION=1.0.0
EOF
    
    chown "$AXONOTE_USER:www-data" .env.local
    
    # Construir aplicación
    sudo -u "$AXONOTE_USER" npm run build &
    spinner $!
    wait
    
    log_success "Frontend construido ✓"
}

# =============================================================================
# CONFIGURACIÓN DE SERVICIOS
# =============================================================================

create_systemd_services() {
    log_step "Creando servicios del sistema..."
    
    # Servicio API
    cat > /etc/systemd/system/axonote-api.service << EOF
[Unit]
Description=AxoNote FastAPI Service
After=network.target postgresql.service redis.service

[Service]
Type=exec
User=$AXONOTE_USER
Group=www-data
WorkingDirectory=$INSTALL_DIR/apps/api
Environment=PATH=$INSTALL_DIR/apps/api/venv/bin
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/apps/api/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Servicio Worker
    cat > /etc/systemd/system/axonote-worker.service << EOF
[Unit]
Description=AxoNote Celery Worker
After=network.target redis.service axonote-api.service

[Service]
Type=exec
User=$AXONOTE_USER
Group=www-data
WorkingDirectory=$INSTALL_DIR/apps/api
Environment=PATH=$INSTALL_DIR/apps/api/venv/bin
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/apps/api/venv/bin/celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Servicio Frontend
    cat > /etc/systemd/system/axonote-web.service << EOF
[Unit]
Description=AxoNote Next.js Frontend
After=network.target

[Service]
Type=exec
User=$AXONOTE_USER
Group=www-data
WorkingDirectory=$INSTALL_DIR/apps/web
Environment=NODE_ENV=production
Environment=NEXT_PUBLIC_API_URL=https://$DOMAIN_NAME/api
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Recargar servicios
    systemctl daemon-reload
    
    # Habilitar servicios
    systemctl enable axonote-api axonote-worker axonote-web
    
    log_success "Servicios del sistema creados ✓"
}

configure_apache_vhost() {
    log_step "Configurando VirtualHost de Apache..."
    
    cat > /etc/apache2/sites-available/axonote.conf << EOF
<VirtualHost *:80>
    ServerName $DOMAIN_NAME
    ServerAlias www.$DOMAIN_NAME
    DocumentRoot $INSTALL_DIR/apps/web
    
    # Redirección a HTTPS
    RewriteEngine On
    RewriteCond %{HTTPS} off
    RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [R=301,L]
    
    ErrorLog \${APACHE_LOG_DIR}/axonote_error.log
    CustomLog \${APACHE_LOG_DIR}/axonote_access.log combined
</VirtualHost>

<VirtualHost *:443>
    ServerName $DOMAIN_NAME
    ServerAlias www.$DOMAIN_NAME
    DocumentRoot $INSTALL_DIR/apps/web
    
    # SSL Configuration (se configurará con Let's Encrypt)
    SSLEngine on
    
    # Security Headers
    Header always set X-Frame-Options DENY
    Header always set X-Content-Type-Options nosniff
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"
    Header always set Referrer-Policy "strict-origin-when-cross-origin"
    
    # Proxy configuración
    ProxyPreserveHost On
    ProxyRequests Off
    
    # API routes -> FastAPI backend
    ProxyPass /api/ http://127.0.0.1:8000/
    ProxyPassReverse /api/ http://127.0.0.1:8000/
    
    # Health checks
    ProxyPass /health http://127.0.0.1:8000/health
    ProxyPassReverse /health http://127.0.0.1:8000/health
    
    # Todo lo demás -> Next.js frontend
    ProxyPass / http://127.0.0.1:3000/
    ProxyPassReverse / http://127.0.0.1:3000/
    
    # WebSocket support
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/?(.*) "ws://127.0.0.1:3000/\$1" [P,L]
    
    # Caching para archivos estáticos
    <LocationMatch "\.(css|js|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$">
        ExpiresActive On
        ExpiresDefault "access plus 1 month"
        Header append Cache-Control "public"
    </LocationMatch>
    
    # PWA files sin cache
    <LocationMatch "\.(json|webmanifest)$">
        Header set Cache-Control "no-cache"
    </LocationMatch>
    
    ErrorLog \${APACHE_LOG_DIR}/axonote_ssl_error.log
    CustomLog \${APACHE_LOG_DIR}/axonote_ssl_access.log combined
</VirtualHost>
EOF

    # Habilitar sitio
    a2ensite axonote.conf
    a2dissite 000-default.conf
    
    # Test configuración
    if apache2ctl configtest; then
        log_success "Configuración de Apache válida ✓"
    else
        log_error "Error en la configuración de Apache"
        exit 1
    fi
    
    systemctl reload apache2
    
    log_success "VirtualHost de Apache configurado ✓"
}

setup_ssl() {
    if [[ "$SETUP_SSL" == true ]]; then
        log_step "Configurando SSL con Let's Encrypt..."
        
        # Instalar Certbot
        $PACKAGE_MANAGER install -y certbot python3-certbot-apache &
        spinner $!
        wait
        
        # Obtener certificado
        log_info "Obteniendo certificado SSL para $DOMAIN_NAME..."
        certbot --apache --non-interactive --agree-tos --email "$ADMIN_EMAIL" \
                --domains "$DOMAIN_NAME,www.$DOMAIN_NAME" &
        spinner $!
        wait
        
        # Configurar renovación automática
        (crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet") | crontab -
        
        log_success "SSL configurado correctamente ✓"
    else
        log_warning "SSL omitido - configurar certificados manualmente"
    fi
}

# =============================================================================
# CONFIGURACIÓN DE SEGURIDAD
# =============================================================================

configure_firewall() {
    log_step "Configurando firewall..."
    
    # Habilitar UFW
    ufw --force enable
    ufw default deny incoming
    ufw default allow outgoing
    
    # Permitir puertos necesarios
    ufw allow 22/tcp   # SSH
    ufw allow 80/tcp   # HTTP
    ufw allow 443/tcp  # HTTPS
    
    # PostgreSQL y Redis solo local
    ufw allow from 127.0.0.1 to any port 5432
    ufw allow from 127.0.0.1 to any port 6379
    
    log_success "Firewall configurado ✓"
}

configure_fail2ban() {
    log_step "Configurando Fail2ban..."
    
    cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
destemail = $ADMIN_EMAIL
sendername = Fail2Ban
mta = sendmail

[sshd]
enabled = true

[apache-auth]
enabled = true

[apache-badbots]
enabled = true

[apache-noscript]
enabled = true

[apache-overflows]
enabled = true
EOF

    systemctl enable fail2ban
    systemctl start fail2ban
    
    log_success "Fail2ban configurado ✓"
}

configure_logrotate() {
    log_step "Configurando rotación de logs..."
    
    cat > /etc/logrotate.d/axonote << EOF
/var/log/axonote/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    copytruncate
    create 644 $AXONOTE_USER www-data
}

$INSTALL_DIR/apps/web/.next/standalone/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
    create 644 $AXONOTE_USER www-data
}
EOF

    log_success "Rotación de logs configurada ✓"
}

# =============================================================================
# SCRIPTS DE MANTENIMIENTO
# =============================================================================

create_maintenance_scripts() {
    log_step "Creando scripts de mantenimiento..."
    
    # Script de backup
    cat > /usr/local/bin/axonote-backup << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/axonote"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="axonote"
DB_USER="axonote_user"

# Crear backup de base de datos
pg_dump -h localhost -U $DB_USER $DB_NAME > "$BACKUP_DIR/db_$DATE.sql"

# Backup de archivos
tar -czf "$BACKUP_DIR/files_$DATE.tar.gz" /var/lib/axonote/uploads/

# Limpiar backups antiguos (más de 30 días)
find "$BACKUP_DIR" -name "*.sql" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete

echo "Backup completado: $DATE"
EOF

    # Script de monitoreo
    cat > /usr/local/bin/axonote-status << 'EOF'
#!/bin/bash
echo "=== AxoNote System Status ==="
echo "Fecha: $(date)"
echo

echo "=== Servicios ==="
systemctl is-active postgresql redis-server axonote-api axonote-worker axonote-web apache2

echo -e "\n=== Uso de Recursos ==="
echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')%"
echo "RAM: $(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')"
echo "Disco: $(df -h / | awk 'NR==2{printf "%s", $5}')"

echo -e "\n=== Salud API ==="
curl -s http://localhost:8000/health/simple || echo "API no responde"

echo -e "\n=== Logs Recientes ==="
tail -n 5 /var/log/axonote/app.log 2>/dev/null || echo "No hay logs disponibles"
EOF

    # Script de actualización
    cat > /usr/local/bin/axonote-update << EOF
#!/bin/bash
set -e

echo "Iniciando actualización de AxoNote..."

# Backup antes de actualizar
/usr/local/bin/axonote-backup

# Parar servicios
systemctl stop axonote-api axonote-worker axonote-web

# Actualizar código
cd $INSTALL_DIR
sudo -u $AXONOTE_USER git pull origin main

# Actualizar backend
cd $INSTALL_DIR/apps/api
sudo -u $AXONOTE_USER bash -c "source venv/bin/activate && poetry install --no-dev"
sudo -u $AXONOTE_USER bash -c "source venv/bin/activate && export \\\$(cat ../../.env | xargs) && alembic upgrade head"

# Actualizar frontend
cd $INSTALL_DIR/apps/web
sudo -u $AXONOTE_USER npm ci --production
sudo -u $AXONOTE_USER npm run build

# Reiniciar servicios
systemctl start axonote-api axonote-worker axonote-web

echo "Actualización completada"
EOF

    # Hacer scripts ejecutables
    chmod +x /usr/local/bin/axonote-backup
    chmod +x /usr/local/bin/axonote-status
    chmod +x /usr/local/bin/axonote-update
    
    # Programar backup diario
    (crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/axonote-backup") | crontab -
    
    log_success "Scripts de mantenimiento creados ✓"
}

# =============================================================================
# INICIO DE SERVICIOS Y VERIFICACIÓN
# =============================================================================

start_services() {
    log_step "Iniciando servicios de AxoNote..."
    
    # Crear directorios de logs
    mkdir -p /var/log/axonote
    chown "$AXONOTE_USER:www-data" /var/log/axonote
    
    # Crear directorios de uploads
    mkdir -p /var/lib/axonote/uploads
    chown -R "$AXONOTE_USER:www-data" /var/lib/axonote
    
    # Iniciar servicios
    systemctl start axonote-api
    sleep 5
    
    systemctl start axonote-worker
    sleep 3
    
    systemctl start axonote-web
    sleep 5
    
    # Recargar Apache
    systemctl reload apache2
    
    log_success "Servicios iniciados ✓"
}

verify_installation() {
    log_step "Verificando instalación..."
    
    # Verificar servicios
    local failed_services=()
    
    for service in postgresql redis-server axonote-api axonote-worker axonote-web apache2; do
        if ! systemctl is-active --quiet "$service"; then
            failed_services+=("$service")
        fi
    done
    
    if [[ ${#failed_services[@]} -gt 0 ]]; then
        log_error "Los siguientes servicios no están funcionando: ${failed_services[*]}"
        return 1
    fi
    
    # Verificar API
    local api_health
    api_health=$(curl -s http://localhost:8000/health/simple 2>/dev/null || echo "ERROR")
    
    if [[ "$api_health" != *"healthy"* ]]; then
        log_error "API no responde correctamente"
        return 1
    fi
    
    # Verificar frontend
    local frontend_test
    frontend_test=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")
    
    if [[ "$frontend_test" != "200" ]]; then
        log_error "Frontend no responde correctamente"
        return 1
    fi
    
    log_success "Verificación completada - Todos los servicios funcionando ✓"
    return 0
}

# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

show_completion_message() {
    log_success ""
    log_success "🎉 ¡INSTALACIÓN DE AXONOTE COMPLETADA! 🎉"
    log_success ""
    log_info "=== INFORMACIÓN DE LA INSTALACIÓN ==="
    log_info "Sitio web: https://$DOMAIN_NAME"
    log_info "API Docs: https://$DOMAIN_NAME/api/docs"
    log_info "Directorio: $INSTALL_DIR"
    log_info "Usuario del sistema: $AXONOTE_USER"
    log_info "Base de datos: $DB_NAME"
    log_info "Logs: /var/log/axonote/"
    log_info ""
    log_info "=== COMANDOS ÚTILES ==="
    log_info "Estado del sistema: axonote-status"
    log_info "Backup manual: axonote-backup"
    log_info "Actualizar aplicación: axonote-update"
    log_info "Ver logs API: journalctl -u axonote-api -f"
    log_info "Ver logs Worker: journalctl -u axonote-worker -f"
    log_info "Ver logs Web: journalctl -u axonote-web -f"
    log_info ""
    log_info "=== SERVICIOS ==="
    log_info "Reiniciar API: sudo systemctl restart axonote-api"
    log_info "Reiniciar Worker: sudo systemctl restart axonote-worker"
    log_info "Reiniciar Frontend: sudo systemctl restart axonote-web"
    log_info ""
    
    if [[ "$USE_GPU" == true ]]; then
        log_warning "⚠️  IMPORTANTE: Se instalaron drivers de GPU."
        log_warning "Es recomendable reiniciar el sistema para cargar los drivers correctamente."
        log_warning "Después del reinicio, ejecute: nvidia-smi para verificar la GPU."
    fi
    
    log_info "=== PRÓXIMOS PASOS ==="
    log_info "1. Acceder a https://$DOMAIN_NAME y verificar funcionamiento"
    log_info "2. Configurar DNS para que $DOMAIN_NAME apunte a este servidor"
    log_info "3. Revisar logs para asegurar que todo funciona correctamente"
    log_info "4. Configurar monitoreo adicional si es necesario"
    
    if [[ -z "$OPENAI_API_KEY" ]]; then
        log_info "5. Configurar OpenAI API Key en $INSTALL_DIR/.env (opcional)"
    fi
    
    log_success ""
    log_success "¡AxoNote está listo para usar!"
    log_success ""
}

# =============================================================================
# FUNCIÓN PRINCIPAL DE INSTALACIÓN
# =============================================================================

main() {
    # Mostrar banner
    echo -e "${PURPLE}"
    echo "=============================================="
    echo "       INSTALADOR AUTOMÁTICO DE AXONOTE"
    echo "=============================================="
    echo "Plataforma PWA para Transcripción Médica"
    echo "Versión: 1.0.0"
    echo "=============================================="
    echo -e "${NC}"
    
    # Crear log file
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
    
    log_info "Iniciando instalación de AxoNote..."
    log_info "Log disponible en: $LOG_FILE"
    
    # Verificaciones iniciales
    check_root
    check_os
    check_internet
    check_system_resources
    
    # Recolectar información del usuario
    collect_user_input
    
    # Mostrar resumen antes de proceder
    log_info ""
    log_info "=== RESUMEN DE CONFIGURACIÓN ==="
    log_info "Repositorio: $GIT_REPO_URL"
    log_info "Dominio: $DOMAIN_NAME"
    log_info "Email: $ADMIN_EMAIL"
    log_info "Directorio: $INSTALL_DIR"
    log_info "GPU: $USE_GPU"
    log_info "SSL automático: $SETUP_SSL"
    log_info "=================================="
    log_info ""
    
    if ! confirm "¿Continuar con la instalación?" "y"; then
        log_info "Instalación cancelada por el usuario."
        exit 0
    fi
    
    # Proceso de instalación
    log_info "Iniciando proceso de instalación..."
    
    update_system
    install_base_packages
    install_apache
    install_postgresql
    install_redis
    install_python
    install_nodejs
    install_ai_dependencies
    
    create_system_user
    
    clone_repository
    install_backend_dependencies
    install_frontend_dependencies
    
    create_env_file
    setup_database
    build_frontend
    
    create_systemd_services
    configure_apache_vhost
    setup_ssl
    
    configure_firewall
    configure_fail2ban
    configure_logrotate
    
    create_maintenance_scripts
    
    start_services
    
    # Verificación final
    if verify_installation; then
        show_completion_message
        
        # Guardar información de instalación
        cat > "$INSTALL_DIR/INSTALLATION_INFO.txt" << EOF
AxoNote Installation Information
================================
Date: $(date)
Domain: $DOMAIN_NAME
Admin Email: $ADMIN_EMAIL
Installation Directory: $INSTALL_DIR
Database: $DB_NAME
User: $AXONOTE_USER
GPU Enabled: $USE_GPU
SSL Configured: $SETUP_SSL

Repository: $GIT_REPO_URL
OS: $OS $VER

Log File: $LOG_FILE
EOF
        
        log_info "Información de instalación guardada en: $INSTALL_DIR/INSTALLATION_INFO.txt"
        
    else
        log_error "La verificación de instalación falló."
        log_error "Por favor revise los logs en $LOG_FILE"
        log_error "También puede ejecutar: axonote-status"
        exit 1
    fi
}

# =============================================================================
# MANEJO DE ERRORES Y LIMPIEZA
# =============================================================================

cleanup() {
    local exit_code=$?
    
    if [[ $exit_code -ne 0 ]]; then
        log_error "La instalación falló con código de salida: $exit_code"
        log_error "Por favor revise los logs en: $LOG_FILE"
        
        # Preguntar si desea limpiar archivos parciales
        if confirm "¿Desea limpiar archivos de instalación parcial?"; then
            log_info "Limpiando instalación parcial..."
            
            # Parar servicios si existen
            systemctl stop axonote-api axonote-worker axonote-web 2>/dev/null || true
            systemctl disable axonote-api axonote-worker axonote-web 2>/dev/null || true
            
            # Eliminar archivos de servicio
            rm -f /etc/systemd/system/axonote-*.service
            systemctl daemon-reload
            
            # Eliminar directorio de instalación
            if [[ -d "$INSTALL_DIR" ]]; then
                rm -rf "$INSTALL_DIR"
            fi
            
            # Eliminar usuario del sistema
            if id "$AXONOTE_USER" &>/dev/null; then
                userdel -r "$AXONOTE_USER" 2>/dev/null || true
            fi
            
            log_info "Limpieza completada."
        fi
    fi
}

# Configurar trap para limpieza en caso de error
trap cleanup EXIT

# =============================================================================
# EJECUCIÓN DEL SCRIPT
# =============================================================================

# Verificar que se ejecute directamente (no como source)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi


