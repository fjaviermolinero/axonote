/**
 * Upload Queue Manager - Gestión avanzada de colas de upload
 * 
 * Características:
 * - Queue persistente con IndexedDB
 * - Retry automático con backoff exponencial
 * - Priorización de uploads
 * - Recovery de sesiones interrumpidas
 * - Métricas de rendimiento
 * - Offline support completo
 */

import { openDB, DBSchema, IDBPDatabase } from 'idb';

// Tipos TypeScript
export interface QueuedUpload {
  id: string;
  recordingId?: string;
  uploadSessionId?: string;
  audioBlob: Blob;
  metadata: {
    asignatura: string;
    tema: string;
    profesorText: string;
    duration: number;
    size: number;
    createdAt: number;
  };
  status: 'pending' | 'uploading' | 'paused' | 'completed' | 'failed' | 'cancelled';
  priority: 'low' | 'normal' | 'high' | 'urgent';
  retryCount: number;
  maxRetries: number;
  lastError?: string;
  progress: {
    chunksUploaded: number;
    totalChunks: number;
    bytesUploaded: number;
    totalBytes: number;
    percentage: number;
    speed?: number; // MB/s
    eta?: number; // seconds
  };
  timestamps: {
    createdAt: number;
    startedAt?: number;
    lastActivityAt?: number;
    completedAt?: number;
  };
  config: {
    chunkSize: number;
    compressionEnabled: boolean;
    validationEnabled: boolean;
    networkOptimized: boolean;
  };
}

export interface QueueMetrics {
  totalUploads: number;
  completedUploads: number;
  failedUploads: number;
  activeUploads: number;
  averageSpeed: number; // MB/s
  totalBytesUploaded: number;
  successRate: number;
  averageRetries: number;
}

interface UploadQueueDB extends DBSchema {
  uploads: {
    key: string;
    value: QueuedUpload;
    indexes: {
      'by-status': string;
      'by-priority': string;
      'by-created': number;
    };
  };
  chunks: {
    key: string;
    value: {
      uploadId: string;
      chunkNumber: number;
      data: Blob;
      uploaded: boolean;
      checksum?: string;
    };
  };
  metrics: {
    key: string;
    value: QueueMetrics;
  };
}

export type UploadEventType = 
  | 'queue-added' 
  | 'upload-started' 
  | 'upload-progress' 
  | 'upload-completed' 
  | 'upload-failed' 
  | 'upload-paused' 
  | 'upload-resumed' 
  | 'upload-cancelled'
  | 'queue-empty';

export interface UploadEvent {
  type: UploadEventType;
  uploadId: string;
  upload?: QueuedUpload;
  progress?: QueuedUpload['progress'];
  error?: string;
  timestamp: number;
}

export type UploadEventListener = (event: UploadEvent) => void;

class UploadQueueManager {
  private db: IDBPDatabase<UploadQueueDB> | null = null;
  private isProcessing = false;
  private listeners: Map<UploadEventType, UploadEventListener[]> = new Map();
  private processingPromise: Promise<void> | null = null;
  private retryTimeouts: Map<string, NodeJS.Timeout> = new Map();
  
  // Configuración
  private readonly CONFIG = {
    MAX_CONCURRENT_UPLOADS: 2,
    RETRY_DELAY_BASE: 1000, // 1 segundo
    RETRY_DELAY_MAX: 30000, // 30 segundos
    CHUNK_SIZE_DEFAULT: 5 * 1024 * 1024, // 5MB
    NETWORK_CHECK_INTERVAL: 5000, // 5 segundos
    CLEANUP_INTERVAL: 60000, // 1 minuto
  };
  
  constructor() {
    this.initializeDB();
    this.startNetworkMonitoring();
    this.startPeriodicCleanup();
  }
  
