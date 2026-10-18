import { createContext, useContext, useState, type ReactNode } from "react";
import { classContext } from "@/data/classContext";
type WorkingValue = { activeStudentId: string | null; setActiveStudentId: (id: string | null) => void; selectedObjectIds: string[]; activeFileId: string | null; filters: Record<string, unknown>; search: string; setSearch: (search: string) => void };
const WorkingContext = createContext<WorkingValue | null>(null);
export function WorkingContextProvider({ children }: { children: ReactNode }) { const [activeStudentId,setActiveStudentId] = useState<string | null>(null); const [search,setSearch] = useState(""); return <WorkingContext.Provider value={{...classContext,activeStudentId,setActiveStudentId,selectedObjectIds:activeStudentId?[activeStudentId]:[],activeFileId:null,filters:{},search,setSearch}}>{children}</WorkingContext.Provider>; }
export const useWorkingContext = () => { const value = useContext(WorkingContext); if (!value) throw new Error("WorkingContextProvider is required"); return value; };
