/**
 * Click-to-source: what is behind the line the physician just clicked.
 *
 * For a spoken or tapped answer this shows the patient's exact words, the question they were
 * answering, and the ASR confidence. For a document fact it shows the OCR text and draws the
 * bounding box on a page outline, so "where on the page did this come from" is answered
 * without opening the scan.
 */
import type { Source } from '../shared/api';

interface Props {
  sources: Source[];
  lineText: string | null;
}

function tierLabel(tier: string): string {
  if (tier === 'stated') return 'stated — the patient volunteered this';
  if (tier === 'confirmed') return 'confirmed — the patient affirmed a direct question';
  return 'document — extracted from an uploaded record';
}

export function SourcePanel({ sources, lineText }: Props): JSX.Element {
  if (!lineText) {
    return (
      <div className="source-empty">
        Click any line in the summary to see the exact words it came from.
        <br />
        <br />
        Every clinical claim on this screen resolves to something the patient said or to a
        span of a document they uploaded. If a line could not be traced, the summary would
        have failed to generate rather than appearing without its source.
      </div>
    );
  }

  if (!sources.length) {
    return <div className="source-empty">This line is a heading or a count — it makes no clinical claim.</div>;
  }

  return (
    <div>
      <div className="side-head">Source</div>
      {sources.map((source) => (
        <div key={source.factId} className="source-card">
          <div className="source-verbatim" lang={source.language}>
            “{source.verbatim}”
          </div>
          <dl className="source-meta">
            <dt>tier</dt>
            <dd style={{ fontFamily: 'var(--font)' }}>{tierLabel(source.tier)}</dd>
            <dt>confidence</dt>
            <dd>{(source.confidence * 100).toFixed(0)}%</dd>
            {source.questionId && (
              <>
                <dt>question</dt>
                <dd>{source.questionId}</dd>
              </>
            )}
            {source.modality && (
              <>
                <dt>how</dt>
                <dd>{source.modality}</dd>
              </>
            )}
            {source.asrConfidence !== null && (
              <>
                <dt>speech</dt>
                <dd>{(source.asrConfidence * 100).toFixed(0)}% ASR</dd>
              </>
            )}
            {source.documentId && (
              <>
                <dt>document</dt>
                <dd>
                  {source.documentId} p{source.page}
                </dd>
              </>
            )}
            {source.handwritten && (
              <>
                <dt>note</dt>
                <dd style={{ color: 'var(--warn)', fontFamily: 'var(--font)' }}>
                  handwritten — human verified
                </dd>
              </>
            )}
            <dt>fact</dt>
            <dd>{source.factId}</dd>
          </dl>

          {source.bbox && (
            <div className="source-bbox">
              <div
                className="source-bbox-rect"
                style={{
                  left: `${source.bbox.x * 100}%`,
                  top: `${source.bbox.y * 100}%`,
                  width: `${source.bbox.width * 100}%`,
                  height: `${source.bbox.height * 100}%`,
                }}
              />
              <div className="source-bbox-caption">page {source.page}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
