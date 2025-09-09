# 📚 Documentación Técnica - Axonote

## 🏷️ Convención de Etiquetas

Este directorio contiene toda la documentación técnica del proyecto Axonote, organizada con un sistema de etiquetas para facilitar la navegación y mantenimiento.

### **Formato de Etiquetas**
```
[ÁREA][FASE].[NÚMERO]-[DESCRIPCIÓN].md
```

#### **Áreas de Desarrollo**
- **`B`** → **Backend** (FastAPI, Celery, Base de datos, APIs)
- **`A`** → **App/Frontend** (Next.js, PWA, Componentes UI)
- **`I`** → **Infraestructura** (Docker, Deployment, CI/CD)
- **`M`** → **ML/IA** (Whisper, Diarización, LLM, OCR, TTS)
- **`N`** → **Notion** (Integración, Sincronización, APIs)
- **`S`** → **Seguridad** (Autenticación, Autorización, Privacy)
- **`T`** → **Testing** (Unit tests, Integration, E2E)
- **`D`** → **DevOps** (Monitoring, Logging, Performance)

#### **Fases de Desarrollo**
- **`0`** → Infraestructura y setup inicial
- **`1`** → Backend base y fundamentos
- **`2`** → Frontend PWA y UI
- **`3`** → Upload de archivos y gestión
- **`4`** → ASR y diarización (IA core)
- **`5`** → Post-procesamiento y léxico
- **`6`** → LLM y generación de contenido
- **`7`** → Research y fuentes médicas
- **`8`** → Integración Notion completa
- **`9`** → OCR y micro-memos
- **`10`** → Export y TTS
- **`11`** → Dashboard y métricas
- **`12`** → Seguridad y compliance final

### **Ejemplos de Etiquetas**
```
B0.1-Fase-0-Infraestructura.md          # Backend, Fase 0, doc 1
B1.1-FastAPI-Setup-y-Configuracion.md   # Backend, Fase 1, doc 1
B1.2-Modelos-SQLAlchemy.md               # Backend, Fase 1, doc 2
A2.1-Next.js-PWA-Setup.md               # App, Fase 2, doc 1
A2.2-Componentes-UI-Medicos.md          # App, Fase 2, doc 2
M4.1-Whisper-Integracion-CUDA.md        # ML, Fase 4, doc 1
M4.2-Pyannote-Diarizacion.md            # ML, Fase 4, doc 2
N8.1-Notion-SDK-Integracion.md          # Notion, Fase 8, doc 1
T1.1-Backend-Unit-Tests.md              # Testing, Fase 1, doc 1
D11.1-Monitoring-y-Metricas.md          # DevOps, Fase 11, doc 1
```

## 📁 Estructura de Documentación

### **Por Fases de Desarrollo**
```
Documentacion/
├─ B0.1-Fase-0-Infraestructura.md       ✅ Completado
├─ B1.1-FastAPI-Setup.md                🔄 Próximo
├─ B1.2-Modelos-Base-Datos.md           ⏳ Pendiente
├─ B1.3-Celery-Workers.md               ⏳ Pendiente
├─ A2.1-Next.js-PWA-Setup.md            ⏳ Pendiente
├─ A2.2-UI-Componentes-Medicos.md       ⏳ Pendiente
├─ M4.1-Whisper-ASR-Integration.md      ⏳ Pendiente
├─ M4.2-Diarizacion-Speakers.md         ⏳ Pendiente
├─ N8.1-Notion-API-Integration.md       ⏳ Pendiente
└─ ...                                  ⏳ Más docs por fase
```

### **Por Áreas Técnicas**
```
Backend (B*)
├─ Infraestructura y setup
├─ APIs REST y routers
├─ Base de datos y modelos
├─ Servicios y integraciones
└─ Workers y procesamiento

Frontend/App (A*)
├─ PWA y configuración
├─ Componentes UI médicos
├─ Estado y gestión de datos
├─ Offline y sincronización
└─ UX específico médico

Machine Learning (M*)
├─ ASR (Whisper + WhisperX)
├─ Diarización (pyannote)
├─ LLM local/remoto
├─ OCR (Tesseract)
└─ TTS (Piper)

Notion Integration (N*)
├─ SDK y autenticación
├─ Creación de databases
├─ Sincronización de datos
└─ Templates y estructuras

Testing (T*)
├─ Unit tests backend
├─ Component tests frontend
├─ Integration tests
└─ E2E workflows

DevOps/Infrastructure (D*)
├─ Docker y containers
├─ Monitoring y logs
├─ Performance optimization
└─ Deployment strategies
```

## 📝 Plantilla de Documentación

### **Estructura Estándar**
Cada documento técnico debe seguir esta estructura:

```markdown
# [ETIQUETA] - [TÍTULO DESCRIPTIVO]

## 📋 Resumen
Descripción breve del contenido y objetivos

## 🎯 Objetivos
Lista de objetivos específicos de esta fase/área

## 🏗️ Implementación
Detalles técnicos de la implementación

### Código
Ejemplos de código relevantes

### Configuración
Archivos de configuración necesarios

## ✅ Checklist de Validación
Lista de verificación para completar la tarea

## 🔧 Troubleshooting
Problemas comunes y soluciones

## 📊 Métricas
Métricas de rendimiento/calidad específicas

## 🚀 Próximos Pasos
Enlaces a la siguiente fase/documentación

---
**Estado**: [Completado/En Progreso/Pendiente]
**Fase**: [Número de fase]
**Dependencias**: [Documentos relacionados]
```

## 🔄 Mantenimiento de Documentación

### **Actualización Continua**
- Cada cambio significativo debe documentarse
- Links entre documentos relacionados
- Versionado de cambios importantes
- Screenshots y diagramas cuando sea necesario

### **Revisión de Calidad**
- Código funcional y probado
- Instrucciones paso a paso verificadas
- Links y referencias actualizadas
- Consistent formatting y estilo

### **Estado de Documentos**
- ✅ **Completado**: Implementado y verificado
- 🔄 **En Progreso**: Siendo desarrollado actualmente
- ⏳ **Pendiente**: Programado para futuras fases
- 🚧 **En Revisión**: Requiere actualización
- ❌ **Obsoleto**: Ya no aplicable

## 🔍 Búsqueda y Navegación

### **Por Etiqueta de Fase**
```bash
# Buscar documentación de una fase específica
ls Documentacion/*1.*  # Fase 1
ls Documentacion/*4.*  # Fase 4
```

### **Por Área Técnica**
```bash
# Buscar por área
ls Documentacion/B*    # Backend
ls Documentacion/A*    # App/Frontend
ls Documentacion/M*    # Machine Learning
```

### **Grep por Contenido**
```bash
# Buscar términos específicos
grep -r "Whisper" Documentacion/
grep -r "Notion" Documentacion/
grep -r "PostgreSQL" Documentacion/
```

## 🎯 Objetivos de Documentación

### **Para Desarrolladores**
- Guías step-by-step para cada implementación
- Código de ejemplo funcional y probado
- Troubleshooting de problemas comunes
- Arquitectura y decisiones técnicas

### **Para DevOps**
- Configuración de infraestructura
- Deployment procedures
- Monitoring y debugging
- Performance optimization

### **Para QA/Testing**
- Test cases y scenarios
- Validation checklists
- Performance benchmarks
- Security verification

---

**📚 Esta documentación es un recurso vivo que evoluciona con el proyecto Axonote.**

**🔄 Última actualización**: Fase 0 - Infraestructura completada  
**📅 Próxima revisión**: Al completar Fase 1 - Backend Base
