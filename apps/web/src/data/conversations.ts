export type ConversationMessage = { role: "user" | "assistant"; text: string; action?: boolean };
export const initialConversations = [{ id: "today", title: "今天的班级工作", messages: [] as ConversationMessage[] }, { id: "seat-adjustment", title: "座位与分组调整", messages: [] as ConversationMessage[] }] as const;
