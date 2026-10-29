import { Clipboard, ClipboardCheck, ExternalLink } from "lucide-react";

import type { AgentAnswerResponse } from "../api/client";
import { pdfViewerUrl, resolvePdfSource } from "../data/pdf-sources";

type Citation = AgentAnswerResponse["claims"][number]["citations"][number];

interface EvidenceDrawerProps {
  citation: Citation;
  copied: boolean;
  onCopyCitation: (value: string) => void;
  onOpenPdfPreview: (trigger: HTMLButtonElement) => void;
}

function formatLocation(citation: Citation): string {
  if (citation.row_key) {
    const location = [
      citation.row_key.country_iso3,
      citation.row_key.year,
      citation.row_key.indicator_id,
    ].filter((value) => value !== undefined);
    return location.length > 0 ? location.join(" · ") : "Structured row";
  }

  const page =
    citation.page_start && citation.page_end
      ? citation.page_start === citation.page_end
        ? `Page ${citation.page_start}`
        : `Pages ${citation.page_start}–${citation.page_end}`
      : citation.page_start
        ? `Page ${citation.page_start}`
        : null;
  return (
    [page, citation.section_path.join(" / ") || null]
      .filter((part): part is string => Boolean(part))
      .join(" · ") || "Source passage"
  );
}

function sourceLink(
  citation: Citation,
): { href: string; isPdf: boolean } | null {
  const pdfSource = resolvePdfSource(
    citation.source_uri,
    citation.source_id,
    true,
  );
  if (pdfSource) {
    return {
      href: pdfViewerUrl(pdfSource, citation.page_start, citation.excerpt),
      isPdf: true,
    };
  }
  if (!citation.source_uri) return null;

  try {
    const url = new URL(citation.source_uri);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username.length > 0 ||
      url.password.length > 0
    ) {
      return null;
    }

    return { href: url.toString(), isPdf: false };
  } catch {
    return null;
  }
}

export default function EvidenceDrawer({
  citation,
  copied,
  onCopyCitation,
  onOpenPdfPreview,
}: EvidenceDrawerProps) {
  const location = formatLocation(citation);
  const source = sourceLink(citation);
  const isPdfPage = source?.isPdf && citation.page_start !== null;

  return (
    <article
      aria-label={`Citation from ${citation.title}`}
      className="citation-card"
    >
      <header className="citation-card-header">
        <div className="citation-source">
          <span className="citation-source-label">SOURCE</span>
          <strong>{citation.title}</strong>
          <span className="citation-source-id">{citation.source_id}</span>
        </div>
        <span className="citation-location">{location}</span>
      </header>
      <blockquote className="citation-quote">
        <mark className="citation-highlight">{citation.excerpt}</mark>
      </blockquote>
      <details className="citation-provenance">
        <summary>Provenance details</summary>
        <dl>
          <div>
            <dt>Passage</dt>
            <dd>{citation.passage_id}</dd>
          </div>
          <div>
            <dt>Source hash</dt>
            <dd>{citation.source_content_sha256}</dd>
          </div>
          {citation.row_key &&
            Object.entries(citation.row_key).map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll("_", " ")}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
      </details>
      <div className="citation-actions">
        {source?.isPdf ? (
          <button
            aria-label={
              isPdfPage
                ? `Open PDF preview at page ${citation.page_start}, with cited text highlighted`
                : `Open PDF preview for ${citation.title}`
            }
            className="citation-open-link"
            onClick={(event) => onOpenPdfPreview(event.currentTarget)}
            type="button"
          >
            <ExternalLink aria-hidden="true" size={14} />
            {isPdfPage
              ? `Preview PDF · page ${citation.page_start}`
              : "Preview PDF"}
          </button>
        ) : source ? (
          <a
            aria-label={`Open source for ${citation.title}`}
            className="citation-open-link"
            href={source.href}
            rel="noopener noreferrer"
            target="_blank"
          >
            <ExternalLink aria-hidden="true" size={14} />
            Open source
          </a>
        ) : (
          <span className="citation-link-unavailable">
            Original source link unavailable
          </span>
        )}
        <button
          aria-label="Copy citation"
          className="copy-citation"
          onClick={() =>
            onCopyCitation(
              `${citation.title} (${citation.source_id}), ${location}. "${citation.excerpt}" [${citation.passage_id}]`,
            )
          }
          type="button"
        >
          {copied ? (
            <ClipboardCheck aria-hidden="true" size={14} />
          ) : (
            <Clipboard aria-hidden="true" size={14} />
          )}
          Copy citation
        </button>
      </div>
    </article>
  );
}
