/**
 * ChunkUploader - Componente de upload por chunks resiliente
 * 
 * Características:
 * - Upload por chunks con progress tracking
 * - Recovery automático de errores
 * - Compresión de audio opcional
 * - UI médica profesional
 * - Gestión de estado completa
 */

'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Button } from './Button';
import { audioCompressor, getRecommendedPreset, estimateCompressedSize, CompressionProgress } from '@/lib/audio-compression';

// Tipos TypeScript
interface ChunkUploadConfig {
  maxChunkSizeMb: number;
  recommendedChunkSizeMb: number;
  supportedFormats: string[];
  uploadSessionId: string;
  totalChunksExpected?: number;
  expiresAt: string;
  validationEnabled: boolean;
}

interface UploadSession {
  recordingId: string;
  uploadSessionId: string;
  uploadUrls: {
    chunkUploadUrl: string;
    completeUrl: string;
    statusUrl: string;
    recoveryUrl: string;
  };
  chunkConfig: ChunkUploadConfig;
}

interface UploadProgress {
  chunksUploaded: number;
  totalChunks: number;
  bytesUploaded: number;
  totalBytes: number;
  percentage: number;
  currentChunk?: number;
  speed?: number; // MB/s
  eta?: number; // seconds
}

interface UploadError {
  type: 'validation' | 'network' | 'server' | 'timeout';
  message: string;
  chunk?: number;
  retryable: boolean;
}

interface ChunkUploaderProps {
  audioBlob: Blob;
  audioMetadata: {
    asignatura: string;
    tema: string;
    profesorText: string;
    duration: number;
  };
  enableCompression?: boolean;
  compressionQuality?: 'low' | 'medium' | 'high' | 'auto';
  onUploadStart?: () => void;
  onProgress?: (progress: UploadProgress) => void;
  onCompressionProgress?: (progress: CompressionProgress) => void;
  onComplete?: (result: { recordingId: string; finalUrl: string }) => void;
  onError?: (error: UploadError) => void;
  onCancel?: () => void;
  className?: string;
}

interface ChunkInfo {
  number: number;
  data: Blob;
  size: number;
  uploaded: boolean;
  uploading: boolean;
  error?: string;
  retryCount: number;
}

