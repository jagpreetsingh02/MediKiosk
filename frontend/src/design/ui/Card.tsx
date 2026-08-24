/**
 * A surface. `interactive` renders a real <button> so keyboard and screen
 * readers get a control rather than a div that happens to have onClick.
 */
import type { HTMLAttributes, ReactNode } from 'react';
import { motion } from 'motion/react';
import { liftHover, press } from '../motion';

interface Props extends Omit<HTMLAttributes<HTMLDivElement>, 'onAnimationStart' | 'onDragStart' | 'onDragEnd' | 'onDrag'> {
  raised?: boolean;
  glass?: boolean;
  /** No padding, clipped corners — for cards that contain their own header/media. */
  flush?: boolean;
  children?: ReactNode;
}

export function Card({ raised, glass, flush, className = '', children, ...rest }: Props) {
  const classes = [
    'mk-card',
    raised ? 'mk-card--raised' : '',
    glass ? 'mk-card--glass' : '',
    flush ? 'mk-card--flush' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}

interface ActionProps extends Omit<HTMLAttributes<HTMLButtonElement>, 'onAnimationStart' | 'onDragStart' | 'onDragEnd' | 'onDrag'> {
  raised?: boolean;
  flush?: boolean;
  disabled?: boolean;
  children?: ReactNode;
}

export function CardButton({ raised, flush, className = '', children, ...rest }: ActionProps) {
  const classes = [
    'mk-card',
    'mk-card--interactive',
    raised ? 'mk-card--raised' : '',
    flush ? 'mk-card--flush' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <motion.button type="button" className={classes} whileHover={liftHover} whileTap={press} {...rest}>
      {children}
    </motion.button>
  );
}
