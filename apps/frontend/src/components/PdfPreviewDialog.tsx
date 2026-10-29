import { useEffect, useRef } from "react";
import { ExternalLink, X } from "lucide-react";

export interface PdfPreviewRequest {
  url: string;
  title: string;
  location: string;
  excerpt: string;
}

interface PdfPreviewDialogProps {
  preview: PdfPreviewRequest;
  onClose: () => void;
}

export default function PdfPreviewDialog({
  preview,
  onClose,
}: PdfPreviewDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose]);

  return (
    <div className="dialog-backdrop pdf-preview-backdrop" onMouseDown={onClose}>
      <section
        aria-label={`PDF preview: ${preview.title}`}
        aria-modal="true"
        className="pdf-preview-dialog"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="pdf-preview-header">
          <div className="pdf-preview-heading">
            <p>CITED PDF</p>
            <h2>{preview.title}</h2>
            <span>
              {preview.location}
              {preview.excerpt ? " · excerpt search applied" : ""}
            </span>
          </div>
          <div className="pdf-preview-actions">
            <a
              className="citation-open-link"
              href={preview.url}
              rel="noopener noreferrer"
              target="_blank"
            >
              <ExternalLink aria-hidden="true" size={14} />
              Open in new tab
            </a>
            <button
              aria-label="Close PDF preview"
              className="icon-button"
              onClick={onClose}
              ref={closeButtonRef}
              type="button"
            >
              <X aria-hidden="true" size={17} />
            </button>
          </div>
        </header>
        <iframe
          className="pdf-preview-frame"
          referrerPolicy="no-referrer"
          src={preview.url}
          title={`PDF preview: ${preview.title}`}
        />
        {preview.excerpt && (
          <div className="pdf-preview-excerpt">
            <span>Highlighted citation</span>
            <mark>{preview.excerpt}</mark>
          </div>
        )}
      </section>
    </div>
  );
}
