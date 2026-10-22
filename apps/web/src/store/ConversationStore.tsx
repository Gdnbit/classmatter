import { createContext, useContext, useState, type ReactNode } from "react";
import { initialConversations, type ConversationMessage } from "@/data/conversations";
type ConversationValue = { conversations: { id: string; title: string }[]; messagesByConversationId: Record<string, ConversationMessage[]>; drafts: Record<string,string>; setDraft: (id: string, text: string) => void; appendMessage: (id: string, message: ConversationMessage) => void; createConversation: () => string; renameConversation: (id: string, title: string) => void };
const ConversationContext = createContext<ConversationValue | null>(null);
export function ConversationStore({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<{ id: string; title: string }[]>(initialConversations.map(({id,title})=>({id,title})));
  const [messagesByConversationId, setMessages] = useState<Record<string, ConversationMessage[]>>(() => Object.fromEntries(initialConversations.map(x => [x.id,[...x.messages]])));
  const [drafts, setDrafts] = useState<Record<string,string>>({});
  const setDraft = (id: string, text: string) => setDrafts(all => ({ ...all, [id]: text }));
  const renameConversation = (id: string, title: string) => setConversations(all => all.map(c => c.id === id ? { ...c, title: title.trim().slice(0, 60) || "新对话" } : c));
  const appendMessage = (id: string, message: ConversationMessage) => {
    setMessages(all => ({ ...all, [id]: [...(all[id] || []), message] }));
    if (message.role === "user") setConversations(all => all.map(c => c.id === id && c.title === "新对话" ? { ...c, title: message.text.slice(0, 28) } : c));
  };
  const createConversation = () => {
    const id = `chat-${crypto.randomUUID()}`;
    setConversations(all => [{ id, title: "新对话" }, ...all]);
    setMessages(all => ({ ...all, [id]: [] }));
    return id;
  };
  return <ConversationContext.Provider value={{conversations,messagesByConversationId,drafts,setDraft,appendMessage,createConversation,renameConversation}}>{children}</ConversationContext.Provider>;
}
export const useConversationStore = () => { const value = useContext(ConversationContext); if (!value) throw new Error("ConversationStore is required"); return value; };
