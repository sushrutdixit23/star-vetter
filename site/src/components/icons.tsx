// Small stroke icons, drawn inline so they follow the text colour in both
// themes and need no icon library.

type P = { className?: string };

const base = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function LogoMark({ className }: P) {
  return (
    <svg viewBox="0 0 32 32" className={className} {...base}>
      <circle cx="16" cy="16" r="13" opacity={0.5} />
      <ellipse cx="16" cy="16" rx="13" ry="5" transform="rotate(-25 16 16)" />
      <circle cx="16" cy="16" r="3.2" fill="currentColor" stroke="none" />
      <circle cx="26.5" cy="11" r="1.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconSample({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <circle cx="12" cy="12" r="7" />
      <circle cx="12" cy="12" r="2" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
    </svg>
  );
}

export function IconFetch({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M4 10h16M10 4v16" />
      <path d="M14 14l2 2 3-4" />
    </svg>
  );
}

export function IconVet({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M3 8h5l2 8 2-8h9" />
      <path d="M3 20h18" opacity={0.5} />
    </svg>
  );
}

export function IconCatalog({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M4 5.5C6 4.5 9 4.5 12 6c3-1.5 6-1.5 8-.5v13c-2-1-5-1-8 .5-3-1.5-6-1.5-8-.5z" />
      <path d="M12 6v13" />
    </svg>
  );
}

export function IconPixel({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <rect x="3" y="3" width="18" height="18" rx="1.5" />
      <path d="M9 3v18M15 3v18M3 9h18M3 15h18" opacity={0.6} />
      <rect x="9" y="9" width="6" height="6" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconDossier({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4M9 12h6M9 15h6M9 18h4" />
    </svg>
  );
}

export function IconArrow({ className }: P) {
  return (
    <svg viewBox="0 0 20 20" className={className} {...base}>
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  );
}

export function IconNeighbours({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6 7l2 2M8 7l-2 2M16 15l2 2M18 15l-2 2" />
    </svg>
  );
}

export function IconDownload({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M12 4v11M7 10l5 5 5-5M5 19h14" />
    </svg>
  );
}

export function IconQuote({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M7 7h4v4c0 3-2 5-4 6M14 7h4v4c0 3-2 5-4 6" />
    </svg>
  );
}

export function IconShare({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <circle cx="18" cy="18" r="2.5" />
      <path d="M8.2 10.8l7.6-3.6M8.2 13.2l7.6 3.6" />
    </svg>
  );
}

export function IconExternal({ className }: P) {
  return (
    <svg viewBox="0 0 24 24" className={className} {...base}>
      <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </svg>
  );
}
