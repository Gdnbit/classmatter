import { createContext, useContext, useState, useRef, type ReactNode } from "react";
import { useMockDomainStore } from "@/store/MockDomainStore";
import type { Phase } from "@/types/transaction";
import { useSessionStore } from "@/store/SessionStore";
import { createSeatPlan, projectSeatPlan, type SeatPlan } from "@/demo/seat-plan";
type SeatSession = { phase: Phase | null; plan: SeatPlan | null; error: string | null };
type TransactionValue = SeatSession & { setPhase: (phase: Phase | null) => void; commitSeatSwap: () => void; createSeatDraft: (request: string) => string | null };
const TransactionContext = createContext<TransactionValue | null>(null);
export function TransactionSessionProvider({ children }: { children: ReactNode }) {
  const { activeConversationId } = useSessionStore();
  const { students, applySeatSwap } = useMockDomainStore();
  const [sessions, setSessions] = useState<Record<string, SeatSession>>({});
  const applied = useRef(new Set<SeatPlan>());
  const session = sessions[activeConversationId] || { phase: null, plan: null, error: null };
  const update = (next: SeatSession) => setSessions(all => ({ ...all, [activeConversationId]: next }));
  const setPhase = (phase: Phase | null) => {
    // Only commitSeatSwap can claim an applied result.
    if (phase === "committed" || phase === "committing") return;
    update({ ...session, phase });
  };
  const createSeatDraft = (request: string) => {
    if (session.phase && !["committed", "discarded"].includes(session.phase)) return "本次对话已有未完成草稿，请先处理后再生成。";
    try {
      const plan = createSeatPlan(students, request);
      projectSeatPlan(students, plan);
      update({ phase: "preview-ready", plan, error: null });
      return null;
    } catch (error) { return (error as Error).message; }
  };
  const commitSeatSwap = () => {
    if (session.phase !== "confirming" || !session.plan || applied.current.has(session.plan)) return;
    try {
      projectSeatPlan(students, session.plan);
      applied.current.add(session.plan);
      applySeatSwap(session.plan.changes[0].studentId, session.plan.changes[1].studentId);
      update({ ...session, phase: "committed", error: null });
    } catch (error) { update({ ...session, phase: "conflict", error: (error as Error).message }); }
  };
  return <TransactionContext.Provider value={{ ...session, setPhase, createSeatDraft, commitSeatSwap }}>{children}</TransactionContext.Provider>;
}
export const useTransactionSession = () => { const value = useContext(TransactionContext); if (!value) throw new Error("TransactionSessionProvider is required"); return value; };
