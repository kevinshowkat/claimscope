export const metadata = {
  title: "Claimscope",
  description: "Reproducing AI-lab claims with pinned, open harnesses.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{fontFamily: 'Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif', background:'#0B0F14', color:'#E6EDF3'}}>
        <div style={{maxWidth: 960, margin: '0 auto', padding: '24px'}}>
          <header style={{marginBottom: 24}}>
            <h1 style={{margin: 0}}>Claimscope — Labs Edition</h1>
            <p style={{opacity: 0.8}}>Paste a claim, run a reproduction, share a receipt.</p>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
