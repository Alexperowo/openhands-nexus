import { Children, isValidElement, type ElementType, type ReactNode } from "react";

/** Canvas confirmation titles are spans; use their text as the surrounding dialog's name. */
export function dialogLabel(children: ReactNode, titleType: ElementType): string | undefined {
  for (const child of Children.toArray(children)) {
    if (!isValidElement<{ title?: unknown; children?: ReactNode }>(child)) continue;
    if (child.type === titleType && typeof child.props.title === "string") return child.props.title;
    const nested = dialogLabel(child.props.children, titleType);
    if (nested) return nested;
  }
}
