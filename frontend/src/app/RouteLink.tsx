import type { MouseEvent, ReactNode } from "react";
import { navigate, ROUTE_PATH, type Route } from "./useRoute";

interface Props {
  to: Route;
  className?: string;
  children: ReactNode;
  "aria-current"?: "page";
}

/** An in-app link: a real href (open in new tab works), no page reload. */
export function RouteLink({ to, className, children, ...rest }: Props) {
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    const modified =
      event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
    if (event.defaultPrevented || event.button !== 0 || modified) return;
    event.preventDefault();
    navigate(to);
  };
  return (
    <a href={ROUTE_PATH[to]} className={className} onClick={onClick} {...rest}>
      {children}
    </a>
  );
}
