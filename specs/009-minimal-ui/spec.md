# Feature Specification: PolicyLens Research Workbench

**Feature Branch**: `009-minimal-ui`
**Created**: 2026-10-24
**Updated**: 2026-10-28
**Status**: Draft
**Input**: Enhanced Feature 009 research interface with provider settings, evaluation visibility, and architecture education.

> **Supersession note:** Feature 009's original browser-only follow-up context was replaced by Feature 011's persisted sessions and server-owned hot context. The Feature 009 requirements below preserve the original implementation contract; current session and memory behavior is documented in `specs/011-session-memory/`.

## Product Outcome

Policy researchers can ask evidence-grounded questions in a clear chat workspace, choose an available configured model, continue bounded follow-ups, inspect safe operational progress and provider-reported usage, and understand how retrieval, agent runtime, tools, and session state work.

## Scope and Dependencies

Feature 009 upgrades the current status-only web shell into a responsive research workbench. It includes the chat workflow, example-prompt autofill, provider/model selection, fixed Hybrid retrieval and Standard answer settings, bounded follow-ups, typed safe progress streaming, answer and evidence inspection, provider-reported usage, read-only evaluation summaries, system status, and an architecture guide. PDF examples automatically scope their requests to the matching report; manually entered questions search the full corpus. A per-answer trail may show the provider-generated reasoning summary returned by the Responses API; it must never show private reasoning content, prompts, raw tool arguments, or evidence payloads. Standard OpenAI uses Responses API; custom endpoints retain Chat Completions by default, with an explicit compatibility-gated setting to opt into Responses API. Feature 011 supplies persisted sessions and their five-pair hot context. Contracts remain typed and provider credentials and local files stay server-side.

## Clarifications

No critical ambiguities remain. The following safe defaults bound implementation:

- Model choices are limited to provider/model options explicitly reported as configured by the backend; users cannot submit arbitrary model identifiers.
- Selecting OpenAI does not itself grant consent. The user must affirm external processing for each run that sends query/evidence to OpenAI; the browser never receives credentials.
- The research composer always requests Standard reasoning (`none`) and Hybrid retrieval; it does not expose search, filter, or answer-depth controls. The backend continues to validate the requested reasoning effort against the selected route.
- Follow-up context is sent explicitly from browser memory, bounded to 8 prior user/assistant messages, 4,000 characters per message, and 12,000 characters total. It is not provider-managed or persisted across reloads, and every OpenAI follow-up requires fresh consent.
- Progress is delivered as typed operational events. It may describe retrieval, approved tool activity, validation, and terminal state, but MUST NOT expose hidden reasoning, prompts, raw tool arguments, or evidence payloads.
- Model usage is shown only when reported by the provider. The trail identifies the selected route and effort, displays a provider-generated Responses API `summary_text` when returned, and explains when a summary is unavailable. Private reasoning content is never exposed.
- Standard OpenAI uses Responses API. A custom endpoint uses Chat Completions by default; `OPENAI_USE_RESPONSES_API=true` is an explicit opt-in only after confirming that the configured endpoint supports the Responses API. There is no automatic route fallback.
- Evaluation screens are read-only summaries of existing run manifests. Starting, editing, or deleting evaluation runs is not part of this feature.
- Agent run state is request-scoped. Bounded follow-up context exists only in the current browser session; no cross-session conversational memory is implemented or implied.
- Architecture documentation distinguishes implemented behavior from planned or unavailable behavior.

## User Scenarios & Testing

### User Story 1 - Ask Questions in the Research Workspace (Priority: P1)

As a policy researcher, I can ask a question in a chat-like workspace, use an example as a starting point, and follow a safe progress and terminal state.

**Why this priority**: Asking a grounded question is the primary value of the product and the MVP for the enhanced frontend.

**Independent Test**: Browser tests submit a question, click an example prompt and observe it autofill without submitting, follow progress, cancel when supported, and inspect success and failure states.

**Acceptance Scenarios**:

1. **AC-009-01** Given the research workspace is open, When I click an example prompt, Then its text is placed in the composer and no request is sent.
2. **AC-009-02** Given a valid question, When I submit it, Then the UI shows typed safe operational progress (including any reported reranking outcome, model, candidate count, duration, and fallback), a trace ID, and the final state without hidden reasoning.
3. **AC-009-03** Given the streamed answer request is in flight, When I stop waiting, Then the browser aborts its stream and reports local cancellation while clearly stating that backend work may continue until its configured timeout; it MUST NOT claim provider execution stopped unless server-side cancellation is implemented.
4. **AC-009-04** Given validation, offline, timeout, unavailable provider, permission, or server failure, When the run ends, Then the user sees an accessible, distinct explanation and can recover.

