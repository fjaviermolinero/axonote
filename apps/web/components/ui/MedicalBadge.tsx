/**
 * MedicalBadge - Badges semánticos especializados para estados médicos
 */

'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export interface MedicalBadgeProps {
  className?: string;
  variant?: 'estado' | 'especialidad' | 'prioridad' | 'confianza' | 'tipo' | 'progreso';
  value?: string | number;
  size?: 'sm' | 'md' | 'lg';
  children?: React.ReactNode;
}

// Configuraciones para diferentes tipos de badges médicos
const variantConfig = {
  estado: {
    uploaded: { 
      label: 'Subido', 
      className: 'bg-blue-50 text-blue-700 border-blue-200',
      icon: '📁'
    },
    processing: { 
      label: 'Procesando', 
      className: 'bg-yellow-50 text-yellow-700 border-yellow-200',
      icon: '⚙️'
    },
    transcribing: { 
      label: 'Transcribiendo', 
      className: 'bg-purple-50 text-purple-700 border-purple-200',
      icon: '🎤'
    },
    analyzing: { 
      label: 'Analizando', 
      className: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      icon: '🧠'
    },
    completed: { 
      label: 'Completado', 
      className: 'bg-green-50 text-green-700 border-green-200',
      icon: '✅'
    },
    error: { 
      label: 'Error', 
      className: 'bg-red-50 text-red-700 border-red-200',
      icon: '❌'
    },
    reviewing: { 
      label: 'En revisión', 
      className: 'bg-orange-50 text-orange-700 border-orange-200',
      icon: '👨‍⚕️'
    }
  },
  
  especialidad: {
    cardiologia: { 
      label: 'Cardiología', 
      className: 'bg-red-50 text-red-700 border-red-200',
      icon: '❤️'
    },
    neurologia: { 
      label: 'Neurología', 
      className: 'bg-purple-50 text-purple-700 border-purple-200',
      icon: '🧠'
    },
    respiratorio: { 
      label: 'Respiratorio', 
      className: 'bg-blue-50 text-blue-700 border-blue-200',
      icon: '🫁'
    },
    digestivo: { 
      label: 'Digestivo', 
      className: 'bg-green-50 text-green-700 border-green-200',
      icon: '🫄'
    },
    endocrino: { 
      label: 'Endocrino', 
      className: 'bg-yellow-50 text-yellow-700 border-yellow-200',
      icon: '⚗️'
    },
    anatomia: { 
      label: 'Anatomía', 
      className: 'bg-gray-50 text-gray-700 border-gray-200',
      icon: '🦴'
    },
    farmacologia: { 
      label: 'Farmacología', 
      className: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      icon: '💊'
    },
    patologia: { 
      label: 'Patología', 
      className: 'bg-orange-50 text-orange-700 border-orange-200',
      icon: '🔬'
    }
  },
  
  prioridad: {
    alta: { 
      label: 'Alta', 
      className: 'bg-red-50 text-red-700 border-red-200',
      icon: '🔴'
    },
    media: { 
      label: 'Media', 
      className: 'bg-yellow-50 text-yellow-700 border-yellow-200',
      icon: '🟡'
    },
    baja: { 
      label: 'Baja', 
      className: 'bg-green-50 text-green-700 border-green-200',
      icon: '🟢'
    },
    urgente: { 
      label: 'Urgente', 
      className: 'bg-red-100 text-red-800 border-red-300 animate-pulse',
      icon: '🚨'
    }
  },
  
  tipo: {
    leccion: { 
      label: 'Lección', 
      className: 'bg-blue-50 text-blue-700 border-blue-200',
      icon: '📚'
    },
    seminario: { 
      label: 'Seminario', 
      className: 'bg-purple-50 text-purple-700 border-purple-200',
      icon: '👥'
    },
    practica: { 
      label: 'Práctica', 
      className: 'bg-green-50 text-green-700 border-green-200',
      icon: '🔬'
    },
    examen: { 
      label: 'Examen', 
      className: 'bg-red-50 text-red-700 border-red-200',
      icon: '📝'
    },
    conferencia: { 
      label: 'Conferencia', 
      className: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      icon: '🎤'
    }
  }
};

