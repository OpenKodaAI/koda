"use client";

import type { AnchorHTMLAttributes, ReactNode } from "react";

type ExternalLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string;
  children: ReactNode;
};

export function ExternalLink({
  href,
  children,
  rel,
  target,
  ...props
}: ExternalLinkProps) {
  return (
    <a
      href={href}
      target={target ?? "_blank"}
      rel={rel ?? "noopener noreferrer"}
      {...props}
    >
      {children}
    </a>
  );
}
