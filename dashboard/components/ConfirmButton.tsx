"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A destructive action that asks once, in place.
 *
 * Trilith's deletes are physical - there is no undo behind them - so the
 * second click has to be deliberate. It reverts on its own if the operator
 * walks away from it.
 */
export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  className = "",
  disabled = false,
  icon,
}: {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  className?: string;
  disabled?: boolean;
  icon?: React.ReactNode;
}) {
  const [armed, setArmed] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  function handleClick() {
    if (!armed) {
      setArmed(true);
      timer.current = window.setTimeout(() => setArmed(false), 4000);
      return;
    }
    window.clearTimeout(timer.current);
    setArmed(false);
    onConfirm();
  }

  return (
    <button
      type="button"
      className={`${className} ${armed ? "is-armed" : ""}`}
      onClick={handleClick}
      disabled={disabled}
    >
      {icon}
      {armed ? confirmLabel : label}
    </button>
  );
}
