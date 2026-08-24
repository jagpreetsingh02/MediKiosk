/**
 * A segmented control with a pill that travels between options.
 *
 * The travelling pill is a `layoutId`, not a transform we compute: Motion moves
 * the same DOM node between positions, which is what makes it read as one object
 * sliding rather than two objects cross-fading.
 */
import { motion } from 'motion/react';
import { springSoft } from '../motion';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  count?: number;
}

interface Props<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (next: T) => void;
  /** Unique per instance — two controls sharing a layoutId animate into each other. */
  layoutGroup: string;
  ariaLabel: string;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  layoutGroup,
  ariaLabel,
}: Props<T>) {
  return (
    <div className="mk-segmented" role="tablist" aria-label={ariaLabel}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={selected}
            className="mk-segmented__item"
            onClick={() => onChange(option.value)}
          >
            {selected && (
              <motion.span
                layoutId={`segmented-${layoutGroup}`}
                className="mk-segmented__pill"
                transition={springSoft}
              />
            )}
            <span className="mk-segmented__text">
              {option.label}
              {option.count != null && ` (${option.count})`}
            </span>
          </button>
        );
      })}
    </div>
  );
}
