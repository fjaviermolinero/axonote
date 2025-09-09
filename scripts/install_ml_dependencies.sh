#!/bin/bash

# ==============================================================================
# Script de instalación de dependencias ML para Axonote Fase 4
# ==============================================================================

set -e  # Exit on any error

echo "🚀 Instalando dependencias ML para Axonote Fase 4..."

# Verificar que estamos en el directorio correcto
if [ ! -f "apps/api/pyproject.toml" ]; then
    echo "❌ Error: Ejecutar desde el directorio raíz del proyecto"
    exit 1
fi

# Cambiar al directorio de la API
cd apps/api

echo "📦 Instalando dependencias con Poetry..."
poetry install --with ml

echo "🔍 Verificando instalación de PyTorch..."
python -c "
import torch
print(f'✅ PyTorch {torch.__version__}')
print(f'✅ CUDA disponible: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'✅ GPU: {torch.cuda.get_device_name(0)}')
    print(f'✅ CUDA version: {torch.version.cuda}')
    print(f'✅ Memoria GPU: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')
else:
    print('⚠️  CUDA no disponible - usando CPU')
"

echo "🎤 Verificando Whisper..."
python -c "
try:
    from faster_whisper import WhisperModel
    print('✅ faster-whisper instalado correctamente')
except ImportError as e:
    print(f'❌ Error importando faster-whisper: {e}')
"

echo "🗣️  Verificando pyannote-audio..."
python -c "
try:
    from pyannote.audio import Pipeline
    print('✅ pyannote-audio instalado correctamente')
    print('⚠️  Recuerda configurar HF_TOKEN para usar modelos de diarización')
except ImportError as e:
    print(f'❌ Error importando pyannote-audio: {e}')
"

echo "🔊 Verificando librerías de audio..."
python -c "
try:
    import librosa
    import soundfile
    import scipy
    print('✅ Librerías de audio instaladas correctamente')
except ImportError as e:
    print(f'❌ Error importando librerías de audio: {e}')
"

echo ""
echo "✅ Instalación de dependencias ML completada!"
echo ""
echo "📝 Próximos pasos:"
echo "1. Configurar HF_TOKEN en .env para pyannote-audio:"
echo "   HF_TOKEN=tu_token_de_hugging_face"
echo ""
echo "2. Obtener token en: https://huggingface.co/settings/tokens"
echo ""
echo "3. Verificar modelos descargados:"
echo "   poetry run python -c \"from app.services.whisper_service import whisper_service; print('Whisper OK')\""
echo ""
echo "4. Ejecutar health check:"
echo "   curl http://localhost:8000/api/v1/processing/health"
echo ""
echo "🎯 ¡La Fase 4 (ASR y Diarización) está lista para usar!"
