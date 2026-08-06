import * as React from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Optional label for what part of the UI this boundary protects, shown in the fallback. */
  section?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render-time errors anywhere below it in the tree and shows a friendly fallback
 * instead of a blank page or a raw stack trace (rule 9 of the Phase 18 spec: never expose one
 * to the user). Logs the real error to the console for whoever's debugging, but the on-screen
 * message never includes it.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error("ErrorBoundary caught an error:", error, info.componentStack);
  }

  private readonly reset = (): void => this.setState({ error: null });

  override render(): React.ReactNode {
    if (this.state.error === null) return this.props.children;

    return (
      <div
        role="alert"
        className="flex flex-col items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-8 text-center"
      >
        <AlertTriangle className="h-8 w-8 text-destructive" aria-hidden="true" />
        <p className="font-medium text-foreground">
          {this.props.section ? `Something went wrong in ${this.props.section}.` : "Something went wrong."}
        </p>
        <p className="max-w-md text-sm text-muted-foreground">
          Try again, or reload the page if the problem continues.
        </p>
        <Button variant="outline" size="sm" onClick={this.reset}>
          Try again
        </Button>
      </div>
    );
  }
}
