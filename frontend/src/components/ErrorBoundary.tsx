import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Minimal error boundary (L5). Wrap anything that can throw at render/runtime —
 * notably the WebGL `<Canvas>`, which hard-fails on older GPUs or when WebGL is
 * disabled — so the panel shows an intentional fallback instead of a blank void.
 */
interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}
interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div
            role="alert"
            className="flex h-full items-center justify-center p-4 text-center text-[12px] text-muted-foreground"
          >
            Couldn't render this view.
          </div>
        )
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
