import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useMockDomainStore } from "@/store/MockDomainStore";
import type { Phase } from "@/types/transaction";
type TransactionValue = { phase: Phase | null; setPhase: (phase: Phase | null) => void; commitSeatSwap: () => void };
const TransactionContext = createContext<TransactionValue | null>(null);
export function TransactionSessionProvider({ children }: { children: ReactNode }) { const [phase,setPhase] = useState<Phase | null>(null); const {applySeatSwap} = useMockDomainStore(); useEffect(()=>{ if(phase !== "committing") return; const timer=window.setTimeout(()=>{applySeatSwap("99002","99005");setPhase("committed")},1200); return ()=>window.clearTimeout(timer); },[phase,applySeatSwap]); return <TransactionContext.Provider value={{phase,setPhase,commitSeatSwap:()=>setPhase("committing")}}>{children}</TransactionContext.Provider>; }
export const useTransactionSession = () => { const value = useContext(TransactionContext); if (!value) throw new Error("TransactionSessionProvider is required"); return value; };