### User Story 2 - Choose a Configured Model Safely (Priority: P1)

As a researcher, I can choose among backend-configured OpenAI and local model options and understand the privacy effect before running a question.

**Why this priority**: Provider choice affects privacy, availability, and response behavior; the interface must not imply a choice it cannot honor.

**Independent Test**: Contract and browser tests choose each available configured option, reject an unavailable option, verify OpenAI requires a fresh per-run confirmation, and confirm no request silently changes providers.

**Acceptance Scenarios**:

1. **AC-009-05** Given multiple configured model options, When I open model settings, Then the UI names each available provider/model and identifies local versus external processing.
2. **AC-009-06** Given OpenAI is selected, When I submit without confirming external processing for this run, Then no request is sent.
3. **AC-009-07** Given a selected provider is unconfigured or unavailable, When I try to use it, Then the UI explains the state and never falls back silently.
4. **AC-009-19** Given I submit a question, Then the UI uses Hybrid retrieval and Standard reasoning (`none`) without exposing search/filter/depth controls; the backend rejects unsupported effort values, and Responses API requests receive an effort-scaled output-token budget bounded to 8,000.

### User Story 3 - Inspect Answers, Evidence, and Tool Activity (Priority: P1)

As a reviewer, I can inspect the answer, claim-linked citations, source evidence, calculations, uncertainty, conflicts, limitations, and safe tool activity.

**Why this priority**: Evidence inspection is essential to trust and distinguishes PolicyLens from a general chat interface.

**Independent Test**: Response fixtures cover answered, abstained, clarification, conflict, calculations, and failed-safe runs; citations open exact bounded evidence and copy actions work.

**Acceptance Scenarios**:

1. **AC-009-08** Given an answer contains factual claims, When I inspect a claim, Then its citation opens the exact bounded passage or structured rows and provenance.
2. **AC-009-09** Given a run uses a deterministic tool, When I open activity, Then I see tool name, status, and a safe summary without private reasoning or raw secrets.
3. **AC-009-10** Given evidence is missing, conflicting, or insufficient, When the response abstains or asks for clarification, Then the UI presents that state without fabricating a confident answer.
4. **AC-009-22** Given a model run returns usage or a Responses API reasoning summary, When I expand that answer's activity trail, Then the UI shows the selected API route, reasoning effort, provider-reported token counts, and only the SDK-provided summary text; when usage or summary is absent it is labeled as not reported or unavailable, never as zero or private reasoning.

### User Story 4 - Review Evaluation Results (Priority: P2)

As an evaluator, I can inspect existing evaluation runs and their coverage, metrics, and limitations without starting an evaluation from the browser.

**Why this priority**: Existing benchmark artifacts should be understandable from the product, while evaluation execution remains an explicit controlled workflow.

**Independent Test**: API and browser tests cover populated, blocked, empty, malformed, and unavailable manifest states and confirm responses contain summaries only.

**Acceptance Scenarios**:

1. **AC-009-11** Given evaluation records exist, When I open Evaluations, Then I can compare run status, timestamp, case count, split/category coverage, key metrics, and declared limitations.
2. **AC-009-12** Given manifests are missing or contain no results, When I open Evaluations, Then the UI shows an honest empty state rather than zero-valued or fabricated metrics.
3. **AC-009-13** Given I view evaluation data, When the page loads, Then no evaluation or provider run is started and no raw prompt/case text is exposed.
4. **AC-009-23** Given a run contains AI-judged answer metrics, When I inspect it, Then groundedness/relevance are labeled as AI-judged, the rubric/model, whether the judge shares the generator model ID, and attempted/scored/failed/skipped counts are visible, and the UI states that the scores are not human-validated; absent scores remain “Not measured.”
5. **AC-009-24** Given a run contains measured metrics, When I inspect its results, Then each metric shows its scored sample count, retrieval shows expected-anchor hits and denominator when recorded, groundedness shows its score distribution, and condition/category comparisons remain distinguishable from run-level aggregates. Historical metrics without anchor totals are identified as not recalculated.
6. **AC-009-25** Given a recorded metric or cost is shown, When I expand its explanation, Then I can read its plain-language calculation and denominator; cost identifies provider-reported versus token-estimated values, the priced model and rate date, and any token-usage gaps.

