/**
 * SyncIndicator - Indicador de sincronización en tiempo real
 */

'use client';

import React, { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { 
  WifiIcon,
  CloudIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ArrowPathIcon,
  XCircleIcon
} from '@heroicons/react/24/outline';

export interface SyncIndicatorProps {
  className?: string;
  status: 'online' | 'offline' | 'syncing' | 'error' | 'completed';
  pendingCount?: number;
  lastSync?: Date;
  onRetry?: () => void;
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left' | 'inline';
  showDetails?: boolean;
}

const statusConfig = {
  online: {
    icon: CloudIcon,
    label: 'En línea',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
    description: 'Conectado y sincronizado'
  },
  offline: {
    icon: WifiIcon,
    label: 'Sin conexión',
    color: 'text-gray-600',
    bgColor: 'bg-gray-50',
    borderColor: 'border-gray-200',
    description: 'Datos guardados localmente'
  },
  syncing: {
    icon: ArrowPathIcon,
    label: 'Sincronizando',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    description: 'Subiendo datos al servidor'
  },
  error: {
    icon: ExclamationTriangleIcon,
    label: 'Error',
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    description: 'Error en la sincronización'
  },
  completed: {
    icon: CheckCircleIcon,
    label: 'Completado',
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
    description: 'Sincronización exitosa'
  }
};

const positionConfig = {
  'top-right': 'fixed top-4 right-4 z-50',
  'top-left': 'fixed top-4 left-4 z-50',
  'bottom-right': 'fixed bottom-4 right-4 z-50',
  'bottom-left': 'fixed bottom-4 left-4 z-50',
  'inline': 'relative'
};

export function SyncIndicator({
  className,
  status,
  pendingCount = 0,
  lastSync,
  onRetry,
  position = 'top-right',
  showDetails = true,
  ...props
}: SyncIndicatorProps) {
  
  const [isExpanded, setIsExpanded] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  
  const config = statusConfig[status];
  const IconComponent = config.icon;
  
  // Auto-collapse después de mostrar éxito
  useEffect(() => {
    if (status === 'completed') {
      setShowSuccess(true);
      const timer = setTimeout(() => {
        setShowSuccess(false);
        setIsExpanded(false);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [status]);
  
  const formatLastSync = (date: Date) => {
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    
    if (diffMins < 1) return 'Ahora mismo';
    if (diffMins < 60) return `Hace ${diffMins}m`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `Hace ${diffHours}h`;
    
    const diffDays = Math.floor(diffHours / 24);
    return `Hace ${diffDays}d`;
  };

  const handleClick = () => {
    if (status === 'error' && onRetry) {
      onRetry();
    } else if (showDetails) {
      setIsExpanded(!isExpanded);
    }
  };

  return (
    <div
      className={cn(
        'sync-indicator',
        positionConfig[position],
        className
      )}
      {...props}
    >
      {/* Indicador principal */}
      <div
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-lg border shadow-sm',
          'transition-all duration-300 cursor-pointer select-none',
          'hover:shadow-md',
          config.bgColor,
          config.borderColor,
          isExpanded && 'rounded-b-none'
        )}
        onClick={handleClick}
      >
        {/* Icono con animación */}
        <div className="relative">
          <IconComponent 
            className={cn(
              'w-4 h-4 transition-transform duration-300',
              config.color,
              status === 'syncing' && 'animate-spin',
              isExpanded && 'scale-110'
            )} 
          />
          
          {/* Indicador de pendientes */}
          {pendingCount > 0 && (
            <div className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full flex items-center justify-center">
              <span className="text-white text-xs font-bold leading-none">
                {pendingCount > 9 ? '9+' : pendingCount}
              </span>
            </div>
          )}
        </div>
        
        {/* Texto del estado */}
        <span className={cn('text-sm font-medium', config.color)}>
          {config.label}
        </span>
        
        {/* Indicador de expandido */}
        {showDetails && (
          <div className={cn(
            'w-1 h-1 rounded-full transition-transform duration-300',
            config.color.replace('text-', 'bg-'),
            isExpanded && 'scale-150'
          )} />
        )}
        
        {/* Animación de éxito */}
        {showSuccess && status === 'completed' && (
          <div className="absolute inset-0 bg-green-100 rounded-lg animate-ping opacity-75" />
        )}
      </div>
      
      {/* Panel expandido */}
      {isExpanded && showDetails && (
        <div className={cn(
          'mt-0 p-3 rounded-b-lg border border-t-0 shadow-sm bg-white',
          'min-w-64 transition-all duration-300',
          config.borderColor
        )}>
          <div className="space-y-2">
            {/* Descripción del estado */}
            <p className="text-sm text-gray-600">
              {config.description}
            </p>
            
            {/* Información adicional */}
            <div className="text-xs text-gray-500 space-y-1">
              {lastSync && (
                <div className="flex justify-between">
                  <span>Última sincronización:</span>
                  <span className="font-medium">{formatLastSync(lastSync)}</span>
                </div>
              )}
              
              {pendingCount > 0 && (
                <div className="flex justify-between">
                  <span>Pendientes:</span>
                  <span className="font-medium text-orange-600">
                    {pendingCount} elemento{pendingCount !== 1 ? 's' : ''}
                  </span>
                </div>
              )}
              
              {status === 'offline' && (
                <div className="text-amber-600 text-xs mt-2 p-2 bg-amber-50 rounded border-l-2 border-amber-300">
                  💾 Los datos se guardan localmente y se sincronizarán cuando vuelva la conexión
                </div>
              )}
              
              {status === 'error' && onRetry && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onRetry();
                  }}
                  className="w-full mt-2 px-3 py-1.5 bg-red-500 text-white text-xs rounded hover:bg-red-600 transition-colors"
                >
                  🔄 Reintentar sincronización
                </button>
              )}
            </div>
            
            {/* Progreso de sincronización */}
            {status === 'syncing' && (
              <div className="mt-2">
                <div className="w-full h-1 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full animate-pulse" style={{ width: '60%' }} />
                </div>
                <p className="text-xs text-gray-500 mt-1">Sincronizando datos médicos...</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Hook para gestionar el estado de sincronización
export function useSyncStatus() {
  const [status, setStatus] = useState<'online' | 'offline' | 'syncing' | 'error' | 'completed'>('online');
  const [pendingCount, setPendingCount] = useState(0);
  const [lastSync, setLastSync] = useState<Date>(new Date());
  
  useEffect(() => {
    // Listener para estado de conexión
    const handleOnline = () => setStatus('online');
    const handleOffline = () => setStatus('offline');
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    
    // Estado inicial
    setStatus(navigator.onLine ? 'online' : 'offline');
    
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);
  
  const startSync = () => {
    setStatus('syncing');
  };
  
  const completeSync = () => {
    setStatus('completed');
    setLastSync(new Date());
    setPendingCount(0);
  };
  
  const errorSync = () => {
    setStatus('error');
  };
  
  const addPending = (count: number = 1) => {
    setPendingCount(prev => prev + count);
  };
  
  const removePending = (count: number = 1) => {
    setPendingCount(prev => Math.max(0, prev - count));
  };
  
  return {
    status,
    pendingCount,
    lastSync,
    startSync,
    completeSync,
    errorSync,
    addPending,
    removePending
  };
}
