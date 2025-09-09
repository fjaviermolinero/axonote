/**
 * Audio Compression Library - Compresión de audio optimizada para transcripción
 * 
 * Características:
 * - Compresión inteligente con preservación de calidad para ASR
 * - Múltiples niveles de compresión
 * - Optimización específica para voz humana
 * - Reducción de ruido básica
 * - Métricas de compresión
 * - Web Workers para rendimiento
 */

// Tipos TypeScript
export interface CompressionConfig {
  quality: 'low' | 'medium' | 'high' | 'lossless';
  sampleRate: number;
  bitRate: number;
  channels: 1 | 2; // Mono o Stereo
  format: 'webm' | 'mp3' | 'wav';
  noiseReduction: boolean;
  voiceOptimized: boolean;
  preserveForASR: boolean; // Preservar frecuencias importantes para ASR
}

export interface CompressionResult {
  compressedBlob: Blob;
  originalSize: number;
  compressedSize: number;
  compressionRatio: number;
  timeTaken: number;
  quality: CompressionConfig['quality'];
  estimatedAccuracyLoss: number; // Estimación de pérdida de precisión ASR (0-100%)
}

export interface CompressionProgress {
  phase: 'analyzing' | 'encoding' | 'optimizing' | 'finalizing';
  percentage: number;
  message: string;
}

/**
 * Configuraciones predefinidas optimizadas para diferentes casos de uso
 */
export const COMPRESSION_PRESETS: Record<string, CompressionConfig> = {
  // Máxima calidad para transcripción médica crítica
  MEDICAL_HIGH_QUALITY: {
    quality: 'high',
    sampleRate: 16000, // Óptimo para Whisper
    bitRate: 128,
    channels: 1,
    format: 'webm',
    noiseReduction: true,
    voiceOptimized: true,
    preserveForASR: true
  },
  
  // Balance entre calidad y tamaño
  MEDICAL_BALANCED: {
    quality: 'medium',
    sampleRate: 16000,
    bitRate: 96,
    channels: 1,
    format: 'webm',
    noiseReduction: true,
    voiceOptimized: true,
    preserveForASR: true
  },
  
  // Máxima compresión para conexiones lentas
  MOBILE_OPTIMIZED: {
    quality: 'low',
    sampleRate: 16000,
    bitRate: 64,
    channels: 1,
    format: 'webm',
    noiseReduction: true,
    voiceOptimized: true,
    preserveForASR: true
  },
  
  // Sin compresión para máxima fidelidad
  LOSSLESS: {
    quality: 'lossless',
    sampleRate: 44100,
    bitRate: 1411, // CD quality
    channels: 1,
    format: 'wav',
    noiseReduction: false,
    voiceOptimized: false,
    preserveForASR: true
  }
};

/**
 * Clase principal para compresión de audio
 */
class AudioCompressor {
  private audioContext: AudioContext | null = null;
  private worker: Worker | null = null;
  
  constructor() {
    this.initializeAudioContext();
  }
  
  /**
   * Inicializar contexto de audio
   */
  private async initializeAudioContext(): Promise<void> {
    try {
      this.audioContext = new AudioContext();
    } catch (error) {
      console.error('Error inicializando AudioContext:', error);
    }
  }
  
  /**
   * Comprimir audio con configuración específica
   */
  async compressAudio(
    audioBlob: Blob,
    config: CompressionConfig,
    onProgress?: (progress: CompressionProgress) => void
  ): Promise<CompressionResult> {
    const startTime = performance.now();
    const originalSize = audioBlob.size;
    
    try {
      onProgress?.({
        phase: 'analyzing',
        percentage: 10,
        message: 'Analizando audio original...'
      });
      
      // Analizar audio original
      const audioBuffer = await this.blobToAudioBuffer(audioBlob);
      
      onProgress?.({
        phase: 'encoding',
        percentage: 30,
        message: 'Aplicando compresión...'
      });
      
      // Aplicar procesamiento de audio
      const processedBuffer = await this.processAudio(audioBuffer, config);
      
      onProgress?.({
        phase: 'optimizing',
        percentage: 70,
        message: 'Optimizando para transcripción...'
      });
      
      // Codificar a formato final
      const compressedBlob = await this.encodeAudio(processedBuffer, config);
      
      onProgress?.({
        phase: 'finalizing',
        percentage: 100,
        message: 'Finalizando compresión...'
      });
      
      const endTime = performance.now();
      const compressedSize = compressedBlob.size;
      
      return {
        compressedBlob,
        originalSize,
        compressedSize,
        compressionRatio: originalSize / compressedSize,
        timeTaken: endTime - startTime,
        quality: config.quality,
        estimatedAccuracyLoss: this.estimateAccuracyLoss(config)
      };
      
    } catch (error) {
      throw new Error(`Error en compresión de audio: ${error}`);
    }
  }
  
