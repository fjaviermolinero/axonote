/**
 * MedicalCard - Tarjeta médica profesional con elevación y diseño especializado
 */

'use client';

import React from 'react';
import { cn } from '@/lib/utils';
import { Badge } from './badge';
import { Button } from './Button';
import { 
  ClockIcon, 
  UserIcon, 
  DocumentTextIcon,
  ChartBarIcon,
  PlayIcon,
  EllipsisVerticalIcon
} from '@heroicons/react/24/outline';

interface MedicalCardProps {
  className?: string;
  title: string;
  subtitle?: string;
  asignatura: string;
  profesor: string;
  fecha: string;
  duracion?: string;
  estado?: 'uploaded' | 'processing' | 'transcribing' | 'analyzing' | 'completed' | 'error';
  confianza_asr?: number;
  confianza_llm?: number;
  tags?: string[];
  onClick?: () => void;
  onPlay?: () => void;
  onMore?: () => void;
  children?: React.ReactNode;
}

const estadoConfig = {
  uploaded: {
    label: 'Subido',
    color: 'bg-blue-100 text-blue-800',
    icon: '📁'
  },
  processing: {
    label: 'Procesando',
    color: 'bg-yellow-100 text-yellow-800',
    icon: '⚙️'
  },
  transcribing: {
    label: 'Transcribiendo',
    color: 'bg-purple-100 text-purple-800',
    icon: '🎤'
  },
  analyzing: {
    label: 'Analizando',
    color: 'bg-indigo-100 text-indigo-800',
    icon: '🧠'
  },
  completed: {
    label: 'Completado',
    color: 'bg-green-100 text-green-800',
    icon: '✅'
  },
  error: {
    label: 'Error',
    color: 'bg-red-100 text-red-800',
    icon: '❌'
  }
};

export function MedicalCard({
  className,
  title,
  subtitle,
  asignatura,
  profesor,
  fecha,
  duracion,
  estado = 'uploaded',
  confianza_asr,
  confianza_llm,
  tags = [],
  onClick,
  onPlay,
  onMore,
  children,
  ...props
}: MedicalCardProps) {
  const estadoInfo = estadoConfig[estado];

  return (
    <div
      className={cn(
        // Estilo médico profesional con elevación
        'medical-card',
        'group relative bg-white rounded-xl border border-gray-200',
        'shadow-sm hover:shadow-lg transition-all duration-300',
        'hover:border-primary-300 hover:-translate-y-1',
        'p-6 cursor-pointer overflow-hidden',
        className
      )}
      onClick={onClick}
      {...props}
    >
      {/* Banda superior con asignatura */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary-500 to-primary-600" />
      
      {/* Header con estado y acciones */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-lg bg-primary-50 flex items-center justify-center text-xl">
            {estadoInfo.icon}
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 text-lg leading-tight">
              {title}
            </h3>
            {subtitle && (
              <p className="text-sm text-gray-600 mt-0.5">{subtitle}</p>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className={cn('text-xs font-medium', estadoInfo.color)}>
            {estadoInfo.label}
          </Badge>
          
          {onMore && (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onMore();
              }}
              className="opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <EllipsisVerticalIcon className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Información médica */}
      <div className="space-y-3 mb-4">
        {/* Asignatura */}
        <div className="flex items-center text-sm text-gray-700">
          <DocumentTextIcon className="w-4 h-4 mr-2 text-primary-600" />
          <span className="font-medium text-primary-700">{asignatura}</span>
        </div>

        {/* Profesor */}
        <div className="flex items-center text-sm text-gray-600">
          <UserIcon className="w-4 h-4 mr-2" />
          <span>{profesor}</span>
        </div>

        {/* Fecha y duración */}
        <div className="flex items-center justify-between text-sm text-gray-600">
          <div className="flex items-center">
            <ClockIcon className="w-4 h-4 mr-2" />
            <span>{fecha}</span>
          </div>
          {duracion && (
            <span className="font-medium text-primary-600">{duracion}</span>
          )}
        </div>
      </div>

      {/* Métricas de confianza */}
      {(confianza_asr !== undefined || confianza_llm !== undefined) && (
        <div className="bg-gray-50 rounded-lg p-3 mb-4">
          <div className="flex items-center gap-4">
            <ChartBarIcon className="w-4 h-4 text-gray-500" />
            <div className="flex-1 space-y-2">
              {confianza_asr !== undefined && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-600">Transcripción</span>
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div 
                        className={cn(
                          'h-full rounded-full transition-all duration-500',
                          confianza_asr >= 0.8 ? 'bg-green-500' :
                          confianza_asr >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                        )}
                        style={{ width: `${confianza_asr * 100}%` }}
                      />
                    </div>
                    <span className="font-medium text-gray-700 min-w-[2.5rem]">
                      {Math.round(confianza_asr * 100)}%
                    </span>
                  </div>
                </div>
              )}
              
              {confianza_llm !== undefined && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-600">Análisis</span>
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div 
                        className={cn(
                          'h-full rounded-full transition-all duration-500',
                          confianza_llm >= 0.8 ? 'bg-green-500' :
                          confianza_llm >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                        )}
                        style={{ width: `${confianza_llm * 100}%` }}
                      />
                    </div>
                    <span className="font-medium text-gray-700 min-w-[2.5rem]">
                      {Math.round(confianza_llm * 100)}%
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tags médicos */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-4">
          {tags.slice(0, 3).map((tag, index) => (
            <Badge
              key={index}
              variant="outline"
              className="text-xs px-2 py-0.5 bg-primary-50 text-primary-700 border-primary-200"
            >
              {tag}
            </Badge>
          ))}
          {tags.length > 3 && (
            <Badge variant="outline" className="text-xs px-2 py-0.5 text-gray-500">
              +{tags.length - 3}
            </Badge>
          )}
        </div>
      )}

      {/* Contenido adicional */}
      {children && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          {children}
        </div>
      )}

      {/* Acción principal */}
      {onPlay && estado === 'completed' && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onPlay();
            }}
            className="w-full text-primary-700 border-primary-200 hover:bg-primary-50"
          >
            <PlayIcon className="w-4 h-4 mr-2" />
            Reproducir análisis
          </Button>
        </div>
      )}

      {/* Indicador de carga para estados en proceso */}
      {['processing', 'transcribing', 'analyzing'].includes(estado) && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gray-200 overflow-hidden">
          <div className="h-full bg-primary-500 animate-pulse" />
        </div>
      )}
    </div>
  );
}