const sizeConfig = {
  sm: 'text-xs px-2 py-0.5',
  md: 'text-sm px-2.5 py-1',
  lg: 'text-base px-3 py-1.5'
};

export function MedicalBadge({
  className,
  variant = 'estado',
  value,
  size = 'sm',
  children,
  ...props
}: MedicalBadgeProps) {
  
  // Determinar la configuración basada en variant y value
  const getConfig = () => {
    if (variant === 'confianza' && typeof value === 'number') {
      const percentage = Math.round(value * 100);
      if (percentage >= 90) {
        return { 
          label: `${percentage}%`, 
          className: 'bg-green-50 text-green-700 border-green-200',
          icon: '🎯'
        };
      } else if (percentage >= 70) {
        return { 
          label: `${percentage}%`, 
          className: 'bg-yellow-50 text-yellow-700 border-yellow-200',
          icon: '⚠️'
        };
      } else {
        return { 
          label: `${percentage}%`, 
          className: 'bg-red-50 text-red-700 border-red-200',
          icon: '❌'
        };
      }
    }
    
    if (variant === 'progreso' && typeof value === 'number') {
      const percentage = Math.round(value * 100);
      return { 
        label: `${percentage}%`, 
        className: 'bg-blue-50 text-blue-700 border-blue-200',
        icon: '📊'
      };
    }
    
    if (value && variant in variantConfig) {
      const config = variantConfig[variant as keyof typeof variantConfig];
      return config[value as keyof typeof config] || {
        label: String(value),
        className: 'bg-gray-50 text-gray-700 border-gray-200',
        icon: '🏷️'
      };
    }
    
    return {
      label: children || String(value || ''),
      className: 'bg-gray-50 text-gray-700 border-gray-200',
      icon: ''
    };
  };
  
  const config = getConfig();
  const showIcon = size !== 'sm';
  
  return (
    <span
      className={cn(
        'medical-badge',
        'inline-flex items-center gap-1 font-medium rounded-full border',
        'transition-all duration-200 hover:shadow-sm',
        sizeConfig[size],
        config.className,
        className
      )}
      {...props}
    >
      {showIcon && config.icon && (
        <span className="leading-none">{config.icon}</span>
      )}
      <span className="leading-none">
        {children || config.label}
      </span>
    </span>
  );
}

// Componentes especializados para casos comunes
export function EstadoBadge({ estado, ...props }: Omit<MedicalBadgeProps, 'variant' | 'value'> & { estado: string }) {
  return <MedicalBadge variant="estado" value={estado} {...props} />;
}

export function EspecialidadBadge({ especialidad, ...props }: Omit<MedicalBadgeProps, 'variant' | 'value'> & { especialidad: string }) {
  return <MedicalBadge variant="especialidad" value={especialidad} {...props} />;
}

export function ConfianzaBadge({ confianza, ...props }: Omit<MedicalBadgeProps, 'variant' | 'value'> & { confianza: number }) {
  return <MedicalBadge variant="confianza" value={confianza} {...props} />;
}

export function PrioridadBadge({ prioridad, ...props }: Omit<MedicalBadgeProps, 'variant' | 'value'> & { prioridad: string }) {
  return <MedicalBadge variant="prioridad" value={prioridad} {...props} />;
}

export function TipoBadge({ tipo, ...props }: Omit<MedicalBadgeProps, 'variant' | 'value'> & { tipo: string }) {
  return <MedicalBadge variant="tipo" value={tipo} {...props} />;
}

export function ProgresoBadge({ progreso, ...props }: Omit<MedicalBadgeProps, 'variant' | 'value'> & { progreso: number }) {
  return <MedicalBadge variant="progreso" value={progreso} {...props} />;
}
