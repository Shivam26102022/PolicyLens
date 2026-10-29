# Feature Specification: Session Chat and Memory

**Feature Branch**: `011-session-memory`

**Created**: 2026-10-27

**Status**: Draft

**Input**: User description: "Check why messages are not working. I want a real chatbot experience with sessions, follow-up next messages, hot memory for the last 5 message pairs, warm session memory, and long-term memory in the existing vector store."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resume and Continue a Chat Session (Priority: P1)

As a policy researcher, I can create a conversation, send successive messages, and return to the same conversation after reloading the workbench.

**Why this priority**: A reliable session and next-message flow is the basic chatbot experience and prevents context loss between turns.

**Independent Test**: Create a session, exchange multiple messages, reload the page, reopen the session, and verify its ordered messages remain available and a follow-up is sent with the correct recent context.

**Acceptance Scenarios**:

1. **Given** a session is open, **When** I submit a message, **Then** the user message and completed assistant response are saved to that session in order.
2. **Given** a session has completed messages, **When** I reload or reopen it, **Then** its transcript and latest response are restored without resubmitting a request.
3. **Given** a completed turn, **When** I send the next message, **Then** the UI identifies it as a follow-up and the request includes at most the five most recent completed user/assistant pairs from that session.
4. **Given** a session is selected, **When** I create or switch to another session, **Then** no transcript or hot context from the previous session is sent with the new session.

### User Story 2 - Recall Relevant Long-Term Context (Priority: P1)

As a researcher, I can benefit from relevant context from my earlier sessions without treating remembered conversation text as verified policy evidence.

**Why this priority**: Long-term recall makes sessions useful over time while preserving PolicyLens's evidence-first answer requirements.

**Independent Test**: Add distinct memory in one session, start another session in the same workspace, ask a semantically related follow-up, and verify only relevant, same-workspace memory is provided as untrusted context while new factual claims still require current corpus evidence.

**Acceptance Scenarios**:

1. **Given** long-term memory is enabled, **When** a turn completes, **Then** a bounded memory representation is saved for later semantic retrieval in the same local workspace.
2. **Given** related memories exist, **When** I ask a question in another session, **Then** only the five most relevant memories from my workspace may be included as clearly labeled context.
3. **Given** a retrieved memory contains a factual claim or instruction, **When** the assistant answers, **Then** the memory cannot serve as citation evidence, authorize a tool, or override application policy.
4. **Given** a different local workspace has similar memories, **When** I search or ask a question, **Then** its messages and memories are not returned.
5. **Given** a session turn would send content to an external model or embedding provider, **When** I have not approved that processing for the current turn, **Then** no session content is sent externally and the UI requests fresh consent.

### User Story 3 - Inspect and Control Stored Memory (Priority: P1)

As a researcher, I can see when memory is being used and clear a session or all long-term memory when I no longer want it retained.

**Why this priority**: Persistent conversation data needs transparent scope and dependable user control.

**Independent Test**: Inspect a session's memory state, clear one session, clear all long-term memory, and verify deleted content is absent from session lists, transcript requests, and subsequent memory retrieval.

**Acceptance Scenarios**:

1. **Given** a request is running, **When** session history or long-term memory is loaded, **Then** the UI reports safe operational stages and the number of memories considered without displaying hidden reasoning or raw stored payloads.
2. **Given** I delete a session, **When** deletion succeeds, **Then** its transcript and memories derived from it are removed and the UI confirms the deletion.
3. **Given** I clear long-term memory, **When** deletion succeeds, **Then** no memories from the workspace are used on later turns.
4. **Given** persistence or deletion fails, **When** the operation ends, **Then** the UI reports failure and does not present an unsaved or undeleted state as successful.
5. **Given** I have not acknowledged the data-use notice, **When** I try to create a persistent session or submit a session turn, **Then** the request is not persisted and the UI asks me to confirm that stored content will be public, synthetic, or appropriately anonymized.
6. **Given** a session contains multiple assistant responses, **When** I view one response's activity summary, **Then** it is open by default, I can collapse or reopen it, I see only that response's safe processing events, and the same trail remains attached after reload.

## Edge Cases