### User Story 5 - Understand the System Architecture (Priority: P2)

As a contributor or reviewer, I can explore how the UI, API, retrieval, agent runtime, memory/state, tools, providers, validation, and evaluation fit together.

**Why this priority**: Clear system explanations make the many documents and components navigable and set accurate expectations about agent capabilities.

**Independent Test**: Architecture view tests verify every documented layer and trust boundary is present, keyboard navigable, and labels implemented versus unavailable behavior.

**Acceptance Scenarios**:

1. **AC-009-14** Given I open Architecture, When I select a layer, Then I see its responsibility, inputs/outputs, trust boundary, and links to relevant documentation.
2. **AC-009-15** Given I inspect memory and runtime tools, When I read their descriptions, Then the UI states that agent state is request-scoped, identifies the bounded statistics tool, and does not claim persistent chat memory.
3. **AC-009-16** Given a capability is planned or unavailable, When it appears in the architecture guide, Then it is visibly labeled and not presented as implemented.

### User Story 6 - Check System Status (Priority: P2)

As a contributor, I can see backend, retrieval/index, MCP, and configured model status without exposing internal paths or secrets.

**Independent Test**: Browser tests exercise ready, degraded, unavailable, and not-configured status responses.

**Acceptance Scenarios**:

1. **AC-009-17** Given services are ready, degraded, or unavailable, When I open System Status, Then each component has a distinct accessible state and safe description.
2. **AC-009-18** Given a health response contains an internal path, credential, or stack detail, When it is rendered, Then that detail is not shown to the user.

### User Story 7 - Continue a Research Conversation (Priority: P1)

As a researcher, I can ask a follow-up question that uses a small amount of prior turn context without creating persistent or provider-managed chat memory.

**Why this priority**: Follow-up questions support natural research iteration while preserving the product's explicit evidence and privacy boundaries.

**Independent Test**: Component/API tests verify prior turns are sent within message and character bounds, can be cleared, and each OpenAI turn requires fresh consent.

**Acceptance Scenarios**:

1. **AC-009-20** Given a completed answer, When I submit a follow-up, Then the request includes only bounded prior user/assistant turns and the current question remains independently evidence-validated.
2. **AC-009-21** Given I clear the conversation or reload the page, When I submit another question, Then cleared/reloaded prior turns are not sent.

### Edge Cases

- No provider is configured, only one provider is available, or a provider becomes unavailable after the options view loads.
- OpenAI is selected but per-run external-processing consent is absent or withdrawn before submission.
- The browser aborts its stream, the backend continues until its bounded timeout, or the request returns an unknown status/error code.
- Follow-up history reaches a message or character bound, is cleared, or contains assistant text that must be treated as untrusted context rather than evidence.
- The selected provider does not advertise Standard reasoning (`none`), or its capability changes after model options load.
- A provider route does not report usage, a Responses API run returns no summary, or a custom endpoint is not compatible with the Responses API.
- An evaluation manifest is absent, malformed, contains blocked runs, or has metrics represented as `null`.
- A run has no citations, multiple citations, structured calculation evidence, or an unsafe/untrusted source string.
- The architecture guide describes a future capability or a component that is not configured in the current deployment.
- The browser is 320 CSS pixels wide, keyboard-only, or using a screen reader.

## Requirements

### Functional Requirements

