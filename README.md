# 🎓 Axonote - Plataforma PWA para Transcripción Médica

> **Plataforma avanzada de grabación, transcripción y análisis de clases universitarias con IA local y privacidad garantizada**

Axonote es una aplicación Progressive Web App (PWA) diseñada específicamente para el entorno médico universitario que permite grabar clases, transcribirlas automáticamente, separarlas por hablantes (docente/alumnos), generar resúmenes inteligentes en español con citas en idioma original, crear glosarios médicos, flashcards y sincronizar todo con Notion.

## 🚀 Características Principales

### 🔒 **Privacidad y Seguridad First**
- **Audio local**: Todas las grabaciones permanecen en tu servidor (MinIO/Nextcloud)
- **ASR on-premise**: Transcripción con Whisper en GPU local (RTX 4090)
- **LLM local**: Procesamiento con Qwen2.5-14B-Instruct local por defecto
- **OpenAI opcional**: Limitado a 25€/mes y solo para casos específicos

### 🎯 **Funcionalidades Core**
- **Grabación avanzada**: MediaRecorder con VAD, colas offline (IndexedDB)
- **Transcripción inteligente**: faster-whisper + WhisperX con alineación de palabras
- **Diarización**: Separación automática Docente vs Alumnos con pyannote.audio 3.1
- **Resúmenes bilingües**: Contenido en español con citas precisas en idioma original
- **Investigación automática**: Ampliación con fuentes médicas verificadas (WHO, CDC, NIH, etc.)
- **Glosario médico**: Términos automáticos con definiciones contextuales
- **Flashcards**: Generación automática para estudio
- **TTS offline**: Audio del resumen con Piper (ES/IT)
- **OCR**: Captura de pizarras y diapositivas con Tesseract

### 🧠 **Tecnologías de IA**
- **ASR**: faster-whisper + WhisperX (CUDA optimizado)
- **Diarización**: pyannote.audio 3.1
- **LLM**: Qwen2.5-14B-Instruct (local) / OpenAI GPT-4o-mini (fallback)
- **OCR**: Tesseract CLI (italiano + inglés)
- **TTS**: Piper offline (español/italiano)

## 🏗️ Arquitectura Técnica

### **Stack Backend**
- **FastAPI** + **Celery** (Redis) para procesamiento asíncrono
- **SQLAlchemy + Alembic** para migraciones de base de datos
- **PostgreSQL** como base de datos principal
- **MinIO** para almacenamiento de objetos

### **Stack Frontend**
- **Next.js 14** + **TypeScript** (PWA)
- **Tailwind CSS** para diseño responsive y médico
- **Zustand** para gestión de estado
- **IndexedDB** para colas offline

### **Servicios Auxiliares**
- **Redis** para Celery y caché
- **LM Studio/Ollama** para LLM local
- **Notion SDK** para sincronización

## 📁 Estructura del Proyecto

```
axonote/
├─ apps/
│  ├─ api/                  # FastAPI Backend
│  │  ├─ app/
│  │  │  ├─ main.py
│  │  │  ├─ api/           # Routers REST
│  │  │  ├─ core/          # Config, seguridad, logging
│  │  │  ├─ models/        # SQLAlchemy models
│  │  │  ├─ schemas/       # Pydantic schemas
│  │  │  ├─ services/      # Notion, MinIO, LLM, ASR, OCR, TTS
│  │  │  ├─ tasks/         # Tareas Celery
│  │  │  └─ workers/       # Celery workers
│  │  ├─ alembic/          # Migraciones DB
│  │  └─ pyproject.toml
│  └─ web/                 # Next.js PWA
│     ├─ app/              # Next 14 App Router
│     ├─ components/       # Componentes React
│     ├─ lib/              # Utilidades, API client
│     └─ public/           # Archivos estáticos, manifest PWA
├─ docker/                 # Dockerfiles
├─ deploy/                 # Docker Compose
├─ scripts/                # Scripts de utilidad
├─ Documentacion/          # Documentación técnica
└─ Makefile               # Comandos de desarrollo
```

## 🚦 Inicio Rápido

### **Prerrequisitos**
- Docker & Docker Compose
- GPU NVIDIA con drivers (para ASR/diarización)
- 8GB+ RAM disponible
- Node.js 18+ (para desarrollo local)
- Python 3.11+ (para desarrollo local)

### **1. Clonación y Setup**
```bash
git clone <repository-url> axonote
cd axonote
cp env.example .env
```

### **2. Configuración Básica**
Edita `.env` con tus configuraciones:
```bash
# Tokens necesarios
NOTION_TOKEN=secret_xxx
OPENAI_API_KEY=sk-xxx  # Opcional
HF_TOKEN=hf_xxx        # Para pyannote

# Ajustes locales
LMSTUDIO_BASE_URL=http://your-ai-server:1234/v1
```

