/**
 * Two sources that disagree, shown side by side.
 *
 * There is no "accept this one" button here, and that is the point. The system detected the
 * conflict; resolving it is a clinical judgement, and this product does not make clinical
 * judgements. The physician reads both, asks the patient the supplied question if it helps,
 * and corrects the record through the ordinary edit path.
 */
import type { Contradiction } from '../shared/api';

interface Props {
  contradictions: Contradiction[];
  onSelectFact: (factId: string) => void;
}

export function ContradictionPanel({ contradictions, onSelectFact }: Props): JSX.Element {
  if (!contradictions.length) {
    return (
      <div className="source-empty">
        No source disagrees with another in this session.
        <br />
        <br />
        When a patient says one thing and their own paperwork says another, both are kept and
        the conflict appears here — neither is overwritten.
      </div>
    );
  }

  return (
    <div>
      <div className="side-head">
        {contradictions.length} conflict{contradictions.length === 1 ? '' : 's'} — unresolved
      </div>
      {contradictions.map(entry => (
        <div key={entry.contradictionId} className="cx-item">
          <div className="cx-label">{entry.label}</div>

          <button type="button" className="cx-side" onClick={() => onSelectFact(entry.patientSide.factId)}>
            <span className="cx-who">patient said</span>
            <span className="cx-quote">“{entry.patientSide.verbatim}”</span>
          </button>

          <div className="cx-versus">versus</div>

          <button type="button" className="cx-side" onClick={() => onSelectFact(entry.documentSide.factId)}>
            <span className="cx-who">{entry.documentSide.origin}</span>
            <span className="cx-quote">“{entry.documentSide.verbatim}”</span>
          </button>

          {entry.clarifyingQuestion && (
            <div className="cx-ask">Ask the patient: “{entry.clarifyingQuestion}”</div>
          )}
          <div className="cx-rule">{entry.ruleId}</div>
        </div>
      ))}
    </div>
  );
}
