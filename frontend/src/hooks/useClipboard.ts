import { useCallback, useRef, useState } from "react";

const RESET_DELAY_MS = 1500;

export interface UseClipboardResult {
  copied: boolean;
  copy: (text: string) => Promise<void>;
}

/** Copies text to the clipboard and reports a brief "copied" state a button can show feedback
 * with, e.g. swapping a Copy icon for a Check icon for `RESET_DELAY_MS`.
 */
export function useClipboard(): UseClipboardResult {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const copy = useCallback(async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setCopied(false), RESET_DELAY_MS);
  }, []);

  return { copied, copy };
}
