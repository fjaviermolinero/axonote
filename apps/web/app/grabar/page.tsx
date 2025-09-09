/**
 * Página de grabación - Interfaz principal para grabar clases
 */

'use client';

import { useState, useEffect } from 'react';
import { useRecordingStore } from '@/lib/stores/recording';
import { Button } from '@/components/ui/Button';
import { RecordButton } from '@/components/ui/RecordButton';
import { formatDuration } from '@/lib/utils';
import Link from 'next/link';

export default function GrabarPage() {
  const {
    currentSession,
    isRecording,
    isPaused,
    currentTime,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    addKeyMoment,
    addMicromemo,
    captureImage,
    clearSession,
  } = useRecordingStore();

  const [sessionData, setSessionData] = useState({
    asignatura: '',
    tema: '',
    profesor_text: '',
  });

  const [showForm, setShowForm] = useState(!currentSession);

  const handleStartRecording = async () => {
    if (!currentSession) {
      await startRecording(sessionData);
      setShowForm(false);
    }
  };

  const handleKeyMoment = (type: 'idea_clave' | 'no_entendi' | 'pregunta' | 'importante') => {
    const note = prompt(`Añadir nota para ${type.replace('_', ' ')}:`);
    if (note) {
      addKeyMoment(type, note);
    }
  };

  const handleMicromemo = async () => {
    const note = prompt('Descripción del micro-memo:');
    if (note) {
      await addMicromemo(note);
    }
  };

  const handleCaptureImage = async (type: 'pizarra' | 'diapositiva') => {
    const note = prompt(`Descripción de la ${type}:`);
    if (note) {
      await captureImage(type, note);
    }
  };

  if (showForm) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="mobile-container">
          <div className="bg-white rounded-2xl shadow-xl p-8">
            <h1 className="text-2xl font-bold text-gray-900 mb-6 text-center">
              Nueva Grabación
            </h1>
            
            <form className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Asignatura *
                </label>
                <input
                  type="text"
                  value={sessionData.asignatura}
                  onChange={(e) => setSessionData(prev => ({ ...prev, asignatura: e.target.value }))}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  placeholder="ej. Medicina Interna"
                  required
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Tema *
                </label>
                <input
                  type="text"
                  value={sessionData.tema}
                  onChange={(e) => setSessionData(prev => ({ ...prev, tema: e.target.value }))}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  placeholder="ej. Cardiología - Arritmias"
                  required
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Profesor *
                </label>
                <input
                  type="text"
                  value={sessionData.profesor_text}
                  onChange={(e) => setSessionData(prev => ({ ...prev, profesor_text: e.target.value }))}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  placeholder="ej. Dr. Francesco Rossi"
                  required
                />
              </div>
              
              <div className="flex space-x-3 pt-4">
                <Link href="/" className="flex-1">
                  <Button variant="outline" fullWidth>
                    Cancelar
                  </Button>
                </Link>
                <Button
                  fullWidth
                  onClick={handleStartRecording}
                  disabled={!sessionData.asignatura || !sessionData.tema || !sessionData.profesor_text}
                  className="flex-1"
                >
                  Comenzar Grabación
                </Button>
              </div>
            </form>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header con información de la sesión */}
      <header className="bg-white shadow-sm border-b">
        <div className="mobile-container">
          <div className="text-center py-4">
            <h1 className="text-xl font-bold text-gray-900">
              {currentSession?.tema}
            </h1>
            <p className="text-primary-600 font-medium">
              {currentSession?.asignatura}
            </p>
            <p className="text-gray-600 text-sm">
              {currentSession?.profesor_text}
            </p>
          </div>
        </div>
      </header>

      <div className="mobile-container space-y-6 pb-32">
        {/* Tiempo de grabación */}
        <div className="bg-white rounded-xl p-6 text-center shadow-sm">
          <div className="text-4xl font-mono font-bold text-gray-900 mb-2">
            {formatDuration(currentTime)}
          </div>
          <div className="flex justify-center space-x-4 text-sm text-gray-600">
            <span>
              Estado: {!isRecording ? 'Detenido' : isPaused ? 'Pausado' : 'Grabando'}
            </span>
          </div>
        </div>

        {/* Visualización de onda (placeholder) */}
        <div className="bg-white rounded-xl p-4 shadow-sm">
          <div className="waveform-container">
            <div className="flex items-center justify-center h-full text-gray-500">
              {isRecording && !isPaused ? (
                <div className="flex space-x-1">
                  {[...Array(20)].map((_, i) => (
                    <div
                      key={i}
                      className="w-1 bg-primary-500 animate-pulse"
                      style={{
                        height: `${Math.random() * 40 + 10}px`,
                        animationDelay: `${i * 0.1}s`,
                      }}
                    />
                  ))}
                </div>
              ) : (
                <span>Forma de onda del audio</span>
              )}
            </div>
          </div>
        </div>

        {/* Botones de anotación */}
        <div className="bg-white rounded-xl p-6 shadow-sm">
          <h3 className="font-semibold text-gray-900 mb-4">Anotaciones Rápidas</h3>
          <div className="grid grid-cols-2 gap-3">
            <Button
              variant="success"
              size="md"
              onClick={() => handleKeyMoment('idea_clave')}
              disabled={!isRecording}
              className="h-16 flex-col space-y-1"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm">Idea Clave</span>
            </Button>
            
            <Button
              variant="warning"
              size="md"
              onClick={() => handleKeyMoment('no_entendi')}
              disabled={!isRecording}
              className="h-16 flex-col space-y-1"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm">No Entendí</span>
            </Button>
            
            <Button
              variant="outline"
              size="md"
              onClick={handleMicromemo}
              disabled={!isRecording}
              className="h-16 flex-col space-y-1"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              </svg>
              <span className="text-sm">Micro-memo</span>
            </Button>
            
            <Button
              variant="outline"
              size="md"
              onClick={() => handleCaptureImage('pizarra')}
              disabled={!isRecording}
              className="h-16 flex-col space-y-1"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586l-2.707-2.707a1 1 0 00-1.414 0L13 7.757 9.464 4.222a1 1 0 00-1.414 0L4 8.172V4z" />
                <path d="M4 9.586l3.879-3.879a1 1 0 011.414 0L13 9.414l3.293-3.293a1 1 0 011.414 0L21 9.586V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.586z" />
              </svg>
              <span className="text-sm">Capturar</span>
            </Button>
          </div>
        </div>

        {/* Información de la sesión */}
        {currentSession && (
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <h4 className="font-medium text-gray-900 mb-3">Sesión Actual</h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Inicio:</span>
                <span>{currentSession.startTime ? new Date(currentSession.startTime).toLocaleTimeString() : '--'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Estado:</span>
                <span className={`font-medium ${
                  currentSession.status === 'recording' ? 'text-green-600' :
                  currentSession.status === 'error' ? 'text-red-600' : 'text-gray-600'
                }`}>
                  {currentSession.status === 'recording' ? 'Grabando' : 
                   currentSession.status === 'completed' ? 'Completado' :
                   currentSession.status === 'error' ? 'Error' : 'Detenido'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Controles de grabación fijos */}
      <div className="recording-controls">
        <RecordButton
          isRecording={isRecording}
          isPaused={isPaused}
          onStartRecord={handleStartRecording}
          onPauseRecord={pauseRecording}
          onResumeRecord={resumeRecording}
          onStopRecord={stopRecording}
        />
      </div>
    </div>
  );
}
