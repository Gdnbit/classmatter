import { createContext, useContext, useState, type ReactNode } from "react";
import { students as initialStudents } from "@/data/students";
import type { Student } from "@/types/student";
type MockDomainValue = { students: Student[]; applySeatSwap: (firstId: string, secondId: string) => void };
const MockDomainContext = createContext<MockDomainValue | null>(null);
export function MockDomainStore({ children }: { children: ReactNode }) { const [students, setStudents] = useState(initialStudents); const applySeatSwap = (firstId: string, secondId: string) => setStudents((current) => { const a = current.find((student) => student.id === firstId); const b = current.find((student) => student.id === secondId); if (!a || !b) return current; return current.map((student) => student.id === a.id ? { ...student, seat: b.seat } : student.id === b.id ? { ...student, seat: a.seat } : student); }); return <MockDomainContext.Provider value={{ students, applySeatSwap }}>{children}</MockDomainContext.Provider>; }
export const useMockDomainStore = () => { const value = useContext(MockDomainContext); if (!value) throw new Error("MockDomainStore is required"); return value; };
