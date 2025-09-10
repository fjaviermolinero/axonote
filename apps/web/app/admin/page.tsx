import AdminDashboard from '@/components/admin/AdminDashboard'

export default function AdminPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <AdminDashboard />
    </div>
  )
}

export const metadata = {
  title: 'Admin Dashboard - AxoNote',
  description: 'Panel de administración del sistema AxoNote',
}
