/// <reference types="vite/client" />

/**
 * Build-time configuration.
 *
 * Declared rather than inherited from `vite/client`'s catch-all so an
 * unknown `VITE_*` name is a type error, not a silent `undefined` at runtime.
 */
interface ImportMetaEnv {
  /**
   * Backend origin, e.g. "https://api.example.com". Leave unset for the
   * normal same-origin deployments - see src/api/config.ts.
   */
  readonly VITE_API_BASE?: string;
  /**
   * "off" draws the tactical map without internet tiles - see
   * src/components/map/mapConfig.ts.
   */
  readonly VITE_MAP_TILES?: "off";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