### **3. Desarrollo Local**
```bash
# Setup completo automático
make dev-setup

# O paso a paso:
make install-deps  # Instalar dependencias
make up            # Levantar servicios
make migrate       # Aplicar migraciones
make health        # Verificar estado
```

### **4. Acceso a la Aplicación**
- **Frontend PWA**: http://localhost:3000
- **API REST**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001

## 🔧 Comandos de Desarrollo

```bash
# Gestión de servicios
make up              # Levantar todos los servicios
make down            # Parar servicios
make logs            # Ver logs de todos los servicios
make restart         # Reiniciar servicios

# Desarrollo
make format          # Formatear código (ruff + black + prettier)
make lint            # Verificar estilo de código
make test            # Ejecutar todos los tests
make test-e2e        # Tests end-to-end

# Base de datos
make migrate         # Aplicar migraciones
make migration       # Crear nueva migración
make db-reset        # Reset completo de BD (⚠️ elimina datos)

# Utilidades
make shell-api       # Shell en contenedor API
make shell-db        # Shell en PostgreSQL
make health          # Verificar salud de servicios
make clean           # Limpiar contenedores no utilizados
```

## 📊 Monitorización y Logs

### **Logs Estructurados**
```bash
# Logs en tiempo real
make logs
make logs-api      # Solo API
make logs-worker   # Solo worker

# Logs específicos
docker-compose logs -f api --tail=100
```

### **Métricas de Rendimiento**
- **WER (Word Error Rate)**: Precisión de transcripción
- **Confianza ASR**: Nivel de confianza de Whisper
- **Confianza LLM**: Validez de respuestas JSON
- **Tiempos de procesamiento**: Por etapa del pipeline
- **Uso de GPU**: Monitorización CUDA

## 🔐 Seguridad y Compliance

### **Medidas de Seguridad**
- Autenticación JWT con refresh tokens
- Rate limiting configurable
- Validación estricta de uploads
- Headers de seguridad (CORS, CSP, etc.)
- Cifrado de datos sensibles en reposo

### **Privacidad de Datos**
- **Audio crudo**: Solo en servidor local (MinIO)
- **Transcripciones**: Procesamiento local únicamente
- **Metadatos**: Base de datos PostgreSQL local
- **Backups**: Cifrados y programables

## 📈 Roadmap de Desarrollo

### **✅ Fase 0** - Infraestructura (Actual)
- [x] Estructura de proyecto
- [x] Docker Compose development
- [x] Configuración de herramientas
- [x] CI/CD básico

### **🔄 Fase 1** - Backend Base
- [ ] FastAPI con endpoints core
- [ ] Base de datos y migraciones
- [ ] Servicios básicos (MinIO, Notion)
- [ ] Celery workers

### **📱 Fase 2** - Frontend PWA
- [ ] Next.js con App Router
- [ ] Grabación con MediaRecorder
- [ ] Colas offline con IndexedDB
- [ ] UI responsive médica

### **🎵 Fase 3** - Subida por Chunks
- [ ] Upload resiliente por chunks
- [ ] Progress tracking
- [ ] Recuperación de errores

### **🗣️ Fase 4** - ASR + Diarización
- [ ] Integración faster-whisper
- [ ] Diarización con pyannote
- [ ] Optimización CUDA

### **🧠 Fases 5-12** - IA Avanzada, Integración Notion, Exportación, etc.

## 🐛 Troubleshooting

### **Problemas Comunes**
```bash
# Servicios no inician
make down && make up
make health

# Problemas de permisos
sudo chown -R $USER:$USER .

# Limpiar cache Docker
make clean

# Reset completo
make clean-all && make dev-setup
```

### **Logs de Debug**
```bash
# Habilitar logs detallados
export LOG_LEVEL=DEBUG
make restart-api

# Verificar GPU
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu20.04 nvidia-smi
```

## 🤝 Contribución

### **Estándares de Código**
- **Python**: ruff + black + mypy (strict)
- **TypeScript**: ESLint (Airbnb) + Prettier
- **Commits**: Conventional Commits
- **Tests**: Coverage ≥85%

### **Flujo de Desarrollo**
1. Fork del repositorio
2. Crear rama feature: `git checkout -b feat/nueva-funcionalidad`
3. Desarrollo con tests: `make test`
4. Formateo: `make format`
5. Commit: `git commit -m "feat: nueva funcionalidad"`
6. PR con descripción detallada

## 📄 Licencia

Este proyecto está bajo licencia MIT. Ver `LICENSE` para más detalles.

## 📞 Soporte

Para soporte técnico o preguntas:
- **Issues**: Crear issue en GitHub con etiquetas apropiadas
- **Documentación**: Ver `/Documentacion/` para guías técnicas
- **Logs**: Usar `make logs` para debugging

---

**🎓 Axonote** - Transformando la educación médica con IA local y privacidad garantizada.
