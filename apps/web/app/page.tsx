/**
 * Página principal - Lista de clases grabadas
 */

'use client';

import { useEffect, useState } from 'react';
import { useAppStore, type ClassSession } from '@/lib/stores/app';
import { Button } from '@/components/ui/Button';
import { MedicalCard } from '@/components/ui/MedicalCard';
import { MedicalBadge, EstadoBadge, EspecialidadBadge, ConfianzaBadge } from '@/components/ui/MedicalBadge';
import { SyncIndicator, useSyncStatus } from '@/components/ui/SyncIndicator';
import { formatDuration, formatRelativeDate, getInitials, getColorFromText } from '@/lib/utils';
import Link from 'next/link';

const SAMPLE_SESSIONS: ClassSession[] = [
  {
    id: '1',
    asignatura: 'Medicina Interna',
    tema: 'Cardiología - Arritmias cardíacas',
    profesor_text: 'Dr. Francesco Rossi',
    fecha: '2024-01-15',
    duracion_sec: 3600,
    estado_pipeline: 'done',
    confianza_asr: 0.92,
    notion_page_id: 'abc123',
    created_at: '2024-01-15T09:00:00Z',
  },
  {
    id: '2',
    asignatura: 'Anatomía',
    tema: 'Sistema Nervioso Central',
    profesor_text: 'Dra. Maria Bianchi',
    fecha: '2024-01-14',
    duracion_sec: 2700,
    estado_pipeline: 'nlp',
    confianza_asr: 0.89,
    notion_page_id: null,
    created_at: '2024-01-14T14:30:00Z',
  },
  {
    id: '3',
    asignatura: 'Farmacología',
    tema: 'Antibióticos y resistencia bacteriana',
    profesor_text: 'Prof. Giuseppe Verdi',
    fecha: '2024-01-13',
    duracion_sec: 4200,
    estado_pipeline: 'asr',
    confianza_asr: 0.85,
    notion_page_id: null,
    created_at: '2024-01-13T11:15:00Z',
  },
];

const getStatusColor = (status: string) => {
  switch (status) {
    case 'done': return 'success';
    case 'error': return 'error';
    case 'asr': case 'nlp': case 'notion': return 'warning';
    default: return 'info';
  }
};

const getStatusText = (status: string) => {
  switch (status) {
    case 'done': return 'Completado';
    case 'error': return 'Error';
    case 'asr': return 'Transcribiendo';
    case 'nlp': return 'Procesando';
    case 'notion': return 'Sincronizando';
    case 'uploaded': return 'Subido';
    default: return 'Procesando';
  }
};

