import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App', () => {
  it('renders the engineering baseline', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: '工程基线已就绪' })).toBeInTheDocument()
    expect(screen.getByText('/api/v1/health/live', { exact: false })).toBeInTheDocument()
  })
})