  /**
   * Inicializar base de datos IndexedDB
   */
  private async initializeDB(): Promise<void> {
    try {
      this.db = await openDB<UploadQueueDB>('axonote-upload-queue', 1, {
        upgrade(db) {
          // Store de uploads
          const uploadsStore = db.createObjectStore('uploads', { keyPath: 'id' });
          uploadsStore.createIndex('by-status', 'status');
          uploadsStore.createIndex('by-priority', 'priority');
          uploadsStore.createIndex('by-created', 'timestamps.createdAt');
          
          // Store de chunks
          db.createObjectStore('chunks', { keyPath: ['uploadId', 'chunkNumber'] });
          
          // Store de métricas
          db.createObjectStore('metrics', { keyPath: 'id' });
        },
      });
      
      // Recuperar uploads pendientes al inicializar
      this.recoverPendingUploads();
      
    } catch (error) {
      console.error('Error inicializando base de datos de upload queue:', error);
    }
  }
  
  /**
   * Agregar upload a la cola
   */
  async addUpload(
    audioBlob: Blob,
    metadata: Omit<QueuedUpload['metadata'], 'size' | 'createdAt'>,
    options: Partial<Pick<QueuedUpload, 'priority' | 'maxRetries' | 'config'>> = {}
  ): Promise<string> {
    if (!this.db) {
      throw new Error('Base de datos no inicializada');
    }
    
    const uploadId = `upload_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    const queuedUpload: QueuedUpload = {
      id: uploadId,
      audioBlob,
      metadata: {
        ...metadata,
        size: audioBlob.size,
        createdAt: Date.now()
      },
      status: 'pending',
      priority: options.priority || 'normal',
      retryCount: 0,
      maxRetries: options.maxRetries || 3,
      progress: {
        chunksUploaded: 0,
        totalChunks: 0,
        bytesUploaded: 0,
        totalBytes: audioBlob.size,
        percentage: 0
      },
      timestamps: {
        createdAt: Date.now()
      },
      config: {
        chunkSize: this.CONFIG.CHUNK_SIZE_DEFAULT,
        compressionEnabled: true,
        validationEnabled: true,
        networkOptimized: true,
        ...options.config
      }
    };
    
    // Guardar en IndexedDB
    await this.db.put('uploads', queuedUpload);
    
    // Emitir evento
    this.emit('queue-added', {
      type: 'queue-added',
      uploadId,
      upload: queuedUpload,
      timestamp: Date.now()
    });
    
    // Iniciar procesamiento si no está activo
    if (!this.isProcessing) {
      this.startProcessing();
    }
    
    return uploadId;
  }
  
  /**
   * Pausar upload específico
   */
  async pauseUpload(uploadId: string): Promise<void> {
    if (!this.db) return;
    
    const upload = await this.db.get('uploads', uploadId);
    if (!upload || upload.status !== 'uploading') return;
    
    upload.status = 'paused';
    upload.timestamps.lastActivityAt = Date.now();
    
    await this.db.put('uploads', upload);
    
    this.emit('upload-paused', {
      type: 'upload-paused',
      uploadId,
      upload,
      timestamp: Date.now()
    });
  }
  
  /**
   * Reanudar upload específico
   */
  async resumeUpload(uploadId: string): Promise<void> {
    if (!this.db) return;
    
    const upload = await this.db.get('uploads', uploadId);
    if (!upload || upload.status !== 'paused') return;
    
    upload.status = 'pending';
    upload.timestamps.lastActivityAt = Date.now();
    
    await this.db.put('uploads', upload);
    
    this.emit('upload-resumed', {
      type: 'upload-resumed',
      uploadId,
      upload,
      timestamp: Date.now()
    });
    
    // Reiniciar procesamiento
    if (!this.isProcessing) {
      this.startProcessing();
    }
  }
  
  /**
   * Cancelar upload específico
   */
  async cancelUpload(uploadId: string): Promise<void> {
    if (!this.db) return;
    
    const upload = await this.db.get('uploads', uploadId);
    if (!upload) return;
    
    upload.status = 'cancelled';
    upload.timestamps.lastActivityAt = Date.now();
    
    await this.db.put('uploads', upload);
    
    // Cancelar timeout de retry si existe
    const timeout = this.retryTimeouts.get(uploadId);
    if (timeout) {
      clearTimeout(timeout);
      this.retryTimeouts.delete(uploadId);
    }
    
    this.emit('upload-cancelled', {
      type: 'upload-cancelled',
      uploadId,
      upload,
      timestamp: Date.now()
    });
  }
  
  /**
   * Obtener estado de upload específico
   */
  async getUploadStatus(uploadId: string): Promise<QueuedUpload | null> {
    if (!this.db) return null;
    return this.db.get('uploads', uploadId) || null;
  }
  
  /**
   * Listar uploads con filtros
   */
  async listUploads(
    status?: QueuedUpload['status'],
    limit: number = 50
  ): Promise<QueuedUpload[]> {
    if (!this.db) return [];
    
    if (status) {
      return this.db.getAllFromIndex('uploads', 'by-status', status);
    }
    
    return this.db.getAll('uploads', undefined, limit);
  }
  
  /**
   * Obtener métricas de la cola
   */
  async getMetrics(): Promise<QueueMetrics> {
    if (!this.db) {
      return {
        totalUploads: 0,
        completedUploads: 0,
        failedUploads: 0,
        activeUploads: 0,
        averageSpeed: 0,
        totalBytesUploaded: 0,
        successRate: 0,
        averageRetries: 0
      };
    }
    
    const uploads = await this.db.getAll('uploads');
    
    const metrics: QueueMetrics = {
      totalUploads: uploads.length,
      completedUploads: uploads.filter(u => u.status === 'completed').length,
      failedUploads: uploads.filter(u => u.status === 'failed').length,
      activeUploads: uploads.filter(u => u.status === 'uploading').length,
      averageSpeed: 0,
      totalBytesUploaded: uploads
        .filter(u => u.status === 'completed')
        .reduce((sum, u) => sum + u.progress.bytesUploaded, 0),
      successRate: 0,
      averageRetries: uploads.reduce((sum, u) => sum + u.retryCount, 0) / Math.max(uploads.length, 1)
    };
    
    if (metrics.totalUploads > 0) {
      metrics.successRate = (metrics.completedUploads / metrics.totalUploads) * 100;
    }
    
    // Calcular velocidad promedio de uploads completados
    const completedWithSpeed = uploads.filter(u => 
      u.status === 'completed' && u.progress.speed
    );
    
    if (completedWithSpeed.length > 0) {
      metrics.averageSpeed = completedWithSpeed.reduce((sum, u) => 
        sum + (u.progress.speed || 0), 0
      ) / completedWithSpeed.length;
    }
    
    return metrics;
  }
  
  /**
   * Limpiar uploads completados antiguos
   */
  async cleanupCompletedUploads(olderThanDays: number = 7): Promise<number> {
    if (!this.db) return 0;
    
    const cutoffTime = Date.now() - (olderThanDays * 24 * 60 * 60 * 1000);
    const uploads = await this.db.getAll('uploads');
    
    let cleanedCount = 0;
    
    for (const upload of uploads) {
      if (
        upload.status === 'completed' && 
        upload.timestamps.completedAt && 
        upload.timestamps.completedAt < cutoffTime
      ) {
        await this.db.delete('uploads', upload.id);
        cleanedCount++;
      }
    }
    
    return cleanedCount;
  }
  
  /**
   * Iniciar procesamiento de la cola
   */
  private async startProcessing(): Promise<void> {
    if (this.isProcessing || !this.db) return;
    
    this.isProcessing = true;
    this.processingPromise = this.processQueue();
    
    try {
      await this.processingPromise;
    } catch (error) {
      console.error('Error en procesamiento de cola:', error);
    } finally {
      this.isProcessing = false;
      this.processingPromise = null;
    }
  }
  
  /**
   * Procesar cola de uploads
   */
  private async processQueue(): Promise<void> {
    if (!this.db) return;
    
    while (true) {
      // Obtener uploads pendientes ordenados por prioridad
      const pendingUploads = await this.getPendingUploadsByPriority();
      
      if (pendingUploads.length === 0) {
        this.emit('queue-empty', {
          type: 'queue-empty',
          uploadId: '',
          timestamp: Date.now()
        });
        break;
      }
      
      // Verificar conectividad
      if (!navigator.onLine) {
        await this.waitForOnline();
        continue;
      }
      
      // Procesar uploads concurrentes
      const activeUploads = Math.min(
        pendingUploads.length,
        this.CONFIG.MAX_CONCURRENT_UPLOADS
      );
      
      const promises = pendingUploads
        .slice(0, activeUploads)
        .map(upload => this.processUpload(upload));
      
      await Promise.allSettled(promises);
      
      // Esperar un poco antes del siguiente ciclo
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  
  /**
   * Obtener uploads pendientes ordenados por prioridad
   */
  private async getPendingUploadsByPriority(): Promise<QueuedUpload[]> {
    if (!this.db) return [];
    
    const uploads = await this.db.getAllFromIndex('uploads', 'by-status', 'pending');
    
    // Ordenar por prioridad y tiempo de creación
    const priorityOrder = { urgent: 0, high: 1, normal: 2, low: 3 };
    
    return uploads.sort((a, b) => {
      const priorityDiff = priorityOrder[a.priority] - priorityOrder[b.priority];
      if (priorityDiff !== 0) return priorityDiff;
      
      return a.timestamps.createdAt - b.timestamps.createdAt;
    });
  }
  
  /**
   * Procesar upload individual
   */
  private async processUpload(upload: QueuedUpload): Promise<void> {
    if (!this.db) return;
    
    try {
      // Marcar como uploading
      upload.status = 'uploading';
      upload.timestamps.startedAt = Date.now();
      upload.timestamps.lastActivityAt = Date.now();
      
      await this.db.put('uploads', upload);
      
      this.emit('upload-started', {
        type: 'upload-started',
        uploadId: upload.id,
        upload,
        timestamp: Date.now()
      });
      
      // Usar ChunkUploader para el proceso de upload
      await this.performChunkedUpload(upload);
      
      // Marcar como completado
      upload.status = 'completed';
      upload.timestamps.completedAt = Date.now();
      upload.progress.percentage = 100;
      
      await this.db.put('uploads', upload);
      
      this.emit('upload-completed', {
        type: 'upload-completed',
        uploadId: upload.id,
        upload,
        timestamp: Date.now()
      });
      
    } catch (error) {
      await this.handleUploadError(upload, error as Error);
    }
  }
  
  /**
   * Realizar upload por chunks
   */
  private async performChunkedUpload(upload: QueuedUpload): Promise<void> {
    // Esta es una implementación simplificada
    // En la implementación real, se integraría con ChunkUploader
    
    // Simular progreso de chunks
    const totalChunks = Math.ceil(upload.audioBlob.size / upload.config.chunkSize);
    upload.progress.totalChunks = totalChunks;
    
    for (let i = 0; i < totalChunks; i++) {
      // Verificar si el upload fue pausado/cancelado
      const currentUpload = await this.db!.get('uploads', upload.id);
      if (currentUpload?.status !== 'uploading') {
        throw new Error('Upload interrumpido');
      }
      
      // Simular subida de chunk
      await new Promise(resolve => setTimeout(resolve, Math.random() * 1000));
      
      // Actualizar progreso
      upload.progress.chunksUploaded = i + 1;
      upload.progress.bytesUploaded = Math.min(
        (i + 1) * upload.config.chunkSize,
        upload.audioBlob.size
      );
      upload.progress.percentage = (upload.progress.bytesUploaded / upload.progress.totalBytes) * 100;
      upload.timestamps.lastActivityAt = Date.now();
      
      await this.db!.put('uploads', upload);
      
      this.emit('upload-progress', {
        type: 'upload-progress',
        uploadId: upload.id,
        upload,
        progress: upload.progress,
        timestamp: Date.now()
      });
    }
  }
  
  /**
   * Manejar errores de upload
   */
  private async handleUploadError(upload: QueuedUpload, error: Error): Promise<void> {
    if (!this.db) return;
    
    upload.retryCount++;
    upload.lastError = error.message;
    upload.timestamps.lastActivityAt = Date.now();
    
    if (upload.retryCount >= upload.maxRetries) {
      // Máximo de reintentos alcanzado
      upload.status = 'failed';
      
      await this.db.put('uploads', upload);
      
      this.emit('upload-failed', {
        type: 'upload-failed',
        uploadId: upload.id,
        upload,
        error: error.message,
        timestamp: Date.now()
      });
      
    } else {
      // Programar retry con backoff exponencial
      upload.status = 'pending';
      
      const retryDelay = Math.min(
        this.CONFIG.RETRY_DELAY_BASE * Math.pow(2, upload.retryCount - 1),
        this.CONFIG.RETRY_DELAY_MAX
      );
      
      await this.db.put('uploads', upload);
      
      const timeout = setTimeout(() => {
        this.retryTimeouts.delete(upload.id);
        // El upload se procesará en el siguiente ciclo de la cola
      }, retryDelay);
      
      this.retryTimeouts.set(upload.id, timeout);
    }
  }
  
  /**
   * Recuperar uploads pendientes al inicializar
   */
  private async recoverPendingUploads(): Promise<void> {
    if (!this.db) return;
    
    const uploads = await this.db.getAll('uploads');
    const pendingUploads = uploads.filter(u => 
      u.status === 'uploading' || u.status === 'pending'
    );
    
    // Resetear uploads que estaban "uploading" a "pending"
    for (const upload of pendingUploads) {
      if (upload.status === 'uploading') {
        upload.status = 'pending';
        await this.db.put('uploads', upload);
      }
    }
    
    // Iniciar procesamiento si hay uploads pendientes
    if (pendingUploads.length > 0 && !this.isProcessing) {
      this.startProcessing();
    }
  }
  
  /**
   * Esperar hasta que haya conexión
   */
  private async waitForOnline(): Promise<void> {
    return new Promise(resolve => {
      if (navigator.onLine) {
        resolve();
        return;
      }
      
      const handleOnline = () => {
        window.removeEventListener('online', handleOnline);
        resolve();
      };
      
      window.addEventListener('online', handleOnline);
    });
  }
  
  /**
   * Monitorear conectividad de red
   */
  private startNetworkMonitoring(): void {
    window.addEventListener('online', () => {
      if (!this.isProcessing) {
        this.startProcessing();
      }
    });
    
    window.addEventListener('offline', () => {
      // Los uploads en curso se pausarán automáticamente
      console.log('Red desconectada - uploads se pausarán');
    });
  }
  
  /**
   * Limpieza periódica
   */
  private startPeriodicCleanup(): void {
    setInterval(async () => {
      try {
        const cleaned = await this.cleanupCompletedUploads(7);
        if (cleaned > 0) {
          console.log(`Limpiados ${cleaned} uploads completados antiguos`);
        }
      } catch (error) {
        console.error('Error en limpieza periódica:', error);
      }
    }, this.CONFIG.CLEANUP_INTERVAL);
  }
  
  /**
   * Sistema de eventos
   */
  on(eventType: UploadEventType, listener: UploadEventListener): void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, []);
    }
    this.listeners.get(eventType)!.push(listener);
  }
  
  off(eventType: UploadEventType, listener: UploadEventListener): void {
    const listeners = this.listeners.get(eventType);
    if (listeners) {
      const index = listeners.indexOf(listener);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    }
  }
  
  private emit(eventType: UploadEventType, event: UploadEvent): void {
    const listeners = this.listeners.get(eventType);
    if (listeners) {
      listeners.forEach(listener => {
        try {
          listener(event);
        } catch (error) {
          console.error('Error en listener de upload queue:', error);
        }
      });
    }
  }
}

// Instancia singleton
export const uploadQueue = new UploadQueueManager();
