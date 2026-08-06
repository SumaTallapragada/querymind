import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional class names, resolving conflicting Tailwind utility classes correctly. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
