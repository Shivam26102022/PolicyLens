import { useEffect, useRef } from "react";
import { ArrowUpRight, X } from "lucide-react";

interface ProviderConsentDialogProps {
  question: string;
  hasConversation?: boolean;
  externalGeneration?: boolean;
  externalEmbeddings?: boolean;
  longMemoryEnabled?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function ProviderConsentDialog({
  question,
  hasConversation = false,
  externalGeneration = true,
  externalEmbeddings = false,
  longMemoryEnabled = false,
  onCancel,
  onConfirm,
}: ProviderConsentDialogProps) {
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const generationOnly = externalGeneration && !externalEmbeddings;

  useEffect(() => {
    cancelButtonRef.current?.focus();
  }, []);

  return (
    <div className="dialog-backdrop" onMouseDown={onCancel}>
      <section
        aria-labelledby="provider-consent-title"
        aria-modal="true"
        className="consent-dialog"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="dialog-topline">
          <span className="external-label">
            <ArrowUpRight aria-hidden="true" size={15} />
            External processing
          </span>
          <button
            aria-label="Close consent dialog"
            className="icon-button"
            onClick={onCancel}
            type="button"
          >
            <X aria-hidden="true" size={17} />
          </button>
        </div>
        <h2 id="provider-consent-title">
          {generationOnly
            ? "Send this question to OpenAI?"
            : "Allow external processing for this turn?"}
        </h2>
        {externalGeneration && (
          <p>
            OpenAI may process your question, current evidence
            {hasConversation
              ? ", and up to five recent messages from this session"
              : ""}
            {longMemoryEnabled ? ", plus relevant long-term memory" : ""}.
          </p>
        )}
        {externalEmbeddings && (
          <p>
            OpenAI embeddings will process this question for retrieval
            {longMemoryEnabled
              ? " and the completed question/answer pair for long-term memory"
              : ""}
            .
          </p>
        )}
        <p>This approval applies to this turn only.</p>
        <blockquote>{question}</blockquote>
        <div className="dialog-actions">
          <button
            className="button button-secondary"
            onClick={onCancel}
            ref={cancelButtonRef}
            type="button"
          >
            {generationOnly ? "Keep it local" : "Cancel"}
          </button>
          <button
            className="button button-primary"
            onClick={onConfirm}
            type="button"
          >
            {generationOnly ? "Continue with OpenAI" : "Allow this turn"}
          </button>
        </div>
      </section>
    </div>
  );
}
