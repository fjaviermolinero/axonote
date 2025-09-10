/**
 * RecordingControls - Controles de grabación fijos con funcionalidad médica avanzada
 */

'use client';

import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { Button } from './Button';
import { RecordButton } from './RecordButton';
import { MedicalBadge } from './MedicalBadge';
import { 
  MicrophoneIcon,
  PauseIcon,
  StopIcon,
  LightBulbIcon,
  QuestionMarkCircleIcon,
  CameraIcon,
  ChatBubbleLeftIcon,
  ClockIcon,
  WaveformIcon
} from '@heroicons/react/24/outline';

interface RecordingControlsProps {
  className?: string;
  isRecording: boolean;
  isPaused: boolean;
  currentTime: number;
  onStartRecording: () => void;
  onPauseRecording: () => void;
  onResumeRecording: () => void;
  onStopRecording: () => void;
  onKeyMoment: (type: 'idea_clave' | 'no_entendi' | 'pregunta' | 'importante') => void;
  onMicromemo: () => void;
  onCaptureImage: (type: 'pizarra' | 'diapositiva') => void;
  sessionInfo?: {
    asignatura?: string;
    tema?: string;
    profesor?: string;
  };
  audioLevel?: number;
  disabled?: boolean;
}

export function RecordingControls({
  className,
  isRecording,
  isPaused,
  currentTime,
  onStartRecording,
  onPauseRecording,
  onResumeRecording,
  onStopRecording,
  onKeyMoment,
  onMicromemo,
  onCaptureImage,
  sessionInfo,
  audioLevel = 0,
  disabled = false,
  ...props
}: RecordingControlsProps) {
  
  const [showQuickActions, setShowQuickActions] = useState(false);
  
  const formatTime = (seconds: number): string => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hrs > 0) {
      return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const quickActions = [
    {
      id: 'idea_clave',
      label: 'Idea Clave',
      icon: LightBulbIcon,
      color: 'bg-green-500 hover:bg-green-600',
      textColor: 'text-white',
      description: 'Marcar concepto importante'
    },
    {
      id: 'no_entendi',
      label: 'No Entendí',
      icon: QuestionMarkCircleIcon,
      color: 'bg-yellow-500 hover:bg-yellow-600',
      textColor: 'text-white',
      description: 'Marcar para revisar'
    },
    {
      id: 'pregunta',
      label: 'Pregunta',
      icon: ChatBubbleLeftIcon,
      color: 'bg-blue-500 hover:bg-blue-600',
      textColor: 'text-white',
      description: 'Marcar pregunta del profesor'
    },
    {
      id: 'importante',
      label: 'Importante',
      icon: '⭐',
      color: 'bg-purple-500 hover:bg-purple-600',
      textColor: 'text-white',
      description: 'Marcar como muy relevante'
    }
  ];

  return (
    <div
      className={cn(
        'recording-controls',
        'fixed bottom-0 left-0 right-0 z-50',
        'bg-white border-t border-gray-200 shadow-lg',
        'transition-all duration-300',
        isRecording ? 'translate-y-0' : 'translate-y-full',
        className
      )}
      {...props}
    >
      {/* Información de sesión */}
      {sessionInfo && (
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
          <div className="flex items-center justify-between max-w-4xl mx-auto">
            <div className="flex items-center gap-4 text-sm">
              {sessionInfo.asignatura && (
                <MedicalBadge variant="especialidad" value="general" size="sm">
                  {sessionInfo.asignatura}
                </MedicalBadge>
              )}
              {sessionInfo.tema && (
                <span className="text-gray-600 truncate max-w-48">
                  {sessionInfo.tema}
                </span>
              )}
              {sessionInfo.profesor && (
                <span className="text-gray-500 truncate max-w-32">
                  Prof. {sessionInfo.profesor}
                </span>
              )}
            </div>
            
            {/* Timer */}
            <div className="flex items-center gap-2 font-mono text-lg font-medium text-gray-900">
              <ClockIcon className="w-5 h-5" />
              {formatTime(currentTime)}
            </div>
          </div>
        </div>
      )}

      {/* Controles principales */}
      <div className="px-4 py-4">
        <div className="flex items-center justify-between max-w-4xl mx-auto">
          {/* Visualización de audio */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <MicrophoneIcon className="w-5 h-5 text-gray-400" />
              <div className="flex items-end gap-0.5 h-6">
                {Array.from({ length: 8 }, (_, i) => (
                  <div
                    key={i}
                    className={cn(
                      'w-1 bg-gray-300 rounded-sm transition-all duration-150',
                      'h-2',
                      audioLevel > (i / 8) && isRecording && !isPaused && 'bg-green-500',
                      audioLevel > (i / 8) && audioLevel > 0.7 && 'bg-red-500'
                    )}
                    style={{
                      height: isRecording && !isPaused && audioLevel > (i / 8) 
                        ? `${8 + (audioLevel * 16)}px` 
                        : '8px'
                    }}
                  />
                ))}
              </div>
            </div>
            
            {/* Estado de grabación */}
            <div className="flex items-center gap-2">
              {isRecording && (
                <MedicalBadge 
                  variant="estado" 
                  value={isPaused ? 'paused' : 'recording'} 
                  size="sm"
                >
                  {isPaused ? '⏸️ Pausado' : '🔴 Grabando'}
                </MedicalBadge>
              )}
            </div>
          </div>

          {/* Botón principal de grabación */}
          <div className="flex items-center gap-3">
            <RecordButton
              isRecording={isRecording}
              isPaused={isPaused}
              onStartRecording={onStartRecording}
              onPauseRecording={onPauseRecording}
              onResumeRecording={onResumeRecording}
              disabled={disabled}
              size="lg"
            />
            
            {isRecording && (
              <Button
                variant="outline"
                size="lg"
                onClick={onStopRecording}
                className="text-red-600 border-red-200 hover:bg-red-50"
                disabled={disabled}
              >
                <StopIcon className="w-5 h-5 mr-2" />
                Detener
              </Button>
            )}
          </div>

          {/* Acciones rápidas */}
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowQuickActions(!showQuickActions)}
              disabled={!isRecording || disabled}
              className={cn(
                'transition-all duration-200',
                showQuickActions && 'bg-primary-50 text-primary-700'
              )}
            >
              <span className="text-lg">⚡</span>
              Acciones
            </Button>
          </div>
        </div>
      </div>

      {/* Panel de acciones rápidas expandido */}
      {showQuickActions && isRecording && (
        <div className="px-4 pb-4 border-t border-gray-100 bg-gray-50">
          <div className="max-w-4xl mx-auto">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 py-3">
              {/* Momentos clave */}
              {quickActions.map((action) => (
                <Button
                  key={action.id}
                  variant="outline"
                  size="sm"
                  onClick={() => onKeyMoment(action.id as any)}
                  className={cn(
                    'flex flex-col items-center gap-1 h-auto py-3',
                    action.color,
                    action.textColor,
                    'border-transparent hover:scale-105 transition-transform'
                  )}
                  disabled={disabled}
                >
                  {typeof action.icon === 'string' ? (
                    <span className="text-xl">{action.icon}</span>
                  ) : (
                    <action.icon className="w-5 h-5" />
                  )}
                  <span className="text-xs font-medium">{action.label}</span>
                </Button>
              ))}
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 border-t border-gray-200">
              {/* Micro-memo */}
              <Button
                variant="outline"
                size="sm"
                onClick={onMicromemo}
                className="flex items-center gap-2 bg-indigo-500 hover:bg-indigo-600 text-white border-transparent"
                disabled={disabled}
              >
                <MicrophoneIcon className="w-4 h-4" />
                <span>Micro-memo (10s)</span>
              </Button>
              
              {/* Capturar pizarra */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => onCaptureImage('pizarra')}
                className="flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white border-transparent"
                disabled={disabled}
              >
                <CameraIcon className="w-4 h-4" />
                <span>Capturar pizarra</span>
              </Button>
              
              {/* Capturar diapositiva */}
              <Button
                variant="outline"
                size="sm"
                onClick={() => onCaptureImage('diapositiva')}
                className="flex items-center gap-2 bg-cyan-500 hover:bg-cyan-600 text-white border-transparent"
                disabled={disabled}
              >
                <CameraIcon className="w-4 h-4" />
                <span>Capturar slide</span>
              </Button>
            </div>
            
            {/* Ayuda rápida */}
            <div className="mt-3 pt-3 border-t border-gray-200">
              <p className="text-xs text-gray-500 text-center">
                💡 Tip: Usa las acciones rápidas para marcar momentos importantes durante la grabación
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
