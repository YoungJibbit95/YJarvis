const PATHS = {
  chat: "M4 5h16v11H9l-5 4V5Z M8 9h8 M8 12h5",
  approvals: "M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z M8 12l3 3 5-6",
  settings: "M4 7h16 M4 17h16 M8 4v6 M16 14v6",
  smarthome: "m3 11 9-8 9 8 M6 9v12h12V9 M10 21v-7h4v7"
};
export function InterfaceIcon({ name }: { name: keyof typeof PATHS }) {
  return <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[name]} /></svg>;
}