- **UI-009-01**: The research workspace MUST provide a chat composer and submit/cancel controls, use Hybrid retrieval and Standard reasoning (`none`) without visible search/filter/depth controls, and provide non-submitting example prompts. An example MAY apply its reviewed PDF source ID; manually edited questions MUST use no inherited example source filter.
- **UI-009-02**: Recent run summaries and bounded follow-up context MUST remain in browser memory only, MUST be cleared on reload or explicit conversation clear, and MUST NOT be represented as persistent or provider-managed conversation memory.
- **UI-009-03**: The user MUST be able to select only provider/model options explicitly reported available by the backend; unsupported model identifiers MUST be rejected.
- **UI-009-04**: Each OpenAI run MUST require explicit, visible user consent for external processing; consent MUST NOT be persisted as blanket authorization or granted by provider selection alone.
- **UI-009-05**: Provider selection MUST be passed to the backend as a typed per-run choice; an unavailable selection MUST fail clearly with no implicit fallback.
- **UI-009-06**: Answer views MUST separate status, answer, claim-linked citations, calculations, uncertainty/conflicts, limitations, provider/model, and trace ID.
- **UI-009-07**: Evidence details MUST show source metadata, page/section or structured row identity, exact bounded evidence, provenance, and copy-citation action.
- **UI-009-08**: Tool activity MUST show tool name, state, and safe result summary, excluding hidden reasoning, credentials, and raw sensitive payloads.
- **UI-009-09**: The Evaluations view MUST display read-only, versioned summaries of existing evaluation runs, including status, case count, split/category coverage, available aggregate metrics, and limitations.
- **UI-009-10**: Evaluation summaries MUST distinguish unavailable or null metrics from measured zero and MUST NOT expose raw case prompts or initiate a run.
- **UI-009-11**: The Architecture view MUST explain UI/API, retrieval/index, agent runtime/state, bounded tool/MCP calls, provider gateway, evidence validation, evaluation, and logs/trace layers; distinguish request-scoped state from persistent memory.
- **UI-009-12**: The Architecture view MUST label each capability as implemented, configured, planned, or unavailable and link to relevant project documentation.
- **UI-009-13**: System Status MUST show backend, retrieval/index, MCP, and model configuration states without secrets, internal paths, or raw infrastructure details.
- **UI-009-14**: All browser communication MUST use typed backend contracts; the browser MUST NOT access model providers, MCP, local manifests/files, or vector stores directly.
- **UI-009-15**: The research view MUST submit Standard reasoning (`none`) without exposing a reasoning-effort selector; the backend MUST reject unsupported values before starting the runtime. For Responses API requests, the backend MUST scale the output-token ceiling with the requested effort to leave room for reasoning and the final structured answer, while keeping the ceiling at or below 8,000 tokens.
- **UI-009-16**: The answer workflow MUST stream typed operational progress and terminal events, and MUST support follow-up requests with at most 8 prior messages, 4,000 characters per message, and 12,000 characters total, held in browser memory only. Every OpenAI turn, including follow-ups, MUST require fresh consent. When the backend reports cross-encoder reranking, progress MUST display its model, candidate count, duration, and explicit fallback state. Progress MUST NOT expose hidden reasoning, prompts, raw tool arguments, or evidence payloads.
- **UI-009-17**: Each answer's activity trail MUST display the selected model route and reasoning effort and, when reported, provider usage counts and a Responses API SDK-generated reasoning summary. Missing usage or summaries MUST remain visibly unavailable; the UI MUST display summary text only and MUST NOT expose private reasoning content.
- **UI-009-18**: Evaluation summaries MUST expose safe AI-judge provenance, whether the judge shares the generator model ID, and attempted/scored/failed/skipped counts, label groundedness and answer relevance as AI-judged, and state that scores are not human-validated. The read-only UI MUST NOT expose raw answers, judge rationale, credentials, or configuration details beyond the model ID and rubric version.
- **UI-009-19**: Evaluation summaries MUST show each metric's scored sample count, groundedness distribution when scores exist, and condition/category breakdowns. Retrieval recall MUST be explained as a per-result average over expected evidence anchors, with passage variants for one anchor counted once; display recorded anchor hits/denominator and identify historical values whose anchor denominator is unavailable. The UI MUST distinguish pooled totals from averages and must not present unmeasured distributions as zero.
- **UI-009-20**: Every run- and condition-level evaluation metric card MUST have an accessible expandable plain-language explanation of what it measures and how its denominator is formed. Cost MUST prefer a complete provider-reported total; otherwise it MAY estimate only models with an explicit price, and MUST disclose the model, rate date, uncached-input assumption, and incomplete usage coverage. Unknown model prices MUST remain unavailable rather than borrowing another model's rate.
- **A11Y-009-01**: All core views MUST support semantic screen-reader labels/status, visible focus, keyboard navigation, contrast, reduced motion, and widths down to 320 CSS pixels.
- **SEC-009-01**: Model, source, MCP, evaluation, and error strings MUST render as untrusted text; the UI MUST NOT render arbitrary HTML or hidden chain-of-thought.
- **TEST-009-01**: Component and browser tests MUST cover prompt autofill, provider consent, answered/evidence, abstention, cancellation/error, evaluation empty/populated states, and architecture navigation.

### Key Entities

