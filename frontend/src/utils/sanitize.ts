import xss from 'xss'

export function sanitizeMarkdownHtml(html: string): string {
  return xss(html, {
    css: false,
    stripIgnoreTagBody: ['script', 'style', 'iframe', 'object', 'embed'],
  })
}
