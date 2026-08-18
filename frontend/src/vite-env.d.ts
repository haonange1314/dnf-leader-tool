/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SHOW_DEV_LOGIN?: string;
  readonly VITE_DEV_LOGIN_ACCOUNT?: string;
  readonly VITE_DEV_LOGIN_CODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
