'use client'

import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { 
  Users, 
  Building2, 
  Activity, 
  AlertTriangle, 
  Clock, 
  TrendingUp,
  Server,
  Database,
  Cpu,
  HardDrive,
  Zap,
  RefreshCw
} from 'lucide-react'

interface DashboardOverview {
  resumen: {
    total_tenants: number
    tenants_activos: number
    total_usuarios: number
    usuarios_activos: number
    total_sesiones: number
    sesiones_ultima_semana: number
    jobs_pendientes: number
    jobs_procesando: number
    alertas_criticas: number
  }
  metricas_sistema: {
    cpu_usage: number
    memory_usage: number
    response_time_avg: number
    requests_total: number
  }
  distribucion_planes: Array<{
    plan: string
    count: number
  }>
  timestamp: string
}

interface Tenant {
  id: string
  nombre: string
  slug: string
  tipo_institucion: string
  pais: string
  ciudad: string
  plan: string
  activo: boolean
  fecha_creacion: string
  usuarios_count: number
  limite_usuarios: number
  limite_almacenamiento_gb: number
  email_contacto: string
  fecha_suspension?: string
  motivo_suspension?: string
}

interface Alerta {
  id: string
  nombre: string
  descripcion: string
  severidad: 'critica' | 'alta' | 'media' | 'baja' | 'info'
  categoria: string
  activa: boolean
  reconocida: boolean
  resuelta: boolean
  fecha_creacion: string
  fecha_reconocimiento?: string
  fecha_resolucion?: string
  valor_actual?: number
  valor_umbral?: number
  metrica_asociada?: string
  tenant_id?: string
  duracion_activa_segundos?: number
}

