'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, Activity, TrendingUp, AlertTriangle, CheckCircle } from 'lucide-react';

// Tipos TypeScript
interface ResumenDashboard {
  timestamp: string;
  sesiones_activas: number;
  metricas_24h: number;
  calidad_promedio_24h: number;
  estado_sistema: string;
  metricas_sistema: {
    [key: string]: {
      valor: number;
      unidad: string;
      estado: string;
      timestamp: string;
    };
  };
  alertas_activas: any[];
}

interface MetricaRendimiento {
  periodo_horas: number;
  total_operaciones: number;
  duracion_promedio_ms: number;
  calidad_promedio: number;
  tasa_exito_general: number;
  estadisticas_por_tipo: {
    [key: string]: {
      cantidad: number;
      duracion_promedio_ms: number;
      tasa_exito: number;
    };
  };
}

interface SesionMetrica {
  session_id: string;
  nombre: string;
  tipo: string;
  estado: string;
  duracion: number;
  cantidad_metricas: number;
  alertas_criticas: number;
  alertas_warning: number;
  tiempo_inicio: string;
}

// Hook personalizado para datos del dashboard
function useDashboardData() {
  const [resumen, setResumen] = useState<ResumenDashboard | null>(null);
  const [rendimiento, setRendimiento] = useState<MetricaRendimiento | null>(null);
  const [sesiones, setSesiones] = useState<SesionMetrica[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setError(null);
      
      // Fetch resumen
      const resumenResponse = await fetch('/api/v1/dashboard/resumen');
      if (!resumenResponse.ok) throw new Error('Error obteniendo resumen');
      const resumenData = await resumenResponse.json();
      setResumen(resumenData);

      // Fetch rendimiento
      const rendimientoResponse = await fetch('/api/v1/dashboard/rendimiento?horas=24');
      if (!rendimientoResponse.ok) throw new Error('Error obteniendo rendimiento');
      const rendimientoData = await rendimientoResponse.json();
      setRendimiento(rendimientoData);

      // Fetch sesiones
      const sesionesResponse = await fetch('/api/v1/dashboard/sesiones?limite=10');
      if (!sesionesResponse.ok) throw new Error('Error obteniendo sesiones');
      const sesionesData = await sesionesResponse.json();
      setSesiones(sesionesData.sesiones || []);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido');
      console.error('Error fetching dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    
    // Auto-refresh cada 30 segundos
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  return { resumen, rendimiento, sesiones, loading, error, refetch: fetchData };
}

// Componente principal del Dashboard
export default function DashboardPage() {
  const { resumen, rendimiento, sesiones, loading, error, refetch } = useDashboardData();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">Cargando dashboard...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto p-6">
        <Alert className="border-red-200">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Error cargando el dashboard: {error}
            <button 
              onClick={refetch}
              className="ml-2 text-blue-600 underline"
            >
              Reintentar
            </button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard Axonote</h1>
          <p className="text-muted-foreground">
            Monitoreo en tiempo real del sistema de transcripción médica
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <EstadoSistema estado={resumen?.estado_sistema || 'desconocido'} />
          <Badge variant="outline">
            Actualizado: {resumen ? new Date(resumen.timestamp).toLocaleTimeString() : '--'}
          </Badge>
        </div>
      </div>

      {/* Resumen rápido */}
      <ResumenRapido resumen={resumen} />

      {/* Tabs principales */}
      <Tabs defaultValue="rendimiento" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="rendimiento">Rendimiento</TabsTrigger>
          <TabsTrigger value="sistema">Sistema</TabsTrigger>
          <TabsTrigger value="sesiones">Sesiones</TabsTrigger>
          <TabsTrigger value="alertas">Alertas</TabsTrigger>
        </TabsList>

        <TabsContent value="rendimiento" className="space-y-4">
          <RendimientoTab rendimiento={rendimiento} />
        </TabsContent>

        <TabsContent value="sistema" className="space-y-4">
          <SistemaTab resumen={resumen} />
        </TabsContent>

        <TabsContent value="sesiones" className="space-y-4">
          <SesionesTab sesiones={sesiones} />
        </TabsContent>

        <TabsContent value="alertas" className="space-y-4">
          <AlertasTab resumen={resumen} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// Componente de estado del sistema
function EstadoSistema({ estado }: { estado: string }) {
  const getEstadoConfig = (estado: string) => {
    switch (estado) {
      case 'saludable':
        return { color: 'text-green-600', bg: 'bg-green-100', icon: CheckCircle, text: 'Saludable' };
      case 'warning':
        return { color: 'text-yellow-600', bg: 'bg-yellow-100', icon: AlertTriangle, text: 'Advertencia' };
      case 'critico':
        return { color: 'text-red-600', bg: 'bg-red-100', icon: AlertTriangle, text: 'Crítico' };
      default:
        return { color: 'text-gray-600', bg: 'bg-gray-100', icon: Activity, text: 'Desconocido' };
    }
  };

  const config = getEstadoConfig(estado);
  const Icon = config.icon;

  return (
    <div className={`flex items-center space-x-2 px-3 py-2 rounded-lg ${config.bg}`}>
      <Icon className={`h-4 w-4 ${config.color}`} />
      <span className={`text-sm font-medium ${config.color}`}>
        {config.text}
      </span>
    </div>
  );
}

// Componente de resumen rápido
function ResumenRapido({ resumen }: { resumen: ResumenDashboard | null }) {
  if (!resumen) return null;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Sesiones Activas</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{resumen.sesiones_activas}</div>
          <p className="text-xs text-muted-foreground">
            Procesamiento en tiempo real
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Métricas 24h</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{resumen.metricas_24h}</div>
          <p className="text-xs text-muted-foreground">
            Operaciones completadas
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Calidad Promedio</CardTitle>
          <CheckCircle className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {(resumen.calidad_promedio_24h * 100).toFixed(1)}%
          </div>
          <p className="text-xs text-muted-foreground">
            Últimas 24 horas
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">CPU/GPU</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {resumen.metricas_sistema.cpu_usage?.valor?.toFixed(1) || '--'}%
          </div>
          <p className="text-xs text-muted-foreground">
            GPU: {resumen.metricas_sistema.gpu_usage?.valor?.toFixed(1) || '--'}%
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// Tab de rendimiento
function RendimientoTab({ rendimiento }: { rendimiento: MetricaRendimiento | null }) {
  if (!rendimiento) {
    return <div>No hay datos de rendimiento disponibles</div>;
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle>Operaciones Totales</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-3xl font-bold">{rendimiento.total_operaciones}</div>
          <p className="text-sm text-muted-foreground">
            Últimas {rendimiento.periodo_horas} horas
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tiempo Promedio</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-3xl font-bold">
            {(rendimiento.duracion_promedio_ms / 1000).toFixed(1)}s
          </div>
          <p className="text-sm text-muted-foreground">
            Por operación
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tasa de Éxito</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-3xl font-bold">
            {(rendimiento.tasa_exito_general * 100).toFixed(1)}%
          </div>
          <p className="text-sm text-muted-foreground">
            Operaciones exitosas
          </p>
        </CardContent>
      </Card>

      {/* Estadísticas por tipo */}
      <Card className="md:col-span-2 lg:col-span-3">
        <CardHeader>
          <CardTitle>Rendimiento por Tipo de Procesamiento</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Object.entries(rendimiento.estadisticas_por_tipo).map(([tipo, stats]) => (
              <div key={tipo} className="flex items-center justify-between p-3 border rounded">
                <div>
                  <div className="font-medium capitalize">{tipo}</div>
                  <div className="text-sm text-muted-foreground">
                    {stats.cantidad} operaciones
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-medium">
                    {(stats.duracion_promedio_ms / 1000).toFixed(1)}s
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {(stats.tasa_exito * 100).toFixed(1)}% éxito
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Tab de sistema
function SistemaTab({ resumen }: { resumen: ResumenDashboard | null }) {
  if (!resumen?.metricas_sistema) {
    return <div>No hay datos de sistema disponibles</div>;
  }

  const metricas = resumen.metricas_sistema;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {Object.entries(metricas).map(([nombre, metrica]) => (
        <Card key={nombre}>
          <CardHeader>
            <CardTitle className="capitalize">
              {nombre.replace('_', ' ')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {metrica.valor.toFixed(1)}{metrica.unidad}
            </div>
            <div className="flex items-center space-x-2 mt-2">
              <EstadoSistema estado={metrica.estado} />
              <span className="text-xs text-muted-foreground">
                {new Date(metrica.timestamp).toLocaleTimeString()}
              </span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// Tab de sesiones
function SesionesTab({ sesiones }: { sesiones: SesionMetrica[] }) {
  if (!sesiones.length) {
    return <div>No hay sesiones recientes</div>;
  }

  return (
    <div className="space-y-4">
      {sesiones.map((sesion) => (
        <Card key={sesion.session_id}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">{sesion.nombre}</CardTitle>
              <div className="flex items-center space-x-2">
                <Badge variant={sesion.estado === 'completada' ? 'default' : 'secondary'}>
                  {sesion.estado}
                </Badge>
                <Badge variant="outline">{sesion.tipo}</Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <div className="font-medium">Duración</div>
                <div>{Math.round(sesion.duracion / 60)} min</div>
              </div>
              <div>
                <div className="font-medium">Métricas</div>
                <div>{sesion.cantidad_metricas}</div>
              </div>
              <div>
                <div className="font-medium">Alertas Críticas</div>
                <div className="text-red-600">{sesion.alertas_criticas}</div>
              </div>
              <div>
                <div className="font-medium">Warnings</div>
                <div className="text-yellow-600">{sesion.alertas_warning}</div>
              </div>
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              Iniciado: {new Date(sesion.tiempo_inicio).toLocaleString()}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// Tab de alertas
function AlertasTab({ resumen }: { resumen: ResumenDashboard | null }) {
  if (!resumen?.alertas_activas?.length) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center h-32">
          <div className="text-center">
            <CheckCircle className="h-8 w-8 text-green-600 mx-auto mb-2" />
            <p className="text-muted-foreground">No hay alertas activas</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {resumen.alertas_activas.map((alerta, index) => (
        <Alert key={index} className="border-red-200">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            <div className="font-medium">{alerta.tipo}</div>
            <div>{alerta.mensaje}</div>
            {alerta.timestamp && (
              <div className="text-xs text-muted-foreground mt-1">
                {new Date(alerta.timestamp).toLocaleString()}
              </div>
            )}
          </AlertDescription>
        </Alert>
      ))}
    </div>
  );
}
