import Link from "next/link";

const scenarios = [
  { slug: "form", label: "Mission Intake Form" },
  { slug: "table", label: "Telemetry Table" },
  { slug: "files", label: "Document Download" },
  { slug: "flow", label: "Checklist Flow" },
];

export default function CGUIIndex() {
  return (
    <ul style={{ listStyle: "none", padding: 0, marginTop: 24, display: "grid", gap: 16 }}>
      {scenarios.map((scenario) => (
        <li key={scenario.slug}>
          <Link
            href={`/cgui/${scenario.slug}`}
            style={{
              display: "block",
              padding: "16px 20px",
              borderRadius: 8,
              border: "1px solid #223",
              background: "#11161C",
              color: "#e6edf3",
            }}
          >
            {scenario.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}