export default function HomePage() {
  const { classSessions, isLoading, loadClassSessions, favoriteSubjects } = useAppStore();
  const [filter, setFilter] = useState<string>('all');
  const [sessions, setSessions] = useState<ClassSession[]>(SAMPLE_SESSIONS);
  const syncStatus = useSyncStatus();

  useEffect(() => {
    // loadClassSessions();
    setSessions(SAMPLE_SESSIONS); // Usar datos de ejemplo por ahora
  }, []);

  const filteredSessions = sessions.filter(session => {
    if (filter === 'all') return true;
    if (filter === 'favorites') return favoriteSubjects.includes(session.asignatura);
    if (filter === 'completed') return session.estado_pipeline === 'done';
    if (filter === 'processing') return ['asr', 'nlp', 'notion'].includes(session.estado_pipeline);
    return session.asignatura === filter;
  });

  const uniqueSubjects = [...new Set(sessions.map(s => s.asignatura))];

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-primary-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-600">Cargando clases...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="mobile-container">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Clases</h1>
              <p className="text-gray-600">{sessions.length} grabaciones</p>
            </div>
            
            {/* Indicador de sincronización */}
            <SyncIndicator
              status={syncStatus.status}
              pendingCount={syncStatus.pendingCount}
              lastSync={syncStatus.lastSync}
              position="inline"
              showDetails={false}
            />
          </div>
        </div>
      </header>

      <div className="mobile-container space-y-6">
        {/* Botón de nueva grabación */}
        <Link href="/grabar">
          <Button 
            size="lg" 
            fullWidth 
            className="h-16 text-lg font-semibold"
            leftIcon={
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v1a7 7 0 0 1-14 0v-1a1 1 0 0 1 2 0v1a5 5 0 0 0 10 0v-1a1 1 0 0 1 2 0Z" />
                <path d="M12 19a1 1 0 0 1 0 2h-2a1 1 0 0 1 0-2h2Z" />
              </svg>
            }
          >
            Nueva Grabación
          </Button>
        </Link>

        {/* Filtros */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <h3 className="font-medium text-gray-900 mb-3">Filtrar por:</h3>
          <div className="flex flex-wrap gap-2">
            <Button
              variant={filter === 'all' ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setFilter('all')}
            >
              Todas ({sessions.length})
            </Button>
            <Button
              variant={filter === 'completed' ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setFilter('completed')}
            >
              Completadas ({sessions.filter(s => s.estado_pipeline === 'done').length})
            </Button>
            <Button
              variant={filter === 'processing' ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setFilter('processing')}
            >
              Procesando ({sessions.filter(s => ['asr', 'nlp', 'notion'].includes(s.estado_pipeline)).length})
            </Button>
          </div>
          
          {uniqueSubjects.length > 0 && (
            <div className="mt-3 space-y-2">
              <p className="text-sm text-gray-600">Por asignatura:</p>
              <div className="flex flex-wrap gap-2">
                {uniqueSubjects.map(subject => (
                  <Button
                    key={subject}
                    variant={filter === subject ? 'primary' : 'ghost'}
                    size="sm"
                    onClick={() => setFilter(filter === subject ? 'all' : subject)}
                  >
                    {subject} ({sessions.filter(s => s.asignatura === subject).length})
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Lista de clases */}
        <div className="space-y-4">
          {filteredSessions.length === 0 ? (
            <div className="text-center py-12">
              <svg className="w-16 h-16 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No hay clases</h3>
              <p className="text-gray-600 mb-4">
                {filter === 'all' ? 'Aún no has grabado ninguna clase.' : 'No se encontraron clases con este filtro.'}
              </p>
              {filter === 'all' && (
                <Link href="/grabar">
                  <Button>Grabar primera clase</Button>
                </Link>
              )}
            </div>
          ) : (
            filteredSessions.map((session) => (
              <MedicalCard
                key={session.id}
                title={session.tema}
                asignatura={session.asignatura}
                profesor={session.profesor_text}
                fecha={formatRelativeDate(session.created_at)}
                duracion={session.duracion_sec ? formatDuration(session.duracion_sec) : undefined}
                estado={session.estado_pipeline as any}
                confianza_asr={session.confianza_asr}
                confianza_llm={session.confianza_llm}
                tags={['Medicina', 'Clase']}
                onClick={() => {
                  console.log('Clicked session:', session.id);
                }}
                onPlay={session.estado_pipeline === 'completed' ? () => {
                  console.log('Play session:', session.id);
                } : undefined}
                onMore={() => {
                  console.log('More options:', session.id);
                }}
              >
                {/* Acciones adicionales */}
                {session.notion_page_id && (
                  <div className="flex items-center gap-2 text-sm text-gray-600">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l8.893-.548c.16 0 .027-.133-.014-.146L14.86 3.094c-.254-.146-.547-.306-1.026-.306l-8.893.533c-.427.027-.573.306-.48.88zm.24 2.507v13.336c0 .746.373 1.026 1.013.986l9.893-.56c.64-.053.746-.426.746-.96V6.262c0-.533-.16-.8-.533-.773l-10.24.586c-.426.027-.88.213-.88.64zm8.853-.693c.08.4 0 .8-.4.853l-.64.133v9.386c-.56.293-1.073.426-1.466.426-.746 0-.933-.226-1.466-.906l-4.533-7.12v6.88c0 0-.293.906-1.293.906h-1.733s-.4-.226-.4-.906V7.995c0-.533.24-.853.746-.906l2.053-.133c.746 0 1.2.226 1.6.906l4.64 7.253V8.248c0-.533.213-.8.693-.826l1.733-.4z" />
                    </svg>
                    <span>Sincronizado con Notion</span>
                  </div>
                )}
              </MedicalCard>
            ))
          )}
        </div>
      </div>

      {/* Navegación inferior */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 px-4 py-2">
        <div className="flex justify-around">
          <Button variant="ghost" size="sm" className="flex-col space-y-1">
            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
              <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" />
            </svg>
            <span className="text-xs">Clases</span>
          </Button>
          
          <Link href="/grabar">
            <Button variant="ghost" size="sm" className="flex-col space-y-1">
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v1a7 7 0 0 1-14 0v-1a1 1 0 0 1 2 0v1a5 5 0 0 0 10 0v-1a1 1 0 0 1 2 0Z" />
              </svg>
              <span className="text-xs">Grabar</span>
            </Button>
          </Link>
          
          <Link href="/dashboard">
            <Button variant="ghost" size="sm" className="flex-col space-y-1">
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" />
              </svg>
              <span className="text-xs">Dashboard</span>
            </Button>
          </Link>
          
          <Link href="/ajustes">
            <Button variant="ghost" size="sm" className="flex-col space-y-1">
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 15.5A3.5 3.5 0 0 1 8.5 12A3.5 3.5 0 0 1 12 8.5a3.5 3.5 0 0 1 3.5 3.5 3.5 3.5 0 0 1-3.5 3.5m7.43-2.53c.04-.32.07-.64.07-.97 0-.33-.03-.66-.07-1l2.11-1.63c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.31-.61-.22l-2.49 1c-.52-.39-1.06-.73-1.69-.98l-.37-2.65A.506.506 0 0 0 14 2h-4c-.25 0-.46.18-.5.42l-.37 2.65c-.63.25-1.17.59-1.69.98l-2.49-1c-.22-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64L4.57 11c-.04.34-.07.67-.07 1 0 .33.03.65.07.97l-2.11 1.66c-.19.15-.25.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1.01c.52.4 1.06.74 1.69.99l.37 2.65c.04.24.25.42.5.42h4c.25 0 .46-.18.5-.42l.37-2.65c.63-.26 1.17-.59 1.69-.99l2.49 1.01c.22.08.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.66Z" />
              </svg>
              <span className="text-xs">Ajustes</span>
            </Button>
          </Link>
        </div>
      </nav>
    </div>
  );
}
