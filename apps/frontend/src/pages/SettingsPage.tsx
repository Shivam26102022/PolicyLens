import { Cloud, Laptop, ShieldCheck } from "lucide-react";

import { useWorkbench } from "../state/WorkbenchContext";

export default function SettingsPage() {
  const {
    modelOptions,
    modelOptionsError,
    selectedProvider,
    setSelectedProvider,
  } = useWorkbench();

  return (
    <div className="settings-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">PREFERENCES / PROVIDER ROUTING</p>
          <h1>Model settings</h1>
          <p className="page-description">
            Choose among the models configured by this PolicyLens backend.
          </p>
        </div>
      </section>

      <section
        aria-labelledby="model-options-title"
        className="settings-section"
      >
        <div className="settings-section-heading">
          <div>
            <p className="eyebrow">GENERATION</p>
            <h2 id="model-options-title">Available models</h2>
          </div>
          <span className="settings-scope">
            Provider keys stay on the backend
          </span>
        </div>

        {modelOptionsError && (
          <p className="inline-alert" role="status">
            {modelOptionsError}
          </p>
        )}
        {!modelOptions && !modelOptionsError && (
          <p className="settings-loading" role="status">
            Loading configured model options…
          </p>
        )}

        {modelOptions && (
          <fieldset className="model-option-list">
            <legend className="sr-only">Select a generation model</legend>
            {modelOptions.options.map((option) => {
              const isOpenAI = option.provider === "openai";
              const Icon = isOpenAI ? Cloud : Laptop;
              const providerName = isOpenAI ? "OpenAI" : "Local MLX";
              return (
                <label
                  className={`model-option${option.configured ? "" : " is-unavailable"}`}
                  key={option.provider}
                >
                  <input
                    checked={selectedProvider === option.provider}
                    disabled={!option.configured}
                    name="generation-provider"
                    onChange={() => setSelectedProvider(option.provider)}
                    type="radio"
                    value={option.provider}
                  />
                  <span className="model-option-mark" aria-hidden="true" />
                  <Icon
                    className="model-option-icon"
                    aria-hidden="true"
                    size={19}
                  />
                  <span className="model-option-copy">
                    <span className="model-option-name">{providerName}</span>
                    <span className="model-option-id">
                      {option.configured
                        ? option.model_id
                        : `No ${isOpenAI ? "OpenAI" : "local"} model is configured.`}
                    </span>
                  </span>
                  <span
                    className={`model-scope${isOpenAI ? " scope-external" : ""}`}
                  >
                    {isOpenAI ? "External" : "Loopback only"}
                  </span>
                  {isOpenAI && option.configured && (
                    <span className="consent-required">Consent each run</span>
                  )}
                </label>
              );
            })}
          </fieldset>
        )}

        {selectedProvider === "openai" && (
          <p className="selected-provider-note" role="status">
            Consent is requested separately for every research run.
          </p>
        )}

        <div className="settings-notice">
          <ShieldCheck aria-hidden="true" size={18} />
          <div>
            <h3>External processing stays explicit</h3>
            <p>
              Each OpenAI run asks for external-processing consent before
              sending your question and selected evidence. Consent is never
              saved. A provider that is unavailable will not be substituted
              automatically.
            </p>
          </div>
        </div>
        <p className="settings-footnote">
          This preference applies in this browser session. It does not change
          the backend configuration or store a conversation.
        </p>
      </section>
    </div>
  );
}