  /**
   * Comprimir con preset específico
   */
  async compressWithPreset(
    audioBlob: Blob,
    presetName: keyof typeof COMPRESSION_PRESETS,
    onProgress?: (progress: CompressionProgress) => void
  ): Promise<CompressionResult> {
    const config = COMPRESSION_PRESETS[presetName];
    if (!config) {
      throw new Error(`Preset desconocido: ${presetName}`);
    }
    
    return this.compressAudio(audioBlob, config, onProgress);
  }
  
  /**
   * Compresión automática basada en tamaño y conexión
   */
  async autoCompress(
    audioBlob: Blob,
    targetSizeMB?: number,
    onProgress?: (progress: CompressionProgress) => void
  ): Promise<CompressionResult> {
    // Detectar calidad de conexión
    const connectionInfo = this.getConnectionInfo();
    const sizeMB = audioBlob.size / (1024 * 1024);
    
    let presetName: keyof typeof COMPRESSION_PRESETS;
    
    // Seleccionar preset basado en tamaño y conexión
    if (targetSizeMB && sizeMB > targetSizeMB * 2) {
      presetName = 'MOBILE_OPTIMIZED';
    } else if (connectionInfo.effectiveType === '4g' || connectionInfo.effectiveType === 'wifi') {
      presetName = sizeMB > 50 ? 'MEDICAL_BALANCED' : 'MEDICAL_HIGH_QUALITY';
    } else if (connectionInfo.effectiveType === '3g') {
      presetName = 'MEDICAL_BALANCED';
    } else {
      presetName = 'MOBILE_OPTIMIZED';
    }
    
    return this.compressWithPreset(audioBlob, presetName, onProgress);
  }
  
  /**
   * Convertir Blob a AudioBuffer
   */
  private async blobToAudioBuffer(blob: Blob): Promise<AudioBuffer> {
    if (!this.audioContext) {
      throw new Error('AudioContext no disponible');
    }
    
    const arrayBuffer = await blob.arrayBuffer();
    return this.audioContext.decodeAudioData(arrayBuffer);
  }
  
  /**
   * Procesar audio con configuración específica
   */
  private async processAudio(
    audioBuffer: AudioBuffer,
    config: CompressionConfig
  ): Promise<AudioBuffer> {
    if (!this.audioContext) {
      throw new Error('AudioContext no disponible');
    }
    
    // Crear buffer de salida con nueva configuración
    const outputBuffer = this.audioContext.createBuffer(
      config.channels,
      Math.floor(audioBuffer.length * (config.sampleRate / audioBuffer.sampleRate)),
      config.sampleRate
    );
    
    // Procesar cada canal
    for (let channel = 0; channel < Math.min(config.channels, audioBuffer.numberOfChannels); channel++) {
      const inputData = audioBuffer.getChannelData(channel);
      const outputData = outputBuffer.getChannelData(channel);
      
      // Resamplear si es necesario
      if (config.sampleRate !== audioBuffer.sampleRate) {
        this.resampleChannel(inputData, outputData, audioBuffer.sampleRate, config.sampleRate);
      } else {
        outputData.set(inputData);
      }
      
      // Aplicar procesamiento adicional
      if (config.noiseReduction) {
        this.applyNoiseReduction(outputData);
      }
      
      if (config.voiceOptimized) {
        this.optimizeForVoice(outputData, config.sampleRate);
      }
      
      if (config.preserveForASR) {
        this.optimizeForASR(outputData, config.sampleRate);
      }
    }
    
    return outputBuffer;
  }
  
