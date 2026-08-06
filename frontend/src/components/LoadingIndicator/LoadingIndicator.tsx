import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface LoadingIndicatorProps {
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE_CLASSES: Record<NonNullable<LoadingIndicatorProps["size"]>, string> = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-9 w-9",
};

/** A spinner with an accessible label -- always announced to assistive tech (rule 8). */
export function LoadingIndicator({
  label = "Loading",
  size = "md",
  className,
}: LoadingIndicatorProps) {
  return (
    <div role="status" className={cn("flex items-center gap-2 text-muted-foreground", className)}>
      <Loader2 className={cn("animate-spin", SIZE_CLASSES[size])} aria-hidden="true" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
