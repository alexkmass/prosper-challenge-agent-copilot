import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ToolCatalogProvider } from './hooks/useToolCatalog.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToolCatalogProvider>
      <App />
    </ToolCatalogProvider>
  </StrictMode>,
)
