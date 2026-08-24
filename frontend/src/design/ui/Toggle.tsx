/**
 * A switch with its label as one hit target.
 *
 * Built as `role="switch"` on a button rather than a styled checkbox: the whole
 * row including the description text has to be tappable on a kiosk, and a
 * label-wrapped input makes that awkward to do without breaking the a11y tree.
 */
import { motion } from 'motion/react';
import { press } from '../motion';

interface Props {
  checked: boolean;
  onChange: (next: boolean) => void;
  title: string;
  hint?: string;
  disabled?: boolean;
  id?: string;
}

export function Toggle({ checked, onChange, title, hint, disabled, id }: Props) {
  return (
    <motion.button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      className="mk-toggle"
      disabled={disabled}
      whileTap={disabled ? undefined : press}
      onClick={() => onChange(!checked)}
    >
      <span className="mk-toggle__track" aria-hidden="true">
        <span className="mk-toggle__thumb" />
      </span>
      <span className="mk-toggle__body">
        <span className="mk-toggle__title">{title}</span>
        {hint && <span className="mk-toggle__hint">{hint}</span>}
      </span>
    </motion.button>
  );
}
