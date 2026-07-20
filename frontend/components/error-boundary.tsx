"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
    children?: ReactNode;
    fallback?: ReactNode;
    title?: string;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
    public state: State = {
        hasError: false,
        error: null
    };

    public static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error("Uncaught error in widget:", error, errorInfo);
    }

    public render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }
            
            return (
                <div className="w-full h-full min-h-[150px] rounded-xl border border-destructive/20 bg-destructive/5 p-4 flex flex-col items-center justify-center text-center">
                    <AlertTriangle className="w-8 h-8 text-destructive mb-2" />
                    <h3 className="font-semibold text-foreground/90 text-sm mb-1">
                        {this.props.title || "Widget Unavailable"}
                    </h3>
                    <p className="text-xs text-muted-foreground max-w-[200px] mb-4 line-clamp-2">
                        {this.state.error?.message || "An unexpected error occurred."}
                    </p>
                    <button 
                        onClick={() => this.setState({ hasError: false, error: null })}
                        className="flex items-center gap-1.5 text-xs font-medium text-destructive hover:text-destructive/80 transition-colors bg-destructive/10 px-3 py-1.5 rounded-md"
                    >
                        <RefreshCw className="w-3 h-3" />
                        Try Again
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}