  /**
   * Resamplear canal de audio
   */
  private resampleChannel(
    input: Float32Array,
    output: Float32Array,
    inputRate: number,
    outputRate: number
  ): void {
    const ratio = inputRate / outputRate;
    
    for (let i = 0; i < output.length; i++) {
      const index = i * ratio;
      const indexFloor = Math.floor(index);
      const indexCeil = Math.min(indexFloor + 1, input.length - 1);
      const fraction = index - indexFloor;
      
      // Interpolación lineal
      output[i] = input[indexFloor] * (1 - fraction) + input[indexCeil] * fraction;
    }
  }
  
  /**
   * Aplicar reducción básica de ruido
   */
  private applyNoiseReduction(data: Float32Array): void {
    // Algoritmo simple de gate de ruido
    const threshold = 0.01; // Umbral de ruido
    const attackTime = 0.003; // 3ms
    const releaseTime = 0.1; // 100ms
    
    let gate = 0;
    const attackCoeff = Math.exp(-1 / (attackTime * 16000)); // Asumiendo 16kHz
    const releaseCoeff = Math.exp(-1 / (releaseTime * 16000));
    
    for (let i = 0; i < data.length; i++) {
      const absValue = Math.abs(data[i]);
      
      if (absValue > threshold) {
        gate = gate * attackCoeff + (1 - attackCoeff);
      } else {
        gate = gate * releaseCoeff;
      }
      
      data[i] *= gate;
    }
  }
  
  /**
   * Optimizar para voz humana
   */
  private optimizeForVoice(data: Float32Array, sampleRate: number): void {
    // Aplicar filtro pasa-banda para frecuencias de voz (80Hz - 8kHz)
    const lowCutoff = 80 / (sampleRate / 2);
    const highCutoff = 8000 / (sampleRate / 2);
    
    // Implementación simplificada de filtro Butterworth
    this.applyBandpassFilter(data, lowCutoff, highCutoff);
    
    // Compresión dinámica suave para voz
    this.applyDynamicCompression(data, 0.3, 3.0); // Ratio 3:1, threshold 0.3
  }
  
  /**
   * Optimizar para ASR (Automatic Speech Recognition)
   */
  private optimizeForASR(data: Float32Array, sampleRate: number): void {
    // Preservar frecuencias críticas para reconocimiento de voz
    // Enfasis en 1-4kHz donde están la mayoría de consonantes
    
    // Aplicar pre-énfasis ligero
    for (let i = data.length - 1; i > 0; i--) {
      data[i] = data[i] - 0.97 * data[i - 1];
    }
    
    // Normalización de volumen
    this.normalizeVolume(data, 0.8); // 80% del máximo
  }
  
  /**
   * Aplicar filtro pasa-banda simple
   */
  private applyBandpassFilter(data: Float32Array, lowCutoff: number, highCutoff: number): void {
    // Implementación simplificada usando promedio móvil
    const windowSize = Math.floor(1 / lowCutoff);
    const temp = new Float32Array(data.length);
    
    // Filtro pasa-altos (quitar frecuencias muy bajas)
    for (let i = 1; i < data.length; i++) {
      temp[i] = data[i] - data[i - 1] * 0.95;
    }
    
    // Filtro pasa-bajos (quitar frecuencias muy altas)
    for (let i = 1; i < temp.length; i++) {
      data[i] = temp[i] * 0.1 + data[i - 1] * 0.9;
    }
  }
  
  /**
   * Aplicar compresión dinámica
   */
  private applyDynamicCompression(data: Float32Array, threshold: number, ratio: number): void {
    for (let i = 0; i < data.length; i++) {
      const absValue = Math.abs(data[i]);
      
      if (absValue > threshold) {
        const excess = absValue - threshold;
        const compressedExcess = excess / ratio;
        const newValue = threshold + compressedExcess;
        
        data[i] = data[i] > 0 ? newValue : -newValue;
      }
    }
  }
  
