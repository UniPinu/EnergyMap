/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of service B (our own API). The browser never talks to anything else. */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
