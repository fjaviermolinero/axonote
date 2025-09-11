import { render, screen } from '@testing-library/react'
import Home from '@/app/page'

// Mock the components that might have complex dependencies
jest.mock('@/components/ui/RecordButton', () => {
  return function MockRecordButton() {
    return <button>Mock Record Button</button>
  }
})

jest.mock('@/components/ui/RecordingControls', () => {
  return function MockRecordingControls() {
    return <div>Mock Recording Controls</div>
  }
})

describe('Home Page', () => {
  it('renders without crashing', () => {
    render(<Home />)
    expect(screen.getByText(/axonote/i)).toBeInTheDocument()
  })

  it('displays the main heading', () => {
    render(<Home />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toBeInTheDocument()
  })
})
