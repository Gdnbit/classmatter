import AppShell from "@/shell/AppShell"

import { MockDomainStore } from "@/store/MockDomainStore"

import { ConversationStore } from "@/store/ConversationStore"

import { SessionStore } from "@/store/SessionStore"

import { WorkingContextProvider } from "@/state/WorkingContextProvider"

import { TransactionSessionProvider } from "@/state/TransactionSessionProvider"
import { UiFeedbackStore } from "@/store/UiFeedbackStore"
import R1App from "@/runtime/R1App"
import { DemoWorkStore } from "@/store/DemoWorkStore"
export default function App() {
  if (import.meta.env.VITE_CLASS_OS_DEMO !== "true") return <R1App />
  return (
    <MockDomainStore>
      <ConversationStore>
        <SessionStore>
          <WorkingContextProvider>
            <TransactionSessionProvider>
              <UiFeedbackStore>
                <DemoWorkStore><AppShell /></DemoWorkStore>
              </UiFeedbackStore>
            </TransactionSessionProvider>
          </WorkingContextProvider>
        </SessionStore>
      </ConversationStore>
    </MockDomainStore>
  )
}