- A session has no assistant response yet because generation failed, timed out, or the browser stopped waiting.
- A session grows beyond the amount of transcript that can be displayed or supplied as hot context.
- The vector store is unavailable, returns no relevant memories, or returns malformed records.
- A memory is retrieved from a prior session that the user has since deleted.
- Two sessions receive messages at nearly the same time or the same session is submitted twice.
- The selected model is OpenAI and prior turns or retrieved memories would be sent externally.
- A local embedding route is unavailable or the configured embedding route requires external processing.
- The user's browser workspace identifier is missing, malformed, reset, or copied into another browser profile.
- Memory content contains prompt injection, HTML, secrets, or unsupported factual claims.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to create, list, open, and delete conversation sessions.
- **FR-002**: The system MUST persist completed user and assistant messages in their original order and restore them when a session is reopened.
- **FR-003**: Each answer request MUST include no more than the five most recent completed user/assistant message pairs from the selected session as hot context.
- **FR-004**: The full saved transcript MUST remain available as warm session history but MUST NOT be sent wholesale as model context.
- **FR-005**: The system MUST support long-term semantic recall across sessions only within the same local browser workspace and MUST limit each turn to at most five retrieved memories.
- **FR-006**: Retrieved long-term memories MUST be explicitly labeled as untrusted conversation context, not evidence. Corpus-derived factual claims MUST still be independently retrieved and validated for the current run.
- **FR-007**: Session and memory records MUST remain isolated by workspace, and deleting a session MUST delete its transcript and memories derived from that session.
- **FR-008**: Users MUST be able to clear all long-term memories for their workspace and disable their use in future requests.
- **FR-009**: The UI MUST display the active session, ordered transcript, next-message action, memory state, and accessible loading, error, and deletion states.
- **FR-010**: Operational progress MAY report session loading, hot-context selection, long-memory retrieval, and persistence status, but MUST NOT expose hidden reasoning, prompts, raw stored memory payloads, or secrets.
- **FR-011**: Every turn that sends a question, history, retrieved memory, or derived memory content to an external model or embedding provider MUST require explicit consent for that turn before external processing; consent MUST NOT carry over to later turns.
- **FR-012**: The system MUST use explicit application-managed session context; it MUST NOT depend on provider-managed conversation state to preserve sessions.
- **FR-013**: Browser communication MUST remain limited to typed backend contracts; the browser MUST NOT access Chroma, embedding providers, model providers, or local files directly.
- **FR-014**: Session, memory retrieval, and deletion failures MUST be explicit and MUST NOT result in success-shaped UI state.
- **FR-015**: Before any session transcript or long-term memory is persisted, the system MUST require and record the user's acknowledgement that only public, synthetic, or appropriately anonymized content will be stored; the UI MUST explain that restricted or identifiable private content must not be stored.
- **FR-016**: Each assistant response MUST have an accessible operational summary open by default with a clear collapse/reopen control, derived only from that turn's safe progress events; saved session history MUST restore the matching trail. The summary MUST NOT expose hidden reasoning, prompts, raw tool arguments, or secrets.

### Key Entities *(include if feature involves data)*

- **Workspace**: A local browser-owned memory scope with an opaque identifier used to isolate the operator's sessions and long-term memories.
- **Conversation Session**: An ordered chat with a stable identifier, title, timestamps, and a workspace owner.
- **Conversation Turn**: One user message and its resulting assistant state, including safe run identity and optional answer/evidence reference.
- **Hot Context**: The last five completed user/assistant pairs from the active session supplied to the current turn.
- **Warm Session History**: The complete persisted transcript available for display and resumption, separate from model prompt context.
- **Long-Term Memory**: A bounded, semantically retrievable representation of completed conversation content scoped to one workspace and source session.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In all session-resume tests, a saved transcript is restored in the same order after a page reload, with zero duplicate or missing completed messages.
- **SC-002**: Every model request includes at most five prior completed user/assistant pairs from the currently selected session and includes zero turns from another session.
- **SC-003**: Every long-memory retrieval returns no more than five records, all scoped to the current workspace, and no deleted memory is returned after a successful delete.
- **SC-004**: Every corpus-derived factual answer remains linked to current-run evidence; memory-only content is never accepted as citation evidence.
- **SC-005**: Users can clear a session and all workspace memory through visible controls, and the next request contains no cleared context.
- **SC-006**: All UI tests for persistence errors, vector-store unavailability, and external-consent denial show an accessible failure state without claiming the operation succeeded.
- **SC-007**: Session creation and turn persistence are rejected until the workspace has recorded the required data-use acknowledgement; long-term memory remains disabled until the user enables it.
- **SC-008**: For every persisted assistant response, its activity trail is open by default and can be collapsed/reopened, showing only that response's safe events, including after reload; adjacent responses' events are never mixed.

## Assumptions

- The application remains a local, single-operator assessment workbench; authentication and multi-user hosting are out of scope.
- An opaque workspace identifier is scoped to the browser profile. It is not a substitute for production authentication.
- Users must acknowledge that only public, synthetic, or appropriately anonymized content will be persisted; restricted or identifiable private content is not allowed.
- Session transcripts and derived memories persist until explicitly deleted by the user.
- Long-term memory is disabled for a new workspace and begins storing/retrieving only after the user explicitly enables it.
- Hot context contains five complete user/assistant pairs; incomplete or failed turns are not added as completed assistant messages.
- Warm history is persisted for session resumption and display, but only hot context and up to five long-term memories may be sent to a model.
- Long-term memories provide conversational context only. They are never represented as corpus evidence or used to validate factual claims.
- Consent for external model or embedding processing remains fresh for every turn, including any turn that includes saved history or long-term memories.

## Out of Scope

Provider-managed conversation IDs, cross-user sharing, cloud synchronization, public multi-tenant deployment, automatic personality profiling, unbounded transcript injection, memory-based factual citations, and display of hidden chain-of-thought.
