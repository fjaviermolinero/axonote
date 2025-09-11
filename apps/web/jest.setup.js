import '@testing-library/jest-dom'

// Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      back: jest.fn(),
      forward: jest.fn(),
      refresh: jest.fn(),
    }
  },
  useSearchParams() {
    return new URLSearchParams()
  },
  usePathname() {
    return '/'
  },
}))

// Mock IndexedDB
const mockIDBRequest = {
  onsuccess: null,
  onerror: null,
  result: undefined,
  error: null,
  readyState: 'done',
  transaction: null,
  source: null,
}

const mockIDBDatabase = {
  close: jest.fn(),
  createObjectStore: jest.fn(),
  deleteObjectStore: jest.fn(),
  transaction: jest.fn(() => ({
    objectStore: jest.fn(() => ({
      add: jest.fn(() => mockIDBRequest),
      put: jest.fn(() => mockIDBRequest),
      get: jest.fn(() => mockIDBRequest),
      delete: jest.fn(() => mockIDBRequest),
      clear: jest.fn(() => mockIDBRequest),
      getAll: jest.fn(() => mockIDBRequest),
      index: jest.fn(() => ({
        get: jest.fn(() => mockIDBRequest),
        getAll: jest.fn(() => mockIDBRequest),
      })),
    })),
    oncomplete: null,
    onerror: null,
    onabort: null,
    abort: jest.fn(),
  })),
  version: 1,
  name: 'test-db',
  objectStoreNames: [],
  onabort: null,
  onclose: null,
  onerror: null,
  onversionchange: null,
}

global.indexedDB = {
  open: jest.fn(() => {
    const request = { ...mockIDBRequest }
    setTimeout(() => {
      request.result = mockIDBDatabase
      if (request.onsuccess) request.onsuccess({ target: request })
    }, 0)
    return request
  }),
  deleteDatabase: jest.fn(() => mockIDBRequest),
  databases: jest.fn(() => Promise.resolve([])),
  cmp: jest.fn(),
}

// Mock MediaRecorder
global.MediaRecorder = jest.fn(() => ({
  start: jest.fn(),
  stop: jest.fn(),
  pause: jest.fn(),
  resume: jest.fn(),
  state: 'inactive',
  stream: null,
  mimeType: 'audio/webm',
  addEventListener: jest.fn(),
  removeEventListener: jest.fn(),
  dispatchEvent: jest.fn(),
}))

global.MediaRecorder.isTypeSupported = jest.fn(() => true)

// Mock getUserMedia
global.navigator.mediaDevices = {
  getUserMedia: jest.fn(() => Promise.resolve({
    getTracks: () => [{ stop: jest.fn() }]
  })),
}
