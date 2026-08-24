/**
 * The tap options. Always rendered, for every question, in every modality.
 *
 * "Speech OR touch, interchangeably, at any point" means touch is never the fallback — it is
 * always right there. A patient who finds the microphone intimidating never has to discover
 * that tapping was possible.
 *
 * ONE TAP IS THE WHOLE ANSWER on a single-choice question. There used to be a Continue button
 * after it, and it was a real usability failure rather than an extra click: the option
 * highlighted, nothing else happened, and the patient had no way to know whether the machine
 * had taken their answer or was waiting for something they had not spotted. Multi-select is
 * the one case that genuinely needs a closing action, because "I have finished choosing" is
 * information the interface cannot infer — so Done stays there and only there.
 */
import type { Option } from '../shared/api';
import { Icon } from '../shared/Icon';
import { AnimatePresence, motion } from 'motion/react';
import { press, springPop } from '../design/motion';

interface Props {
  options: Option[];
  selected: string[];
  multi: boolean;
  /** Disabled while an answer is in flight, so a double tap cannot record two facts. */
  busy?: boolean;
  /** Multi-select only: track the running selection. */
  onSelect: (values: string[]) => void;
  /** Single-choice only: this tap IS the answer. */
  onAnswer: (value: string) => void;
}

export function TapGrid({
  options,
  selected,
  multi,
  busy,
  onSelect,
  onAnswer,
}: Props): JSX.Element {
  function choose(option: Option): void {
    if (busy) return;
    if (!multi) {
      // Selected and submitted in the same gesture. The highlight still paints, because the
      // parent keeps the value until the next question arrives — a tap with no visible
      // effect feels broken even when it worked.
      onSelect([option.value]);
      onAnswer(option.value);
      return;
    }
    // An exclusive option ("None of these") clears everything else, and picking anything
    // else clears it. Both directions, or the patient ends up with a contradiction.
    if (option.exclusive) {
      onSelect(selected.includes(option.value) ? [] : [option.value]);
      return;
    }
    const withoutExclusives = selected.filter(
      (value) => !options.find((o) => o.value === value)?.exclusive,
    );
    onSelect(
      withoutExclusives.includes(option.value)
        ? withoutExclusives.filter((value) => value !== option.value)
        : [...withoutExclusives, option.value],
    );
  }

  // Short labels tile into two columns; long ones stay in a single column, because
  // a two-column grid of wrapping sentences is harder to scan than a list.
  const compact = options.every((o) => o.label.length <= 22);

  return (
    <div
      className={`kx-options${compact ? ' kx-options--pair' : ''}`}
      role={multi ? 'group' : 'radiogroup'}
    >
      {options.map((option) => {
        const chosen = selected.includes(option.value);
        return (
          <motion.button
            key={option.value}
            type="button"
            className="kx-option"
            role={multi ? undefined : 'radio'}
            aria-checked={multi ? undefined : chosen}
            aria-pressed={multi ? chosen : undefined}
            disabled={busy}
            whileTap={busy ? undefined : press}
            onClick={() => choose(option)}
          >
            {option.icon && (
              <span className="kx-option__glyph" aria-hidden="true">
                <Icon name={option.icon} />
              </span>
            )}
            <span>{option.label}</span>
            <AnimatePresence>
              {chosen && (
                <motion.span
                  className="kx-option__tick"
                  aria-hidden="true"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={springPop}
                >
                  <Icon name="check" />
                </motion.span>
              )}
            </AnimatePresence>
          </motion.button>
        );
      })}
    </div>
  );
}