const AdminDashboard: React.FC = () => {
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [alertas, setAlertas] = useState<Alerta[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const fetchDashboardData = async () => {
    try {
      setRefreshing(true)
      
      // Fetch overview
      const overviewResponse = await fetch('/api/v1/admin/dashboard/overview', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      })
      
      if (!overviewResponse.ok) {
        throw new Error('Error obteniendo datos del dashboard')
      }
      
      const overviewData = await overviewResponse.json()
      setOverview(overviewData.data)

      // Fetch tenants
      const tenantsResponse = await fetch('/api/v1/admin/tenants?limite=20', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      })
      
      if (tenantsResponse.ok) {
        const tenantsData = await tenantsResponse.json()
        setTenants(tenantsData.data.tenants)
      }

      // Fetch alertas
      const alertasResponse = await fetch('/api/v1/admin/system/alerts?limite=20', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      })
      
      if (alertasResponse.ok) {
        const alertasData = await alertasResponse.json()
        setAlertas(alertasData.data.alertas)
      }

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchDashboardData()
    
    // Auto refresh cada 30 segundos
    const interval = setInterval(fetchDashboardData, 30000)
    return () => clearInterval(interval)
  }, [])

  const getSeverityColor = (severidad: string) => {
    switch (severidad) {
      case 'critica': return 'bg-red-500'
      case 'alta': return 'bg-orange-500'
      case 'media': return 'bg-yellow-500'
      case 'baja': return 'bg-blue-500'
      default: return 'bg-gray-500'
    }
  }

  const getPlanColor = (plan: string) => {
    switch (plan) {
      case 'basic': return 'bg-gray-100 text-gray-800'
      case 'pro': return 'bg-blue-100 text-blue-800'
      case 'enterprise': return 'bg-purple-100 text-purple-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}h ${minutes}m`
  }

  const acknowledgeAlert = async (alertaId: string) => {
    try {
      const response = await fetch(`/api/v1/admin/system/alerts/${alertaId}/acknowledge`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      })

      if (response.ok) {
        fetchDashboardData() // Refresh data
      }
    } catch (err) {
      console.error('Error reconociendo alerta:', err)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500"></div>
      </div>
    )
  }

  if (error) {
    return (
      <Alert className="mb-6">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Dashboard Administrativo</h1>
          <p className="text-gray-600">Gestión y monitoreo del sistema AxoNote</p>
        </div>
        <Button 
          onClick={fetchDashboardData}
          disabled={refreshing}
          variant="outline"
          size="sm"
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
          Actualizar
        </Button>
      </div>

      {/* Alertas críticas */}
      {alertas.filter(a => a.severidad === 'critica' && a.activa).length > 0 && (
        <Alert className="border-red-200 bg-red-50">
          <AlertTriangle className="h-4 w-4 text-red-600" />
          <AlertDescription className="text-red-800">
            Hay {alertas.filter(a => a.severidad === 'critica' && a.activa).length} alertas críticas que requieren atención inmediata.
          </AlertDescription>
        </Alert>
      )}

      {/* Cards de resumen */}
      {overview && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Tenants Activos</CardTitle>
              <Building2 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{overview.resumen.tenants_activos}</div>
              <p className="text-xs text-muted-foreground">
                de {overview.resumen.total_tenants} totales
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Usuarios Activos</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{overview.resumen.usuarios_activos}</div>
              <p className="text-xs text-muted-foreground">
                de {overview.resumen.total_usuarios} totales
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Jobs Pendientes</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{overview.resumen.jobs_pendientes}</div>
              <p className="text-xs text-muted-foreground">
                {overview.resumen.jobs_procesando} procesando
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Alertas Críticas</CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600">{overview.resumen.alertas_criticas}</div>
              <p className="text-xs text-muted-foreground">
                Requieren atención
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Métricas del sistema */}
      {overview && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Server className="h-5 w-5 mr-2" />
              Estado del Sistema
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="flex items-center space-x-2">
                <Cpu className="h-4 w-4 text-blue-500" />
                <div>
                  <p className="text-sm text-gray-600">CPU</p>
                  <p className="text-lg font-semibold">{overview.metricas_sistema.cpu_usage.toFixed(1)}%</p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <Database className="h-4 w-4 text-green-500" />
                <div>
                  <p className="text-sm text-gray-600">Memoria</p>
                  <p className="text-lg font-semibold">{overview.metricas_sistema.memory_usage.toFixed(1)}%</p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <Zap className="h-4 w-4 text-yellow-500" />
                <div>
                  <p className="text-sm text-gray-600">Resp. Time</p>
                  <p className="text-lg font-semibold">{overview.metricas_sistema.response_time_avg.toFixed(0)}ms</p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <TrendingUp className="h-4 w-4 text-purple-500" />
                <div>
                  <p className="text-sm text-gray-600">Requests</p>
                  <p className="text-lg font-semibold">{overview.metricas_sistema.requests_total}</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs principales */}
      <Tabs defaultValue="tenants" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="tenants">Tenants</TabsTrigger>
          <TabsTrigger value="alertas">Alertas</TabsTrigger>
          <TabsTrigger value="planes">Distribución Planes</TabsTrigger>
        </TabsList>

        {/* Tab Tenants */}
        <TabsContent value="tenants" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Tenants Recientes</CardTitle>
              <CardDescription>
                Lista de organizaciones en el sistema
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {tenants.map((tenant) => (
                  <div key={tenant.id} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <h3 className="font-semibold">{tenant.nombre}</h3>
                        <Badge className={getPlanColor(tenant.plan)}>
                          {tenant.plan}
                        </Badge>
                        {!tenant.activo && (
                          <Badge variant="destructive">Suspendido</Badge>
                        )}
                      </div>
                      <p className="text-sm text-gray-600">
                        {tenant.tipo_institucion} • {tenant.ciudad}, {tenant.pais}
                      </p>
                      <p className="text-xs text-gray-500">
                        {tenant.usuarios_count}/{tenant.limite_usuarios} usuarios • {tenant.email_contacto}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium">
                        {new Date(tenant.fecha_creacion).toLocaleDateString()}
                      </p>
                      {tenant.fecha_suspension && (
                        <p className="text-xs text-red-600">
                          Suspendido: {new Date(tenant.fecha_suspension).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab Alertas */}
        <TabsContent value="alertas" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Alertas del Sistema</CardTitle>
              <CardDescription>
                Alertas activas y eventos del sistema
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {alertas.map((alerta) => (
                  <div key={alerta.id} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className={`w-3 h-3 rounded-full ${getSeverityColor(alerta.severidad)}`} />
                      <div>
                        <h4 className="font-medium">{alerta.nombre}</h4>
                        <p className="text-sm text-gray-600">{alerta.descripcion}</p>
                        <div className="flex items-center space-x-2 mt-1">
                          <Badge variant="outline" className="text-xs">
                            {alerta.categoria}
                          </Badge>
                          {alerta.duracion_activa_segundos && (
                            <span className="text-xs text-gray-500">
                              Activa {formatDuration(alerta.duracion_activa_segundos)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      {alerta.activa && !alerta.reconocida && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => acknowledgeAlert(alerta.id)}
                        >
                          Reconocer
                        </Button>
                      )}
                      {alerta.reconocida && !alerta.resuelta && (
                        <Badge variant="secondary">Reconocida</Badge>
                      )}
                      {alerta.resuelta && (
                        <Badge variant="default">Resuelta</Badge>
                      )}
                    </div>
                  </div>
                ))}
                {alertas.length === 0 && (
                  <div className="text-center py-8">
                    <p className="text-gray-500">No hay alertas actualmente</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab Planes */}
        <TabsContent value="planes" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Distribución de Planes</CardTitle>
              <CardDescription>
                Distribución de tenants por tipo de plan
              </CardDescription>
            </CardHeader>
            <CardContent>
              {overview && (
                <div className="space-y-4">
                  {overview.distribucion_planes.map((plan) => (
                    <div key={plan.plan} className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <Badge className={getPlanColor(plan.plan)}>
                          {plan.plan.toUpperCase()}
                        </Badge>
                        <span className="font-medium">{plan.count} tenants</span>
                      </div>
                      <div className="w-32 bg-gray-200 rounded-full h-2">
                        <div 
                          className="bg-blue-500 h-2 rounded-full" 
                          style={{ 
                            width: `${(plan.count / overview.resumen.total_tenants) * 100}%` 
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Footer con timestamp */}
      {overview && (
        <div className="text-center text-xs text-gray-500">
          Última actualización: {new Date(overview.timestamp).toLocaleString()}
        </div>
      )}
    </div>
  )
}

export default AdminDashboard
