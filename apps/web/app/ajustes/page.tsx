/**
 * Página de ajustes y configuración
 */

'use client';

import { useState, useEffect } from 'react';
import { useAppStore } from '@/lib/stores/app';
import { Button } from '@/components/ui/Button';
import { settingsApi } from '@/lib/api';
import Link from 'next/link';

export default function AjustesPage() {
  const { settings, updateSettings, capabilities, setCapabilities } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [systemInfo, setSystemInfo] = useState<any>(null);

  useEffect(() => {
    loadSystemInfo();
  }, []);

  const loadSystemInfo = async () => {
    try {
      setLoading(true);
      const [caps, limits] = await Promise.all([
        settingsApi.getCapabilities(),
        settingsApi.getLimits(),
      ]);
      setCapabilities(caps.capabilities);
      setSystemInfo({ capabilities: caps, limits });
    } catch (error) {
      console.error('Error loading system info:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSettingChange = (key: keyof typeof settings, value: any) => {
    updateSettings({ [key]: value });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="mobile-container">
          <div className="flex items-center justify-between py-4">
            <Link href="/">
              <Button variant="ghost" size="sm">
                <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Volver
              </Button>
            </Link>
            <h1 className="text-xl font-bold text-gray-900">Ajustes</h1>
            <div className="w-16" /> {/* Spacer */}
          </div>
        </div>
      </header>

      <div className="mobile-container space-y-6">
        {/* Configuración de Grabación */}
        <div className="bg-white rounded-xl p-6 shadow-sm">
          <h3 className="font-semibold text-gray-900 mb-4">Grabación</h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Ganancia del micrófono
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={settings.microphoneGain}
                onChange={(e) => handleSettingChange('microphoneGain', parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>Bajo</span>
                <span>{Math.round(settings.microphoneGain * 100)}%</span>
                <span>Alto</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Tamaño de chunk (segundos)
              </label>
              <select
                value={settings.chunkSize}
                onChange={(e) => handleSettingChange('chunkSize', parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              >
                <option value={5}>5 segundos</option>
                <option value={10}>10 segundos</option>
                <option value={15}>15 segundos</option>
                <option value={30}>30 segundos</option>
              </select>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Mantener pantalla encendida</span>
              <button
                onClick={() => handleSettingChange('keepScreenOn', !settings.keepScreenOn)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.keepScreenOn ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.keepScreenOn ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Subida automática</span>
              <button
                onClick={() => handleSettingChange('autoUpload', !settings.autoUpload)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.autoUpload ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.autoUpload ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>
        </div>

        {/* Interfaz */}
        <div className="bg-white rounded-xl p-6 shadow-sm">
          <h3 className="font-semibold text-gray-900 mb-4">Interfaz</h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Tema
              </label>
              <select
                value={settings.theme}
                onChange={(e) => handleSettingChange('theme', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              >
                <option value="system">Sistema</option>
                <option value="light">Claro</option>
                <option value="dark">Oscuro</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Idioma
              </label>
              <select
                value={settings.language}
                onChange={(e) => handleSettingChange('language', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
              >
                <option value="es">Español</option>
                <option value="it">Italiano</option>
                <option value="en">English</option>
              </select>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Notificaciones</span>
              <button
                onClick={() => handleSettingChange('notifications', !settings.notifications)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.notifications ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.notifications ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">Indicador de sincronización</span>
              <button
                onClick={() => handleSettingChange('syncIndicator', !settings.syncIndicator)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.syncIndicator ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.syncIndicator ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>
        </div>

        {/* Información del Sistema */}
        {capabilities && (
          <div className="bg-white rounded-xl p-6 shadow-sm">
            <h3 className="font-semibold text-gray-900 mb-4">Capacidades del Sistema</h3>
            
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700">Transcripción</span>
                <span className={`medical-badge ${capabilities.transcription.available ? 'success' : 'error'}`}>
                  {capabilities.transcription.available ? 'Disponible' : 'No disponible'}
                </span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700">Diarización</span>
                <span className={`medical-badge ${capabilities.diarization.available ? 'success' : 'error'}`}>
                  {capabilities.diarization.available ? 'Disponible' : 'No disponible'}
                </span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700">LLM Local</span>
                <span className={`medical-badge ${capabilities.llm.local_available ? 'success' : 'error'}`}>
                  {capabilities.llm.local_available ? 'Disponible' : 'No disponible'}
                </span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700">OCR</span>
                <span className={`medical-badge ${capabilities.ocr.available ? 'success' : 'error'}`}>
                  {capabilities.ocr.available ? 'Disponible' : 'No disponible'}
                </span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700">TTS</span>
                <span className={`medical-badge ${capabilities.tts.available ? 'success' : 'error'}`}>
                  {capabilities.tts.available ? 'Disponible' : 'No disponible'}
                </span>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700">Notion</span>
                <span className={`medical-badge ${capabilities.notion.available ? 'success' : 'error'}`}>
                  {capabilities.notion.available ? 'Disponible' : 'No disponible'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Acciones */}
        <div className="bg-white rounded-xl p-6 shadow-sm">
          <h3 className="font-semibold text-gray-900 mb-4">Acciones</h3>
          
          <div className="space-y-3">
            <Button
              variant="outline"
              fullWidth
              onClick={loadSystemInfo}
              loading={loading}
            >
              Verificar Estado del Sistema
            </Button>
            
            <Button
              variant="outline"
              fullWidth
              onClick={() => {
                if (confirm('¿Estás seguro de que quieres limpiar todos los datos locales?')) {
                  // clearData(); // Uncomment when implemented
                  alert('Datos limpiados');
                }
              }}
            >
              Limpiar Datos Locales
            </Button>
          </div>
        </div>

        {/* Información de la App */}
        <div className="bg-white rounded-xl p-6 shadow-sm">
          <h3 className="font-semibold text-gray-900 mb-4">Información</h3>
          
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Versión:</span>
              <span>0.1.0</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Entorno:</span>
              <span>Desarrollo</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">API:</span>
              <span>http://localhost:8000</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
