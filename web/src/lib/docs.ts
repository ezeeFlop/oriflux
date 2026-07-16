/** In-app documentation route for a guide slug (#78). The guides render inside
 *  the dashboard (DocsView) in the current UI locale; the same markdown source
 *  in docs/public also feeds the public Astro landing. Use with react-router:
 *  `<Link to={docsUrl(slug)}>`. */
export function docsUrl(slug: string): string {
  return `/docs/${slug}`;
}
