import type { DomainId, SurfaceId } from "./surfaceIds";
export interface ActiveSurfaceStack { domain: DomainId; rootSurfaceId: SurfaceId; subpageSurfaceId?: SurfaceId; viewSurfaceId?: SurfaceId; modeSurfaceIds: SurfaceId[]; params: Record<string, string>; }
