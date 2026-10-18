import type { SurfaceId } from "@/types/surfaceIds";
export type ToolbarConfig = { controls: string[] };
export const surfaceToolbars: Partial<Record<SurfaceId, ToolbarConfig>> = { "HOME-CONVERSATION-IDLE": { controls: ["定时安排"] }, "STUDENT-LIST": { controls: ["当前视图", "筛选"] }, "VIEW-SEAT": { controls: ["编辑布局", "约束"] } };
export const transactionToolbarOverride: ToolbarConfig = { controls: ["预览"] };
