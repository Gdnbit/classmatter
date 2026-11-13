import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { memo } from 'react'
import './document-body.css'

// Presentation only: the caller retains the exact revision/candidate body.
// Do not add raw HTML, executable extensions or automatic remote resources.
export const DocumentBody = memo(function DocumentBody({ body, format }: { body: string; format: string }) {
  return <div className={`document-body ${format === 'markdown' ? 'document-markdown' : 'document-plain'}`}>
    {format === 'markdown' ? <Markdown remarkPlugins={[remarkGfm]} components={{
      img: ({ alt }) => <span>{alt || '图片'}</span>,
      a: ({ children, href }) => <span>{children}{href && <>（{href}）</>}</span>,
    }}>{body}</Markdown> : body}
  </div>
})
