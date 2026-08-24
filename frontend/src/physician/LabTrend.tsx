/**
 * One analyte over time: a small multiple with the reference band drawn behind it.
 *
 * WHY SMALL MULTIPLES AND NOT ONE CHART. Seven analytes in five different units cannot
 * share a y-axis, and putting two scales on one plot invents a correlation that is not in
 * the data — the single worst chart mistake there is. One panel per analyte, each with its
 * own scale, is the only honest arrangement.
 *
 * WHY THE LINE HAS NO COLOUR OF ITS OWN. Each panel holds exactly one series, so hue would
 * carry no information; the title names the analyte. Colour is spent where it means
 * something instead: a point outside the reference interval gets a status ring AND the word
 * "high" or "low", never the colour alone.
 *
 * WHY THE BAND COMES FROM THE SERVER. `referenceLow`/`referenceHigh` are the interval
 * printed on the report the physician can open. A normal range invented in the browser
 * would be a clinical claim made by a stylesheet.
 *
 * WHAT THIS IS NOT. It is not a risk score, a trajectory or a projection. There is no
 * trend line, no extrapolation beyond the last measured point, and no percentage anywhere.
 * The only derived number is a subtraction between two measurements, and it is labelled as
 * one.
 */
import { useId, useState } from 'react';
import type { LabSeries } from '../shared/api';

interface Props {
  series: LabSeries;
  /** Opens the source document the point came from. */
  onOpenSource?: (documentRef: string | null) => void;
}

const W = 236;
const H = 78;
const PAD_X = 14;
const PAD_Y = 14;

export function LabTrend({ series, onOpenSource }: Props): JSX.Element {
  const clipId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const points = series.points.filter((p) => p.value != null);
  const values = points.map((p) => p.value as number);

  // The band must be visible even when every measurement sits outside it — otherwise a
  // patient whose values never enter the normal range gets a chart with no reference at
  // all, which is precisely the patient the reference matters most for.
  const candidates = [...values, series.referenceLow, series.referenceHigh].filter(
    (v): v is number => v != null,
  );
  const rawMin = Math.min(...candidates);
  const rawMax = Math.max(...candidates);
  const pad = (rawMax - rawMin || Math.abs(rawMax) || 1) * 0.18;
  const min = rawMin - pad;
  const max = rawMax + pad;

  const x = (i: number) =>
    points.length === 1
      ? W / 2
      : PAD_X + (i / (points.length - 1)) * (W - PAD_X * 2);
  const y = (v: number) => H - PAD_Y - ((v - min) / (max - min || 1)) * (H - PAD_Y * 2);

  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.value as number)}`).join(' ');

  const bandTop = series.referenceHigh != null ? y(series.referenceHigh) : null;
  const bandBottom = series.referenceLow != null ? y(series.referenceLow) : null;

  const latest = points[points.length - 1];
  const change = series.change;
  const active = hover != null ? points[hover] : null;

  return (
    <figure className="lab">
      <figcaption className="lab__head">
        <span className="lab__name">{series.display}</span>
        <span className="lab__latest">
          <span className="lab__value">
            {formatValue(latest?.value)}
            <span className="lab__unit">{series.unit ?? ''}</span>
          </span>
          {/* Status is a word first. The ring below is the second encoding, never the only one. */}
          {latest?.rangeFlag && latest.rangeFlag !== 'in_range' && (
            <span className={`lab__flag lab__flag--${latest.rangeFlag}`}>{latest.rangeFlag}</span>
          )}
        </span>
      </figcaption>

      <svg
        className="lab__plot"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={describe(series)}
        preserveAspectRatio="none"
      >
        <clipPath id={clipId}>
          <rect x="0" y="0" width={W} height={H} />
        </clipPath>
        <g clipPath={`url(#${clipId})`}>
          {/* The reference interval, printed on the source report. Recessive on purpose:
              it is context behind the data, not a mark competing with it. */}
          {bandTop != null && bandBottom != null && (
            <rect
              className="lab__band"
              x="0"
              y={Math.min(bandTop, bandBottom)}
              width={W}
              height={Math.abs(bandBottom - bandTop)}
            />
          )}
          <path className="lab__line" d={path} />
          {points.map((p, i) => {
            const out = p.rangeFlag === 'high' || p.rangeFlag === 'low';
            return (
              <g key={p.observedOn ?? i}>
                {/* A hit target far larger than the mark, so a 4px dot is still reachable. */}
                <circle
                  className="lab__hit"
                  cx={x(i)}
                  cy={y(p.value as number)}
                  r={16}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => onOpenSource?.(p.documentRef)}
                />
                <circle
                  className={`lab__dot${out ? ' lab__dot--out' : ''}${hover === i ? ' is-hover' : ''}`}
                  cx={x(i)}
                  cy={y(p.value as number)}
                  r={hover === i ? 5 : 4}
                />
              </g>
            );
          })}
        </g>
      </svg>

      {/* Selective labelling: the endpoints and the change, never a number on every point. */}
      <div className="lab__foot">
        <span className="lab__when">{shortDate(points[0]?.observedOn)}</span>
        <span className="lab__change" title="Difference between the last two measurements">
          {change.delta === 0
            ? 'unchanged'
            : `${change.delta > 0 ? '+' : ''}${formatValue(change.delta)} ${change.direction} than ${shortDate(change.sinceOn)}`}
        </span>
        <span className="lab__when">{shortDate(latest?.observedOn)}</span>
      </div>

      {active && (
        <div className="lab__tip" role="status">
          <strong>
            {formatValue(active.value)} {series.unit}
          </strong>
          <span>{longDate(active.observedOn)}</span>
          <span className="lab__tip-flag">
            {active.rangeFlag === 'in_range'
              ? 'within the printed reference range'
              : `${active.rangeFlag} against ${series.referenceLow}–${series.referenceHigh}`}
          </span>
          {active.documentRef && <span className="lab__tip-src">click to open the report</span>}
        </div>
      )}
    </figure>
  );
}

/**
 * Clinical convention, not JavaScript's.
 *
 * `String(9.0)` is "9", which on a lab panel reads as a truncation error rather than a
 * haemoglobin. Small values carry a decimal; values of 100 and above are reported whole,
 * which is how a glucose or a cholesterol is printed on the report itself.
 */
function formatValue(value: number | null | undefined): string {
  if (value == null) return '—';
  if (Math.abs(value) >= 100) return String(Math.round(value));
  return value.toFixed(1);
}

function shortDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
}

function longDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** The chart's text alternative — the same facts, for a screen reader. */
function describe(series: LabSeries): string {
  const readings = series.points
    .map((p) => `${formatValue(p.value)} on ${longDate(p.observedOn)} (${p.rangeFlag})`)
    .join('; ');
  return (
    `${series.display}, measured ${series.points.length} times: ${readings}. ` +
    `Reference range ${series.referenceLow} to ${series.referenceHigh} ${series.unit ?? ''}.`
  );
}
