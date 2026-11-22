import Markdown, { type Options } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

const remarkPlugins: Options['remarkPlugins'] = [remarkGfm, remarkMath]
const rehypePlugins: Options['rehypePlugins'] = [[rehypeKatex, { trust: false, maxExpand: 100, maxSize: 20, errorColor: '#1f2b24' }]]
const components: Options['components'] = {
  img: ({ alt }) => <span>{alt || '图片'}</span>,
  a: ({ children, href }) => <span>{children}{href && <>（{href}）</>}</span>,
  // Unsupported formulas remain readable without exposing renderer diagnostics.
  span: ({ node: _node, title, className, ...props }) => <span {...props} className={className}
    title={className?.split(' ').includes('katex-error') ? undefined : title} />,
}

export default function MarkdownBody({ body }: { body: string }) {
  return <Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>{body}</Markdown>
}