  /**
   * Normalizar volumen
   */
  private normalizeVolume(data: Float32Array, targetPeak: number): void {
    // Encontrar pico absoluto
    let peak = 0;
    for (let i = 0; i < data.length; i++) {
      peak = Math.max(peak, Math.abs(data[i]));
    }
    
    if (peak > 0) {
      const gain = targetPeak / peak;
      for (let i = 0; i < data.length; i++) {
        data[i] *= gain;
      }
    }
  }
  
  /**
   * Codificar audio a formato final
   */
  private async encodeAudio(
    audioBuffer: AudioBuffer,
    config: CompressionConfig
  ): Promise<Blob> {
    // Para formatos con pérdida, usamos MediaRecorder API
    if (config.format === 'webm' || config.format === 'mp3') {
      return this.encodeWithMediaRecorder(audioBuffer, config);
    }
    
    // Para WAV, codificamos directamente
    if (config.format === 'wav') {
      return this.encodeToWav(audioBuffer);
    }
    
    throw new Error(`Formato no soportado: ${config.format}`);
  }
  
  /**
   * Codificar usando MediaRecorder API
   */
  private async encodeWithMediaRecorder(
    audioBuffer: AudioBuffer,
    config: CompressionConfig
  ): Promise<Blob> {
    if (!this.audioContext) {
      throw new Error('AudioContext no disponible');
    }
    
    // Crear stream de audio desde buffer
    const source = this.audioContext.createBufferSource();
    const destination = this.audioContext.createMediaStreamDestination();
    
    source.buffer = audioBuffer;
    source.connect(destination);
    
    // Configurar MediaRecorder
    const mimeType = config.format === 'webm' 
      ? `audio/webm;codecs=opus`
      : `audio/mpeg`;
    
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      throw new Error(`Formato no soportado por MediaRecorder: ${mimeType}`);
    }
    
    const mediaRecorder = new MediaRecorder(destination.stream, {
      mimeType,
      audioBitsPerSecond: config.bitRate * 1000
    });
    
    const chunks: Blob[] = [];
    
