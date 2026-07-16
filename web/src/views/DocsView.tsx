/** In-app documentation (PRD #75 / #78). Renders the public guides from
 *  docs/public inside the dashboard (single source, also served on the landing).
 *  `/docs` lists the guides; `/docs/:slug` renders one in the UI locale. */

import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { docSlugs, docTitle, getDoc, type DocLang } from "../lib/docsContent";

function useLang(): DocLang {
  const { i18n } = useTranslation();
  const lng = i18n.language.slice(0, 2);
  return lng === "en" || lng === "es" ? lng : "fr";
}

const MD: Components = {
  h1: (p) => <h1 className="mt-8 text-2xl font-bold text-ink first:mt-0" {...p} />,
  h2: (p) => <h2 className="mt-6 border-b border-line pb-1 text-lg font-semibold text-ink" {...p} />,
  h3: (p) => <h3 className="mt-5 text-base font-semibold text-ink" {...p} />,
  p: (p) => <p className="mt-3 leading-relaxed text-ink-soft" {...p} />,
  ul: (p) => <ul className="mt-3 list-disc space-y-1 pl-5 text-ink-soft" {...p} />,
  ol: (p) => <ol className="mt-3 list-decimal space-y-1 pl-5 text-ink-soft" {...p} />,
  li: (p) => <li className="leading-relaxed" {...p} />,
  a: (p) => <a className="text-flame underline-offset-2 hover:underline" {...p} />,
  strong: (p) => <strong className="font-semibold text-ink" {...p} />,
  blockquote: (p) => (
    <blockquote className="mt-3 border-l-2 border-line pl-3 text-ink-soft italic" {...p} />
  ),
  pre: (p) => (
    <pre className="mt-3 overflow-x-auto rounded-md border border-line bg-paper p-3 text-xs" {...p} />
  ),
  code: ({ className, ...p }) =>
    /language-/.test(className ?? "") ? (
      <code className={`${className} font-mono`} {...p} />
    ) : (
      <code className="rounded bg-paper px-1 py-0.5 font-mono text-[0.85em] text-ink" {...p} />
    ),
  table: (p) => (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm" {...p} />
    </div>
  ),
  th: (p) => <th className="border border-line bg-paper px-2 py-1 text-left font-semibold" {...p} />,
  td: (p) => <td className="border border-line px-2 py-1 text-ink-soft" {...p} />,
};

function DocsIndex() {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="text-xl font-semibold text-ink">{t("docsUi.title")}</h1>
      <p className="mt-1 text-sm text-ink-soft">{t("docsUi.subtitle")}</p>
      <ul className="mt-5 space-y-2">
        {docSlugs.map((slug) => (
          <li key={slug}>
            <Link
              to={`/docs/${slug}`}
              className="block rounded-lg border border-line bg-surface px-4 py-3 hover:border-flame"
            >
              <span className="text-sm font-semibold text-ink">{docTitle(slug, lang)}</span>
              <code className="ml-2 text-[11px] text-ink-soft/70">{slug}</code>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function DocsView() {
  const { t } = useTranslation();
  const lang = useLang();
  const { slug } = useParams();

  if (!slug) return <DocsIndex />;
  const md = getDoc(slug, lang);
  if (!md) return <Navigate to="/docs" replace />;

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <Link to="/docs" className="text-xs font-medium text-flame hover:underline">
        ← {t("docsUi.title")}
      </Link>
      <article className="mt-2">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
          {md}
        </ReactMarkdown>
      </article>
    </div>
  );
}
