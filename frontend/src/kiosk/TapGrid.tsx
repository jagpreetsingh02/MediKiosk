/**
 * The tap options. Always rendered, for every question, in every modality.
 *
 * "Speech OR touch, interchangeably, at any point" means touch is never the fallback — it is
 * always right there. A patient who finds the microphone intimidating never has to discover
 * that tapping was possible.
 */
import type { Option } from '../shared/api';
import { Icon } from '../shared/Icon';

interface Props {
  options: Option[];
  selected: string[];
  multi: boolean;
  onSelect: (values: string[]) => void;
}

export function TapGrid({ options, selected, multi, onSelect }: Props): JSX.Element {
  function choose(option: Option): void {
    if (!multi) {
      onSelect([option.value]);
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

  return (
    <div className="tap-grid" role={multi ? 'group' : 'radiogroup'}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`tap-option${option.exclusive ? ' exclusive' : ''}`}
          aria-pressed={selected.includes(option.value)}
          onClick={() => choose(option)}
        >
          {option.icon && <Icon name={option.icon} />}
          <span>{option.label}</span>
        </button>
      ))}
    </div>
  );
}
