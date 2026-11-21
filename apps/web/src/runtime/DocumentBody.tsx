import { lazy, memo, Suspense } from 'react'
import './document-body.css'

const MarkdownBody = lazy(() => import('./MarkdownBody'))

// Presentation only: the caller retains the exact revision/candidate body.
// Do not add raw HTML, executable extensions or automatic remote resources.
export const DocumentBody = memo(function DocumentBody({ body, format }: { body: string; format: string }) {
  return <div className={`document-body ${format === 'markdown' ? 'document-markdown' : 'document-plain'}`}>
    {format === 'markdown'
      ? <Suspense fallback={<div className="document-plain" data-document-loading>{body}</div>}><MarkdownBody body={body} /></Suspense>
      : body}
  </div>
})
