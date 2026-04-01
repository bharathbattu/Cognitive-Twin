# Cognitive Twin E2E Robustness Manual Checklist

Date: 2026-04-01
Scope: Frontend UX behavior + restart/reload resilience that is not fully covered by backend automated tests.
Rule: Do not change product logic. Observe behavior only.

## Execution Log Template

Use this format for each check:

- Check: <name>
- Step: <what was done>
- Expected: <expected behavior>
- Actual: <observed behavior>
- Result: PASS | FAIL
- Notes: <optional details>

## Part 2: Frontend <-> Backend Integration Validation

1. Chat request contract
- Open the app and send one chat message.
- Verify browser network request path is /api/v1/chat.
- Verify payload has message, session_id, top_k.
- Verify response envelope fields are success, data, error.
- Verify UI renders data.reply and memory_hits.

2. Memory request contract
- Open memory panel for current session.
- Verify request path is /api/v1/memory/<session_id>.
- Verify response data has session_id, count, items.
- Verify list renders roles and timestamps.

3. Profile request contract
- Verify request path is /api/v1/twin/<session_id>/profile.
- Verify response data has twin_status, summary, latest_topics, memory_count.
- Verify status label changes from Learning... to Cognitive Twin Active when deployed.

4. Simulation request contract
- Submit a simulation scenario.
- Verify request path is /api/v1/twin/simulate.
- Verify payload has session_id, scenario, debug.
- Verify decision and reasoning sections update.

## Part 3: Session Consistency and Reload

1. Session continuity
- Send one chat, run one simulation, refresh memory and profile.
- Verify same session_id appears in simulation panel and API requests.

2. Page reload persistence
- Reload the page.
- Verify session_id remains unchanged (localStorage persistence).
- Verify memory/profile are still present for the same session.

## Part 8: UI State Validation

1. Loading states
- Trigger chat submission and simulation submission.
- Verify buttons show Thinking... or Simulating... while request is in flight.
- Verify memory/profile show loading text while fetching.

2. Disabled controls
- During chat submit, verify Send message button is disabled.
- During simulation submit, verify Run simulation button is disabled.

3. Error handling
- Stop backend temporarily and submit chat/simulation.
- Verify user-friendly error messages are shown.
- Restart backend and verify UI recovers without a hard reload.

## Part 9: Multi-user Lifecycle Flow

1. Complete first twin lifecycle
- Send >= 8 meaningful chat messages until status becomes deployed.
- Trigger lifecycle transition via normal chat-triggered transition behavior.

2. Verify reset semantics
- Verify new_session_id is received and UI switches to new session.
- Verify old session data is archived (backend archive record present).
- Verify new session starts in training with near-empty memory.

## Part 10: System Resilience Validation

1. Backend restart resilience
- Keep browser open with existing session.
- Restart backend process.
- Verify health status recovers to connected.
- Verify memory/profile/simulation calls work again without creating a new session.

2. API failure resilience
- Force temporary API outage (stop backend or block network).
- Verify UI remains usable and shows controlled errors.
- Restore API and verify normal interaction resumes.

3. Refresh and no data loss
- After successful interactions, refresh page.
- Verify no data loss for current session memory/profile.

## Completion Criteria

- All automated robustness tests in backend/tests/test_system_e2e_robustness.py pass.
- All manual checks above are marked PASS.
- Any FAIL includes reproducible steps and observed weak point details.
