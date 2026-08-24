/**
 * The one button.
 *
 * Variants are a *register*, not a palette: `primary` is the single forward
 * action on a screen, `secondary` is a real alternative, `quiet` is "not now",
 * `ghost` is a toolbar affordance and `danger` destroys something. If a screen
 * needs two primaries, the screen is wrong, not the button.
 *
 * `loading` keeps the label mounted and hides it, so the button never resizes
 * mid-submit — a resizing button under a finger is how double-taps happen.
 */
import { forwardRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { motion } from 'motion/react';
import { press } from '../motion';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onAnimationStart' | 'onDragStart' | 'onDragEnd' | 'onDrag'> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Stretch to the container. Used for the kiosk's stacked action areas. */
  block?: boolean;
  /** Square icon-only button. Provide `aria-label` — there is no text to read. */
  iconOnly?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  trailingIcon?: ReactNode;
  children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  {
    variant = 'primary',
    size = 'md',
    block = false,
    iconOnly = false,
    loading = false,
    icon,
    trailingIcon,
    children,
    className = '',
    disabled,
    ...rest
  },
  ref,
) {
  const classes = [
    'mk-btn',
    `mk-btn--${variant}`,
    size !== 'md' ? `mk-btn--${size}` : '',
    block ? 'mk-btn--block' : '',
    iconOnly ? 'mk-btn--icon' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <motion.button
      ref={ref}
      type="button"
      className={classes}
      data-loading={loading || undefined}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      whileTap={disabled || loading ? undefined : press}
      {...rest}
    >
      {icon && <span className="mk-btn__icon">{icon}</span>}
      {children != null && <span className="mk-btn__label">{children}</span>}
      {trailingIcon && <span className="mk-btn__icon">{trailingIcon}</span>}
      {loading && <span className="mk-btn__spinner" aria-hidden="true" />}
    </motion.button>
  );
});
