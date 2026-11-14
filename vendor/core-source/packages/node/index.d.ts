export interface CoreContext {
  officialAccount?: boolean;
  authenticated?: boolean;
  subject?: string;
  publicNavigation?: boolean;
  issuer?: string;
}
export interface CoreManifest {
  version: string;
  ui_api: number;
  icon_sources?: Record<string, string>;
  entrypoints: Record<string, string>;
  files: Record<string, { sha256: string; size: number; data?: string }>;
}
export function active(app: string): CoreManifest;
export function manifest(version?: string): CoreManifest;
export function asset(uri: string): { data: Buffer; type: string } | null;
export function inject(
  body: string,
  app?: string,
  context?: CoreContext,
): string;
export function installCore(
  app: any,
  options?: {
    appId?: string;
    context?: (request: any, response: any) => CoreContext;
  },
): void;
export function managerRequest(
  appId: string,
  action?: string,
  data?: Record<string, unknown>,
): Promise<any>;
export const iconSources: Readonly<Record<string, string>>;
export const iconLibrary: { name: string; label: string }[];
export function icon(name: string): string;

export function renderTemplate(
  name: string,
  slots?: Record<string, string>,
): string;

export interface CoreNotice {
  id: string;
  version: string;
  title: string;
  items: string[];
}
export interface CoreNoticeState {
  available: boolean;
  notice: CoreNotice | null;
}
export function readNotice(
  appId: string,
  subject: string,
  isDismissed: (subject: string, id: string) => boolean | Promise<boolean>,
): Promise<CoreNoticeState>;
export function dismissNotice(
  appId: string,
  subject: string,
  id: string,
  saveDismissed: (subject: string, id: string) => void | Promise<void>,
): Promise<{ dismissed: true }>;
