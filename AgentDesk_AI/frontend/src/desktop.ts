/** Bridge to the pywebview desktop shell (desktop/shell.py). Absent in a normal browser. */
interface DesktopApi {
  expand: () => Promise<void>;
  collapse: () => Promise<void>;
  get_autostart: () => Promise<boolean>;
  set_autostart: (enabled: boolean) => Promise<boolean>;
}

declare global {
  interface Window {
    pywebview?: { api?: Partial<DesktopApi> };
  }
}

export function desktopApi(): Partial<DesktopApi> | null {
  return window.pywebview?.api ?? null;
}

export const isDesktop = () => desktopApi() !== null;

export async function expandPanel(): Promise<void> {
  const api = desktopApi();
  if (api?.expand) await api.expand();
  else window.location.href = '/';
}

export async function collapseToOrb(): Promise<void> {
  await desktopApi()?.collapse?.();
}