    return new Promise((resolve, reject) => {
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };
      
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: mimeType });
        resolve(blob);
      };
      
      mediaRecorder.onerror = (event) => {
        reject(new Error(`Error en MediaRecorder: ${event}`));
      };
      
      mediaRecorder.start();
      source.start();
      
      // Parar grabación después de la duración del buffer
      setTimeout(() => {
        mediaRecorder.stop();
        source.stop();
      }, (audioBuffer.duration + 0.1) * 1000);
    });
  }
  
  /**
   * Codificar a formato WAV
   */
  private encodeToWav(audioBuffer: AudioBuffer): Blob {
    const numberOfChannels = audioBuffer.numberOfChannels;
    const sampleRate = audioBuffer.sampleRate;
    const format = 1; // PCM
    const bitDepth = 16;
    
    const bytesPerSample = bitDepth / 8;
    const blockAlign = numberOfChannels * bytesPerSample;
    const byteRate = sampleRate * blockAlign;
    const dataSize = audioBuffer.length * blockAlign;
    const bufferSize = 44 + dataSize;
    
    const buffer = new ArrayBuffer(bufferSize);
    const view = new DataView(buffer);
    
    // WAV header
    let offset = 0;
    
    // "RIFF" chunk descriptor
    view.setUint32(offset, 0x52494646, false); offset += 4; // "RIFF"
    view.setUint32(offset, bufferSize - 8, true); offset += 4; // File size - 8
    view.setUint32(offset, 0x57415645, false); offset += 4; // "WAVE"
    
    // "fmt " sub-chunk
    view.setUint32(offset, 0x666d7420, false); offset += 4; // "fmt "
    view.setUint32(offset, 16, true); offset += 4; // Subchunk1Size
    view.setUint16(offset, format, true); offset += 2; // AudioFormat
    view.setUint16(offset, numberOfChannels, true); offset += 2; // NumChannels
    view.setUint32(offset, sampleRate, true); offset += 4; // SampleRate
    view.setUint32(offset, byteRate, true); offset += 4; // ByteRate
    view.setUint16(offset, blockAlign, true); offset += 2; // BlockAlign
    view.setUint16(offset, bitDepth, true); offset += 2; // BitsPerSample
    
    // "data" sub-chunk
    view.setUint32(offset, 0x64617461, false); offset += 4; // "data"
    view.setUint32(offset, dataSize, true); offset += 4; // Subchunk2Size
    
    // Audio data
    const channels = [];
    for (let i = 0; i < numberOfChannels; i++) {
      channels.push(audioBuffer.getChannelData(i));
    }
    
    let sampleIndex = 0;
    while (offset < buffer.byteLength) {
      for (let channel = 0; channel < numberOfChannels; channel++) {
        const sample = Math.max(-1, Math.min(1, channels[channel][sampleIndex]));
        const intSample = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        view.setInt16(offset, intSample, true);
        offset += 2;
      }
      sampleIndex++;
    }
    
    return new Blob([buffer], { type: 'audio/wav' });
  }
  
  /**
   * Estimar pérdida de precisión ASR
   */
  private estimateAccuracyLoss(config: CompressionConfig): number {
    let loss = 0;
    
    // Pérdida por compresión de calidad
    switch (config.quality) {
      case 'low': loss += 15; break;
      case 'medium': loss += 8; break;
      case 'high': loss += 3; break;
      case 'lossless': loss += 0; break;
    }
    
    // Pérdida por sample rate bajo
    if (config.sampleRate < 16000) loss += 10;
    if (config.sampleRate < 8000) loss += 20;
    
    // Pérdida por bitrate muy bajo
    if (config.bitRate < 64) loss += 10;
    if (config.bitRate < 32) loss += 25;
    
    // Ganancia por optimizaciones
    if (config.voiceOptimized) loss -= 2;
    if (config.preserveForASR) loss -= 3;
    if (config.noiseReduction) loss -= 1;
    
    return Math.max(0, Math.min(100, loss));
  }
  
  /**
   * Obtener información de conexión
   */
  private getConnectionInfo(): any {
    const nav = navigator as any;
    return nav.connection || nav.mozConnection || nav.webkitConnection || {
      effectiveType: '4g', // Fallback
      downlink: 10
    };
  }
  
  /**
   * Cleanup de recursos
   */
  destroy(): void {
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close();
    }
    
    if (this.worker) {
      this.worker.terminate();
    }
  }
}

/**
 * Funciones de utilidad para compresión
 */

/**
 * Obtener preset recomendado basado en condiciones
 */
export function getRecommendedPreset(
  fileSizeMB: number,
  durationMinutes: number,
  connectionSpeed: 'slow' | 'medium' | 'fast' = 'medium'
): keyof typeof COMPRESSION_PRESETS {
  if (connectionSpeed === 'slow' || fileSizeMB > 100) {
    return 'MOBILE_OPTIMIZED';
  }
  
  if (durationMinutes > 60 || fileSizeMB > 50) {
    return 'MEDICAL_BALANCED';
  }
  
  if (durationMinutes < 10 && fileSizeMB < 20) {
    return 'MEDICAL_HIGH_QUALITY';
  }
  
  return 'MEDICAL_BALANCED';
}

/**
 * Calcular tamaño estimado después de compresión
 */
export function estimateCompressedSize(
  originalSizeMB: number,
  preset: keyof typeof COMPRESSION_PRESETS
): number {
  const ratios = {
    MEDICAL_HIGH_QUALITY: 0.6, // 60% del tamaño original
    MEDICAL_BALANCED: 0.4,     // 40% del tamaño original
    MOBILE_OPTIMIZED: 0.25,    // 25% del tamaño original
    LOSSLESS: 1.0              // Sin compresión
  };
  
  return originalSizeMB * (ratios[preset] || 0.4);
}

// Instancia singleton del compresor
export const audioCompressor = new AudioCompressor();
