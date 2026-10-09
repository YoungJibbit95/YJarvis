declare global {
  interface Window {
    jarvisDesktop?: {
      platform: string;
      microphoneStatus: () => Promise<"granted" | "denied" | "restricted" | "not-determined" | "unknown">;
      windowControls: {
        close: () => void;
        minimize: () => void;
        toggleMaximize: () => void;
      };
      versions: {
        electron: string;
        chrome: string;
        node: string;
      };
    };
  }
}

export {};
