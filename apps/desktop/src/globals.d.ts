declare global {
  interface Window {
    jarvisDesktop?: {
      platform: string;
      versions: {
        electron: string;
        chrome: string;
        node: string;
      };
    };
  }
}

export {};
