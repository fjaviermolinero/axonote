/**
 * Botón especializado para grabación con animaciones médicas
 */

import { useState } from 'react';
import { Button } from './Button';
import { cn } from '@/lib/utils';

interface RecordButtonProps {
  isRecording: boolean;
  isPaused: boolean;
  onStartRecord: () => void;
  onPauseRecord: () => void;
  onResumeRecord: () => void;
  onStopRecord: () => void;
  disabled?: boolean;
  className?: string;
}

export const RecordButton: React.FC<RecordButtonProps> = ({
  isRecording,
  isPaused,
  onStartRecord,
  onPauseRecord,
  onResumeRecord,
  onStopRecord,
  disabled,
  className,
}) => {
  const [isLongPress, setIsLongPress] = useState(false);

  const handleStart = () => {
    if (!isRecording) {
      onStartRecord();
    } else if (isPaused) {
      onResumeRecord();
    } else {
      onPauseRecord();
    }
  };

  const handleLongPress = () => {
    if (isRecording) {
      setIsLongPress(true);
      setTimeout(() => {
        onStopRecord();
        setIsLongPress(false);
      }, 1000);
    }
  };

  return (
    <div className={cn('flex flex-col items-center space-y-4', className)}>
      {/* Botón principal de grabación */}
      <div className="relative">
        <Button
          variant={isRecording ? (isPaused ? 'warning' : 'error') : 'primary'}
          size="xl"
          onClick={handleStart}
          onMouseDown={handleLongPress}
          disabled={disabled}
          className={cn(
            'rounded-full w-20 h-20 shadow-2xl transition-all duration-300',
            isRecording && !isPaused && 'animate-pulse bg-red-500 hover:bg-red-600',
            isPaused && 'bg-yellow-500 hover:bg-yellow-600',
            !isRecording && 'bg-primary-600 hover:bg-primary-700'
          )}
        >
          {!isRecording ? (
            // Icono micrófono
            <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v1a7 7 0 0 1-14 0v-1a1 1 0 0 1 2 0v1a5 5 0 0 0 10 0v-1a1 1 0 0 1 2 0Z" />
              <path d="M12 19a1 1 0 0 1 0 2h-2a1 1 0 0 1 0-2h2Z" />
            </svg>
          ) : isPaused ? (
            // Icono play
            <svg className="w-8 h-8 ml-1" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          ) : (
            // Icono pausa
            <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
            </svg>
          )}
        </Button>

        {/* Anillo de grabación animado */}
        {isRecording && !isPaused && (
          <div className="absolute inset-0 rounded-full border-4 border-red-500 animate-ping opacity-75" />
        )}

        {/* Indicador de larga pulsación */}
        {isLongPress && (
          <div className="absolute inset-0 rounded-full border-4 border-white animate-pulse" />
        )}
      </div>

      {/* Texto de estado */}
      <div className="text-center">
        <p className="text-lg font-medium text-gray-800">
          {!isRecording && 'Pulsar para grabar'}
          {isRecording && !isPaused && 'Grabando...'}
          {isRecording && isPaused && 'Pausado'}
        </p>
        {isRecording && (
          <p className="text-sm text-gray-600 mt-1">
            {isPaused ? 'Pulsar para continuar' : 'Pulsar para pausar'}
            <br />
            <span className="text-xs">Mantener pulsado para detener</span>
          </p>
        )}
      </div>

      {/* Botón de parada (visible solo durante grabación) */}
      {isRecording && (
        <Button
          variant="outline"
          size="md"
          onClick={onStopRecord}
          className="border-red-500 text-red-500 hover:bg-red-50"
        >
          <svg className="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 6h12v12H6z" />
          </svg>
          Finalizar grabación
        </Button>
      )}
    </div>
  );
};
