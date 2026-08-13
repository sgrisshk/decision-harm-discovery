const pipeline = ["Raw", "Normalized", "Analytical", "Finding", "Policy"];

export default function Home() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return (
    <main>
      <header className="masthead">
        <a className="brand" href="#top" aria-label="Signal Foundry home">
          <span className="brandMark">SF</span>
          Signal Foundry
        </a>
        <span className="environment"><i /> foundation / 0.1</span>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow">OUTCOME-DRIVEN POLICY DISCOVERY</div>
        <h1>Turn decision history into <em>defensible action.</em></h1>
        <p className="lede">
          A deterministic evidence pipeline for finding costly decision patterns—without confusing
          association for causation.
        </p>
        <div className="actions">
          <a className="primary" href={`${apiUrl}/docs`}>Explore API <span>↗</span></a>
          <a className="secondary" href={`${apiUrl}/health`}>System health</a>
        </div>
      </section>

      <section className="workbench" aria-label="System foundation">
        <div className="sectionLabel"><span>01</span> Evidence path</div>
        <div className="pipeline">
          {pipeline.map((step, index) => (
            <div className="stage" key={step}>
              <span className="stageNumber">0{index + 1}</span>
              <strong>{step}</strong>
              {index < pipeline.length - 1 && <span className="connector" aria-hidden="true">→</span>}
            </div>
          ))}
        </div>
      </section>

      <section className="principles">
        <article><span>IMMUTABLE</span><h2>Raw stays raw.</h2><p>Every transformation is versioned, reproducible, and traceable to source records.</p></article>
        <article><span>LEAKAGE-SAFE</span><h2>Time has a boundary.</h2><p>Decision-time signals stay separate from later events and economic outcomes.</p></article>
        <article><span>DETERMINISTIC</span><h2>Numbers come from code.</h2><p>generative models may explain evidence. They never calculate or become the source of truth.</p></article>
      </section>

      <footer><span>FastAPI · Next.js · PostgreSQL</span><span>Built for evidence, not theatre.</span></footer>
    </main>
  );
}

