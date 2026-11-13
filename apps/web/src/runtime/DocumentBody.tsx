import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { memo } from 'react'
import 'katex/dist/katex.min.css'
import './document-body.css'

// Presentation only: the caller retains the exact revision/candidate body.
// Do not add raw HTML, executable extensions or automatic remote resources.
export const DocumentBody = memo(function DocumentBody({ body, format }: { body: string; format: string }) {
  return <div className={`document-body ${format === 'markdown' ? 'document-markdown' : 'document-plain'}`}>
    {format === 'markdown' ? <Markdown remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[[rehypeKatex, { trust: false, maxExpand: 100, maxSize: 20, errorColor: '#1f2b24' }]]} components={{
      img: ({ alt }) => <span>{alt || '图片'}</span>,
      a: ({ children, href }) => <span>{children}{href && <>（{href}）</>}</span>,
      // Unsupported formulas stay readable without exposing renderer diagnostics.
      span: ({ node: _node, title, className, ...props }) => <span {...props} className={className}
        title={className?.split(' ').includes('katex-error') ? undefined : title} />,
    }}>{body}</Markdown> : body}
  </div>
})
