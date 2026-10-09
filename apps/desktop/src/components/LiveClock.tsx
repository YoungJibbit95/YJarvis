import { useEffect, useState } from "react";

export default function LiveClock() {
  const [clockLabel, setClockLabel] = useState<string>(() => new Date().toLocaleTimeString());

  useEffect(() => {
    const interval = window.setInterval(() => {
      setClockLabel(new Date().toLocaleTimeString());
    }, 1000);
    return () => {
      window.clearInterval(interval);
    };
  }, []);

  return <strong className="text-[11px] font-mono text-white/85">{clockLabel}</strong>;
}

