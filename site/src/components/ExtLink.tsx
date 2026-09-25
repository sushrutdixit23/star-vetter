import { createElement } from "react";

// Plain anchor for external links and file downloads (Next's Link is for
// in-site routes). Built with createElement on purpose: a literal anchor tag
// gets mangled when this code is pasted through the chat.
export default function ExtLink({
  href,
  className,
  download,
  newTab = false,
  children,
}: {
  href: string;
  className?: string;
  download?: boolean;
  newTab?: boolean;
  children: React.ReactNode;
}) {
  return createElement(
    "a",
    {
      href,
      className,
      download: download ? "" : undefined,
      target: newTab ? "_blank" : undefined,
      rel: newTab ? "noopener noreferrer" : undefined,
    },
    children
  );
}
