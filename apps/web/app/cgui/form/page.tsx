"use client";

import { FormEvent, useState } from "react";

type Submission = {
  callsign: string;
  crewCount: number;
  launchWindow: string;
  notes: string;
};

const INITIAL: Submission = {
  callsign: "Aurora",
  crewCount: 4,
  launchWindow: "2035-04-18T13:30",
  notes: "",
};

export default function MissionIntakeForm() {
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [formState, setFormState] = useState(INITIAL);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmission(formState);
  }

  return (
    <div style={{ marginTop: 32 }}>
      <h2>Mission Intake Form</h2>
      <form
        onSubmit={handleSubmit}
        style={{ display: "grid", gap: 12, maxWidth: 400 }}
        aria-label="Mission intake form"
      >
        <label htmlFor="callsign">Mission Callsign</label>
        <input
          id="callsign"
          name="callsign"
          value={formState.callsign}
          onChange={(event) => setFormState((prev) => ({ ...prev, callsign: event.target.value }))}
          required
        />

        <label htmlFor="crew">Crew Count</label>
        <input
          id="crew"
          name="crew"
          type="number"
          min={0}
          value={formState.crewCount}
          onChange={(event) =>
            setFormState((prev) => ({ ...prev, crewCount: Number(event.target.value) }))
          }
          required
        />

        <label htmlFor="window">Launch Window (UTC)</label>
        <input
          id="window"
          name="window"
          type="datetime-local"
          value={formState.launchWindow}
          onChange={(event) =>
            setFormState((prev) => ({ ...prev, launchWindow: event.target.value }))
          }
          required
        />

        <label htmlFor="notes">Notes</label>
        <textarea
          id="notes"
          name="notes"
          rows={3}
          value={formState.notes}
          onChange={(event) => setFormState((prev) => ({ ...prev, notes: event.target.value }))}
        />

        <button type="submit" style={{ marginTop: 8 }}>
          Submit
        </button>
      </form>

      {submission && (
        <section
          aria-live="polite"
          style={{
            marginTop: 24,
            padding: 16,
            borderRadius: 8,
            border: "1px solid #2d3440",
            background: "#161b22",
          }}
        >
          <h3 style={{ marginTop: 0 }}>Submission Receipt</h3>
          <dl style={{ display: "grid", gridTemplateColumns: "120px 1fr", rowGap: 6 }}>
            <dt>Callsign</dt>
            <dd>{submission.callsign}</dd>
            <dt>Crew</dt>
            <dd>{submission.crewCount}</dd>
            <dt>Window</dt>
            <dd>{submission.launchWindow}</dd>
            <dt>Notes</dt>
            <dd>{submission.notes || "—"}</dd>
          </dl>
        </section>
      )}
    </div>
  );
}