- **Research Run**: A single question, selected configured model route and advertised reasoning effort, request/trace identity, status, answer, citations, calculations, safe tool events, optional provider usage, and optional provider-generated summary text.
- **Conversation Context**: Explicit, bounded prior user/assistant messages held in browser memory and submitted with a follow-up; it is untrusted context, not evidence or persistent/provider-managed memory.
- **Model Option**: A backend-declared provider/model identity, availability, local/external classification, and consent requirement; never contains credentials.
- **Evaluation Summary**: A read-only run identity, status, time, case/split/category coverage, per-metric sample counts, anchor coverage, aggregate and condition/category metrics, groundedness distribution, safe AI-judge identity/counts, cost value/basis/pricing date/usage gaps, and limitations.
- **Architecture Layer**: A named system responsibility with data flow, trust boundary, implementation status, and documentation references.
- **Example Prompt**: A safe, non-submitting query template with an optional reviewed PDF source ID.

## Success Criteria

### Measurable Outcomes

- **SC-009-01**: Every corpus-derived factual claim displayed as an answer can be opened to at least one bounded evidence item or is clearly identified as unsupported/absent.
- **SC-009-02**: Example prompt selection fills the composer and causes zero network requests until explicit submission.
- **SC-009-03**: Every OpenAI request is preceded by a per-run consent action; all missing/unavailable-provider cases cause zero provider requests and no fallback.
- **SC-009-04**: The evaluation view shows existing summaries and reports empty/null/unavailable values without triggering any run or exposing case prompt text.
- **SC-009-05**: Architecture content accurately documents all nine major layers, including request-scoped state, and labels planned/unavailable capabilities.
- **SC-009-06**: Core chat, evidence, settings, evaluation, and architecture workflows remain usable at 320 CSS pixels and desktop using keyboard-only interaction.
- **SC-009-07**: Browser network inspection shows requests only to the configured backend origin and no provider credentials or direct data-store access.
- **SC-009-08**: Research requests use Hybrid retrieval and Standard reasoning (`none`) without visible search/filter/depth controls; unsupported values are rejected before runtime execution, and Responses requests apply the requested effort's output-token ceiling without exceeding 8,000 tokens.
- **SC-009-09**: The UI renders reviewed operational progress labels from typed stream events, including safe reranking diagnostics when present, without displaying hidden reasoning, prompts, raw tool arguments, or evidence payloads.
- **SC-009-10**: Every follow-up request stays within 8 prior messages, 4,000 characters per message, and 12,000 total characters; clearing or reloading removes prior context.
- **SC-009-11**: Each answer trail identifies its route and effort, presents only provider-reported token counts and an SDK summary when returned, explicitly labels unavailable values, and never renders private reasoning content.
- **SC-009-12**: AI-judged groundedness/relevance are visibly distinguished from deterministic metrics, identify the judge/rubric, generator-model relationship, attempted/scored/failed/skipped coverage, and disclose when scores lack human validation.
- **SC-009-13**: Evaluation readers can identify each metric's sample count, understand the anchor denominator behind retrieval recall where available, inspect score distributions and condition/category comparisons, and distinguish historical missing denominators from measured zero.
- **SC-009-14**: Every evaluation metric card can be expanded to explain its calculation; any token-based cost estimate identifies its priced model, published rate date, assumptions, and missing-usage caveat, while unsupported model prices remain unmeasured.

## Assumptions

- The application remains a local assessment product with no public authentication, multi-tenant settings, or production deployment guarantees.
- Backend model choices are limited to configured model identifiers; selecting a model cannot edit server secrets or arbitrary endpoints.
- Browser preference may remember the selected configured provider locally, but external-processing consent is per run and never stored as authorization.
- Existing evaluation run manifests remain the source for evaluation summaries; UI execution and mutation of evaluation artifacts are excluded.
- Recent run summaries and follow-up context are ephemeral in-memory browser state; page reload may clear them. Follow-up context is bounded and independently evidence-validated on every run.
- Architecture explanations may link to repository docs but must not imply unavailable components are active.

## Out of Scope

Marketing landing pages, arbitrary provider endpoints/model IDs, browser-side provider credentials, direct model/MCP/vector-store calls, raw manifest/file access from the browser, evaluation execution or editing, persistent or provider-managed conversational memory, hidden reasoning or chain-of-thought display, consequential decisions, and production authentication or multi-user settings.
