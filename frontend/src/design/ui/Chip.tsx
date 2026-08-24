/** A filter or a small toggleable option. Pressed state is `aria-pressed`. */
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { motion } from 'motion/react';
import { press } from '../motion';

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onAnimationStart' | 'onDragStart' | 'onDragEnd' | 'onDrag'> {
  active?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}

export function Chip({ active = false, icon, children, className = '', ...rest }: Props) {
  return (
    <motion.button
      type="button"
      className={`mk-chip ${className}`.trim()}
      aria-pressed={active}
      whileTap={press}
      {...rest}
    >
      {icon}
      {children}
    </motion.button>
  );
}
