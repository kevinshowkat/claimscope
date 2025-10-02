import Link from "next/link";

const FILES = [
  {
    name: "mission-brief.txt",
    description: "High-level summary of Aurora milestones.",
    href: "/cgui/static/mission-brief.txt",
  },
  {
    name: "ops-checklist.csv",
    description: "CSV excerpt for handover.",
    href: "/cgui/static/ops-checklist.csv",
  },
];

export default function DocumentDownload() {
  return (
    <section style={{ marginTop: 32 }}>
      <h2>Document Download</h2>
      <p>Download read-only artifacts used by the GUI harness.</p>
      <ul style={{ listStyle: "none", padding: 0, marginTop: 20, display: "grid", gap: 12 }}>
        {FILES.map((file) => (
          <li key={file.name} style={{ border: "1px solid #223", borderRadius: 8, padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
              <div>
                <strong>{file.name}</strong>
                <p style={{ margin: "4px 0 0", color: "#8b949e" }}>{file.description}</p>
              </div>
              <Link
                href={file.href}
                prefetch={false}
                style={{ background: "#238636", color: "#0d1117", padding: "8px 12px", borderRadius: 6 }}
              >
                Download
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
