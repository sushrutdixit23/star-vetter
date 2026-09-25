import Link from "next/link";

// The bordered dashboard tile every section of the site sits in.
export default function Panel({
  title,
  subtitle,
  href,
  hrefLabel = "View all",
  className = "",
  children,
}: {
  title?: string;
  subtitle?: string;
  href?: string;
  hrefLabel?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className={`rounded-xl border border-line bg-panel p-4 sm:p-5 ${className}`}
    >
      {(title || href) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && (
              <h2 className="display-caps text-sm font-semibold text-fg">
                {title}
              </h2>
            )}
            {subtitle && <p className="mt-1 text-xs text-muted">{subtitle}</p>}
          </div>
          {href && (
            <Link
              href={href}
              className="shrink-0 text-xs text-muted hover:text-accent"
            >
              {hrefLabel} &rarr;
            </Link>
          )}
        </div>
      )}
      {children}
    </section>
  );
}