const ChunkUploader: React.FC<ChunkUploaderProps> = ({
  audioBlob,
  audioMetadata,
  enableCompression = true,
  compressionQuality = 'auto',
  onUploadStart,
  onProgress,
  onCompressionProgress,
  onComplete,
  onError,
  onCancel,
  className = ''
}) => {
  // Estados principales
  const [uploadSession, setUploadSession] = useState<UploadSession | null>(null);
  const [chunks, setChunks] = useState<ChunkInfo[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [progress, setProgress] = useState<UploadProgress>({
    chunksUploaded: 0,
    totalChunks: 0,
    bytesUploaded: 0,
    totalBytes: 0,
    percentage: 0
  });
  const [currentError, setCurrentError] = useState<UploadError | null>(null);
  const [isCompleting, setIsCompleting] = useState(false);
  const [isCompressing, setIsCompressing] = useState(false);
  const [compressionProgress, setCompressionProgress] = useState<CompressionProgress | null>(null);
  const [compressedBlob, setCompressedBlob] = useState<Blob | null>(null);
  const [compressionStats, setCompressionStats] = useState<{
    originalSize: number;
    compressedSize: number;
    compressionRatio: number;
    estimatedAccuracyLoss: number;
  } | null>(null);
  
  // Referencias
  const abortControllerRef = useRef<AbortController | null>(null);
  const uploadPromiseRef = useRef<Promise<void> | null>(null);
  
  // Configuración
  const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB por defecto
  const MAX_RETRIES = 3;
  const RETRY_DELAY_BASE = 1000; // 1 segundo base
  
  /**
   * Calcular checksum MD5 simple de un blob
   */
  const calculateChecksum = useCallback(async (blob: Blob): Promise<string> => {
    const buffer = await blob.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }, []);
  
  /**
   * Dividir archivo en chunks
   */
  const createChunks = useCallback(async (file: Blob, chunkSize: number): Promise<ChunkInfo[]> => {
    const chunks: ChunkInfo[] = [];
    const totalChunks = Math.ceil(file.size / chunkSize);
    
    for (let i = 0; i < totalChunks; i++) {
      const start = i * chunkSize;
      const end = Math.min(start + chunkSize, file.size);
      const chunkBlob = file.slice(start, end);
      
      chunks.push({
        number: i + 1,
        data: chunkBlob,
        size: chunkBlob.size,
        uploaded: false,
        uploading: false,
        retryCount: 0
      });
    }
    
    return chunks;
  }, []);
  
  /**
   * Comprimir audio antes del upload
   */
  const compressAudio = useCallback(async (blob: Blob): Promise<Blob> => {
    if (!enableCompression) {
      return blob;
    }
    
    setIsCompressing(true);
    setCompressionProgress({ phase: 'analyzing', percentage: 0, message: 'Iniciando compresión...' });
    
    try {
      const sizeMB = blob.size / (1024 * 1024);
      const durationMinutes = audioMetadata.duration / 60;
      
      // Determinar preset de compresión
      let preset: string;
      if (compressionQuality === 'auto') {
        preset = getRecommendedPreset(sizeMB, durationMinutes);
      } else {
        const qualityMap = {
          low: 'MOBILE_OPTIMIZED',
          medium: 'MEDICAL_BALANCED',
          high: 'MEDICAL_HIGH_QUALITY'
        };
        preset = qualityMap[compressionQuality];
      }
      
      // Comprimir audio
      const result = await audioCompressor.compressWithPreset(
        blob,
        preset as any,
        (progress) => {
          setCompressionProgress(progress);
          onCompressionProgress?.(progress);
        }
      );
      
      // Guardar estadísticas
      setCompressionStats({
        originalSize: result.originalSize,
        compressedSize: result.compressedSize,
        compressionRatio: result.compressionRatio,
        estimatedAccuracyLoss: result.estimatedAccuracyLoss
      });
      
      setCompressedBlob(result.compressedBlob);
      
      return result.compressedBlob;
      
    } catch (error) {
      console.error('Error en compresión:', error);
      // Si falla la compresión, usar archivo original
      return blob;
    } finally {
      setIsCompressing(false);
      setCompressionProgress(null);
    }
  }, [enableCompression, compressionQuality, audioMetadata.duration, onCompressionProgress]);
  
  /**
   * Crear sesión de upload inicial
   */
  const createUploadSession = useCallback(async (finalBlob: Blob): Promise<UploadSession> => {
    const response = await fetch('/api/v1/recordings/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        asignatura: audioMetadata.asignatura,
        tema: audioMetadata.tema,
        profesor_text: audioMetadata.profesorText,
        filename: `recording_${Date.now()}.webm`,
        content_type: finalBlob.type || 'audio/webm',
        file_size_total: finalBlob.size,
        file_checksum: await calculateChecksum(finalBlob)
      }),
    });
    
    if (!response.ok) {
      throw new Error(`Error creando sesión: ${response.status}`);
    }
    
    const result = await response.json();
    return {
      recordingId: result.recording_id,
      uploadSessionId: result.upload_session_id,
      uploadUrls: result.upload_urls,
      chunkConfig: result.chunk_config
    };
  }, [audioMetadata, calculateChecksum]);
  
  /**
   * Subir un chunk individual
   */
  const uploadChunk = useCallback(async (
    session: UploadSession,
    chunk: ChunkInfo,
    totalChunks: number,
    signal?: AbortSignal
  ): Promise<boolean> => {
    const formData = new FormData();
    formData.append('upload_session_id', session.uploadSessionId);
    formData.append('chunk_number', chunk.number.toString());
    formData.append('total_chunks', totalChunks.toString());
    formData.append('file', chunk.data, `chunk_${chunk.number.toString().padStart(6, '0')}`);
    
    const response = await fetch(session.uploadUrls.chunkUploadUrl, {
      method: 'POST',
      body: formData,
      signal
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }
    
    const result = await response.json();
    return result.status === 'received';
  }, []);
  
  /**
   * Completar upload y ensamblar archivo
   */
  const completeUpload = useCallback(async (session: UploadSession): Promise<string> => {
    const formData = new FormData();
    formData.append('upload_session_id', session.uploadSessionId);
    formData.append('validate_checksum', 'true');
    
    const response = await fetch(session.uploadUrls.completeUrl, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      throw new Error(`Error completando upload: ${response.status}`);
    }
    
    const result = await response.json();
    return result.final_file_url;
  }, []);
  
  /**
   * Procesar upload con retry automático
   */
  const processUpload = useCallback(async () => {
    if (!uploadSession || chunks.length === 0) return;
    
    setIsUploading(true);
    setCurrentError(null);
    abortControllerRef.current = new AbortController();
    
    try {
      // Subir chunks pendientes
      const pendingChunks = chunks.filter(chunk => !chunk.uploaded);
      
      for (const chunk of pendingChunks) {
        if (isPaused || abortControllerRef.current?.signal.aborted) {
          break;
        }
        
        let success = false;
        let retryCount = 0;
        
        while (!success && retryCount < MAX_RETRIES) {
          try {
            // Actualizar estado: subiendo chunk
            setChunks(prev => prev.map(c => 
              c.number === chunk.number 
                ? { ...c, uploading: true, error: undefined }
                : c
            ));
            
            setProgress(prev => ({ ...prev, currentChunk: chunk.number }));
            
            // Intentar subir chunk
            success = await uploadChunk(
              uploadSession, 
              chunk, 
              chunks.length,
              abortControllerRef.current?.signal
            );
            
            if (success) {
              // Chunk subido exitosamente
              setChunks(prev => prev.map(c => 
                c.number === chunk.number 
                  ? { ...c, uploaded: true, uploading: false }
                  : c
              ));
              
              // Actualizar progreso
              const newChunksUploaded = chunks.filter(c => 
                c.uploaded || c.number === chunk.number
              ).length;
              
              const newBytesUploaded = chunks
                .filter(c => c.uploaded || c.number === chunk.number)
                .reduce((sum, c) => sum + c.size, 0);
              
              const newProgress: UploadProgress = {
                chunksUploaded: newChunksUploaded,
                totalChunks: chunks.length,
                bytesUploaded: newBytesUploaded,
                totalBytes: audioBlob.size,
                percentage: (newBytesUploaded / audioBlob.size) * 100
              };
              
              setProgress(newProgress);
              onProgress?.(newProgress);
            }
            
          } catch (error) {
            retryCount++;
            
            if (retryCount < MAX_RETRIES) {
              // Esperar antes del retry con backoff exponencial
              const delay = RETRY_DELAY_BASE * Math.pow(2, retryCount - 1);
              await new Promise(resolve => setTimeout(resolve, delay));
            } else {
              // Máximo de reintentos alcanzado
              const uploadError: UploadError = {
                type: 'network',
                message: `Error subiendo chunk ${chunk.number}: ${error}`,
                chunk: chunk.number,
                retryable: true
              };
              
              setChunks(prev => prev.map(c => 
                c.number === chunk.number 
                  ? { ...c, uploading: false, error: uploadError.message, retryCount }
                  : c
              ));
              
              setCurrentError(uploadError);
              onError?.(uploadError);
              throw error;
            }
          }
        }
      }
      
      // Todos los chunks subidos, completar upload
      if (!isPaused && !abortControllerRef.current?.signal.aborted) {
        setIsCompleting(true);
        const finalUrl = await completeUpload(uploadSession);
        
        onComplete?.({
          recordingId: uploadSession.recordingId,
          finalUrl
        });
      }
      
    } catch (error) {
      if (!abortControllerRef.current?.signal.aborted) {
        const uploadError: UploadError = {
          type: 'server',
          message: `Error en upload: ${error}`,
          retryable: true
        };
        setCurrentError(uploadError);
        onError?.(uploadError);
      }
    } finally {
      setIsUploading(false);
      setIsCompleting(false);
      setProgress(prev => ({ ...prev, currentChunk: undefined }));
    }
  }, [uploadSession, chunks, isPaused, uploadChunk, completeUpload, onProgress, onComplete, onError, audioBlob.size]);
  
  /**
   * Iniciar upload
   */
  const startUpload = useCallback(async () => {
    try {
      onUploadStart?.();
      
      // Comprimir audio si está habilitado
      const finalBlob = await compressAudio(audioBlob);
      
      // Crear sesión de upload
      const session = await createUploadSession(finalBlob);
      setUploadSession(session);
      
      // Crear chunks
      const chunkSize = session.chunkConfig.recommendedChunkSizeMb * 1024 * 1024;
      const fileChunks = await createChunks(finalBlob, chunkSize);
      setChunks(fileChunks);
      
      // Inicializar progreso
      const initialProgress: UploadProgress = {
        chunksUploaded: 0,
        totalChunks: fileChunks.length,
        bytesUploaded: 0,
        totalBytes: finalBlob.size,
        percentage: 0
      };
      setProgress(initialProgress);
      onProgress?.(initialProgress);
      
      // Iniciar proceso de upload
      uploadPromiseRef.current = processUpload();
      
    } catch (error) {
      const uploadError: UploadError = {
        type: 'server',
        message: `Error iniciando upload: ${error}`,
        retryable: true
      };
      setCurrentError(uploadError);
      onError?.(uploadError);
    }
  }, [audioBlob, compressAudio, createUploadSession, createChunks, onUploadStart, onProgress, onError, processUpload]);
  
  /**
   * Pausar upload
   */
  const pauseUpload = useCallback(() => {
    setIsPaused(true);
    abortControllerRef.current?.abort();
  }, []);
  
  /**
   * Reanudar upload
   */
  const resumeUpload = useCallback(() => {
    setIsPaused(false);
    uploadPromiseRef.current = processUpload();
  }, [processUpload]);
  
  /**
   * Cancelar upload
   */
  const cancelUpload = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsUploading(false);
    setIsPaused(false);
    setCurrentError(null);
    onCancel?.();
  }, [onCancel]);
  
  /**
   * Reintentar chunk con error
   */
  const retryChunk = useCallback((chunkNumber: number) => {
    setChunks(prev => prev.map(c => 
      c.number === chunkNumber 
        ? { ...c, uploaded: false, error: undefined, retryCount: 0 }
        : c
    ));
    setCurrentError(null);
    
    if (!isUploading) {
      uploadPromiseRef.current = processUpload();
    }
  }, [isUploading, processUpload]);
  
  // Cleanup al desmontar
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);
  
  // Render del componente
  return (
    <div className={`chunk-uploader ${className}`}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 space-y-6">
        
        {/* Header con información del archivo */}
        <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Subiendo Grabación de Clase
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {audioMetadata.asignatura} - {audioMetadata.tema}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-500">
            Duración: {Math.round(audioMetadata.duration / 60)}min | 
            Tamaño: {(audioBlob.size / (1024 * 1024)).toFixed(1)}MB
          </p>
        </div>
        
        {/* Barra de progreso principal */}
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Progreso de subida
            </span>
            <span className="text-sm text-gray-600 dark:text-gray-400">
              {progress.percentage.toFixed(1)}%
            </span>
          </div>
          
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
            <div 
              className="bg-blue-600 h-3 rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress.percentage}%` }}
            />
          </div>
          
          <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>
              {progress.chunksUploaded} / {progress.totalChunks} chunks
            </span>
            <span>
              {(progress.bytesUploaded / (1024 * 1024)).toFixed(1)} / {(progress.totalBytes / (1024 * 1024)).toFixed(1)} MB
            </span>
          </div>
        </div>
        
        {/* Estado de compresión */}
        {isCompressing && compressionProgress && (
          <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4 space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-sm font-medium text-purple-800 dark:text-purple-200">
                Comprimiendo audio
              </span>
              <span className="text-sm text-purple-600 dark:text-purple-400">
                {compressionProgress.percentage.toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-purple-200 dark:bg-purple-700 rounded-full h-2">
              <div 
                className="bg-purple-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${compressionProgress.percentage}%` }}
              />
            </div>
            <p className="text-xs text-purple-700 dark:text-purple-300">
              {compressionProgress.message}
            </p>
          </div>
        )}
        
        {/* Estadísticas de compresión */}
        {compressionStats && (
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-gray-600 dark:text-gray-400">Tamaño original:</span>
                <span className="ml-2 font-medium">{(compressionStats.originalSize / (1024 * 1024)).toFixed(1)}MB</span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">Comprimido:</span>
                <span className="ml-2 font-medium text-green-600">{(compressionStats.compressedSize / (1024 * 1024)).toFixed(1)}MB</span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">Ratio:</span>
                <span className="ml-2 font-medium">{compressionStats.compressionRatio.toFixed(1)}x</span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">Pérdida estimada:</span>
                <span className={`ml-2 font-medium ${
                  compressionStats.estimatedAccuracyLoss < 5 ? 'text-green-600' :
                  compressionStats.estimatedAccuracyLoss < 15 ? 'text-yellow-600' : 'text-red-600'
                }`}>
                  {compressionStats.estimatedAccuracyLoss.toFixed(1)}%
                </span>
              </div>
            </div>
          </div>
        )}
        
        {/* Información de estado actual */}
        {progress.currentChunk && (
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
            <p className="text-sm text-blue-800 dark:text-blue-200">
              Subiendo chunk {progress.currentChunk} de {progress.totalChunks}...
            </p>
          </div>
        )}
        
        {isCompleting && (
          <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
            <p className="text-sm text-green-800 dark:text-green-200">
              Ensamblando archivo final...
            </p>
          </div>
        )}
        
        {/* Errores */}
        {currentError && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <h4 className="text-sm font-medium text-red-800 dark:text-red-200">
                  Error de Upload
                </h4>
                <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                  {currentError.message}
                </p>
                {currentError.retryable && currentError.chunk && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => retryChunk(currentError.chunk!)}
                    className="mt-2"
                  >
                    Reintentar Chunk {currentError.chunk}
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}
        
        {/* Controles de upload */}
        <div className="flex justify-between items-center pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex space-x-3">
            {!uploadSession && (
              <Button
                onClick={startUpload}
                className="bg-green-600 hover:bg-green-700"
                disabled={audioBlob.size === 0}
              >
                Iniciar Subida
              </Button>
            )}
            
            {isUploading && !isPaused && (
              <Button
                onClick={pauseUpload}
                variant="outline"
              >
                Pausar
              </Button>
            )}
            
            {isPaused && (
              <Button
                onClick={resumeUpload}
                className="bg-blue-600 hover:bg-blue-700"
              >
                Reanudar
              </Button>
            )}
          </div>
          
          <Button
            onClick={cancelUpload}
            variant="outline"
            className="text-red-600 border-red-600 hover:bg-red-50"
            disabled={isCompleting}
          >
            Cancelar
          </Button>
        </div>
        
        {/* Lista de chunks (debug, solo en desarrollo) */}
        {process.env.NODE_ENV === 'development' && chunks.length > 0 && (
          <details className="mt-4">
            <summary className="text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer">
              Debug: Estado de chunks ({chunks.length})
            </summary>
            <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
              {chunks.map(chunk => (
                <div 
                  key={chunk.number}
                  className={`text-xs p-2 rounded flex justify-between items-center ${
                    chunk.uploaded 
                      ? 'bg-green-100 dark:bg-green-900/20 text-green-800 dark:text-green-200'
                      : chunk.uploading
                        ? 'bg-blue-100 dark:bg-blue-900/20 text-blue-800 dark:text-blue-200'
                        : chunk.error
                          ? 'bg-red-100 dark:bg-red-900/20 text-red-800 dark:text-red-200'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                  }`}
                >
                  <span>
                    Chunk {chunk.number}: {(chunk.size / 1024).toFixed(1)}KB
                  </span>
                  <span>
                    {chunk.uploaded ? '✓' : chunk.uploading ? '⏳' : chunk.error ? '✗' : '⏸'}
                  </span>
                </div>
              ))}
            </div>
          </details>
        )}
        
      </div>
    </div>
  );
};

export default ChunkUploader;
